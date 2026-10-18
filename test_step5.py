import unittest

from app.dates import add_months, add_period
from app.db import connect
from app.debts import Debts
from app.repo import AppError, Repo
from app.seed import ensure_defaults


def make():
    r = Repo(connect(":memory:"))
    ensure_defaults(r)
    return r


class DebtLinkTests(unittest.TestCase):
    def setUp(self):
        self.r = make()
        self.d = Debts(self.r)
        self.w = self.r.list_wallets()[0]["id"]   # IQD
        self.p = self.r.add_person("علي")

    def test_borrow_posts_income_and_lend_posts_expense(self):
        before = self.r.balance(self.w)
        a = self.d.add_debt("on", self.p, 100000, "IQD", wallet_id=self.w, date="2026-10-01")
        self.assertEqual(self.r.balance(self.w), before + 100000)
        b = self.d.add_debt("for", self.p, 30000, "IQD", wallet_id=self.w, date="2026-10-02")
        self.assertEqual(self.r.balance(self.w), before + 70000)
        self.d.delete_debt(a)
        self.d.delete_debt(b)
        self.assertEqual(self.r.balance(self.w), before)

    def test_wrong_currency_wallet_rejected(self):
        usd = self.r.list_wallets()[1]["id"]
        with self.assertRaises(AppError):
            self.d.add_debt("on", self.p, 10, "IQD", wallet_id=usd)

    def test_installments_schedule(self):
        i = self.d.add_debt("on", self.p, 100000, "IQD", installments=3, first_due="2026-10-31", date="2026-10-01")
        x = self.d.get_debt(i)
        self.assertEqual([s["amount"] for s in x["schedule"]], [33333, 33333, 33334])
        self.assertEqual([s["due"] for s in x["schedule"]], ["2026-10-31", "2026-11-30", "2026-12-31"])
        self.assertEqual(x["due_date"], "2026-10-31")
        self.d.pay(i, 40000, date="2026-10-20")
        x = self.d.list_debts(debt_id=i, today="2026-12-05")[0]
        self.assertEqual([s["status"] for s in x["schedule"]], ["paid", "late", "due"])
        self.assertEqual(x["next_amount"], 26666)
        self.assertTrue(x["overdue"])

    def test_add_to_debt(self):
        i = self.d.add_debt("for", self.p, 50000, "IQD")
        before = self.r.balance(self.w)
        self.d.add_to_debt(i, 20000, self.w, "2026-10-03")
        self.assertEqual(self.d.get_debt(i)["total"], 70000)
        self.assertEqual(self.r.balance(self.w), before - 20000)

    def test_dates(self):
        self.assertEqual(add_months("2026-01-31", 1), "2026-02-28")
        self.assertEqual(add_period("2026-01-31", "monthly", 2), "2026-03-31")
        self.assertEqual(add_period("2024-02-29", "yearly", 1), "2025-02-28")


if __name__ == "__main__":
    unittest.main()


class BudgetRecurringBackupTests(unittest.TestCase):
    def setUp(self):
        from app.budgets import Budgets
        from app.recurring import Recurring
        self.r = make()
        self.b, self.rc = Budgets(self.r), Recurring(self.r)
        self.w = self.r.list_wallets()[0]["id"]
        self.food = self.r.category_tree("expense")[0]
        self.sub = self.food["children"][0]

    def test_budget_status_and_alerts(self):
        self.b.set(None, 1000000, "IQD")
        self.b.set(self.food["id"], 200000, "IQD")
        self.r.add_expense(self.w, 150000, category_id=self.sub["id"], date="2026-10-05")
        self.r.add_expense(self.w, 60000, category_id=self.food["id"], date="2026-10-06")
        st = self.b.status("2026-10", "2026-10-10")
        self.assertEqual(st["overall"]["spent"], 210000)
        c = st["categories"][0]
        self.assertEqual((c["spent"], c["pct"], c["state"]), (210000, 105, "over"))
        self.assertEqual(st["overall"]["projected"], 651000)
        self.assertEqual(st["overall"]["daily_left"], 790000 // 22)
        self.assertEqual(len(self.b.alerts("2026-10", "2026-10-10", self.sub["id"])), 1)
        self.b.set(self.food["id"], 300000, "IQD")
        self.assertEqual(len(self.b.list()), 2)

    def test_budget_currency_conversion(self):
        usd = self.r.list_wallets()[1]["id"]
        self.b.set(None, 100, "USD")
        self.r.add_expense(usd, 10, date="2026-10-02")
        self.r.add_expense(self.w, 148000, date="2026-10-03")  # = $100 at 1480
        self.assertEqual(self.b.status("2026-10", "2026-10-15")["overall"]["spent"], 11000)

    def test_recurring_catch_up(self):
        rid = self.rc.add("expense", self.w, 500000, "monthly", "2026-08-31", note="إيجار", category_id=self.food["id"])
        self.assertEqual(self.rc.run_due("2026-10-15"), 2)   # 31 Aug, 30 Sep
        self.assertEqual(self.rc.run_due("2026-10-15"), 0)
        self.assertEqual(self.rc.get(rid)["next_date"], "2026-10-31")
        self.assertEqual(self.rc.run_due("2026-10-31"), 1)
        txs = self.r.list_transactions(text="إيجار")
        self.assertEqual(sorted(t["date"] for t in txs), ["2026-08-31", "2026-09-30", "2026-10-31"])
        self.rc.update(rid, end_date="2026-10-31")
        self.assertTrue(self.rc.get(rid)["finished"])
        self.rc.set_active(rid, False)
        self.assertEqual(self.rc.run_due("2027-01-01"), 0)

    def test_backup_roundtrip_new_tables(self):
        from app import backup
        self.b.set(None, 1000, "IQD")
        self.rc.add("income", self.w, 1000, "weekly", "2026-10-01")
        d = Debts(self.r)
        p = self.r.add_person("س")
        d.add_debt("on", p, 5000, "IQD", wallet_id=self.w, installments=2, date="2026-10-01")
        data = backup.export_data(self.r)
        other = make()
        res = backup.import_data(other, data, "replace")
        self.assertEqual((res["budgets"], res["recurring"], res["debts"]), (1, 1, 1))
        self.assertEqual(other.balance(other.list_wallets()[0]["id"]), self.r.balance(self.w))
        merged = make()
        res = backup.import_data(merged, data, "merge")
        self.assertEqual((res["budgets"], res["recurring"], res["debts"]), (1, 1, 1))
        self.assertEqual(backup.import_data(merged, data, "merge")["budgets"], 0)


class WipeReminderTests(unittest.TestCase):
    def test_wipe_modes(self):
        import os
        import tempfile
        from app import backup
        r = make()
        w = r.list_wallets()[0]["id"]
        r.add_income(w, 5000, date="2026-10-01")
        r.add_note("n")
        p = r.add_person("ف")
        Debts(r).add_debt("on", p, 100, "IQD")
        d = tempfile.mkdtemp()
        path = backup.wipe(r, False, d)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(r.list_transactions(), [])
        self.assertEqual(Debts(r).list_debts(), [])
        self.assertEqual(len(r.list_notes()), 1)
        self.assertEqual(len(r.list_wallets()), 2)
        backup.wipe(r, True, d)
        self.assertEqual(r.list_notes(), [])
        self.assertEqual(r.list_people(), [])
        self.assertEqual([x["name"] for x in r.list_wallets()], ["نقد", "دولار نقد"])
        self.assertEqual(r.get_rate(), 1480)
        self.assertEqual(r.add_income(r.list_wallets()[0]["id"], 1), 1)  # ids restart

    def test_reminder_items(self):
        from datetime import datetime
        from app import reminders
        r = make()
        p = r.add_person("ف")
        Debts(r).add_debt("on", p, 100000, "IQD", installments=2, first_due="2026-10-10", date="2026-10-01")
        now = datetime(2026, 10, 17, 21, 30)
        self.assertEqual(reminders.items(r, now), [])            # disabled
        reminders.set_config(r, True, "21:00")
        texts = [i["text"] for i in reminders.items(r, now)]
        self.assertEqual(len(texts), 2)                           # nothing logged today + overdue installment
        self.assertTrue(any("متأخر" in t for t in texts))
        self.assertEqual(len(reminders.items(r, datetime(2026, 10, 17, 9, 0))), 1)   # before reminder time
        with self.assertRaises(AppError):
            reminders.set_config(r, time="25:99")
