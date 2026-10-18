"""View-models: turn repo/stats data into display-ready values (strings, tones, ids).

Pure Python (no Flet), so all of it is unit-tested. The Flet screens only render these.
"""
import calendar
from datetime import date as _date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .. import money
from ..stats import MONTH_NAMES, Stats, month_label, pct_change, shift_month

TONE_INCOME, TONE_EXPENSE, TONE_NEUTRAL = "income", "expense", "neutral"
KIND_LABELS = {"expense": "مصروف", "income": "دخل", "transfer": "تحويل"}
PERIODS = [("all", "الكل"), ("today", "اليوم"), ("7d", "آخر 7 أيام"), ("month", "هذا الشهر"),
           ("last_month", "الشهر الماضي"), ("year", "هذه السنة")]


# ------------------------------------------------------------------ dates
def day_label(date_str: str, today: str) -> str:
    d, t = _date.fromisoformat(date_str), _date.fromisoformat(today)
    diff = (t - d).days
    if diff == 0:
        return "اليوم"
    if diff == 1:
        return "أمس"
    if diff == 2:
        return "قبل يومين"
    return f"{d.day} {MONTH_NAMES[d.month - 1]}" + ("" if d.year == t.year else f" {d.year}")


def period_range(key: str, today: str) -> tuple:
    """(date_from, date_to) for a period chip; (None, None) means no limit."""
    t = _date.fromisoformat(today)
    if key == "today":
        return today, today
    if key == "7d":
        return (t - timedelta(days=6)).isoformat(), today
    if key == "month":
        return t.replace(day=1).isoformat(), today
    if key == "last_month":
        ym = shift_month(today[:7], -1)
        return f"{ym}-01", f"{ym}-{calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]:02d}"
    if key == "year":
        return f"{t.year}-01-01", today
    return None, None


def relative_date(choice: str, today: str) -> str:
    """'today' | 'yesterday' | 'two_days' -> ISO date (used by the Add sheet chips)."""
    back = {"today": 0, "yesterday": 1, "two_days": 2}[choice]
    return (_date.fromisoformat(today) - timedelta(days=back)).isoformat()


# ----------------------------------------------------------------- numbers
def compact(minor: int, cur: str) -> str:
    """Short label for charts: 1,250,000 -> '1.3M', 85,000 -> '85k'."""
    v = money.from_minor(minor, cur)
    for limit, suffix in ((1_000_000, "M"), (1_000, "k")):
        if abs(v) >= limit:
            n = (v / limit).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            return f"{n:f}".rstrip("0").rstrip(".") + suffix
    return f"{v:f}".rstrip("0").rstrip(".") if "." in f"{v:f}" else f"{v:f}"


def delta_chip(delta: Optional[int], good_up: bool) -> dict:
    """% change -> {'text', 'tone'}; tone: good | bad | neutral (expense going up is bad)."""
    if delta is None:
        return {"text": "جديد", "tone": "neutral"}
    if delta == 0:
        return {"text": "0%", "tone": "neutral"}
    good = (delta > 0) == good_up
    return {"text": ("▲ " if delta > 0 else "▼ ") + f"{abs(delta)}%", "tone": "good" if good else "bad"}


# --------------------------------------------------------- transaction rows
def tx_row(t: dict, today: str) -> dict:
    """One transaction -> everything a list row needs."""
    cur = t["currency"]
    if t["kind"] == "transfer":
        recv = ""
        if t["to_currency"] != cur:
            recv = money.fmt(t["to_amount"], t["to_currency"])
        return {
            "id": t["id"], "kind": "transfer", "date": t["date"], "date_label": day_label(t["date"], today),
            "title": f"تحويل: {t['wallet_name']} ← {t['to_wallet_name']}",
            "subtitle": f"بسعر {t['rate']:g}" if t["rate"] else "نفس العملة",
            "note": t["note"], "amount_text": money.fmt(t["amount"], cur, symbol=cur == "USD"),
            "recv_text": recv, "tone": TONE_NEUTRAL, "icon": "swap_horiz", "color": "#2B4C9B",
        }
    sign, tone = ("+", TONE_INCOME) if t["kind"] == "income" else ("−", TONE_EXPENSE)
    if t["category_name"]:
        title = (f"{t['parent_category_name']} › {t['category_name']}" if t["parent_category_name"]
                 else t["category_name"])
    else:
        title = KIND_LABELS[t["kind"]]
    sub = t["wallet_name"] + (f" · {t['person_name']}" if t["person_name"] else "")
    return {
        "id": t["id"], "kind": t["kind"], "date": t["date"], "date_label": day_label(t["date"], today),
        "title": title, "subtitle": sub, "note": t["note"],
        "amount_text": sign + money.fmt(t["amount"], cur, symbol=cur == "USD"),
        "recv_text": "", "tone": tone,
        "icon": t["category_icon"] or ("south" if t["kind"] == "income" else "north"),
        "color": t["category_color"] or "#8A9A95",
    }


def group_by_day(rows: list) -> list:
    """[{'label', 'rows': [...]}] keeping order, one group per date."""
    groups = []
    for r in rows:
        if not groups or groups[-1]["date"] != r["date"]:
            groups.append({"date": r["date"], "label": r["date_label"], "rows": []})
        groups[-1]["rows"].append(r)
    return groups


# -------------------------------------------------------------------- home
def home(repo, currency: str, today: str) -> dict:
    st = Stats(repo, currency, today=today)
    ym = today[:7]
    ov = st.totals(ym)
    other = "USD" if currency == "IQD" else "IQD"
    total = repo.total_balance(currency)
    rate = repo.get_rate()
    return {
        "currency": currency,
        "month_label": month_label(ym),
        "total_text": money.fmt(total, currency, symbol=False),
        "unit": money.SYMBOLS[currency],
        "equiv_text": f"يعادل {money.fmt(repo.total_balance(other), other)} بسعر {rate:,.0f}",
        "income_text": "+" + money.fmt(ov["income"], currency, symbol=False),
        "expense_text": "−" + money.fmt(ov["expense"], currency, symbol=False),
        "wallets": [{"id": w["id"], "name": w["name"], "currency": w["currency"],
                     "balance_text": money.fmt(w["balance"], w["currency"]), "hide_balance": bool(w["hide_balance"])}
                    for w in repo.balances()],
        "recent": [tx_row(t, today) for t in repo.list_transactions(limit=5)],
    }


# ------------------------------------------------------------------- stats
def stats_overview(st: Stats, ym: str) -> dict:
    ov, cur = st.overview(ym), st.currency
    f = lambda v: money.fmt(v, cur, symbol=False)  # noqa: E731
    net = ov["net"]
    biggest = ov["biggest"]
    inc, exp, avg = (delta_chip(ov["income_delta"], True), delta_chip(ov["expense_delta"], False),
                     delta_chip(ov["avg_daily_delta"], False))
    rate = ov["savings_rate"]
    kpis = [
        {"label": "الدخل", "value": "+" + f(ov["income"]), "tone": TONE_INCOME, "chip": inc, "chip_suffix": "عن الماضي"},
        {"label": "المصروف", "value": "−" + f(ov["expense"]), "tone": TONE_EXPENSE, "chip": exp, "chip_suffix": "عن الماضي"},
        {"label": "الصافي", "value": ("+" if net >= 0 else "−") + f(abs(net)),
         "tone": TONE_INCOME if net >= 0 else TONE_EXPENSE,
         "chip": {"text": "الماضي: " + ("+" if ov["prev"]["net"] >= 0 else "−") + f(abs(ov["prev"]["net"])), "tone": "neutral"},
         "chip_suffix": ""},
        {"label": "نسبة الادخار", "value": "—" if rate is None else f"{rate}%", "tone": TONE_NEUTRAL,
         "chip": {"text": "ممتازة" if rate is not None and rate >= 20 else "حاول تزيدها",
                  "tone": "good" if rate is not None and rate >= 20 else "warn"}, "chip_suffix": ""},
        {"label": "متوسط الصرف اليومي", "value": f(ov["avg_daily"]), "tone": TONE_NEUTRAL, "chip": avg, "chip_suffix": "عن الماضي"},
        {"label": "أكبر مصروف", "value": f(biggest["converted"]) if biggest else "—", "tone": TONE_NEUTRAL,
         "chip": {"text": (biggest["category_name"] or "بدون فئة") if biggest else "لا يوجد", "tone": "neutral"}, "chip_suffix": ""},
    ]
    series = st.series(ym, 6)
    top = max([max(s["income"], s["expense"]) for s in series] + [1])
    bars = [{"month": s["month"], "label": s["label"], "income": s["income"], "expense": s["expense"],
             "income_h": s["income"] / top, "expense_h": s["expense"] / top,
             "selected": s["month"] == ym} for s in series]
    cur_bar = next(b for b in bars if b["selected"])
    spent = ov["spent_pct"]
    return {
        "month": ym, "label": ov["label"], "kpis": kpis, "bars": bars,
        "bar_summary": f"{MONTH_NAMES[int(ym[5:7]) - 1]}: دخل {f(cur_bar['income'])} · مصروف {f(cur_bar['expense'])}",
        "spent_pct": spent, "spent_fraction": min(1.0, (spent or 0) / 100),
        "spent_note": (f"صرفت {f(ov['expense'])} من أصل دخل {f(ov['income'])} {money.SYMBOLS[cur]}"
                       if ov["income"] else "لا يوجد دخل مسجّل لهذا الشهر"),
        "spent_warn": spent is not None and spent > 90,
        "insights": st.insights(ym),
    }


def stats_categories(st: Stats, ym: str, kind: str) -> dict:
    cur = st.currency
    cats = st.categories(ym, kind)
    total = sum(c["total"] for c in cats)
    return {
        "total_text": money.fmt(total, cur, symbol=False), "unit": money.SYMBOLS[cur], "empty": not cats,
        "slices": [{"name": c["name"], "value": c["total"], "color": c["color"] or "#8A9A95"} for c in cats],
        "rows": [{"name": c["name"], "color": c["color"] or "#8A9A95", "amount_text": money.fmt(c["total"], cur, symbol=False),
                  "pct": c["pct"], "chip": delta_chip(c["delta"], kind == "income"),
                  "children": [{"name": ch["name"], "amount_text": money.fmt(ch["total"], cur, symbol=False), "pct": ch["pct"]}
                               for ch in c["children"]]} for c in cats],
    }


def stats_people(st: Stats, ym: str) -> dict:
    cur = st.currency
    people, wallets = st.by_person(ym), st.by_wallet(ym)
    pmax = max([p["total"] for p in people] + [1])
    wmax = max([w["total"] for w in wallets] + [1])
    return {
        "empty": not people,
        "people": [{"name": p["name"], "count": p["count"], "amount_text": money.fmt(p["total"], cur, symbol=False),
                    "fraction": p["total"] / pmax} for p in people],
        "wallets": [{"name": w["name"], "amount_text": money.fmt(w["total"], cur, symbol=False),
                     "fraction": w["total"] / wmax} for w in wallets],
    }


def stats_patterns(st: Stats, ym: str, today: str) -> dict:
    cur = st.currency
    wd = st.weekdays(ym)
    top = max([d["total"] for d in wd["days"]] + [1])
    tot = st.totals(ym)
    return {
        "peak": wd["peak"],
        "days": [{"name": d["name"].replace("ال", "", 1), "label": compact(d["total"], cur) if d["total"] else "",
                  "fraction": d["total"] / top, "peak": d["name"] == wd["peak"]} for d in wd["days"]],
        "kpis": [{"label": "عدد المعاملات", "value": str(tot["count"])},
                 {"label": "متوسط المعاملة", "value": money.fmt(tot["avg_tx"], cur, symbol=False) if tot["count"] else "—"},
                 {"label": "أكثر يوم صرفاً", "value": wd["peak"] or "—"},
                 {"label": "أعلى فئة", "value": (st.categories(ym) or [{"name": "—"}])[0]["name"]}],
        "top": [{"rank": i + 1, "title": (f"{t['parent_category_name']} › {t['category_name']}" if t["parent_category_name"]
                                          else (t["category_name"] or "بدون فئة")),
                 "subtitle": day_label(t["date"], today) + (f" · {t['note']}" if t["note"] else ""),
                 "amount_text": "−" + money.fmt(t["converted"], cur, symbol=False)}
                for i, t in enumerate(st.top_expenses(ym, 5))],
    }


# ============================================================ merged Transactions screen
import calendar as _cal  # noqa: E402

from ..analysis import Analysis  # noqa: E402


def is_filtered(f: dict, search: str = "") -> bool:
    """True when anything narrows the list (sorting alone does not count)."""
    return bool(f["kinds"] or f["wallets"] or f["categories"] or f["people"] or f["period"] != "all"
                or f["date_from"] or f["date_to"] or f["min"] or f["max"] or (search or "").strip())


def month_bounds(ym: str, today: str) -> tuple:
    last = _cal.monthrange(int(ym[:4]), int(ym[5:7]))[1]
    return f"{ym}-01", f"{ym}-{last:02d}"


def scope_rows(repo, f: dict, search: str, today: str, ym: str, all_time: bool = False) -> dict:
    """Rows + period for the Transactions screen. No filter -> the selected month; any filter -> the filtered set."""
    filtered = is_filtered(f, search)
    if not filtered and all_time:
        return {"filtered": False, "all_time": True, "rows": repo.list_transactions(order=f["order"]), "span": None, "month": None}
    if not filtered:
        d_from, d_to = month_bounds(ym, today)
        rows = repo.list_transactions(date_from=d_from, date_to=d_to, order=f["order"])
        end = min(d_to, today) if d_from <= today else d_to
        return {"filtered": False, "rows": rows, "span": (d_from, max(d_from, end)), "month": ym}
    d_from, d_to = f["date_from"] or None, f["date_to"] or None
    if f["period"] != "all":
        d_from, d_to = period_range(f["period"], today)
    rows = repo.list_transactions(
        kinds=sorted(f["kinds"]) or None, wallet_ids=sorted(f["wallets"]) or None,
        category_ids=sorted(f["categories"]) or None, exclude_categories=f["exclude_categories"],
        person_ids=sorted(f["people"]) or None, date_from=d_from, date_to=d_to,
        min_amount=money.parse_input(f["min"]) or None, max_amount=money.parse_input(f["max"]) or None,
        text=(search or "").strip() or None, order=f["order"])
    return {"filtered": True, "rows": rows, "span": (d_from, d_to) if d_from and d_to else None, "month": None}


def analysis_for(repo, scope: dict, currency: str) -> tuple:
    """(Analysis, previous-month Analysis or None)."""
    rate = repo.get_rate()
    an = Analysis(scope["rows"], currency, rate, scope["span"])
    prev = None
    if not scope["filtered"] and scope.get("month"):
        pm = shift_month(scope["month"], -1)
        a, b = month_bounds(pm, "")
        prev = Analysis(repo.list_transactions(date_from=a, date_to=b), currency, rate, (a, b))
    return an, prev


def scope_and_analysis(ui) -> tuple:
    """(scope, Analysis, previous Analysis). Read-only contexts (history archives, `ui.cacheable`) keep the last
    result per (filters, search, month, period, currency) so switching sub-tabs or re-rendering costs nothing."""
    all_time = bool(getattr(ui, "all_time", False))

    def compute():
        scope = scope_rows(ui.repo, ui.filters, ui.search, ui.today, ui.stats_ym, all_time)
        return (scope, *analysis_for(ui.repo, scope, ui.currency))

    if not getattr(ui, "cacheable", False):
        return compute()
    f = ui.filters
    key = (tuple(sorted((k, tuple(sorted(v)) if isinstance(v, (set, list)) else v) for k, v in f.items())),
           ui.search, ui.stats_ym, all_time, ui.currency)
    cache = ui.__dict__.setdefault("_scope_cache", {})
    if key not in cache:
        cache.clear()  # keep only the latest (an archive scope can be tens of thousands of rows)
        cache[key] = compute()
    return cache[key]


def _f(v, cur):
    return money.fmt(v, cur, symbol=False)


def strip_view(an: Analysis, filtered_kinds: set) -> dict:
    t, cur = an.totals(), an.currency
    return {"income": "+" + _f(t["income"], cur), "expense": "−" + _f(t["expense"], cur),
            "net": ("+" if t["net"] >= 0 else "−") + _f(abs(t["net"]), cur), "net_good": t["net"] >= 0,
            "unit": money.SYMBOLS[cur], "show_income": not filtered_kinds or "income" in filtered_kinds,
            "show_expense": not filtered_kinds or "expense" in filtered_kinds}


def summary_view(an: Analysis, prev) -> dict:
    t, cur = an.totals(), an.currency
    cmp_ = an.compare(prev) if prev else None
    chip = (lambda d, up: delta_chip(d, up)) if cmp_ else (lambda d, up: None)
    kp = []
    kp.append({"label": "الدخل", "value": "+" + _f(t["income"], cur), "tone": "income",
               "chip": chip(cmp_ and cmp_["income"], True), "suffix": "عن الماضي"})
    kp.append({"label": "المصروف", "value": "−" + _f(t["expense"], cur), "tone": "expense",
               "chip": chip(cmp_ and cmp_["expense"], False), "suffix": "عن الماضي"})
    kp.append({"label": "الصافي", "value": ("+" if t["net"] >= 0 else "−") + _f(abs(t["net"]), cur),
               "tone": "income" if t["net"] >= 0 else "expense", "chip": None, "suffix": ""})
    rate = t["savings_rate"]
    kp.append({"label": "نسبة الادخار", "value": "—" if rate is None else f"{rate}%", "tone": "neutral",
               "chip": None if rate is None else {"text": "ممتازة" if rate >= 20 else "حاول تزيدها",
                                                  "tone": "good" if rate >= 20 else "warn"}, "suffix": ""})
    kp.append({"label": "متوسط الصرف اليومي", "value": _f(t["avg_daily"], cur), "tone": "neutral",
               "chip": chip(cmp_ and cmp_["avg_daily"], False), "suffix": "عن الماضي"})
    kp.append({"label": "متوسط المعاملة", "value": _f(t["avg_tx"], cur) if t["expense_count"] else "—", "tone": "neutral",
               "chip": None, "suffix": ""})
    kp.append({"label": "الوسيط (النصف الأوسط)", "value": _f(t["median_tx"], cur) if t["expense_count"] else "—",
               "tone": "neutral", "chip": None, "suffix": ""})
    b = t["biggest"]
    kp.append({"label": "أكبر مصروف", "value": _f(b["converted"], cur) if b else "—", "tone": "neutral",
               "chip": {"text": (b["category_name"] or "بدون فئة"), "tone": "neutral"} if b else None, "suffix": ""})
    tl = an.timeline()
    top = max([max(p["income"], p["expense"]) for p in tl["points"]] + [1])
    pts = [{"label": p["label"], "income_h": p["income"] / top, "expense_h": p["expense"] / top,
            "income": p["income"], "expense": p["expense"]} for p in tl["points"]]
    spent = t["spent_pct"]
    return {
        "kpis": kp, "timeline": {"mode": tl["mode"], "points": pts, "title": "الحركة اليومية" if tl["mode"] == "day" else "الحركة الشهرية"},
        "spent_pct": spent, "spent_fraction": min(1.0, (spent or 0) / 100), "spent_warn": spent is not None and spent > 90,
        "spent_note": (f"صرفت {_f(t['expense'], cur)} من أصل دخل {_f(t['income'], cur)} {money.SYMBOLS[cur]}"
                       if t["income"] else "لا يوجد دخل في هذه الفترة"),
        "insights": an.insights(), "empty": not an.items,
    }


def categories_view(an: Analysis, prev, kind: str) -> dict:
    cur = an.currency
    cats = an.categories(kind, prev)
    total = sum(c["total"] for c in cats)
    return {
        "empty": not cats, "total_text": _f(total, cur), "unit": money.SYMBOLS[cur],
        "slices": [{"name": c["name"], "value": c["total"], "color": c["color"] or "#8A9A95"} for c in cats],
        "rows": [{"name": c["name"], "color": c["color"] or "#8A9A95", "amount_text": _f(c["total"], cur),
                  "pct": c["pct"], "count": c["count"],
                  "chip": delta_chip(c["delta"], kind == "income") if prev is not None else None,
                  "children": [{"name": ch["name"], "amount_text": _f(ch["total"], cur), "pct": ch["pct"]}
                               for ch in c["children"]]} for c in cats],
    }


def analysis_view(an: Analysis, today: str) -> dict:
    cur = an.currency
    hist = an.histogram()
    hmax = max([b["count"] for b in hist] + [1])
    wd = an.weekdays()
    wtop = max([d["total"] for d in wd["days"]] + [1])
    people, wallets = an.by_person(), an.by_wallet()
    pmax, wmax = max([p["total"] for p in people] + [1]), max([w["total"] for w in wallets] + [1])
    return {
        "histogram": [{"label": compact(b["hi"], cur), "range": f"{compact(b['lo'], cur)}–{compact(b['hi'], cur)}",
                       "count": b["count"], "fraction": b["count"] / hmax, "total_text": _f(b["total"], cur)} for b in hist],
        "weekdays": [{"label": d["name"].replace("ال", "", 1), "top": compact(d["total"], cur) if d["total"] else "",
                      "fraction": d["total"] / wtop, "peak": d["name"] == wd["peak"]} for d in wd["days"]],
        "people": [{"name": p["name"], "count": p["count"], "amount_text": _f(p["total"], cur),
                    "fraction": p["total"] / pmax, "pct": p["pct"]} for p in people],
        "wallets": [{"name": w["name"], "amount_text": _f(w["total"], cur), "fraction": w["total"] / wmax,
                     "pct": w["pct"]} for w in wallets],
        "top": [{"rank": i + 1, "title": (f"{t['parent_category_name']} › {t['category_name']}" if t["parent_category_name"]
                                          else (t["category_name"] or "بدون فئة")),
                 "subtitle": day_label(t["date"], today) + (f" · {t['note']}" if t["note"] else ""),
                 "amount_text": "−" + _f(t["converted"], cur)} for i, t in enumerate(an.top_expenses(5))],
        "empty": not an.of("expense"),
    }
