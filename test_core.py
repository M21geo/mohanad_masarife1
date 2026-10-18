import unittest

from app import money
from app.db import connect
from app.repo import AppError, InUse, Repo
from app.seed import ensure_defaults


def make_repo():
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


# ---------------------------------------------------------------- money

class CoreTests(unittest.TestCase):
    def test_minor_units_round_trip(self):
        assert money.to_minor(25000, "IQD") == 25000
        assert money.to_minor("12.5", "USD") == 1250
        assert money.from_minor(1250, "USD") == 12.5


    def test_conversion_both_ways(self):
        # 150,000 IQD at 1480 -> $101.35 ; $100 -> 148,000 IQD
        assert money.convert_minor(150000, "IQD", "USD", 1480) == 10135
        assert money.convert_minor(10000, "USD", "IQD", 1480) == 148000
        assert money.convert_minor(5000, "IQD", "IQD", 1480) == 5000


    def test_formatting(self):
        assert money.fmt(1250000, "IQD") == "1,250,000 د.ع"
        assert money.fmt(15000, "USD") == "$150"
        assert money.fmt(10135, "USD") == "$101.35"


    # ----------------------------------------------------------------- seed
    def test_seed_is_idempotent(self):
        repo = make_repo()
        assert ensure_defaults(repo) is False
        assert [w["name"] for w in repo.list_wallets()] == ["نقد", "دولار نقد"]
        assert repo.get_rate() == 1480
        food = repo.category_tree("expense")[0]
        assert food["name"] == "طعام" and [c["name"] for c in food["children"]][:2] == ["مطاعم", "بقالة"]


    # -------------------------------------------------------------- balances
    def test_balance_follows_transactions(self):
        repo = make_repo()
        cash = wid(repo, "نقد")
        repo.update_wallet(cash, initial=1_000_000)
        repo.add_income(cash, 500_000, cid(repo, "income", "راتب"))
        t = repo.add_expense(cash, 25_000, cid(repo, "expense", "مطاعم"), note="غداء")
        assert repo.balance(cash) == 1_475_000
        repo.delete_transaction(t)
        assert repo.balance(cash) == 1_500_000


    def test_transfer_between_currencies(self):
        repo = make_repo()
        cash, usd = wid(repo, "نقد"), wid(repo, "دولار نقد")
        repo.update_wallet(cash, initial=1_000_000)
        repo.add_transfer(cash, usd, 150_000, rate=1480)
        assert repo.balance(cash) == 850_000
        assert repo.balance(usd) == 10135  # $101.35
        tx = repo.list_transactions(kinds=["transfer"])[0]
        assert tx["to_amount"] == 10135 and tx["rate"] == 1480


    def test_transfer_with_manual_received_amount(self):
        repo = make_repo()
        cash, usd = wid(repo, "نقد"), wid(repo, "دولار نقد")
        repo.add_transfer(cash, usd, 150_000, to_amount=100)  # exchange office gave $100
        assert repo.balance(usd) == 10000


    def test_transfer_same_currency_needs_no_rate(self):
        repo = make_repo()
        cash = wid(repo, "نقد")
        bank = repo.add_wallet("بنك", "IQD")
        repo.add_transfer(cash, bank, 200_000)
        assert repo.balance(bank) == 200_000
        assert repo.list_transactions(kinds=["transfer"])[0]["rate"] is None


    def test_total_balance_in_both_currencies(self):
        repo = make_repo()
        cash, usd = wid(repo, "نقد"), wid(repo, "دولار نقد")
        repo.update_wallet(cash, initial=1_480_000)
        repo.update_wallet(usd, initial=100)
        assert repo.total_balance("IQD", rate=1480) == 1_480_000 + 148_000
        assert repo.total_balance("USD", rate=1480) == 100000 + 10000  # 1,480,000 IQD = $1,000 + $100


    def test_validation(self):
        repo = make_repo()
        cash, usd = wid(repo, "نقد"), wid(repo, "دولار نقد")
        with self.assertRaises(AppError):
            repo.add_expense(cash, 0)
        with self.assertRaises(AppError):
            repo.add_transfer(cash, cash, 10)
        with self.assertRaises(AppError):  # income category on an expense
            repo.add_expense(cash, 10, cid(repo, "income", "راتب"))


    # ------------------------------------------------------------ categories
    def test_category_management_and_order(self):
        repo = make_repo()
        top = [c["name"] for c in repo.category_tree("expense")]
        food = cid(repo, "expense", "طعام")
        repo.move_category(food, +1)
        assert [c["name"] for c in repo.category_tree("expense")][:2] == [top[1], "طعام"]

        new = repo.add_category("expense", "هدايا", icon="card_giftcard")
        sub = repo.add_category("expense", "عيد", parent_id=new)
        assert repo.get_category(sub)["kind"] == "expense"
        with self.assertRaises(AppError):  # no third level
            repo.add_category("expense", "x", parent_id=sub)

        order = [c["id"] for c in repo.category_tree("expense")]
        repo.reorder_categories(list(reversed(order)))
        assert [c["id"] for c in repo.category_tree("expense")] == list(reversed(order))

        repo.update_category(new, name="هدايا ومناسبات", color="#123456")
        assert repo.get_category(new)["name"] == "هدايا ومناسبات"


    def test_delete_category_requires_reassignment(self):
        repo = make_repo()
        cash = wid(repo, "نقد")
        food, trans = cid(repo, "expense", "طعام"), cid(repo, "expense", "مواصلات")
        t = repo.add_expense(cash, 5000, cid(repo, "expense", "بقالة"))
        with self.assertRaises(InUse):
            repo.delete_category(food)
        repo.delete_category(food, reassign_to=trans)
        assert repo.get_transaction(t)["category_id"] == trans
        with self.assertRaises(AppError):
            repo.get_category(food)  # deleted


    # ---------------------------------------------------------------- filters
    def test_filters(self):
        repo = make_repo()
        cash, usd = wid(repo, "نقد"), wid(repo, "دولار نقد")
        ahmad, sara = repo.add_person("أحمد"), repo.add_person("سارة")
        food, rest = cid(repo, "expense", "طعام"), cid(repo, "expense", "مطاعم")
        fuel = cid(repo, "expense", "وقود")
        repo.add_expense(cash, 25_000, rest, ahmad, "غداء مع أحمد", "2026-10-15")
        repo.add_expense(cash, 30_000, fuel, None, "", "2026-10-14")
        repo.add_expense(usd, 20, food, sara, "", "2026-09-30")
        repo.add_income(cash, 1_800_000, cid(repo, "income", "راتب"), None, "", "2026-10-01")

        assert len(repo.list_transactions()) == 4
        assert [t["note"] for t in repo.list_transactions(limit=1)] == ["غداء مع أحمد"]
        assert len(repo.list_transactions(kinds=["expense"])) == 3
        assert len(repo.list_transactions(wallet_ids=[usd])) == 1
        # parent category matches its sub-categories (مطاعم + the $20 on طعام itself)
        assert len(repo.list_transactions(category_ids=[food])) == 2
        # exclude mode: everything except food
        assert {t["note"] for t in repo.list_transactions(category_ids=[food], exclude_categories=True)} == {"", ""}
        assert len(repo.list_transactions(category_ids=[food], exclude_categories=True)) == 2
        assert len(repo.list_transactions(person_ids=[ahmad, sara])) == 2
        assert len(repo.list_transactions(date_from="2026-10-01", date_to="2026-10-14")) == 2
        assert len(repo.list_transactions(text="أحمد")) == 1          # note / person
        assert len(repo.list_transactions(text="طعام")) == 2          # category name (+child via parent)
        assert [t["amount"] for t in repo.list_transactions(wallet_ids=[cash], min_amount=26_000, max_amount=100_000)] == [30_000]
        assert repo.list_transactions(order="largest")[0]["amount"] == 1_800_000
        assert repo.list_transactions(order="oldest")[0]["date"] == "2026-09-30"


    def test_update_transaction(self):
        repo = make_repo()
        cash = wid(repo, "نقد")
        t = repo.add_expense(cash, 10_000, cid(repo, "expense", "قهوة"))
        repo.update_transaction(t, amount=12_500, note="  كابتشينو ", category_id=None)
        row = repo.get_transaction(t)
        assert row["amount"] == 12_500 and row["note"] == "كابتشينو" and row["category_id"] is None
        tr = repo.add_transfer(cash, wid(repo, "دولار نقد"), 148_000)
        with self.assertRaises(AppError):
            repo.update_transaction(tr, amount=5)


    def test_delete_rules(self):
        repo = make_repo()
        cash = wid(repo, "نقد")
        repo.add_expense(cash, 1000)
        with self.assertRaises(InUse):
            repo.delete_wallet(cash)
        repo.archive_wallet(cash)
        assert cash not in [w["id"] for w in repo.list_wallets()]


    def test_people_and_notes(self):
        repo = make_repo()
        p = repo.add_person("أحمد")
        with self.assertRaises(AppError):
            repo.add_person("أحمد")
        cash = wid(repo, "نقد")
        t = repo.add_expense(cash, 1000, person_id=p)
        repo.delete_person(p)
        assert repo.get_transaction(t)["person_id"] is None

        a, b = repo.add_note("ادفع القسط"), repo.add_note("ميزانية الأكل")
        repo.toggle_note_pin(a)
        assert [n["text"] for n in repo.list_notes()] == ["ادفع القسط", "ميزانية الأكل"]


if __name__ == '__main__':
    unittest.main()
