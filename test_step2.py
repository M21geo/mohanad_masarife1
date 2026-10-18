import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta

from app import backup, importer, money
from app.db import connect
from app.debts import Debts
from app.repo import AppError, Repo
from app.seed import ensure_defaults
from app.stats import Stats, shift_month


def make():
    r = Repo(connect(":memory:"))
    ensure_defaults(r)
    return r


def wid(repo, name):
    return next(w["id"] for w in repo.list_wallets() if w["name"] == name)


def cid(repo, kind, name):
    for top in repo.category_tree(kind):
        if top["name"] == name:
            return top["id"]
        for ch in top["children"]:
            if ch["name"] == name:
                return ch["id"]
    raise KeyError(name)


def balances(repo):
    return {w["name"]: w["balance"] for w in repo.balances(include_archived=True)}


# ------------------------------------------------------------------ debts
class DebtTests(unittest.TestCase):
    def setUp(self):
        self.repo = make()
        self.debts = Debts(self.repo)
        self.cash = wid(self.repo, "نقد")
        self.usd = wid(self.repo, "دولار نقد")
        self.ahmad = self.repo.add_person("أحمد")

    def test_partial_payments_and_status(self):
        d = self.debts.add_debt("on", self.ahmad, 750_000, "IQD", due_date="2026-11-01")
        self.debts.pay(d, 250_000, date="2026-10-01")
        self.debts.pay(d, 100_000, date="2026-10-10")
        row = self.debts.get_debt(d)
        self.assertEqual((row["paid"], row["remaining"], row["settled"]), (350_000, 400_000, False))
        self.debts.pay(d, 400_000)
        self.assertTrue(self.debts.get_debt(d)["settled"])
        with self.assertRaises(AppError):
            self.debts.pay(d, 1)  # nothing left

    def test_overpay_and_validation(self):
        d = self.debts.add_debt("on", self.ahmad, 100, "USD")
        with self.assertRaises(AppError):
            self.debts.pay(d, 100.01)
        with self.assertRaises(AppError):
            self.debts.add_debt("on", self.ahmad, 0, "IQD")
        with self.assertRaises(AppError):
            self.debts.add_debt("sideways", self.ahmad, 5, "IQD")

    def test_paying_from_wallet_posts_expense_and_income(self):
        self.repo.update_wallet(self.cash, initial=1_000_000)
        owe = self.debts.add_debt("on", self.ahmad, 300_000, "IQD")
        self.debts.pay(owe, 100_000, wallet_id=self.cash)
        self.assertEqual(self.repo.balance(self.cash), 900_000)
        tx = self.repo.list_transactions(kinds=["expense"])[0]
        self.assertEqual((tx["person_name"], tx["note"]), ("أحمد", "تسديد دين: أحمد"))

        owed = self.debts.add_debt("for", self.ahmad, 50, "USD")
        self.debts.pay(owed, 20, wallet_id=self.usd)
        self.assertEqual(self.repo.balance(self.usd), 2000)
        with self.assertRaises(AppError):  # IQD wallet for a USD debt
            self.debts.pay(owed, 5, wallet_id=self.cash)

    def test_deleting_payment_reverts_wallet(self):
        d = self.debts.add_debt("on", self.ahmad, 300_000, "IQD")
        p = self.debts.pay(d, 100_000, wallet_id=self.cash)
        self.debts.delete_payment(p)
        self.assertEqual(self.repo.balance(self.cash), 0)
        self.assertEqual(self.debts.get_debt(d)["paid"], 0)

    def test_delete_debt_removes_everything(self):
        d = self.debts.add_debt("on", self.ahmad, 300_000, "IQD")
        self.debts.pay(d, 100_000, wallet_id=self.cash)
        self.debts.delete_debt(d)
        self.assertEqual(self.repo.list_transactions(), [])
        self.assertEqual(self.debts.list_debts(), [])

    def test_overdue_ordering_and_summary(self):
        a = self.debts.add_debt("on", self.ahmad, 100_000, "IQD", due_date="2026-10-01")
        b = self.debts.add_debt("on", self.ahmad, 200, "USD", due_date="2026-12-01")
        c = self.debts.add_debt("on", self.ahmad, 50_000, "IQD")
        paid = self.debts.add_debt("on", self.ahmad, 10_000, "IQD")
        self.debts.pay(paid, 10_000)
        self.debts.add_debt("for", self.ahmad, 999, "USD")
        rows = self.debts.list_debts("on", today="2026-10-15")
        self.assertEqual([r["id"] for r in rows], [a, b, c, paid])  # open by due date, no-date, settled last
        self.assertTrue(rows[0]["overdue"] and not rows[1]["overdue"])
        s = self.debts.summary("on")
        self.assertEqual((s["IQD"], s["USD"], s["open"]), (150_000, 20_000, 3))


# ------------------------------------------------------------------ stats
class StatsTests(unittest.TestCase):
    def setUp(self):
        r = self.repo = make()
        cash, usd = wid(r, "نقد"), wid(r, "دولار نقد")
        ahmad = r.add_person("أحمد")
        food, rest, groc = cid(r, "expense", "طعام"), cid(r, "expense", "مطاعم"), cid(r, "expense", "بقالة")
        fuel = cid(r, "expense", "وقود")
        # September (previous month)
        r.add_income(cash, 1_000_000, cid(r, "income", "راتب"), date="2026-09-01")
        r.add_expense(cash, 100_000, groc, date="2026-09-10")
        r.add_expense(cash, 50_000, fuel, date="2026-09-12")
        # October
        r.add_income(cash, 2_000_000, cid(r, "income", "راتب"), date="2026-10-01")
        r.add_expense(cash, 150_000, rest, ahmad, "غداء", "2026-10-15")
        r.add_expense(cash, 100_000, groc, None, "", "2026-10-15")
        r.add_expense(cash, 50_000, food, None, "", "2026-10-10")
        r.add_expense(usd, 100, fuel, None, "", "2026-10-12")      # $100 = 148,000 IQD
        r.add_transfer(cash, usd, 10_000, date="2026-10-14")       # must be ignored
        self.s = Stats(r, "IQD", rate=1480, today="2026-10-15")

    def test_overview_and_deltas(self):
        ov = self.s.overview("2026-10")
        self.assertEqual(ov["income"], 2_000_000)
        self.assertEqual(ov["expense"], 150_000 + 100_000 + 50_000 + 148_000)
        self.assertEqual(ov["net"], 2_000_000 - 448_000)
        self.assertEqual(ov["savings_rate"], 78)
        self.assertEqual(ov["spent_pct"], 22)
        self.assertEqual(ov["avg_daily"], round(448_000 / 15))  # running month -> 15 days
        self.assertEqual(ov["income_delta"], 100)
        self.assertEqual(ov["expense_delta"], round((448_000 - 150_000) / 150_000 * 100))
        self.assertEqual(ov["biggest"]["amount"], 150_000)
        self.assertEqual(self.s.totals("2026-09")["avg_daily"], round(150_000 / 30))  # full month

    def test_usd_display_currency(self):
        usd = Stats(self.repo, "USD", rate=1480, today="2026-10-15")
        self.assertEqual(usd.totals("2026-10")["income"], money.convert_minor(2_000_000, "IQD", "USD", 1480))
        self.assertEqual(usd.totals("2026-10")["expense"], money.convert_minor(300_000, "IQD", "USD", 1480) + 10_000)

    def test_categories_roll_up_with_children(self):
        cats = self.s.categories("2026-10")
        self.assertEqual([c["name"] for c in cats], ["طعام", "مواصلات"])
        food = cats[0]
        self.assertEqual(food["total"], 300_000)
        self.assertEqual({c["name"]: c["total"] for c in food["children"]}, {"مطاعم": 150_000, "بقالة": 100_000, "عام": 50_000})
        self.assertEqual(food["pct"] + cats[1]["pct"], 100)
        self.assertEqual(food["delta"], round((300_000 - 100_000) / 100_000 * 100))
        self.assertEqual(cats[1]["delta"], round((148_000 - 50_000) / 50_000 * 100))
        self.assertEqual(self.s.categories("2026-10", "income")[0]["name"], "راتب")

    def test_people_wallets_patterns(self):
        people = {p["name"]: p for p in self.s.by_person("2026-10")}
        self.assertEqual((people["أحمد"]["total"], people["أحمد"]["count"]), (150_000, 1))
        self.assertEqual(people["بدون شخص"]["count"], 3)
        wallets = {w["name"]: w["total"] for w in self.s.by_wallet("2026-10")}
        self.assertEqual(wallets, {"نقد": 300_000, "دولار نقد": 148_000})
        wd = self.s.weekdays("2026-10")
        thursday = datetime(2026, 10, 15).weekday()
        self.assertEqual(len(wd["days"]), 7)
        self.assertEqual(wd["days"][0]["name"], "السبت")
        self.assertEqual(wd["peak"], {3: "الخميس"}.get(thursday, wd["peak"]))
        self.assertEqual(sum(d["total"] for d in wd["days"]), 448_000)
        top = self.s.top_expenses("2026-10", 2)
        self.assertEqual([t["converted"] for t in top], [150_000, 148_000])

    def test_series_and_insights(self):
        series = self.s.series("2026-10", 3)
        self.assertEqual([x["month"] for x in series], ["2026-08", "2026-09", "2026-10"])
        self.assertEqual((series[0]["income"], series[1]["expense"]), (0, 150_000))
        text = " ".join(self.s.insights("2026-10"))
        self.assertIn("طعام", text)
        self.assertIn("أحمد", text)
        self.assertIn("ادخرت 78%", text)
        self.assertEqual(shift_month("2026-01", -1), "2025-12")
        self.assertEqual(shift_month("2026-12", 1), "2027-01")

    def test_empty_month_is_safe(self):
        self.assertEqual(self.s.categories("2020-01"), [])
        ov = self.s.overview("2020-01")
        self.assertEqual((ov["income"], ov["savings_rate"], ov["income_delta"], ov["biggest"]), (0, None, None, None))
        self.assertEqual(self.s.weekdays("2020-01")["peak"], None)


# ----------------------------------------------------------------- backup
class BackupTests(unittest.TestCase):
    def build(self):
        r = make()
        cash, usd = wid(r, "نقد"), wid(r, "دولار نقد")
        r.update_wallet(cash, initial=500_000)
        p = r.add_person("سارة")
        r.add_expense(cash, 25_000, cid(r, "expense", "مطاعم"), p, "غداء", "2026-10-15")
        r.add_income(cash, 900_000, cid(r, "income", "راتب"), date="2026-10-01")
        r.add_transfer(cash, usd, 148_000, date="2026-10-02")
        r.add_note("ادفع القسط", pinned=True)
        d = Debts(r)
        debt = d.add_debt("on", p, 300_000, "IQD", "2026-11-01")
        d.pay(debt, 100_000, wallet_id=cash, date="2026-10-05")
        return r

    def test_replace_restores_identical_state(self):
        src = self.build()
        data = json.loads(json.dumps(backup.export_data(src), ensure_ascii=False))
        dst = Repo(connect(":memory:"))
        backup.import_data(dst, data, "replace")
        self.assertEqual(balances(dst), balances(src))
        self.assertEqual(backup.export_data(dst)["tables"], data["tables"])
        # ids keep working after a replace (AUTOINCREMENT counters were reset)
        dst.add_expense(wid(dst, "نقد"), 1)

    def test_replace_wipes_existing_data(self):
        src = self.build()
        dst = make()
        dst.add_expense(wid(dst, "نقد"), 777)
        backup.import_data(dst, backup.export_data(src), "replace")
        self.assertEqual(len(dst.list_transactions()), len(src.list_transactions()))

    def test_merge_is_idempotent_and_additive(self):
        src = self.build()
        data = backup.export_data(src)
        before = balances(src)
        added = backup.import_data(src, data, "merge")  # into itself: nothing new
        self.assertEqual(sum(added.values()), 0)
        self.assertEqual(balances(src), before)

        other = make()                                  # fresh device with default wallets
        added = backup.import_data(other, data, "merge")
        self.assertEqual(added["transactions"], len(src.list_transactions()))
        self.assertEqual(added["wallets"], 0)           # matched by name+currency
        self.assertEqual(added["debts"], 1)
        self.assertEqual(len(Debts(other).list_payments(1)), 1)
        again = backup.import_data(other, data, "merge")
        self.assertEqual(sum(again.values()), 0)

    def test_bad_files_are_rejected(self):
        with self.assertRaises(AppError):
            backup.import_data(make(), {"hello": "world"})
        with self.assertRaises(AppError):
            backup.import_data(make(), {"app": "masarif", "schema": 99, "tables": {}})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            open(p, "w").write("not json")
            with self.assertRaises(AppError):
                backup.restore_file(make(), p)

    def test_rotation_and_listing(self):
        r = self.build()
        with tempfile.TemporaryDirectory() as d:
            base = datetime(2026, 10, 1, 12, 0, 0)
            paths = [backup.create_backup(r, d, keep=3, now=base + timedelta(days=i)) for i in range(5)]
            names = [b["name"] for b in backup.list_backups(d)]
            self.assertEqual(len(names), 3)
            self.assertEqual(names[0], os.path.basename(paths[-1]))  # newest first
            self.assertFalse(os.path.exists(paths[0]))
            self.assertFalse(backup.auto_backup_due(d, 1, now=datetime.now()))  # just wrote one
            self.assertTrue(backup.auto_backup_due(d, 1, now=datetime.now() + timedelta(days=2)))
            self.assertTrue(backup.auto_backup_due(os.path.join(d, "none")))
            self.assertTrue(backup.restore_file(make(), paths[-1], "replace")["transactions"] > 0)


# --------------------------------------------------------------- importer
CSV_AR = """التاريخ,المبلغ,الفئة,الفئة الفرعية,المحفظة,الشخص,الملاحظة
15/10/2026,"(25,000)",طعام,مطاعم,نقد,أحمد,غداء
14/10/2026,"(30,000)",مواصلات,وقود,نقد,,
01/10/2026,"1,800,000",راتب,,بنك الرافدين,,راتب الشهر
٠٩/١٠/٢٠٢٦,"(٥٠٠٠)",ترفيه,سينما,نقد,,
بلا تاريخ,100,طعام,,نقد,,
"""


def write(directory, name, text):
    p = os.path.join(directory, name)
    with open(p, "w", encoding="utf-8-sig") as f:
        f.write(text)
    return p


def make_xlsx(path, rows):
    strings, cells_xml = [], []
    for r, row in enumerate(rows, start=1):
        cs = []
        for c, v in enumerate(row):
            ref = "ABCDEFGH"[c] + str(r)
            if isinstance(v, (int, float)):
                cs.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                strings.append(v)
                cs.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        cells_xml.append(f'<row r="{r}">{"".join(cs)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(cells_xml)}</sheetData></worksheet>')


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.repo = make()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_parsers(self):
        self.assertEqual(importer.parse_amount("1,250,000"), 1250000)
        self.assertEqual(importer.parse_amount("(25,000)"), -25000)
        self.assertEqual(importer.parse_amount("-12.5"), -12.5)
        self.assertEqual(importer.parse_amount("1.234,56"), importer.parse_amount("1,234.56"))
        self.assertEqual(importer.parse_amount("٥٠٠٠"), 5000)
        self.assertEqual(importer.parse_amount("$100"), 100)
        self.assertEqual(importer.parse_date("15/10/2026"), "2026-10-15")
        self.assertEqual(importer.parse_date("10/15/2026", day_first=False), "2026-10-15")
        self.assertEqual(importer.parse_date("2026-10-15 13:45:00"), "2026-10-15")
        self.assertEqual(importer.parse_date("٠٩/١٠/٢٠٢٦"), "2026-10-09")
        self.assertEqual(importer.parse_date("46310"), "2026-10-15")  # Excel serial
        for bad in ("", "tomorrow"):
            with self.assertRaises(ValueError):
                importer.parse_date(bad)
        self.assertEqual(importer.parse_kind("مصروف"), "expense")
        self.assertEqual(importer.parse_kind("Income"), "income")
        self.assertIsNone(importer.parse_kind("???"))

    def test_csv_end_to_end(self):
        path = write(self.tmp.name, "old.csv", CSV_AR)
        headers, rows = importer.read_table(path)
        mapping = importer.guess_mapping(headers)
        self.assertEqual(mapping, {"date": "التاريخ", "amount": "المبلغ", "category": "الفئة",
                                   "subcategory": "الفئة الفرعية", "wallet": "المحفظة",
                                   "person": "الشخص", "note": "الملاحظة"})
        items = importer.preview(self.repo, rows, mapping)
        s = importer.summarize(items)
        self.assertEqual((s["total"], s["errors"], s["to_add"]), (5, 1, 4))
        self.assertEqual(items[4]["error"], "تاريخ غير مفهوم")
        self.assertEqual([i["kind"] for i in items[:4]], ["expense", "expense", "income", "expense"])
        self.assertEqual(s["new_wallets"], 1)       # بنك الرافدين
        self.assertEqual(s["new_categories"], 1)    # ترفيه › سينما
        self.assertEqual(s["new_people"], 1)

    def test_sign_and_default_wallet(self):
        path = write(self.tmp.name, "b.csv", "Date,Amount,Note\n2026-10-01,-4000,coffee\n2026-10-02,9000,gift\n")
        headers, rows = importer.read_table(path)
        cash = wid(self.repo, "نقد")
        items = importer.preview(self.repo, rows, importer.guess_mapping(headers), default_wallet_id=cash)
        self.assertEqual([(i["kind"], int(i["amount"])) for i in items], [("expense", 4000), ("income", 9000)])
        none = importer.preview(self.repo, rows, importer.guess_mapping(headers))  # no default wallet: uses a wallet of the currency
        self.assertTrue(all(not i["error"] and i["wallet_id"] == cash for i in none))
        with self.assertRaises(AppError):
            importer.preview(self.repo, rows, {"date": "Date"})

    def test_commit_creates_missing_and_is_idempotent(self):
        path = write(self.tmp.name, "old.csv", CSV_AR)
        headers, rows = importer.read_table(path)
        mapping = importer.guess_mapping(headers)
        backups = os.path.join(self.tmp.name, "bk")
        items = importer.preview(self.repo, rows, mapping)
        res = importer.commit(self.repo, items, backup_dir=backups)
        self.assertEqual(res["added"], 4)
        self.assertEqual(len(os.listdir(backups)), 1)                       # safety backup
        wallets = {w["name"]: w for w in self.repo.list_wallets()}
        self.assertEqual(wallets["بنك الرافدين"]["currency"], "IQD")
        self.assertEqual(self.repo.balance(wallets["نقد"]["id"]), -25_000 - 30_000 - 5_000)
        cinema = next(c for t in self.repo.category_tree("expense") for c in t["children"] if c["name"] == "سينما")
        self.assertEqual(self.repo.get_category(cinema["parent_id"])["name"], "ترفيه")
        tx = self.repo.list_transactions(text="غداء")[0]
        self.assertEqual((tx["person_name"], tx["category_name"], tx["parent_category_name"]), ("أحمد", "مطاعم", "طعام"))
        # re-import the same file: everything is a duplicate now
        items2 = importer.preview(self.repo, rows, mapping)
        self.assertEqual(importer.summarize(items2)["to_add"], 0)
        self.assertEqual(importer.commit(self.repo, items2)["added"], 0)

    def test_identical_rows_in_one_file_are_kept(self):
        path = write(self.tmp.name, "c.csv", "Date,Amount,Note,Wallet\n2026-10-01,-3000,coffee,نقد\n2026-10-01,-3000,coffee,نقد\n")
        headers, rows = importer.read_table(path)
        m = importer.guess_mapping(headers)
        items = importer.preview(self.repo, rows, m)
        self.assertEqual(importer.summarize(items)["to_add"], 2)
        importer.commit(self.repo, items)
        self.assertEqual(importer.summarize(importer.preview(self.repo, rows, m))["to_add"], 0)

    def test_xlsx_and_json(self):
        x = os.path.join(self.tmp.name, "a.xlsx")
        make_xlsx(x, [["Date", "Amount", "Category", "Wallet"], [46310, 15000, "طعام", "نقد"], ["2026-10-02", -2500, "طعام", "نقد"]])
        headers, rows = importer.read_table(x)
        items = importer.preview(self.repo, rows, importer.guess_mapping(headers))
        self.assertEqual([(i["date"], i["kind"], int(i["amount"])) for i in items],
                         [("2026-10-15", "income", 15000), ("2026-10-02", "expense", 2500)])
        j = os.path.join(self.tmp.name, "a.json")
        json.dump({"transactions": [{"date": "2026-10-03", "amount": "-100", "wallet": "نقد"}]}, open(j, "w"))
        headers, rows = importer.read_table(j)
        self.assertEqual(importer.preview(self.repo, rows, importer.guess_mapping(headers))[0]["kind"], "expense")

    def test_windows_arabic_encoding(self):
        p = os.path.join(self.tmp.name, "w.csv")
        with open(p, "wb") as f:
            f.write("Date,Amount,Note,Wallet\n2026-10-01,5000,قهوة,نقد\n".encode("cp1256"))
        headers, rows = importer.read_table(p)
        self.assertEqual(rows[0]["Note"], "قهوة")

    def test_failed_commit_rolls_back(self):
        path = write(self.tmp.name, "old.csv", CSV_AR)
        headers, rows = importer.read_table(path)
        items = importer.preview(self.repo, rows, importer.guess_mapping(headers))
        items[2]["currency"] = "EUR"  # sabotage the 3rd importable row
        before = (len(self.repo.list_transactions()), [w["name"] for w in self.repo.list_wallets()])
        with self.assertRaises(Exception):
            importer.commit(self.repo, items)
        after = (len(self.repo.list_transactions()), [w["name"] for w in self.repo.list_wallets()])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
