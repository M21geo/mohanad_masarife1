"""Statistics behind the Statistics screen (overview / categories / people / patterns).

Everything is computed in one display currency (IQD or USD, minor units) by
converting each transaction with the exchange rate. Transfers are ignored.
Months are 'YYYY-MM' strings.
"""
import calendar
from datetime import date as _date, datetime
from typing import Optional

from . import money
from .repo import Repo

# Saturday first (the Iraqi week); values are Python's weekday(): Mon=0 ... Sun=6
WEEK_ORDER = [5, 6, 0, 1, 2, 3, 4]
WEEKDAY_NAMES = {5: "السبت", 6: "الأحد", 0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة"}
MONTH_NAMES = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
               "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"]
NO_CATEGORY = "بدون فئة"
NO_PERSON = "بدون شخص"


def shift_month(ym: str, delta: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_label(ym: str) -> str:
    return f"{MONTH_NAMES[int(ym[5:7]) - 1]} {ym[:4]}"


def pct_change(cur: int, prev: int) -> Optional[int]:
    """Whole-number % change vs previous; None when there is nothing to compare to."""
    if not prev:
        return None
    return round((cur - prev) / prev * 100)


class Stats:
    def __init__(self, repo: Repo, currency: str = "IQD", rate: Optional[float] = None,
                 today: Optional[str] = None):
        self.repo = repo
        self.currency = currency
        self.rate = rate or repo.get_rate()
        self.today = today or _date.today().isoformat()
        self._cache = {}

    # ------------------------------------------------------------- helpers
    def _conv(self, t: dict) -> int:
        return money.convert_minor(t["amount"], t["currency"], self.currency, self.rate)

    def _month(self, ym: str) -> list:
        """[(tx, converted_amount)] for income/expense in the month."""
        if ym not in self._cache:
            last = calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]
            rows = self.repo.list_transactions(
                kinds=["expense", "income"], date_from=f"{ym}-01", date_to=f"{ym}-{last:02d}")
            self._cache[ym] = [(t, self._conv(t)) for t in rows]
        return self._cache[ym]

    def days_in_scope(self, ym: str) -> int:
        """Days elapsed: today's day-of-month for the running month, else the full month."""
        if ym == self.today[:7]:
            return int(self.today[8:10])
        return calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]

    @staticmethod
    def _share(items: list, key: str = "total") -> list:
        total = sum(i[key] for i in items)
        for i in items:
            i["pct"] = round(i[key] / total * 100) if total else 0
        return items

    # ------------------------------------------------------------ overview
    def totals(self, ym: str) -> dict:
        inc = sum(v for t, v in self._month(ym) if t["kind"] == "income")
        exp_items = [(t, v) for t, v in self._month(ym) if t["kind"] == "expense"]
        exp = sum(v for _, v in exp_items)
        biggest = max(exp_items, key=lambda x: x[1], default=None)
        days = self.days_in_scope(ym)
        return {
            "income": inc,
            "expense": exp,
            "net": inc - exp,
            "savings_rate": round((inc - exp) / inc * 100) if inc else None,
            "spent_pct": round(exp / inc * 100) if inc else None,
            "avg_daily": round(exp / days) if days else 0,
            "count": len(exp_items),
            "avg_tx": round(exp / len(exp_items)) if exp_items else 0,
            "biggest": dict(biggest[0], converted=biggest[1]) if biggest else None,
        }

    def overview(self, ym: str) -> dict:
        """Current-month totals plus % change of each figure vs the previous month."""
        cur, prev = self.totals(ym), self.totals(shift_month(ym, -1))
        return {
            "month": ym, "label": month_label(ym), "currency": self.currency,
            **cur,
            "prev": prev,
            "income_delta": pct_change(cur["income"], prev["income"]),
            "expense_delta": pct_change(cur["expense"], prev["expense"]),
            "avg_daily_delta": pct_change(cur["avg_daily"], prev["avg_daily"]),
        }

    def series(self, ym: str, n: int = 6) -> list:
        """Income vs expense for the n months ending at `ym` (oldest first) - the bar chart."""
        out = []
        for i in range(-(n - 1), 1):
            key = shift_month(ym, i)
            t = self.totals(key)
            out.append({"month": key, "label": MONTH_NAMES[int(key[5:7]) - 1],
                        "income": t["income"], "expense": t["expense"]})
        return out

    # ---------------------------------------------------------- categories
    def categories(self, ym: str, kind: str = "expense") -> list:
        """Top-level categories (sub-categories rolled up) with share, change vs the
        previous month, and a `children` breakdown for drill-down. Biggest first."""
        def group(month):
            g = {}
            for t, v in self._month(month):
                if t["kind"] != kind:
                    continue
                top_id = t["parent_category_id"] or t["category_id"]
                top_name = t["parent_category_name"] or t["category_name"] or NO_CATEGORY
                e = g.setdefault(top_name, {"id": top_id, "name": top_name, "total": 0, "children": {},
                                            "color": t["category_color"], "icon": t["category_icon"]})
                e["total"] += v
                if t["parent_category_id"]:
                    e["children"][t["category_name"]] = e["children"].get(t["category_name"], 0) + v
                elif t["category_id"]:
                    e["children"]["عام"] = e["children"].get("عام", 0) + v
            return g

        cur, prev = group(ym), group(shift_month(ym, -1))
        out = []
        for name, e in cur.items():
            e["delta"] = pct_change(e["total"], prev.get(name, {}).get("total", 0))
            e["children"] = self._share(
                sorted(({"name": k, "total": v} for k, v in e["children"].items()),
                       key=lambda c: -c["total"]))
            out.append(e)
        out.sort(key=lambda e: -e["total"])
        return self._share(out)

    # -------------------------------------------------------------- people
    def by_person(self, ym: str) -> list:
        g = {}
        for t, v in self._month(ym):
            if t["kind"] != "expense":
                continue
            e = g.setdefault(t["person_name"] or NO_PERSON, {"name": t["person_name"] or NO_PERSON, "total": 0, "count": 0})
            e["total"] += v
            e["count"] += 1
        return self._share(sorted(g.values(), key=lambda e: -e["total"]))

    def by_wallet(self, ym: str) -> list:
        g = {}
        for t, v in self._month(ym):
            if t["kind"] != "expense":
                continue
            e = g.setdefault(t["wallet_name"], {"name": t["wallet_name"], "total": 0})
            e["total"] += v
        return self._share(sorted(g.values(), key=lambda e: -e["total"]))

    # ------------------------------------------------------------ patterns
    def weekdays(self, ym: str) -> dict:
        totals = {d: 0 for d in WEEK_ORDER}
        for t, v in self._month(ym):
            if t["kind"] == "expense":
                totals[datetime.strptime(t["date"], "%Y-%m-%d").weekday()] += v
        days = [{"name": WEEKDAY_NAMES[d], "total": totals[d]} for d in WEEK_ORDER]
        peak = max(days, key=lambda d: d["total"])
        return {"days": days, "peak": peak["name"] if peak["total"] else None}

    def top_expenses(self, ym: str, n: int = 5) -> list:
        items = [(t, v) for t, v in self._month(ym) if t["kind"] == "expense"]
        items.sort(key=lambda x: -x[1])
        return [dict(t, converted=v) for t, v in items[:n]]

    # ------------------------------------------------------------ insights
    def insights(self, ym: str) -> list:
        """Short Arabic sentences derived from the numbers (the 'smart notes' card)."""
        ov, out = self.overview(ym), []
        cats = self.categories(ym)
        if cats:
            out.append(f"أعلى فئة صرفاً: {cats[0]['name']} بنسبة {cats[0]['pct']}% من مصروف الشهر.")
        if ov["expense_delta"] is not None:
            word = "أعلى" if ov["expense_delta"] > 0 else "أقل"
            out.append(f"مصروفك هذا الشهر {word} من الشهر الماضي بنسبة {abs(ov['expense_delta'])}%.")
        peak = self.weekdays(ym)["peak"]
        if peak:
            out.append(f"أكثر يوم تصرف فيه هو {peak}.")
        people = [p for p in self.by_person(ym) if p["name"] != NO_PERSON]
        if people:
            out.append(f"أكثر شخص مرتبط بمصاريفك: {people[0]['name']} ({money.fmt(people[0]['total'], self.currency)}).")
        if ov["savings_rate"] is not None:
            if ov["savings_rate"] >= 0:
                out.append(f"ادخرت {ov['savings_rate']}% من دخلك هذا الشهر.")
            else:
                out.append(f"صرفت أكثر من دخلك هذا الشهر بنسبة {abs(ov['savings_rate'])}%.")
        return out
