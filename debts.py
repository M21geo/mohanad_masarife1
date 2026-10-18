"""Debts: money I owe ('on' = عليّ) and money owed to me ('for' = لي).

A payment can optionally be tied to a wallet: paying a debt I owe creates an
expense in that wallet; receiving a payment on a debt owed to me creates an
income. That keeps wallet balances truthful without double entry by the user.
"""
from datetime import date as _date
from typing import Optional

from . import money
from .dates import add_period
from .repo import AppError, NotFound, Repo, _rows

DIRECTIONS = ("on", "for")


class Debts:
    def __init__(self, repo: Repo):
        self.repo = repo
        self.conn = repo.conn

    # ---------------------------------------------------------------- core
    def add_debt(self, direction: str, person_id: int, amount, currency: str,
                 due_date: Optional[str] = None, note: str = "", wallet_id: Optional[int] = None,
                 date: Optional[str] = None, installments: int = 0, first_due: Optional[str] = None,
                 period: str = "monthly") -> int:
        """Create a debt.

        - wallet_id: money really moved through that wallet now. Borrowing ('on') adds income to the
          wallet; lending ('for') takes an expense out of it. Its currency must match the debt.
        - installments (>=2): split into equal parts (the last takes the remainder), due every
          `period` ('monthly' | 'weekly') starting `first_due`.
        """
        if direction not in DIRECTIONS:
            raise AppError("نوع الدين غير صحيح")
        minor = money.to_minor(amount, currency)
        if minor <= 0:
            raise AppError("المبلغ لازم يكون أكبر من صفر")
        person = self.conn.execute("SELECT name FROM people WHERE id=?", (person_id,)).fetchone()
        if not person:
            raise NotFound("الشخص غير موجود")
        date = date or _date.today().isoformat()
        installments = int(installments or 0)
        if installments == 1 or installments < 0 or installments > 120:
            raise AppError("عدد الأقساط لازم يكون بين 2 و120 (أو بدون تقسيط)")
        if installments and period not in ("monthly", "weekly"):
            raise AppError("نوع القسط غير صحيح")
        if installments:
            first_due = first_due or add_period(date, period, 1)
            due_date = add_period(first_due, period, installments - 1)
        else:
            first_due = None
        tx_id = None
        if wallet_id is not None:
            if self.repo.get_wallet(wallet_id)["currency"] != currency:
                raise AppError("عملة المحفظة لازم تطابق عملة الدين")
        with self.conn:
            if wallet_id is not None:
                if direction == "on":
                    tx_id = self.repo.add_income(wallet_id, money.from_minor(minor, currency), person_id=person_id,
                                                 note="استلام دين من " + person["name"], date=date)
                else:
                    tx_id = self.repo.add_expense(wallet_id, money.from_minor(minor, currency), person_id=person_id,
                                                  note="إقراض " + person["name"], date=date)
            return self.conn.execute(
                "INSERT INTO debts(direction,person_id,currency,total,due_date,note,wallet_id,open_tx_id,"
                "inst_count,inst_first,inst_period) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (direction, person_id, currency, minor, due_date or None, note.strip(), wallet_id, tx_id,
                 installments, first_due, period)).lastrowid

    def add_to_debt(self, debt_id: int, amount, wallet_id: Optional[int] = None, date: Optional[str] = None) -> None:
        """Increase an existing debt (borrow/lend more). Posts the wallet transaction if wallet_id is given."""
        d = self.get_debt(debt_id)
        minor = money.to_minor(amount, d["currency"])
        if minor <= 0:
            raise AppError("المبلغ لازم يكون أكبر من صفر")
        date = date or _date.today().isoformat()
        if wallet_id is not None and self.repo.get_wallet(wallet_id)["currency"] != d["currency"]:
            raise AppError("عملة المحفظة لازم تطابق عملة الدين")
        with self.conn:
            if wallet_id is not None:
                if d["direction"] == "on":
                    self.repo.add_income(wallet_id, money.from_minor(minor, d["currency"]), person_id=d["person_id"],
                                         note="زيادة دين من " + d["person_name"], date=date)
                else:
                    self.repo.add_expense(wallet_id, money.from_minor(minor, d["currency"]), person_id=d["person_id"],
                                          note="زيادة مبلغ مُقرَض إلى " + d["person_name"], date=date)
            self.conn.execute("UPDATE debts SET total=total+? WHERE id=?", (minor, debt_id))

    @staticmethod
    def schedule(d: dict, today: str) -> list:
        """Installment plan with status: paid | partial | due | late (empty when not installments)."""
        n = d["inst_count"]
        if n <= 0:
            return []
        base = d["total"] // n
        amounts = [base] * (n - 1) + [d["total"] - base * (n - 1)]
        out, cum = [], 0
        for i, amt in enumerate(amounts):
            due = add_period(d["inst_first"], d["inst_period"], i)
            covered = min(amt, max(0, d["paid"] - cum))
            cum += amt
            status = "paid" if covered >= amt else ("late" if due < today else ("partial" if covered else "due"))
            if status == "partial" and due < today:
                status = "late"
            out.append({"n": i + 1, "due": due, "amount": amt, "covered": covered, "remaining": amt - covered,
                        "status": status})
        return out

    def get_debt(self, debt_id: int) -> dict:
        rows = self.list_debts(debt_id=debt_id)
        if not rows:
            raise NotFound("الدين غير موجود")
        return rows[0]

    def list_debts(self, direction: Optional[str] = None, include_settled: bool = True,
                   debt_id: Optional[int] = None, today: Optional[str] = None) -> list:
        """Debts with `paid`, `remaining` (minor units), `settled` and `overdue`.
        Open debts come first, soonest due date first."""
        today = today or _date.today().isoformat()
        where, args = [], {}
        if direction:
            where.append("d.direction=:dir"); args["dir"] = direction
        if debt_id is not None:
            where.append("d.id=:id"); args["id"] = debt_id
        sql = """
            SELECT d.*, p.name AS person_name,
                   COALESCE((SELECT SUM(amount) FROM debt_payments WHERE debt_id=d.id),0) AS paid
            FROM debts d JOIN people p ON p.id = d.person_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        out = []
        for d in _rows(self.conn.execute(sql, args)):
            d["remaining"] = d["total"] - d["paid"]
            d["settled"] = d["remaining"] <= 0
            d["schedule"] = self.schedule(d, today)
            d["next_due"] = d["next_amount"] = None
            if d["schedule"] and not d["settled"]:
                nxt = next(x for x in d["schedule"] if x["remaining"] > 0)
                d["next_due"], d["next_amount"] = nxt["due"], nxt["remaining"]
                d["due_date"] = nxt["due"]
                d["late_count"] = sum(1 for x in d["schedule"] if x["status"] == "late")
            d["overdue"] = (not d["settled"]) and bool(d["due_date"]) and d["due_date"] < today
            if include_settled or not d["settled"]:
                out.append(d)
        out.sort(key=lambda d: (d["settled"], d["due_date"] is None, d["due_date"] or "", d["id"]))
        return out

    def update_debt(self, debt_id: int, due_date=..., note: Optional[str] = None, total=None) -> None:
        d = self.get_debt(debt_id)
        with self.conn:
            if due_date is not ...:
                self.conn.execute("UPDATE debts SET due_date=? WHERE id=?", (due_date or None, debt_id))
            if note is not None:
                self.conn.execute("UPDATE debts SET note=? WHERE id=?", (note.strip(), debt_id))
            if total is not None:
                minor = money.to_minor(total, d["currency"])
                if minor < d["paid"] or minor <= 0:
                    raise AppError("المبلغ الكلي أقل من المسدّد")
                self.conn.execute("UPDATE debts SET total=? WHERE id=?", (minor, debt_id))

    def delete_debt(self, debt_id: int) -> None:
        """Deletes the debt, its payments, and any wallet transactions they created."""
        self.get_debt(debt_id)
        tx_ids = [r[0] for r in self.conn.execute(
            "SELECT transaction_id FROM debt_payments WHERE debt_id=? AND transaction_id IS NOT NULL", (debt_id,))]
        opened = self.conn.execute("SELECT open_tx_id FROM debts WHERE id=?", (debt_id,)).fetchone()[0]
        if opened:
            tx_ids.append(opened)
        with self.conn:
            for t in tx_ids:
                self.conn.execute("DELETE FROM transactions WHERE id=?", (t,))
            self.conn.execute("DELETE FROM debts WHERE id=?", (debt_id,))

    # ------------------------------------------------------------ payments
    def pay(self, debt_id: int, amount, wallet_id: Optional[int] = None,
            date: Optional[str] = None, note: str = "") -> int:
        """Record a payment (default date = today). With `wallet_id`, also post the
        matching expense/income to that wallet (its currency must match the debt)."""
        d = self.get_debt(debt_id)
        minor = money.to_minor(amount, d["currency"])
        if minor <= 0:
            raise AppError("المبلغ لازم يكون أكبر من صفر")
        if minor > d["remaining"]:
            raise AppError("المبلغ أكبر من المتبقي من الدين")
        date = date or _date.today().isoformat()
        tx_id = None
        if wallet_id is not None:
            if self.repo.get_wallet(wallet_id)["currency"] != d["currency"]:
                raise AppError("عملة المحفظة لازم تطابق عملة الدين")
            label = ("تسديد دين: " if d["direction"] == "on" else "استلام دفعة دين: ") + d["person_name"]
            adder = self.repo.add_expense if d["direction"] == "on" else self.repo.add_income
            tx_id = adder(wallet_id, money.from_minor(minor, d["currency"]),
                          person_id=d["person_id"], note=label, date=date)
        with self.conn:
            return self.conn.execute(
                "INSERT INTO debt_payments(debt_id,amount,date,transaction_id,note) VALUES(?,?,?,?,?)",
                (debt_id, minor, date, tx_id, note.strip()),
            ).lastrowid

    def list_payments(self, debt_id: int) -> list:
        """Payments newest first, each with: `n` (order paid), `wallet_name` (if posted to a wallet) and
        `remaining_after` (debt balance right after that payment)."""
        total = self.conn.execute("SELECT total FROM debts WHERE id=?", (debt_id,)).fetchone()
        rows = _rows(self.conn.execute(
            "SELECT p.*, w.name AS wallet_name FROM debt_payments p "
            "LEFT JOIN transactions t ON t.id=p.transaction_id LEFT JOIN wallets w ON w.id=t.wallet_id "
            "WHERE p.debt_id=? ORDER BY p.date ASC, p.id ASC", (debt_id,)))
        left = total[0] if total else 0
        for i, r in enumerate(rows, 1):
            left -= r["amount"]
            r["n"], r["remaining_after"] = i, left
        return rows[::-1]

    def delete_payment(self, payment_id: int) -> None:
        row = self.conn.execute("SELECT * FROM debt_payments WHERE id=?", (payment_id,)).fetchone()
        if not row:
            raise NotFound("الدفعة غير موجودة")
        with self.conn:
            if row["transaction_id"]:
                self.conn.execute("DELETE FROM transactions WHERE id=?", (row["transaction_id"],))
            self.conn.execute("DELETE FROM debt_payments WHERE id=?", (payment_id,))

    # ------------------------------------------------------------- summary
    def summary(self, direction: str) -> dict:
        """Remaining totals per currency (minor units) + counts, for the header card."""
        out = {"IQD": 0, "USD": 0, "open": 0, "overdue": 0}
        for d in self.list_debts(direction=direction, include_settled=False):
            out[d["currency"]] += d["remaining"]
            out["open"] += 1
            out["overdue"] += int(d["overdue"])
        return out
