"""Transactions tab = list + statistics in one place.

No filter  -> the selected month (month navigator).
Any filter -> exactly the filtered rows, for the list AND every chart.
Sub-tabs: list | summary | categories | analysis. A summary strip is always visible.
"""
import flet as ft

from . import kit, theme as T, vm
from .rows import empty_state, tx_tile
from ..stats import month_label, shift_month

QUICK_KINDS = [("expense", "مصروف"), ("income", "دخل"), ("transfer", "تحويل")]
ORDERS = [("newest", "الأحدث"), ("oldest", "الأقدم"), ("highest", "الأعلى مبلغاً"), ("lowest", "الأقل مبلغاً")]
VIEWS = [("list", "المعاملات"), ("summary", "ملخص"), ("cats", "الفئات"), ("analysis", "تحليل")]


def card(title, *items, sub=None):
    head = [kit.txt(title, 15, True)] + ([kit.txt(sub, 12, color=T.MUTED)] if sub else [])
    return kit.box(kit.col([kit.col(head, spacing=2), *items], spacing=12), padding=16)


def legend_dot(color, label):
    return kit.row([ft.Container(width=10, height=10, bgcolor=color, border_radius=3), kit.txt(label, 12, color=T.MUTED)],
                   spacing=5)


def hbar(label, amount, fraction, color, width, sub=""):
    return kit.col([kit.between(kit.row([kit.txt(label, 14, True), kit.txt(sub, 12, color=T.MUTED)], spacing=6),
                                kit.txt(amount, 14, True)),
                    kit.progress(fraction, color, width)], spacing=5)


# ------------------------------------------------------------------ pieces
def header_controls(ui, scope, an):
    f = ui.filters

    def on_search(e):
        ui.search = e.control.value

    search = ft.TextField(
        value=ui.search, hint_text="ابحث بالملاحظة أو الفئة أو الشخص", on_change=on_search,
        on_submit=lambda e: ui.refresh(), prefix_icon=kit.icon_name("search"), border_radius=14, border_color=T.LINE,
        bgcolor=T.CARD, filled=True, text_size=14, content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
        expand=True)
    n = ui.filters_active()
    filt_btn = ft.Container(
        content=kit.row([kit.icon("tune", 20, "#FFFFFF" if n else T.INK),
                         kit.txt(f"فلتر{f' ({n})' if n else ''}", 13, True, "#FFFFFF" if n else T.INK)], spacing=4),
        padding=ft.padding.symmetric(horizontal=12, vertical=11), border_radius=14, ink=True,
        bgcolor=T.PRIMARY if n else T.CARD, border=ft.border.all(1, T.PRIMARY if n else T.LINE),
        on_click=lambda e: open_filter_sheet(ui))

    def toggle_kind(k):
        f["kinds"] ^= {k}
        ui.refresh()

    def clear(e):
        ui.filters = ui.default_filters()
        ui.search = ""
        ui.refresh()

    chips = [kit.chip(label, k in f["kinds"], lambda e, k=k: toggle_kind(k)) for k, label in QUICK_KINDS]
    if scope["filtered"]:
        chips.append(kit.chip("مسح الفلاتر", False, clear, color=T.EXPENSE))
    return [kit.row([search, filt_btn], spacing=8), kit.hscroll(chips, 8)]


def scope_bar(ui, scope):
    if scope["filtered"]:
        f = ui.filters
        per = dict(vm.PERIODS).get(f["period"], "")
        if f["date_from"] or f["date_to"]:
            per = f"{f['date_from'] or '…'} ← {f['date_to'] or '…'}"
        txt = "نتائج الفلتر" + (f" · {per}" if per and f["period"] != "all" or f["date_from"] or f["date_to"] else " · كل الفترات")
        return kit.box(kit.row([kit.icon("filter_alt", 20, T.PRIMARY), kit.txt(txt, 14, True, T.PRIMARY)], spacing=8),
                       bg=T.PRIMARY_SOFT, border=None, padding=12)

    ym = ui.stats_ym
    if scope.get("all_time"):
        return kit.box(kit.row([kit.icon("history", 20, T.PRIMARY), kit.txt("كل بيانات الأرشيف", 14, True, T.PRIMARY)], spacing=8),
                       bg=T.PRIMARY_SOFT, border=None, padding=12)

    def move(d):
        ui.stats_ym = shift_month(ym, d)
        ui.stats_open_cat = None
        ui.refresh()

    return kit.between(kit.icon_btn("chevron_right", lambda e: move(-1)),
                       ft.Container(kit.txt(month_label(ym), 17, True), ink=True, border_radius=8,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                    on_click=lambda e: (setattr(ui, "stats_ym", ui.today[:7]), ui.refresh())),
                       kit.icon_btn("chevron_left", lambda e: move(1)))


def summary_strip(ui, an):
    v = vm.strip_view(an, ui.filters["kinds"])

    def cell(label, value, color):
        return ft.Container(kit.col([kit.txt(label, 12, color=T.HERO_TEXT), kit.txt(value, 16, True, color)], spacing=3),
                            expand=True)

    cells = []
    if v["show_income"]:
        cells.append(cell("دخل", v["income"], T.MINT))
    if v["show_expense"]:
        cells.append(cell("مصروف", v["expense"], "#FFB4A8"))
    if v["show_income"] and v["show_expense"]:
        cells.append(cell("الصافي", v["net"], "#FFFFFF" if v["net_good"] else "#FFB4A8"))
    return ft.Container(kit.row(cells, spacing=8), bgcolor=T.HERO, border_radius=18, padding=ft.padding.symmetric(horizontal=16, vertical=12))


# ---------------------------------------------------------------- sub-views
PAGE_FIRST, PAGE_NEXT = 40, 80


def view_list(ui, scope):
    """Rows are rendered in batches (40, then +80 per 'show more' tap) - a Flet control per row is expensive,
    and an old archive can hold tens of thousands of transactions."""
    all_rows = scope["rows"]
    if not all_rows:
        return [empty_state("لا توجد معاملات مطابقة")]
    holder = ft.Column(spacing=12)
    state = {"n": 0, "last": None}

    def more_button():
        left = len(all_rows) - state["n"]
        return ft.Container(
            kit.big_button(f"عرض المزيد ({left} متبقية)", lambda e: load(PAGE_NEXT), outline=True), padding=ft.padding.only(top=6))

    def load(count):
        batch = [vm.tx_row(t, ui.today) for t in all_rows[state["n"]:state["n"] + count]]
        state["n"] += len(batch)
        if holder.controls and getattr(holder.controls[-1], "data", None) == "more":
            holder.controls.pop()
        for g in vm.group_by_day(batch):
            if g["label"] != state["last"]:
                holder.controls.append(kit.txt(g["label"], 13, True, T.MUTED))
                state["last"] = g["label"]
            holder.controls.append(kit.box(kit.col([tx_tile(ui, r) for r in g["rows"]], spacing=0),
                                           padding=ft.padding.symmetric(horizontal=12, vertical=4)))
        if state["n"] < len(all_rows):
            btn = more_button()
            btn.data = "more"
            holder.controls.append(btn)
        if count != PAGE_FIRST:
            ui.page.update()

    load(PAGE_FIRST)
    return [kit.txt(f"{len(all_rows)} معاملة", 12, color=T.MUTED), holder]


def view_summary(ui, an, prev):
    d = vm.summary_view(an, prev)
    if d["empty"]:
        return [empty_state("لا توجد بيانات في هذه الفترة")]
    kw = (ui.w - 40 - 10) / 2
    cards = []
    for k in d["kpis"]:
        color = {"income": T.INCOME, "expense": T.EXPENSE}.get(k["tone"], T.INK)
        items = [kit.txt(k["label"], 12, color=T.MUTED), kit.txt(k["value"], 17, True, color)]
        if k["chip"]:
            items.append(kit.row([kit.badge(k["chip"]["text"], k["chip"]["tone"]), kit.txt(k["suffix"], 11, color=T.FAINT)], spacing=4))
        cards.append(kit.box(kit.col(items, spacing=4), width=kw))
    grid = [kit.row(cards[i:i + 2], spacing=10) for i in range(0, len(cards), 2)]
    tl = d["timeline"]
    n = len(tl["points"])
    pts = [{"label": p["label"] if tl["mode"] == "day" else p["label"][:4], "top": "",
            "bars": [(p["income_h"], T.CHART_INCOME), (p["expense_h"], T.CHART_EXPENSE)]} for p in tl["points"]]
    chart = kit.columns_chart(pts, ui.w - 40 - 32, 110, label_every=5 if tl["mode"] == "day" and n > 10 else (2 if n > 8 else 1))
    spent_color = T.EXPENSE if d["spent_warn"] else T.PRIMARY
    out = grid + [
        card(tl["title"], chart, kit.row([legend_dot(T.CHART_INCOME, "دخل"), legend_dot(T.CHART_EXPENSE, "مصروف")], spacing=14)),
        card("نسبة المصروف من الدخل",
             kit.between(kit.txt("—" if d["spent_pct"] is None else f"{d['spent_pct']}%", 22, True, spent_color), kit.txt("", 1)),
             kit.progress(d["spent_fraction"], spent_color, ui.w - 40 - 32, 10),
             kit.txt(d["spent_note"], 12, color=T.MUTED)),
    ]
    if d["insights"]:
        out.append(card("ملاحظات ذكية", *[kit.row([kit.icon("lightbulb", 18, T.PRIMARY), kit.txt(i, 14, expand=True)], spacing=8,
                                                  v_align=ft.CrossAxisAlignment.START) for i in d["insights"]]))
    return out


def view_cats(ui, an, prev):
    d = vm.categories_view(an, prev, ui.stats_kind)

    def set_kind(k):
        ui.stats_kind = k
        ui.stats_open_cat = None
        ui.refresh()

    top = kit.segmented([("expense", "المصاريف"), ("income", "الدخل")], ui.stats_kind, set_kind)
    if d["empty"]:
        return [top, empty_state("لا توجد بيانات")]
    donut = ft.Stack([kit.donut(d["slices"], size=190, hole=60),
                      ft.Container(kit.col([kit.txt(d["total_text"], 17, True), kit.txt(d["unit"], 11, color=T.MUTED)],
                                           spacing=0, h_align=ft.CrossAxisAlignment.CENTER),
                                   alignment=ft.alignment.center, width=190, height=190)], width=190, height=190)
    width = ui.w - 40 - 32
    rows = []
    for r in d["rows"]:
        def toggle(e, name=r["name"]):
            ui.stats_open_cat = None if ui.stats_open_cat == name else name
            ui.refresh()

        parts = [kit.between(kit.row([ft.Container(width=12, height=12, bgcolor=r["color"], border_radius=4),
                                      kit.txt(r["name"], 14, True), kit.txt(f"{r['pct']}%", 12, color=T.MUTED)], spacing=8),
                             kit.txt(r["amount_text"], 14, True)),
                 kit.progress(r["pct"] / 100, r["color"], width)]
        if r["chip"]:
            parts.append(kit.row([kit.badge(r["chip"]["text"], r["chip"]["tone"]), kit.txt("عن الشهر الماضي", 11, color=T.FAINT)], spacing=4))
        if ui.stats_open_cat == r["name"]:
            parts += [kit.between(kit.txt("— " + c["name"], 13, color=T.MUTED), kit.txt(f"{c['amount_text']}  ({c['pct']}%)", 13, color=T.MUTED))
                      for c in r["children"]]
        rows.append(ft.Container(kit.col(parts, spacing=6), ink=bool(r["children"]), border_radius=10, padding=4,
                                 on_click=toggle if r["children"] else None))
    return [top, kit.box(ft.Container(donut, alignment=ft.alignment.center), padding=16),
            card("التفصيل", *rows, sub="اضغط على فئة لعرض الفرعية")]


def view_analysis(ui, an):
    d = vm.analysis_view(an, ui.today)
    if d["empty"]:
        return [empty_state("لا توجد مصاريف في هذه الفترة")]
    W = ui.w - 40 - 32
    out = []
    hist = [{"label": b["label"], "top": str(b["count"]) if b["count"] else "", "bars": [(b["fraction"], T.CHART_INCOME)]}
            for b in d["histogram"]]
    out.append(card("توزيع حجم المصاريف (هستوغرام)", kit.columns_chart(hist, W, 120),
                    kit.txt("كل عمود = عدد المعاملات ضمن نطاق مبلغ، والرقم تحته هو الحد الأعلى للنطاق", 11, color=T.MUTED)))
    wd = [{"label": x["label"], "top": x["top"], "bars": [(x["fraction"], T.CHART_EXPENSE if x["peak"] else T.SERIES[0])]}
          for x in d["weekdays"]]
    out.append(card("الصرف حسب أيام الأسبوع", kit.columns_chart(wd, W, 100)))
    if d["people"]:
        out.append(card("حسب الشخص", *[hbar(p["name"], p["amount_text"], p["fraction"], T.CHART_INCOME, W, f"{p['count']} · {p['pct']}%")
                                       for p in d["people"]]))
    out.append(card("حسب المحفظة", *[hbar(w["name"], w["amount_text"], w["fraction"], T.CHART_EXPENSE, W, f"{w['pct']}%")
                                     for w in d["wallets"]]))
    top = [kit.row([kit.txt(str(t["rank"]), 15, True, T.MUTED),
                    kit.col([kit.txt(t["title"], 14, True), kit.txt(t["subtitle"], 12, color=T.MUTED)], spacing=2, expand=True),
                    kit.txt(t["amount_text"], 14, True, T.EXPENSE)], spacing=10) for t in d["top"]]
    out.append(card("أكبر 5 مصاريف", *top))
    return out


# ------------------------------------------------------------------ screen
def build_txs(ui):
    scope, an, prev = vm.scope_and_analysis(ui)

    def set_cur(c):
        ui.currency = c
        ui.refresh()

    def set_view(v):
        ui.tx_view = v
        ui.refresh()

    body = {"list": lambda: view_list(ui, scope), "summary": lambda: view_summary(ui, an, prev),
            "cats": lambda: view_cats(ui, an, prev), "analysis": lambda: view_analysis(ui, an)}[ui.tx_view]()
    period_seg = []
    if getattr(ui, "allow_all_time", False):
        def set_all(v):
            ui.all_time = v
            ui.refresh()
        period_seg = [kit.segmented([(False, "حسب الشهر"), (True, "كل الفترة")], bool(getattr(ui, "all_time", False)), set_all)]
    head = kit.col([
        kit.between(kit.txt(getattr(ui, "title", "المعاملات"), 24, True), ft.Container(kit.segmented([("IQD", "دينار"), ("USD", "دولار")], ui.currency, set_cur), width=150)),
        *header_controls(ui, scope, an),
        *period_seg,
        scope_bar(ui, scope),
        summary_strip(ui, an),
        kit.segmented(VIEWS, ui.tx_view, set_view),
    ], spacing=10)
    return ft.Container(
        kit.col([head, kit.col(body + [ft.Container(height=90)], spacing=12, scroll=True, expand=True)], spacing=12, expand=True),
        padding=ft.padding.only(left=20, right=20, top=20), expand=True)


def open_filter_sheet(ui):
    repo = ui.repo
    f = {k: (set(v) if isinstance(v, set) else v) for k, v in ui.filters.items()}  # working copy
    body = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    mn, mx = kit.field("من مبلغ", f["min"], thousands=True, expand=True), kit.field("إلى مبلغ", f["max"], thousands=True, expand=True)
    d1 = kit.DateInput(ui, "من تاريخ", f["date_from"], clearable=True)
    d2 = kit.DateInput(ui, "إلى تاريخ", f["date_to"], clearable=True)
    ref = {}

    def tog(key, value):
        f[key] ^= {value}
        render()

    def setv(key, value):
        f[key] = value
        render()

    def group(title, chips):
        return [kit.txt(title, 13, True, T.MUTED), ft.Row(chips, wrap=True, spacing=8, run_spacing=8)]

    def render():
        cats, subs = [], []
        for kind in ("expense", "income"):
            for c in repo.category_tree(kind):
                cats.append(kit.chip(c["name"], c["id"] in f["categories"], lambda e, i=c["id"]: tog("categories", i),
                                     color=c["color"] or T.PRIMARY))
                if c["id"] in f["categories"] and c["children"]:
                    subs += group(f"فرعيات «{c['name']}»", [
                        kit.chip(ch["name"], ch["id"] in f["categories"], lambda e, i=ch["id"]: tog("categories", i), color=T.MUTED)
                        for ch in c["children"]])
        body.controls = (
            [kit.txt("فلتر متقدم", 20, True)]
            + group("النوع", [kit.chip(l, k in f["kinds"], lambda e, k=k: tog("kinds", k)) for k, l in QUICK_KINDS])
            + group("الفترة", [kit.chip(l, f["period"] == k, lambda e, k=k: setv("period", k)) for k, l in vm.PERIODS])
            + [d1.control, d2.control]
            + group("المحفظة", [kit.chip(w["name"], w["id"] in f["wallets"], lambda e, i=w["id"]: tog("wallets", i))
                                for w in repo.list_wallets()])
            + group("الفئة (الرئيسية تشمل فرعياتها)", cats) + subs
            + [kit.row([kit.txt("استثناء الفئات المحددة (كل شي ما عدا)", 13, expand=True),
                        ft.Switch(value=f["exclude_categories"], on_change=lambda e: setv("exclude_categories", e.control.value))])]
            + group("الشخص", [kit.chip(p["name"], p["id"] in f["people"], lambda e, i=p["id"]: tog("people", i))
                              for p in repo.list_people()] or [kit.txt("لا يوجد أشخاص", 13, color=T.MUTED)])
            + [kit.txt("المبلغ (لعملة المحفظة)", 13, True, T.MUTED), kit.row([mn, mx], spacing=8)]
            + group("الترتيب", [kit.chip(l, f["order"] == k, lambda e, k=k: setv("order", k)) for k, l in ORDERS])
            + [kit.row([ft.Container(kit.big_button("مسح", reset, outline=True), expand=True),
                        ft.Container(kit.big_button("تطبيق", apply), expand=True)], spacing=10)])
        ui.page.update()

    def reset(e):
        ui.filters = ui.default_filters()
        ui.page.close(ref["s"])
        ui.refresh()

    def apply(e):
        f["min"], f["max"], f["date_from"], f["date_to"] = mn.value.strip(), mx.value.strip(), d1.value, d2.value
        ui.filters = f
        ui.page.close(ref["s"])
        ui.refresh()

    ref["s"] = ui.open_sheet(body)
    render()
