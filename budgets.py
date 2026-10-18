"""Monthly budgets: one overall limit and/or limits per category (a parent category counts its sub-categories)."""
import calendar
from typing import Optional

from . import money
from .repo import AppError, NotFound, Repo, _rows


class Budgets:
    def __init__(self, repo: Repo):
        self.repo = repo
        self.conn = repo.conn

    def set(self, category_id: Optional[int], amount, currency: str) -> int:
        """Create or replace the budget of a category (None = overall)."""
        minor = money.to_minor(amount, currency)
        if minor <= 0:
            raise AppError("مبلغ الميزانية لازم يكون أكبر من صفر")
        if category_id is not None and self.repo.get_category(category_id)["kind"] != "expense":
            raise AppError("الميزانية للمصاريف فقط")
        row = self.conn.execute("SELECT id FROM budgets WHERE category_id IS ?", (category_id,)).fetchone()
        with self.conn:
            if row:
                self.conn.execute("UPDATE budgets SET amount=?, currency=? WHERE id=?", (minor, currency, row["id"]))
                return row["id"]
            return self.conn.execute("INSERT INTO budgets(category_id,currency,amount) VALUES(?,?,?)",
                                     (category_id, currency, minor)).lastrowid

    def delete(self, budget_id: int) -> None:
        if not self.conn.execute("SELECT 1 FROM budgets WHERE id=?", (budget_id,)).fetchone():
            raise NotFound("الميزانية غير موجودة")
        with self.conn:
            self.conn.execute("DELETE FROM budgets WHERE id=?", (budget_id,))

    def list(self) -> list:
        return _rows(self.conn.execute(
            """SELECT b.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                      c.parent_id AS parent_id, pc.name AS parent_name
               FROM budgets b LEFT JOIN categories c ON c.id=b.category_id
               LEFT JOIN categories pc ON pc.id=c.parent_id
               ORDER BY (b.category_id IS NOT NULL), c.sort_order, b.id"""))

    def status(self, ym: str, today: str) -> dict:
        """{'overall': item|None, 'categories': [item]}; item has spent/remaining/pct/state/projected/daily_left."""
        last = calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]
        txs = self.repo.list_transactions(kinds=["expense"], date_from=f"{ym}-01", date_to=f"{ym}-{last:02d}")
        rate = self.repo.get_rate()
        running = ym == today[:7]
        elapsed = int(today[8:10]) if running else last
        left = last - elapsed + 1 if running else 0
        out = {"overall": None, "categories": []}
        for b in self.list():
            spent = sum(money.convert_minor(t["amount"], t["currency"], b["currency"], rate) for t in txs
                        if b["category_id"] is None or t["category_id"] == b["category_id"]
                        or t["parent_category_id"] == b["category_id"])
            remaining = b["amount"] - spent
            pct = round(spent / b["amount"] * 100)
            item = {"id": b["id"], "category_id": b["category_id"], "currency": b["currency"], "limit": b["amount"],
                    "name": "الميزانية الكلية" if b["category_id"] is None else
                            (f"{b['parent_name']} › {b['category_name']}" if b["parent_name"] else b["category_name"]),
                    "icon": b["category_icon"] or "account_balance_wallet", "color": b["category_color"] or "#0B6B58",
                    "spent": spent, "remaining": remaining, "pct": pct,
                    "state": "over" if pct >= 100 else ("warn" if pct >= 80 else "ok"),
                    "projected": round(spent / elapsed * last) if running and elapsed and spent else None,
                    "daily_left": max(0, remaining) // left if running and left else None}
            if b["category_id"] is None:
                out["overall"] = item
            else:
                out["categories"].append(item)
        out["categories"].sort(key=lambda i: -i["pct"])
        return out

    def alerts(self, ym: str, today: str, category_id: Optional[int]) -> list:
        """Warnings for the budgets a new expense in `category_id` touches (overall + its category/parent)."""
        st = self.status(ym, today)
        cat = self.repo.get_category(category_id) if category_id else None
        related = {category_id, cat["parent_id"] if cat else None} - {None}
        items = ([st["overall"]] if st["overall"] else []) + [i for i in st["categories"] if i["category_id"] in related]
        msgs = []
        for i in items:
            if i["state"] == "over":
                msgs.append(f"تجاوزت «{i['name']}»: {i['pct']}% من الميزانية")
            elif i["state"] == "warn":
                msgs.append(f"اقتربت من حد «{i['name']}»: {i['pct']}%")
        return msgs
