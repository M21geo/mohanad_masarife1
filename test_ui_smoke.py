"""Runs every screen builder against a MagicMock 'flet'. Catches Python errors (typos, bad keys,
wrong vm fields) but NOT Flet API mistakes - those need the real library."""
import sys
import unittest
from unittest.mock import MagicMock

sys.modules["flet"] = MagicMock()

from app.db import connect  # noqa: E402
from app.repo import Repo  # noqa: E402
from app.seed import ensure_defaults  # noqa: E402
from app.ui import app as appmod  # noqa: E402
from app.ui.screens_txs import open_filter_sheet  # noqa: E402


class FakePage:
    width, height = 390, 800

    def __getattr__(self, n):
        return MagicMock()


class Smoke(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(connect(":memory:"))
        ensure_defaults(self.repo)
        w = self.repo.list_wallets()
        cat = self.repo.category_tree("expense")[0]
        p = self.repo.add_person("أحمد")
        self.repo.add_income(w[0]["id"], 1000000, date="2026-10-01")
        self.repo.add_expense(w[0]["id"], 25000, category_id=cat["id"], person_id=p, note="غدا", date="2026-10-15")
        self.repo.add_transfer(w[0]["id"], w[1]["id"], 148000, date="2026-10-16")
        self.ui = appmod.AppUI(FakePage(), self.repo, "2026-10-17")

    def test_all_tabs_and_stats_tabs(self):
        for tab in range(3):
            self.ui.tab = tab
            for st in (["list", "summary", "cats", "analysis"] if tab == 1 else [None]):
                if st:
                    self.ui.tx_view = st
                self.ui.refresh()
                self.assertIsNone(self.ui.last_error, self.ui.last_error)

    def test_filtered_views(self):
        self.ui.tab = 1
        self.ui.filters["kinds"] = {"expense"}
        self.ui.filters["period"] = "year"
        self.ui.search = "غدا"
        for v in ("list", "summary", "cats", "analysis"):
            self.ui.tx_view = v
            self.ui.refresh()
            self.assertIsNone(self.ui.last_error, self.ui.last_error)

    def test_more_pages_and_forms(self):
        from app.debts import Debts
        from app.ui import pages_cats, pages_debts, pages_wallets
        pid = self.repo.list_people()[0]["id"]
        did = Debts(self.repo).add_debt("on", pid, 50000, "IQD", "2026-10-01", "x")
        Debts(self.repo).pay(did, 10000, self.repo.list_wallets()[0]["id"], "2026-10-05")
        self.ui.tab = 2
        for key in ("wallets", "debts", "notes", "cats", "people", "import", "backup", "settings", "budgets", "recurring", "history"):
            self.ui.more_page = key
            if key == "debts":
                for d in ("on", "for"):
                    self.ui.debt_dir = d
                    self.ui.refresh()
                    self.assertIsNone(self.ui.last_error, self.ui.last_error)
            if key == "cats":
                for k in ("expense", "income"):
                    self.ui.cat_kind = k
                    self.ui.refresh()
                    self.assertIsNone(self.ui.last_error, self.ui.last_error)
            self.repo.add_note("ملاحظة")
            self.ui.refresh()
            self.assertIsNone(self.ui.last_error, f"{key}: {self.ui.last_error}")
        w = self.repo.list_wallets()[0]
        pages_wallets.wallet_form(self.ui, None)
        pages_wallets.wallet_form(self.ui, w)
        cat = self.repo.category_tree("expense")[0]
        pages_cats.cat_form(self.ui, None, "expense", None)
        pages_cats.cat_form(self.ui, cat, "expense", None)
        pages_cats.reassign_form(self.ui, cat, 3)
        pages_debts.debt_form(self.ui, None)
        pages_debts.debt_form(self.ui, Debts(self.repo).get_debt(did))
        pages_debts.debt_sheet(self.ui, did)
        pages_debts.pay_form(self.ui, Debts(self.repo).get_debt(did))
        pages_debts.more_form(self.ui, Debts(self.repo).get_debt(did))
        inst = Debts(self.repo).add_debt("for", pid, 90000, "IQD", wallet_id=self.repo.list_wallets()[0]["id"], installments=3)
        pages_debts.debt_sheet(self.ui, inst)
        pages_debts.pay_form(self.ui, Debts(self.repo).get_debt(inst))
        from app.budgets import Budgets
        from app.recurring import Recurring
        from app.ui import pages_budgets, pages_recurring
        b = Budgets(self.repo)
        b.set(None, 500000, "IQD")
        b.set(cat["id"], 100000, "IQD")
        pages_budgets.budget_form(self.ui, None)
        pages_budgets.budget_form(self.ui, b.status("2026-10", "2026-10-17")["overall"])
        rid = Recurring(self.repo).add("expense", self.repo.list_wallets()[0]["id"], 5000, "weekly", "2026-10-01", note="x")
        pages_recurring.add_form(self.ui)
        pages_recurring.edit_form(self.ui, Recurring(self.repo).get(rid))
        self.ui.more_page = "budgets"
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)
        self.ui.more_page = "recurring"
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)
        self.ui.tab = 0
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)
        self.repo.set_setting("hide_balances", "1")
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)

    def test_history_view_and_import_dest(self):
        import os
        import tempfile
        from app import importer, paths
        from app.history import Histories
        from app.ui import pages_history, pages_import
        d = tempfile.mkdtemp()
        os.environ["FLET_APP_STORAGE_DATA"] = d
        hs = Histories(paths.history_dir())
        meta = hs.create(rate=1480)
        arch = hs.open(meta["id"])
        w = arch.add_wallet("قديم", "IQD")
        arch.add_expense(w, 2500, date="2019-05-05", note="قديم")
        arch.conn.close()
        self.ui.tab, self.ui.more_page = 2, "history"
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)
        pages_history.open_archive(self.ui, meta["id"])
        for v in ("list", "summary", "cats", "analysis"):
            self.ui.hist.tx_view = v
            self.ui.refresh()
            self.assertIsNone(self.ui.last_error, self.ui.last_error)
        self.ui.hist.all_time = False
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)
        self.ui.hist.show_tx(1)
        pages_history.close_archive(self.ui)
        self.assertEqual(len(self.repo.list_transactions()), 3)   # main untouched
        st = pages_import._state(self.ui)
        st["dest"] = "history"
        self.ui.more_page = "import"
        path = os.path.join(d, "x.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("التاريخ,المبلغ,الفئة\n2018-01-02,-5000,طعام\n")
        h, rows = importer.read_table(path)
        st.update(path=path, headers=h, rows=rows, mapping=importer.guess_mapping(h))
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)

    def test_reminder_dialog(self):
        self.repo.set_setting("reminder_enabled", "1")
        self.repo.set_setting("reminder_time", "00:00")
        self.ui.check_reminder()

    def test_import_page_flow(self):
        import os
        import tempfile
        from app import importer
        from app.ui import pages_import
        path = os.path.join(tempfile.mkdtemp(), "x.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("التاريخ,المبلغ,الفئة\n2026-09-01,-5000,طعام\n2026-09-02,7000,راتب\n")
        self.ui.tab, self.ui.more_page = 2, "import"
        st = pages_import._state(self.ui)
        h, rows = importer.read_table(path)
        st.update(path=path, headers=h, rows=rows, mapping=importer.guess_mapping(h), wallet=self.repo.list_wallets()[0]["id"])
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)
        st["items"] = importer.preview(self.repo, rows, st["mapping"], st["wallet"])
        self.ui.refresh()
        self.assertIsNone(self.ui.last_error, self.ui.last_error)

    def test_sheets(self):
        self.ui.add_transaction()
        self.ui.add_transaction(self.repo.get_transaction(1))
        self.ui.add_transaction(self.repo.get_transaction(3))
        self.ui.show_tx(2)
        open_filter_sheet(self.ui)


if __name__ == "__main__":
    unittest.main()
