"""More > Monthly budget: an overall limit and per-category limits, with pace and daily allowance."""
import flet as ft

from .. import money
from ..budgets import Budgets
from ..stats import month_label, shift_month
from . import kit, theme as T
from .forms import FormSheet, choices, label
from .rows import empty_state, page_frame

STATE_COLOR = {"ok": T.PRIMARY, "warn": "#B77700", "over": T.EXPENSE}
STATE_BADGE = {"ok": ("good", "ضمن الحد"), "warn": ("warn", "قريب من الحد"), "over": ("bad", "متجاوز")}


def build_budgets(ui):
    bud = Budgets(ui.repo)
    ym = ui.budget_ym
    st = bud.status(ym, ui.today)

    def move(d):
        ui.budget_ym = shift_month(ym, d)
        ui.refresh()

    nav = kit.between(kit.icon_btn("chevron_right", lambda e: move(-1)), kit.txt(month_label(ym), 17, True),
                      kit.icon_btn("chevron_left", lambda e: move(1)))
    W = ui.w - 40 - 32
    parts = [nav]
    o = st["overall"]
    if o:
        c = STATE_COLOR[o["state"]]
        lines = [kit.between(kit.txt("الميزانية الكلية", 15, True), kit.txt(f"{o['pct']}%", 18, True, c)),
                 kit.progress(o["pct"] / 100, c, W, 12),
                 kit.between(kit.txt("المصروف", 13, color=T.MUTED), kit.txt(money.fmt(o["spent"], o["currency"]), 14, True)),
                 kit.between(kit.txt("الميزانية", 13, color=T.MUTED), kit.txt(money.fmt(o["limit"], o["currency"]), 14, True)),
                 kit.between(kit.txt("المتبقي" if o["remaining"] >= 0 else "تجاوز", 13, color=T.MUTED),
                             kit.txt(money.fmt(abs(o["remaining"]), o["currency"]), 14, True, c))]
        if o["daily_left"] is not None and o["remaining"] > 0:
            lines.append(kit.txt(f"تكدر تصرف {money.fmt(o['daily_left'], o['currency'])} باليوم لباقي الشهر", 12, color=T.MUTED))
        if o["projected"] is not None:
            over = o["projected"] > o["limit"]
            lines.append(kit.txt(f"على هذا المعدل راح توصل {money.fmt(o['projected'], o['currency'])} بنهاية الشهر"
                                 + (" ⚠️" if over else ""), 12, color=T.EXPENSE if over else T.MUTED))
        parts.append(kit.box(kit.col(lines, spacing=8), padding=16, on_click=lambda e: budget_form(ui, o)))
    parts.append(kit.big_button("+ ميزانية", lambda e: budget_form(ui, None)))
    for i in st["categories"]:
        c = STATE_COLOR[i["state"]]
        tone, name = STATE_BADGE[i["state"]]
        parts.append(kit.box(kit.col([
            kit.between(kit.row([kit.icon_tile(i["icon"], i["color"], 36), kit.txt(i["name"], 14, True)], spacing=10), kit.badge(name, tone)),
            kit.progress(i["pct"] / 100, c, W, 10),
            kit.between(kit.txt(f"{money.fmt(i['spent'], i['currency'])} من {money.fmt(i['limit'], i['currency'])}", 12, color=T.MUTED),
                        kit.txt(f"{i['pct']}%", 13, True, c))], spacing=8), on_click=lambda e, i=i: budget_form(ui, i)))
    if not o and not st["categories"]:
        parts.append(empty_state("ما في ميزانيات بعد. حدد ميزانية كلية أو لفئة معينة"))
    return page_frame(ui, "الميزانية", parts)


def budget_form(ui, item):
    repo, bud = ui.repo, Budgets(ui.repo)
    tree = repo.category_tree("expense")
    s = {"cat": item["category_id"] if item else None, "cur": item["currency"] if item else "IQD"}
    amount = kit.field("المبلغ الشهري", str(money.from_minor(item["limit"], item["currency"])) if item else "", thousands=True)

    def pick(k, v):
        s[k] = v
        form.render()

    def controls():
        out = []
        if not item:
            opts = [(None, "الميزانية الكلية")] + [(c["id"], c["name"]) for c in tree]
            top = next((c for c in tree if c["id"] == s["cat"] or any(ch["id"] == s["cat"] for ch in c["children"])), None)
            out += [label("تخص"), choices(opts, top["id"] if top else s["cat"], lambda v: pick("cat", v))]
            if top and top["children"]:
                out += [label("أو فئة فرعية"), choices([(top["id"], f"كل {top['name']}")] + [(c["id"], c["name"]) for c in top["children"]],
                                                       s["cat"], lambda v: pick("cat", v), color=T.MUTED)]
            out += [label("العملة"), choices([("IQD", "دينار"), ("USD", "دولار")], s["cur"], lambda v: pick("cur", v))]
        return out + [amount]

    def save():
        bud.set(s["cat"], money.parse_input(amount.value), s["cur"])
        return True

    def delete(e):
        def do():
            bud.delete(item["id"])
            form.close()
            ui.refresh()
        kit.confirm(ui.page, "حذف الميزانية", "متأكد؟", do)

    extra = kit.big_button("حذف الميزانية", delete, bg=T.EXPENSE) if item else None
    form = FormSheet(ui, "تعديل الميزانية" if item else "ميزانية جديدة", controls, save, extra=extra).open()
