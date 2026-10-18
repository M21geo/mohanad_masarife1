"""Statistics over ANY list of transactions (a month, or whatever the filter selected).

Used by the merged Transactions screen: the same rows that fill the list also feed the charts.
Everything is in one display currency (minor units); transfers are ignored.
"""
import math
import statistics
from datetime import date as _date, datetime, timedelta
from typing import Optional

from . import money
from .stats import MONTH_NAMES, NO_CATEGORY, NO_PERSON, WEEKDAY_NAMES, WEEK_ORDER, pct_change


class Analysis:
    def __init__(self, rows: list, currency: str, rate: float, span: Optional[tuple] = None):
        """rows: repo.list_transactions() dicts. span: (date_from, date_to) the period covers
        (used for per-day averages and to draw empty days); defaults to first..last transaction."""
        self.currency = currency
        self.rate = rate
        self.items = [(t, money.convert_minor(t["amount"], t["currency"], currency, rate))
                      for t in rows if t["kind"] in ("income", "expense")]
        dates = sorted(t["date"] for t, _ in self.items)
        if span and span[0] and span[1]:
            self.span = span
        elif dates:
            self.span = (dates[0], dates[-1])
        else:
            self.span = None

    # ---------------------------------------------------------------- basics
    def of(self, kind: str) -> list:
        return [(t, v) for t, v in self.items if t["kind"] == kind]

    @property
    def days(self) -> int:
        if not self.span:
            return 0
        a, b = _date.fromisoformat(self.span[0]), _date.fromisoformat(self.span[1])
        return max(1, (b - a).days + 1)

    @staticmethod
    def _share(items: list) -> list:
        total = sum(i["total"] for i in items)
        for i in items:
            i["pct"] = round(i["total"] / total * 100) if total else 0
        return items

    def totals(self) -> dict:
        exp, inc = self.of("expense"), self.of("income")
        e, i = sum(v for _, v in exp), sum(v for _, v in inc)
        amounts = sorted(v for _, v in exp)
        biggest = max(exp, key=lambda x: x[1], default=None)
        return {
            "income": i, "expense": e, "net": i - e,
            "savings_rate": round((i - e) / i * 100) if i else None,
            "spent_pct": round(e / i * 100) if i else None,
            "avg_daily": round(e / self.days) if self.days else 0,
            "count": len(self.items), "expense_count": len(exp), "income_count": len(inc),
            "avg_tx": round(e / len(exp)) if exp else 0,
            "median_tx": round(statistics.median(amounts)) if amounts else 0,
            "biggest": dict(biggest[0], converted=biggest[1]) if biggest else None,
        }

    def compare(self, prev: "Analysis") -> dict:
        a, b = self.totals(), prev.totals()
        return {"income": pct_change(a["income"], b["income"]), "expense": pct_change(a["expense"], b["expense"]),
                "avg_daily": pct_change(a["avg_daily"], b["avg_daily"]), "prev": b}

    # ------------------------------------------------------------ breakdowns
    def categories(self, kind: str = "expense", prev: Optional["Analysis"] = None) -> list:
        def group(an):
            g = {}
            for t, v in an.of(kind):
                top_name = t["parent_category_name"] or t["category_name"] or NO_CATEGORY
                e = g.setdefault(top_name, {"name": top_name, "total": 0, "count": 0, "children": {},
                                            "color": t["category_color"], "icon": t["category_icon"]})
                e["total"] += v
                e["count"] += 1
                if t["parent_category_id"]:
                    e["children"][t["category_name"]] = e["children"].get(t["category_name"], 0) + v
                elif t["category_id"]:
                    e["children"]["عام"] = e["children"].get("عام", 0) + v
            return g

        cur = group(self)
        before = group(prev) if prev else {}
        out = []
        for name, e in cur.items():
            e["delta"] = pct_change(e["total"], before[name]["total"]) if name in before else None
            e["children"] = self._share(sorted(({"name": k, "total": v} for k, v in e["children"].items()),
                                               key=lambda c: -c["total"]))
            out.append(e)
        out.sort(key=lambda e: -e["total"])
        return self._share(out)

    def _group(self, key_fn, kind="expense") -> list:
        g = {}
        for t, v in self.of(kind):
            k = key_fn(t)
            e = g.setdefault(k, {"name": k, "total": 0, "count": 0})
            e["total"] += v
            e["count"] += 1
        return self._share(sorted(g.values(), key=lambda e: -e["total"]))

    def by_person(self) -> list:
        return self._group(lambda t: t["person_name"] or NO_PERSON)

    def by_wallet(self) -> list:
        return self._group(lambda t: t["wallet_name"])

    def weekdays(self) -> dict:
        totals = {d: 0 for d in WEEK_ORDER}
        counts = {d: 0 for d in WEEK_ORDER}
        for t, v in self.of("expense"):
            wd = datetime.strptime(t["date"], "%Y-%m-%d").weekday()
            totals[wd] += v
            counts[wd] += 1
        days = [{"name": WEEKDAY_NAMES[d], "total": totals[d], "count": counts[d]} for d in WEEK_ORDER]
        peak = max(days, key=lambda d: d["total"])
        return {"days": days, "peak": peak["name"] if peak["total"] else None}

    def top_expenses(self, n: int = 5) -> list:
        items = sorted(self.of("expense"), key=lambda x: -x[1])
        return [dict(t, converted=v) for t, v in items[:n]]

    # ----------------------------------------------------------------- charts
    def timeline(self, max_months: int = 12) -> dict:
        """Income/expense over time. Daily bars when the period is up to ~5 weeks, else monthly."""
        if not self.span:
            return {"mode": "day", "points": []}
        a, b = _date.fromisoformat(self.span[0]), _date.fromisoformat(self.span[1])
        pts = []
        if (b - a).days <= 35:
            by = {}
            for t, v in self.items:
                d = by.setdefault(t["date"], {"income": 0, "expense": 0})
                d[t["kind"]] += v
            d = a
            while d <= b:
                x = by.get(d.isoformat(), {"income": 0, "expense": 0})
                pts.append({"key": d.isoformat(), "label": str(d.day), **x})
                d += timedelta(days=1)
            return {"mode": "day", "points": pts}
        by = {}
        for t, v in self.items:
            m = by.setdefault(t["date"][:7], {"income": 0, "expense": 0})
            m[t["kind"]] += v
        y, m = a.year, a.month
        while (y, m) <= (b.year, b.month):
            key = f"{y:04d}-{m:02d}"
            x = by.get(key, {"income": 0, "expense": 0})
            pts.append({"key": key, "label": MONTH_NAMES[m - 1], **x})
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return {"mode": "month", "points": pts[-max_months:]}

    def histogram(self, kind: str = "expense", max_bins: int = 7) -> list:
        """Distribution of transaction sizes: [{'lo','hi','count','total'}] (minor units), nice edges."""
        vals = [v for _, v in self.of(kind) if v > 0]
        if not vals:
            return []
        dec = money.CURRENCIES[self.currency]
        scale = 10 ** dec
        top = max(vals) / scale
        raw = top / max_bins
        mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
        step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), 10 * mag)
        n = max(1, min(max_bins + 1, math.ceil(top / step)))
        bins = [{"lo": round(i * step * scale), "hi": round((i + 1) * step * scale), "count": 0, "total": 0}
                for i in range(n)]
        for v in vals:
            i = min(n - 1, int(v / (step * scale)))
            bins[i]["count"] += 1
            bins[i]["total"] += v
        return bins

    # --------------------------------------------------------------- insights
    def insights(self) -> list:
        tot, out = self.totals(), []
        cats = self.categories()
        if cats:
            out.append(f"أعلى فئة صرفاً: {cats[0]['name']} بنسبة {cats[0]['pct']}% من المصروف.")
        peak = self.weekdays()["peak"]
        if peak:
            out.append(f"أكثر يوم تصرف فيه هو {peak}.")
        people = [p for p in self.by_person() if p["name"] != NO_PERSON]
        if people:
            out.append(f"أكثر شخص مرتبط بمصاريفك: {people[0]['name']} ({money.fmt(people[0]['total'], self.currency)}).")
        if tot["savings_rate"] is not None:
            if tot["savings_rate"] >= 0:
                out.append(f"ادخرت {tot['savings_rate']}% من دخلك.")
            else:
                out.append(f"صرفت أكثر من دخلك بنسبة {abs(tot['savings_rate'])}%.")
        if tot["expense_count"] > 2 and tot["median_tx"]:
            out.append(f"نصف مصاريفك أقل من {money.fmt(tot['median_tx'], self.currency)}.")
        return out
