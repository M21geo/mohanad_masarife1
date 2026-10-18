import os
import tempfile
import unittest
from datetime import datetime

from app import backup, reminder, reset
from app.db import connect
from app.debts import Debts
from app.history import Histories
from app.repo import Repo
from app.seed import ensure_defaults


def make():
    r = Repo(connect(":memory:"))
    ensure_defaults(r)
    return r


class HistoryTests(unittest.TestCase):
    def test_archives_are_isolated_and_numbered(self):
        h = Histories(tempfile.mkdtemp())
        a, b = h.create(rate=1500), h.create()
        self.assertEqual((a["name"], b["name"]), ("هستوري 1", "هستوري 2"))
        ra = h.open(a["id"])
        self.assertEqual(ra.get_rate(), 1500)
        w = ra.add_wallet("قديم", "IQD")
        ra.add_expense(w, 1000, date="2020-01-05")
        main = make()
        self.assertEqual(main.list_transactions(), [])
        info = h.list()[0]
        self.assertEqual((info["tx_count"], info["date_from"]), (1, "2020-01-05"))
        h.rename(a["id"], "مصاريف 2020")
        h.delete(b["id"])
        self.assertEqual([i["name"] for i in h.list()], ["مصاريف 2020"])
        self.assertEqual(h.create()["name"], "هستوري 3")  # numbers are never reused

    def test_restore_backup_as_history_leaves_main_untouched(self):
        src = make()
        w = src.list_wallets()[0]["id"]
        src.add_expense(w, 5000, date="2019-03-01")
        p = src.add_person("قديم")
        data = backup.export_data(src)
        main = make()
        main.add_person("جديد")
        before = backup.export_data(main)["tables"]
        h = Histories(tempfile.mkdtemp())
        item = h.create()
        arch = h.open(item["id"])
        backup.import_data(arch, data, "replace")
        self.assertEqual(len(arch.list_transactions()), 1)
        self.assertEqual([x["name"] for x in arch.list_people()], ["قديم"])
        self.assertEqual(backup.export_data(main)["tables"], before)

    def test_drafts_hidden_and_purged(self):
        h = Histories(tempfile.mkdtemp())
        d = h.create(draft=True)
        self.assertEqual(h.list(), [])
        h.purge_drafts()
        self.assertEqual(h.list(include_drafts=True), [])
        d2 = h.create(draft=True)
        h.finalize(d2["id"])
        self.assertEqual(len(h.list()), 1)


class HistoryImportTests(unittest.TestCase):
    def test_file_import_into_archive_leaves_main_alone(self):
        from app import importer
        main = make()
        before = (len(main.list_wallets()), len(main.category_tree("expense")), len(main.list_people()), main.balance(main.list_wallets()[0]["id"]))
        h = Histories(tempfile.mkdtemp())
        meta = h.create(rate=1480, draft=True)
        arch = h.open(meta["id"])
        wid = arch.add_wallet("المحفظة", "IQD")
        rows = [{"d": "2018-01-02", "a": "-5000", "c": "ملابس", "p": "خالد"}, {"d": "2018-01-03", "a": "9000", "c": "راتب قديم", "p": ""}]
        items = importer.preview(arch, rows, {"date": "d", "amount": "a", "category": "c", "person": "p"}, wid, "IQD")
        self.assertEqual(importer.commit(arch, items, None)["added"], 2)
        h.finalize(meta["id"])
        self.assertEqual([c["name"] for c in arch.category_tree("expense")], ["ملابس"])
        self.assertEqual([p["name"] for p in arch.list_people()], ["خالد"])
        self.assertEqual(before, (len(main.list_wallets()), len(main.category_tree("expense")), len(main.list_people()), main.balance(main.list_wallets()[0]["id"])))
        self.assertEqual(h.list()[0]["tx_count"], 2)


class ResetTests(unittest.TestCase):
    def test_clear_transactions_keeps_structure(self):
        r = make()
        w = r.list_wallets()[0]["id"]
        r.add_expense(w, 1000)
        Debts(r).add_debt("on", r.add_person("س"), 5, "IQD")
        reset.clear_transactions(r)
        self.assertEqual((r.list_transactions(), len(r.list_wallets()), len(r.list_people())), ([], 2, 1))
        self.assertEqual(r.balance(w), 0)

    def test_factory_reset(self):
        r = make()
        r.set_rate(1600)
        r.add_expense(r.list_wallets()[0]["id"], 1000)
        r.add_note("x")
        reset.factory_reset(r)
        self.assertEqual((r.list_transactions(), r.list_notes(), r.list_people()), ([], [], []))
        self.assertEqual(len(r.list_wallets()), 2)
        self.assertTrue(r.category_tree("expense"))
        self.assertEqual(r.get_rate(), 1600)


class ReminderTests(unittest.TestCase):
    def test_due_rules(self):
        r = make()
        now = datetime(2026, 10, 18, 21, 30)
        self.assertEqual(reminder.due(r, now), [])            # disabled
        r.set_setting("reminder_enabled", "1")
        r.set_setting("reminder_time", "21:00")
        self.assertEqual(reminder.due(r, datetime(2026, 10, 18, 20, 0)), [])   # too early
        self.assertEqual(len(reminder.due(r, now)), 1)
        r.add_expense(r.list_wallets()[0]["id"], 100, date="2026-10-18")
        self.assertEqual(reminder.due(r, now), [])            # already logged today
        Debts(r).add_debt("on", r.add_person("علي"), 5000, "IQD", due_date="2026-10-19")
        self.assertEqual(len(reminder.due(r, now)), 1)
        reminder.mark_shown(r, now)
        self.assertEqual(reminder.due(r, now), [])            # only once a day


if __name__ == "__main__":
    unittest.main()
