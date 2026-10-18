import unittest

from app.db import connect
from app.repo import Repo
from app.seed import ensure_defaults
from app.stats import Stats
from app.ui import vm

TODAY = "2026-10-15"


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


class HelperTests(unittest.TestCase):
    def test_day_label(self):
        self.assertEqual(vm.day_label("2026-10-15", TODAY), "اليوم")
        self.assertEqual(vm.day_label("2026-10-14", TODAY), "أمس")
        self.assertEqual(vm.day_label("2026-10-13", TODAY), "قبل يومين")
        self.assertEqual(vm.day_label("2026-10-01", TODAY), "1 تشرين الأول")
        self.assertEqual(vm.day_label("2025-12-25", TODAY), "25 كانون الأول 2025")

    def test_period_range(self):
        self.assertEqual(vm.period_range("all", TODAY), (None, None))
        self.assertEqual(vm.period_range("7d", TODAY), ("2026-10-09", TODAY))
        self.assertEqual(vm.period_range("month", TODAY), ("2026-10-01", TODAY))
        self.assertEqual(vm.period_range("last_month", TODAY), ("2026-09-01", "2026-09-30"))
        self.assertEqual(vm.period_range("year", TODAY), ("2026-01-01", TODAY))
        self.assertEqual(vm.relative_date("yesterday", TODAY), "2026-10-14")

    def test_compact_and_chip(self):
        self.assertEqual(vm.compact(1_250_000, "IQD"), "1.3M")
        self.assertEqual(vm.compact(85_000, "IQD"), "85k")
        self.assertEqual(vm.compact(500, "IQD"), "500")
        self.assertEqual(vm.compact(250_000, "USD"), "2.5k")  # $2,500
        self.assertEqual(vm.delta_chip(12, False), {"text": "▲ 12%", "tone": "bad"})
        self.assertEqual(vm.delta_chip(-8, False), {"text": "▼ 8%", "tone": "good"})
        self.assertEqual(vm.delta_chip(5, True)["tone"], "good")
        self.assertEqual(vm.delta_chip(None, True)["text"], "جديد")


class RowTests(unittest.TestCase):
    def setUp(self):
        self.r = make()
        self.cash, self.usd = wid(self.r, "نقد"), wid(self.r, "دولار نقد")

    def rows(self, **kw):
        return [vm.tx_row(t, TODAY) for t in self.r.list_transactions(**kw)]

    def test_expense_income_transfer_rows(self):
        p = self.r.add_person("أحمد")
        self.r.add_expense(self.cash, 25_000, cid(self.r, "expense", "مطاعم"), p, "غداء", TODAY)
        self.r.add_income(self.usd, 120.5, cid(self.r, "income", "راتب"), date="2026-10-14")
        self.r.add_transfer(self.cash, self.usd, 148_000, date="2026-10-13")
        self.r.add_expense(self.cash, 1000, date="2026-10-12")
        exp, inc, tr, bare = self.rows()
        self.assertEqual((exp["title"], exp["subtitle"], exp["amount_text"], exp["tone"]),
                         ("طعام › مطاعم", "نقد · أحمد", "−25,000", "expense"))
        self.assertEqual(exp["note"], "غداء")
        self.assertEqual((inc["title"], inc["amount_text"], inc["tone"], inc["date_label"]),
                         ("راتب", "+$120.50", "income", "أمس"))
        self.assertEqual(tr["title"], "تحويل: نقد ← دولار نقد")
        self.assertEqual((tr["amount_text"], tr["recv_text"], tr["tone"], tr["subtitle"]), ("148,000", "$100", "neutral", "بسعر 1480"))
        self.assertEqual(bare["title"], "مصروف")  # no category

    def test_group_by_day(self):
        self.r.add_expense(self.cash, 1, date=TODAY)
        self.r.add_expense(self.cash, 2, date=TODAY)
        self.r.add_expense(self.cash, 3, date="2026-10-14")
        groups = vm.group_by_day(self.rows())
        self.assertEqual([(g["label"], len(g["rows"])) for g in groups], [("اليوم", 2), ("أمس", 1)])


class ScreenVMTests(unittest.TestCase):
    def setUp(self):
        r = self.r = make()
        cash, usd = wid(r, "نقد"), wid(r, "دولار نقد")
        r.update_wallet(cash, initial=1_000_000)
        r.update_wallet(usd, initial=100)
        a = r.add_person("أحمد")
        r.add_income(cash, 2_000_000, cid(r, "income", "راتب"), date="2026-10-01")
        r.add_expense(cash, 150_000, cid(r, "expense", "مطاعم"), a, "غداء", "2026-10-15")
        r.add_expense(cash, 50_000, cid(r, "expense", "وقود"), date="2026-10-10")
        r.add_expense(cash, 100_000, cid(r, "expense", "بقالة"), date="2026-09-10")
        r.add_income(cash, 1_000_000, cid(r, "income", "راتب"), date="2026-09-01")

    def test_home(self):
        h = vm.home(self.r, "IQD", TODAY)
        self.assertEqual(h["total_text"], "3,848,000")   # 1M + 2M + 1M - 300k + $100*1480
        self.assertEqual((h["unit"], h["income_text"], h["expense_text"]), ("د.ع", "+2,000,000", "−200,000"))
        self.assertEqual(h["equiv_text"], "يعادل $2,600 بسعر 1,480")
        self.assertEqual([w["name"] for w in h["wallets"]], ["نقد", "دولار نقد"])
        self.assertEqual(h["wallets"][1]["balance_text"], "$100")
        self.assertEqual(len(h["recent"]), 5)
        usd = vm.home(self.r, "USD", TODAY)
        self.assertEqual(usd["unit"], "$")
        self.assertTrue(usd["equiv_text"].endswith("د.ع بسعر 1,480"))

    def test_stats_overview(self):
        st = Stats(self.r, "IQD", today=TODAY)
        o = vm.stats_overview(st, "2026-10")
        labels = {k["label"]: k for k in o["kpis"]}
        self.assertEqual(labels["الدخل"]["value"], "+2,000,000")
        self.assertEqual(labels["الدخل"]["chip"], {"text": "▲ 100%", "tone": "good"})
        self.assertEqual(labels["المصروف"]["chip"], {"text": "▲ 100%", "tone": "bad"})
        self.assertEqual(labels["نسبة الادخار"]["value"], "90%")
        self.assertEqual(labels["أكبر مصروف"]["chip"]["text"], "مطاعم")
        self.assertEqual(len(o["bars"]), 6)
        self.assertTrue(o["bars"][-1]["selected"] and o["bars"][-1]["income_h"] == 1.0)
        self.assertEqual(o["spent_pct"], 10)
        self.assertFalse(o["spent_warn"])
        self.assertTrue(o["insights"])

    def test_stats_categories_people_patterns(self):
        st = Stats(self.r, "IQD", today=TODAY)
        c = vm.stats_categories(st, "2026-10", "expense")
        self.assertEqual(c["total_text"], "200,000")
        self.assertEqual([r["name"] for r in c["rows"]], ["طعام", "مواصلات"])
        self.assertEqual(c["rows"][0]["children"][0]["name"], "مطاعم")
        self.assertEqual(c["rows"][0]["chip"]["tone"], "bad")      # food spending up vs Sept
        self.assertEqual(vm.stats_categories(st, "2020-01", "expense")["empty"], True)
        p = vm.stats_people(st, "2026-10")
        self.assertEqual(p["people"][0]["name"], "أحمد")
        self.assertEqual(p["people"][0]["fraction"], 1.0)
        pat = vm.stats_patterns(st, "2026-10", TODAY)
        self.assertEqual(len(pat["days"]), 7)
        self.assertEqual(sum(d["peak"] for d in pat["days"]), 1)
        self.assertEqual(pat["top"][0]["amount_text"], "−150,000")
        self.assertEqual(pat["top"][0]["subtitle"], "اليوم · غداء")


if __name__ == "__main__":
    unittest.main()
