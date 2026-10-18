"""Data access + business rules for the expense tracker.

All public methods take/return *user-facing* amounts (Decimal-compatible) where a
wallet/currency is known, and store *minor units* in the database (see money.py).
Rows come back as plain dicts whose money fields are minor units, suffixed
with the currency that applies (`currency`, `to_currency`) so the UI can format
them with money.fmt().
"""
import sqlite3
from datetime import date as _date
from typing import Iterable, Optional

from . import money


class AppError(Exception):
    """A rule of the app was broken (shown to the user as a message)."""


class NotFound(AppError):
    pass


class InUse(AppError):
    pass


def _today() -> str:
    return _date.today().isoformat()


def _rows(cur) -> list:
    return [dict(r) for r in cur.fetchall()]


class Repo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------ settings
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    def get_rate(self) -> float:
        return float(self.get_setting("rate", "1480"))

    def set_rate(self, rate) -> None:
        if float(rate) <= 0:
            raise AppError("سعر الصرف لازم يكون أكبر من صفر")
        self.set_setting("rate", float(rate))

    # ------------------------------------------------------------- wallets
    def add_wallet(self, name: str, currency: str, initial=0) -> int:
        name = name.strip()
        if not name:
            raise AppError("اسم المحفظة مطلوب")
        order = self.conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM wallets").fetchone()[0]
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO wallets(name,currency,initial_balance,sort_order) VALUES(?,?,?,?)",
                (name, currency, money.to_minor(initial, currency), order),
            )
        return cur.lastrowid

    def get_wallet(self, wallet_id: int) -> dict:
        row = self.conn.execute("SELECT * FROM wallets WHERE id=?", (wallet_id,)).fetchone()
        if not row:
            raise NotFound("المحفظة غير موجودة")
        return dict(row)

    def list_wallets(self, include_archived: bool = False) -> list:
        sql = "SELECT * FROM wallets"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY sort_order, id"
        return _rows(self.conn.execute(sql))

    def update_wallet(self, wallet_id: int, name: Optional[str] = None, initial=None,
                      hide_balance: Optional[bool] = None) -> None:
        w = self.get_wallet(wallet_id)
        with self.conn:
            if hide_balance is not None:
                self.conn.execute("UPDATE wallets SET hide_balance=? WHERE id=?", (int(bool(hide_balance)), wallet_id))
            if name is not None:
                if not name.strip():
                    raise AppError("اسم المحفظة مطلوب")
                self.conn.execute("UPDATE wallets SET name=? WHERE id=?", (name.strip(), wallet_id))
            if initial is not None:
                self.conn.execute(
                    "UPDATE wallets SET initial_balance=? WHERE id=?",
                    (money.to_minor(initial, w["currency"]), wallet_id),
                )

    def reorder_wallets(self, ordered_ids: Iterable[int]) -> None:
        with self.conn:
            for pos, wid in enumerate(ordered_ids):
                self.conn.execute("UPDATE wallets SET sort_order=? WHERE id=?", (pos, wid))

    def archive_wallet(self, wallet_id: int, archived: bool = True) -> None:
        self.get_wallet(wallet_id)
        with self.conn:
            self.conn.execute("UPDATE wallets SET archived=? WHERE id=?", (int(archived), wallet_id))

    def delete_wallet(self, wallet_id: int) -> None:
        self.get_wallet(wallet_id)
        used = self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE wallet_id=? OR to_wallet_id=?",
            (wallet_id, wallet_id),
        ).fetchone()[0]
        if used:
            raise InUse("المحفظة فيها معاملات. أرشفها بدل الحذف")
        with self.conn:
            self.conn.execute("DELETE FROM wallets WHERE id=?", (wallet_id,))

    def balance(self, wallet_id: int) -> int:
        """Current balance in the wallet's own minor units."""
        w = self.get_wallet(wallet_id)
        row = self.conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN wallet_id=:w AND kind='income'   THEN amount END),0)
            - COALESCE(SUM(CASE WHEN wallet_id=:w AND kind='expense'  THEN amount END),0)
            - COALESCE(SUM(CASE WHEN wallet_id=:w AND kind='transfer' THEN amount END),0)
            + COALESCE(SUM(CASE WHEN to_wallet_id=:w AND kind='transfer' THEN to_amount END),0)
            FROM transactions WHERE wallet_id=:w OR to_wallet_id=:w
            """,
            {"w": wallet_id},
        ).fetchone()[0]
        return w["initial_balance"] + row

    def balances(self, include_archived: bool = False) -> list:
        out = []
        for w in self.list_wallets(include_archived):
            w["balance"] = self.balance(w["id"])
            out.append(w)
        return out

    def total_balance(self, in_currency: str, rate: Optional[float] = None) -> int:
        """Sum of all (non-archived) wallets converted to `in_currency` minor units."""
        rate = rate or self.get_rate()
        return sum(
            money.convert_minor(w["balance"], w["currency"], in_currency, rate)
            for w in self.balances()
        )

    # ---------------------------------------------------------- categories
    def add_category(self, kind: str, name: str, parent_id: Optional[int] = None,
                     icon: str = "category", color: str = "#8A9A95") -> int:
        name = name.strip()
        if not name:
            raise AppError("اسم الفئة مطلوب")
        if parent_id is not None:
            parent = self.get_category(parent_id)
            if parent["parent_id"] is not None:
                raise AppError("الفئة الفرعية ما تقدر تحتوي فئات فرعية")
            kind = parent["kind"]
        elif kind not in ("expense", "income"):
            raise AppError("نوع الفئة غير صحيح")
        order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order),-1)+1 FROM categories WHERE kind=? AND parent_id IS ?",
            (kind, parent_id),
        ).fetchone()[0]
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO categories(parent_id,kind,name,icon,color,sort_order) VALUES(?,?,?,?,?,?)",
                (parent_id, kind, name, icon, color, order),
            )
        return cur.lastrowid

    def get_category(self, category_id: int) -> dict:
        row = self.conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row:
            raise NotFound("الفئة غير موجودة")
        return dict(row)

    def update_category(self, category_id: int, name: Optional[str] = None,
                        icon: Optional[str] = None, color: Optional[str] = None) -> None:
        self.get_category(category_id)
        with self.conn:
            if name is not None:
                if not name.strip():
                    raise AppError("اسم الفئة مطلوب")
                self.conn.execute("UPDATE categories SET name=? WHERE id=?", (name.strip(), category_id))
            if icon is not None:
                self.conn.execute("UPDATE categories SET icon=? WHERE id=?", (icon, category_id))
            if color is not None:
                self.conn.execute("UPDATE categories SET color=? WHERE id=?", (color, category_id))

    def reorder_categories(self, ordered_ids: Iterable[int]) -> None:
        """Persist a new order. All ids must be siblings (same parent and kind)."""
        ids = list(ordered_ids)
        cats = [self.get_category(i) for i in ids]
        if len({(c["parent_id"], c["kind"]) for c in cats}) > 1:
            raise AppError("الترتيب لازم يكون بين فئات من نفس المستوى")
        with self.conn:
            for pos, cid in enumerate(ids):
                self.conn.execute("UPDATE categories SET sort_order=? WHERE id=?", (pos, cid))

    def move_category(self, category_id: int, direction: int) -> None:
        """Move a category one step up (-1) or down (+1) among its siblings."""
        c = self.get_category(category_id)
        sibs = [r["id"] for r in self.conn.execute(
            "SELECT id FROM categories WHERE kind=? AND parent_id IS ? ORDER BY sort_order, id",
            (c["kind"], c["parent_id"]))]
        i = sibs.index(category_id)
        j = i + (1 if direction > 0 else -1)
        if 0 <= j < len(sibs):
            sibs[i], sibs[j] = sibs[j], sibs[i]
            self.reorder_categories(sibs)

    def category_usage(self, category_id: int) -> int:
        """Number of transactions using this category or any of its children."""
        return self.conn.execute(
            """SELECT COUNT(*) FROM transactions WHERE category_id IN
               (SELECT id FROM categories WHERE id=:c OR parent_id=:c)""",
            {"c": category_id},
        ).fetchone()[0]

    def delete_category(self, category_id: int, reassign_to: Optional[int] = None) -> None:
        """Delete a category (and its children). If it is used, `reassign_to`
        must name another category that receives the transactions."""
        c = self.get_category(category_id)
        used = self.category_usage(category_id)
        if used and reassign_to is None:
            raise InUse(f"الفئة مستخدمة في {used} معاملة. اختر فئة بديلة")
        with self.conn:
            if used:
                target = self.get_category(reassign_to)
                if target["kind"] != c["kind"]:
                    raise AppError("الفئة البديلة لازم تكون من نفس النوع")
                if target["id"] == category_id or target["parent_id"] == category_id:
                    raise AppError("اختر فئة بديلة من خارج الفئة المحذوفة")
                self.conn.execute(
                    """UPDATE transactions SET category_id=:t WHERE category_id IN
                       (SELECT id FROM categories WHERE id=:c OR parent_id=:c)""",
                    {"t": reassign_to, "c": category_id},
                )
            self.conn.execute("DELETE FROM categories WHERE id=?", (category_id,))

    def category_tree(self, kind: str) -> list:
        """Top-level categories of `kind`, each with a `children` list, in user order."""
        rows = _rows(self.conn.execute(
            "SELECT * FROM categories WHERE kind=? ORDER BY sort_order, id", (kind,)))
        tops = [dict(r, children=[]) for r in rows if r["parent_id"] is None]
        by_id = {t["id"]: t for t in tops}
        for r in rows:
            if r["parent_id"] in by_id:
                by_id[r["parent_id"]]["children"].append(r)
        return tops

    # -------------------------------------------------------------- people
    def add_person(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise AppError("اسم الشخص مطلوب")
        try:
            with self.conn:
                return self.conn.execute("INSERT INTO people(name) VALUES(?)", (name,)).lastrowid
        except sqlite3.IntegrityError:
            raise AppError("هذا الشخص موجود من قبل")

    def list_people(self) -> list:
        return _rows(self.conn.execute("SELECT * FROM people ORDER BY name"))

    def rename_person(self, person_id: int, name: str) -> None:
        if not name.strip():
            raise AppError("اسم الشخص مطلوب")
        try:
            with self.conn:
                self.conn.execute("UPDATE people SET name=? WHERE id=?", (name.strip(), person_id))
        except sqlite3.IntegrityError:
            raise AppError("هذا الاسم موجود من قبل")

    def delete_person(self, person_id: int) -> None:
        """Transactions keep existing; they just lose the person tag."""
        with self.conn:
            self.conn.execute("DELETE FROM people WHERE id=?", (person_id,))

    # -------------------------------------------------------- transactions
    def _check_category(self, category_id: Optional[int], kind: str) -> None:
        if category_id is None:
            return
        if self.get_category(category_id)["kind"] != kind:
            raise AppError("نوع الفئة ما يطابق نوع المعاملة")

    def _add_simple(self, kind: str, wallet_id: int, amount, category_id, person_id, note, date) -> int:
        w = self.get_wallet(wallet_id)
        minor = money.to_minor(amount, w["currency"])
        if minor <= 0:
            raise AppError("المبلغ لازم يكون أكبر من صفر")
        self._check_category(category_id, kind)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO transactions(kind,amount,wallet_id,category_id,person_id,note,date) "
                "VALUES(?,?,?,?,?,?,?)",
                (kind, minor, wallet_id, category_id, person_id, note.strip(), date or _today()),
            )
        return cur.lastrowid

    def add_expense(self, wallet_id: int, amount, category_id: Optional[int] = None,
                    person_id: Optional[int] = None, note: str = "", date: Optional[str] = None) -> int:
        return self._add_simple("expense", wallet_id, amount, category_id, person_id, note, date)

    def add_income(self, wallet_id: int, amount, category_id: Optional[int] = None,
                   person_id: Optional[int] = None, note: str = "", date: Optional[str] = None) -> int:
        return self._add_simple("income", wallet_id, amount, category_id, person_id, note, date)

    def add_transfer(self, from_wallet_id: int, to_wallet_id: int, amount, to_amount=None,
                     rate: Optional[float] = None, note: str = "", date: Optional[str] = None) -> int:
        """Move money between wallets. `amount` is in the source wallet's currency.
        If currencies differ, the received amount is computed from `rate`
        (IQD per USD, default = the saved rate) unless `to_amount` is given."""
        if from_wallet_id == to_wallet_id:
            raise AppError("اختر محفظتين مختلفتين")
        src, dst = self.get_wallet(from_wallet_id), self.get_wallet(to_wallet_id)
        minor = money.to_minor(amount, src["currency"])
        if minor <= 0:
            raise AppError("المبلغ لازم يكون أكبر من صفر")
        used_rate = None
        if src["currency"] == dst["currency"]:
            to_minor_amount = minor
        else:
            used_rate = float(rate or self.get_rate())
            if to_amount is not None:
                to_minor_amount = money.to_minor(to_amount, dst["currency"])
                if to_minor_amount <= 0:
                    raise AppError("المبلغ المستلم لازم يكون أكبر من صفر")
            else:
                to_minor_amount = money.convert_minor(minor, src["currency"], dst["currency"], used_rate)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO transactions(kind,amount,wallet_id,to_wallet_id,to_amount,rate,note,date) "
                "VALUES('transfer',?,?,?,?,?,?,?)",
                (minor, from_wallet_id, to_wallet_id, to_minor_amount, used_rate, note.strip(), date or _today()),
            )
        return cur.lastrowid

    def get_transaction(self, tx_id: int) -> dict:
        rows = self.list_transactions(tx_id=tx_id)
        if not rows:
            raise NotFound("المعاملة غير موجودة")
        return rows[0]

    def update_transaction(self, tx_id: int, amount=None, category_id=..., person_id=...,
                           note: Optional[str] = None, date: Optional[str] = None) -> None:
        """Edit an expense/income. (Pass category_id/person_id=None to clear them.)
        For transfers only note/date can change - delete and re-add to change amounts."""
        t = self.get_transaction(tx_id)
        sets, args = [], []
        if t["kind"] == "transfer":
            if amount is not None or category_id is not ... or person_id is not ...:
                raise AppError("التحويل ما ينعدل مبلغه. احذفه وأضفه من جديد")
        else:
            if amount is not None:
                minor = money.to_minor(amount, t["currency"])
                if minor <= 0:
                    raise AppError("المبلغ لازم يكون أكبر من صفر")
                sets.append("amount=?"); args.append(minor)
            if category_id is not ...:
                self._check_category(category_id, t["kind"])
                sets.append("category_id=?"); args.append(category_id)
            if person_id is not ...:
                sets.append("person_id=?"); args.append(person_id)
        if note is not None:
            sets.append("note=?"); args.append(note.strip())
        if date is not None:
            sets.append("date=?"); args.append(date)
        if sets:
            with self.conn:
                self.conn.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE id=?", (*args, tx_id))

    def delete_transaction(self, tx_id: int) -> None:
        self.get_transaction(tx_id)
        with self.conn:
            self.conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))

    def list_transactions(
        self,
        tx_id: Optional[int] = None,
        kinds: Optional[list] = None,
        wallet_ids: Optional[list] = None,
        category_ids: Optional[list] = None,
        exclude_categories: bool = False,
        person_ids: Optional[list] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        min_amount=None,
        max_amount=None,
        text: Optional[str] = None,
        order: str = "newest",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list:
        """Filtered, joined transaction list (the engine behind the filter sheet).

        - A parent category also matches all of its sub-categories.
        - `exclude_categories=True` turns the category filter into "everything except".
        - min/max_amount are user-facing amounts compared against each row in its own
          wallet currency, so use them together with a single-currency wallet filter.
        - order: 'newest' | 'oldest' | 'largest'.
        """
        where, args = [], {}

        def in_clause(name, values):
            keys = []
            for i, v in enumerate(values):
                k = f"{name}{i}"
                args[k] = v
                keys.append(f":{k}")
            return ",".join(keys)

        if tx_id is not None:
            where.append("t.id=:tx_id"); args["tx_id"] = tx_id
        if kinds:
            where.append(f"t.kind IN ({in_clause('kind', kinds)})")
        if wallet_ids:
            ph = in_clause("wal", wallet_ids)
            where.append(f"(t.wallet_id IN ({ph}) OR t.to_wallet_id IN ({ph}))")
        if category_ids:
            ph = in_clause("cat", category_ids)
            inner = f"t.category_id IN (SELECT id FROM categories WHERE id IN ({ph}) OR parent_id IN ({ph}))"
            where.append(f"(t.category_id IS NULL OR NOT {inner})" if exclude_categories else inner)
        if person_ids:
            where.append(f"t.person_id IN ({in_clause('per', person_ids)})")
        if date_from:
            where.append("t.date>=:d_from"); args["d_from"] = date_from
        if date_to:
            where.append("t.date<=:d_to"); args["d_to"] = date_to
        if min_amount is not None:
            where.append("t.amount >= CAST(:min_a * CASE w.currency WHEN 'USD' THEN 100 ELSE 1 END AS INTEGER)")
            args["min_a"] = float(min_amount)
        if max_amount is not None:
            where.append("t.amount <= CAST(:max_a * CASE w.currency WHEN 'USD' THEN 100 ELSE 1 END AS INTEGER)")
            args["max_a"] = float(max_amount)
        if text and text.strip():
            args["q"] = f"%{text.strip()}%"
            where.append("(t.note LIKE :q OR c.name LIKE :q OR pc.name LIKE :q OR pe.name LIKE :q "
                         "OR w.name LIKE :q OR tw.name LIKE :q)")

        order_sql = {
            "newest": "t.date DESC, t.id DESC",
            "oldest": "t.date ASC, t.id ASC",
            "largest": "t.amount DESC, t.id DESC",
        }.get(order)
        if order_sql is None:
            raise AppError("ترتيب غير معروف")

        sql = """
            SELECT t.*, w.name AS wallet_name, w.currency AS currency,
                   tw.name AS to_wallet_name, tw.currency AS to_currency,
                   c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                   c.parent_id AS parent_category_id, pc.name AS parent_category_name,
                   pe.name AS person_name
            FROM transactions t
            JOIN wallets w ON w.id = t.wallet_id
            LEFT JOIN wallets tw ON tw.id = t.to_wallet_id
            LEFT JOIN categories c ON c.id = t.category_id
            LEFT JOIN categories pc ON pc.id = c.parent_id
            LEFT JOIN people pe ON pe.id = t.person_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order_sql}"
        if limit is not None:
            sql += " LIMIT :limit OFFSET :offset"
            args["limit"], args["offset"] = limit, offset
        return _rows(self.conn.execute(sql, args))

    # --------------------------------------------------------------- notes
    def add_note(self, text: str, pinned: bool = False) -> int:
        if not text.strip():
            raise AppError("الملاحظة فارغة")
        with self.conn:
            return self.conn.execute(
                "INSERT INTO notes(text,pinned) VALUES(?,?)", (text.strip(), int(pinned))).lastrowid

    def list_notes(self) -> list:
        return _rows(self.conn.execute("SELECT * FROM notes ORDER BY pinned DESC, id DESC"))

    def toggle_note_pin(self, note_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE notes SET pinned = 1 - pinned WHERE id=?", (note_id,))

    def update_note(self, note_id: int, text: str) -> None:
        if not text.strip():
            raise AppError("الملاحظة فارغة")
        with self.conn:
            self.conn.execute("UPDATE notes SET text=? WHERE id=?", (text.strip(), note_id))

    def delete_note(self, note_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
