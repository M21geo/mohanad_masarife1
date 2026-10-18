import unittest

from app import money
from app.analysis import Analysis
from app.db import connect
from app.repo import Repo
from app.seed import ensure_defaults
from app.ui import vm


def make():
    r = Repo(connect(":memory:"))
    ensure_defaults(r)
    return r


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.r = make()
        self.w = self.r.list_wallets()[0]["id"]
        c = self.r.category_tree("expense")[0]["id"]
        self.r.add_income(self.w, 1000000, date="2026-10-01")
        for d, a in (("2026-10-02", 5000), ("2026-10-03", 20000), ("2026-10-10", 120000), ("2026-09-20", 7000)):
            self.r.add_expense(self.w, a, category_id=c, date=d)

    def test_month_scope_and_totals(self):
        sc = vm.scope_rows(self.r, vm_filters(), "", "2026-10-15", "2026-10")
        self.assertFalse(sc["filtered"])
        an, prev = vm.analysis_for(self.r, sc, "IQD")
        t = an.totals()
        self.assertEqual((t["income"], t["expense"], t["expense_count"]), (1000000, 145000, 3))
        self.assertEqual(t["median_tx"], 20000)
        self.assertEqual(prev.totals()["expense"], 7000)
        self.assertEqual(an.days, 15)  # 1..15 Oct

    def test_filter_scope_all_time(self):
        f = vm_filters()
        f["kinds"] = {"expense"}
        sc = vm.scope_rows(self.r, f, "", "2026-10-15", "2026-10")
        self.assertTrue(sc["filtered"])
        an, prev = vm.analysis_for(self.r, sc, "IQD")
        self.assertIsNone(prev)
        self.assertEqual(an.totals()["expense"], 152000)

    def test_histogram_and_timeline(self):
        self.r.add_expense(self.w, 3000, date="2026-08-05")
        an = Analysis(self.r.list_transactions(), "IQD", 1480)
        h = an.histogram()
        self.assertEqual(sum(b["count"] for b in h), 5)
        self.assertEqual(h[0]["lo"], 0)
        tl = an.timeline()
        self.assertEqual(tl["mode"], "month")
        self.assertEqual([p["key"] for p in tl["points"]], ["2026-08", "2026-09", "2026-10"])

    def test_number_input(self):
        self.assertEqual(money.format_input("10000000"), "10,000,000")
        self.assertEqual(money.parse_input("١٠,٠٠٠"), 10000.0)


def vm_filters():
    from app.ui.app import AppUI
    return AppUI.default_filters()


if __name__ == "__main__":
    unittest.main()
