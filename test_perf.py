"""Archive performance guards: big archives must render in batches and reuse computed statistics."""
import sys
import time
import unittest
from unittest.mock import MagicMock

sys.modules["flet"] = MagicMock()

from app.db import connect  # noqa: E402
from app.repo import Repo  # noqa: E402
from app.seed import ensure_defaults  # noqa: E402
from app.ui import app as appmod, screens_txs, vm  # noqa: E402


class FakePage:
    width, height = 390, 800

    def __getattr__(self, n):
        return MagicMock()


class Perf(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(connect(":memory:"))
        ensure_defaults(self.repo)
        w = self.repo.list_wallets()[0]["id"]
        rows = [(w, "expense", (i % 400 + 1) * 1000, f"20{18 + i % 7}-{i % 12 + 1:02d}-{i % 28 + 1:02d}") for i in range(20000)]
        with self.repo.conn:
            self.repo.conn.executemany("INSERT INTO transactions(wallet_id,kind,amount,date) VALUES(?,?,?,?)", rows)
        self.ui = appmod.AppUI(FakePage(), self.repo, "2026-10-18")
        self.ui.all_time = self.ui.allow_all_time = self.ui.cacheable = True

    def test_list_renders_only_first_batch(self):
        built = []
        orig = screens_txs.tx_tile
        screens_txs.tx_tile = lambda ui, r, *a, **k: built.append(r) or orig(ui, r, *a, **k)
        try:
            t = time.perf_counter()
            screens_txs.build_txs(self.ui)
            self.assertLess(time.perf_counter() - t, 3)
        finally:
            screens_txs.tx_tile = orig
        self.assertEqual(len(built), screens_txs.PAGE_FIRST)

    def test_scope_cached_until_inputs_change(self):
        a = vm.scope_and_analysis(self.ui)
        self.assertIs(a, vm.scope_and_analysis(self.ui))
        self.ui.currency = "USD"
        self.assertIsNot(a, vm.scope_and_analysis(self.ui))

    def test_main_ui_not_cached(self):
        self.ui.cacheable = False
        self.assertIsNot(vm.scope_and_analysis(self.ui), vm.scope_and_analysis(self.ui))


if __name__ == "__main__":
    unittest.main()


class PaymentDetails(unittest.TestCase):
    def test_payment_list_has_wallet_and_balance_after(self):
        from app.debts import Debts
        repo = Repo(connect(":memory:"))
        ensure_defaults(repo)
        w = repo.list_wallets()[0]
        pid = repo.add_person("علي")
        deb = Debts(repo)
        did = deb.add_debt("on", pid, 90000, w["currency"], "2026-10-01", "x", installments=3, first_due="2026-11-01")
        deb.pay(did, 30000, w["id"], "2026-11-01")
        deb.pay(did, 30000, None, "2026-12-01", "نقداً")
        pays = deb.list_payments(did)
        self.assertEqual([p["n"] for p in pays], [2, 1])
        self.assertEqual([p["remaining_after"] for p in pays], [30000, 60000])
        self.assertEqual(pays[1]["wallet_name"], w["name"])
        self.assertIsNone(pays[0]["wallet_name"])
