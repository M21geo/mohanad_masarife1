"""More > Recurring transactions (rent, salary, subscriptions)."""
import flet as ft

from .. import money
from ..recurring import FREQUENCIES, Recurring
from . import kit, theme as T
from .forms import FormSheet, choices, date_field, label
from .rows import empty_state, page_frame

EVERY_LABEL = {"daily": "يوم", "weekly": "أسبوع", "monthly": "شهر", "yearly": "سنة"}


def _freq_text(r):
    return FREQUENCIES[r["frequency"]] if r["every"] == 1 else f"كل {r['every']} {EVERY_LABEL[r['frequency']]}"


def build_recurring(ui):
    rc = Recurring(ui.repo)

    def run_now(e):
        n = rc.run_due(ui.today)
        ui.toast(f"سُجّلت {n} معاملة" if n else "ما في معاملات مستحقة الآن")
        ui.refresh()

    cards = []
    for r in rc.list():
        sign, color = ("+", T.INCOME) if r["kind"] == "income" else ("−", T.EXPENSE)
        badges = [kit.badge(_freq_text(r), "neutral")]
        if r["finished"]:
            badges.append(kit.badge("انتهت", "warn"))
        elif not r["active"]:
            badges.append(kit.badge("متوقفة", "warn"))
        else:
            badges.append(kit.badge("القادمة " + r["next_date"], "good"))
        title = r["note"] or r["category_name"] or ("دخل متكرر" if r["kind"] == "income" else "مصروف متكرر")
        cards.append(kit.box(kit.row([
            kit.icon_tile(r["category_icon"] or "autorenew", r["category_color"] or T.PRIMARY),
            kit.col([kit.txt(title, 15, True), kit.txt(r["wallet_name"] + (f" · {r['category_name']}" if r["category_name"] else ""), 12, color=T.MUTED),
                     kit.row(badges, spacing=6, wrap=True)], spacing=3, expand=True),
            kit.txt(sign + money.fmt(r["amount"], r["currency"]), 15, True, color)], spacing=12),
            on_click=lambda e, r=r: edit_form(ui, r)))
    return page_frame(ui, "معاملات تكرارية", [
        kit.row([ft.Container(kit.big_button("+ قاعدة جديدة", lambda e: add_form(ui)), expand=True),
                 ft.Container(kit.big_button("تنفيذ المستحق", run_now, outline=True), expand=True)], spacing=10),
        kit.txt("تُسجَّل المعاملات تلقائياً عند فتح التطبيق حسب التاريخ (وتلحق الأيام اللي فاتت).", 12, color=T.MUTED),
        *(cards or [empty_state("ما في معاملات تكرارية")])])


def add_form(ui):
    repo, rc = ui.repo, Recurring(ui.repo)
    wallets = repo.list_wallets()
    s = {"kind": "expense", "wallet": wallets[0]["id"] if wallets else None, "cat": None, "person": None, "freq": "monthly"}
    amount = kit.field("المبلغ", "", thousands=True)
    every = kit.field("كل كم", "1", number=True)
    note = kit.field("وصف (مثلاً: إيجار البيت)", "")
    start = date_field(ui, "تبدأ من", ui.today)
    end = date_field(ui, "تنتهي في (اختياري)", "", clearable=True)

    def pick(k, v):
        s[k] = v
        if k == "kind":
            s["cat"] = None
        form.render()

    def controls():
        tree = repo.category_tree(s["kind"])
        top = next((c for c in tree if c["id"] == s["cat"] or any(ch["id"] == s["cat"] for ch in c["children"])), None)
        out = [choices([("expense", "مصروف"), ("income", "دخل")], s["kind"], lambda v: pick("kind", v)), amount,
               label("المحفظة"), choices([(w["id"], f"{w['name']} ({w['currency']})") for w in wallets], s["wallet"], lambda v: pick("wallet", v)),
               label("الفئة"), choices([(None, "بدون")] + [(c["id"], c["name"]) for c in tree], top["id"] if top else s["cat"], lambda v: pick("cat", v))]
        if top and top["children"]:
            out += [label("فئة فرعية"), choices([(top["id"], f"كل {top['name']}")] + [(c["id"], c["name"]) for c in top["children"]],
                                                s["cat"], lambda v: pick("cat", v), color=T.MUTED)]
        out += [label("الشخص"), choices([(None, "بدون")] + [(p["id"], p["name"]) for p in repo.list_people()], s["person"], lambda v: pick("person", v)),
                label("التكرار"), choices(list(FREQUENCIES.items()), s["freq"], lambda v: pick("freq", v)), every,
                start.control, end.control, note]
        return out

    def save():
        a = money.parse_input(amount.value)
        if a <= 0:
            ui.toast("اكتب المبلغ")
            return False
        rc.add(s["kind"], s["wallet"], a, s["freq"], start.value or ui.today, every=int(money.parse_input(every.value) or 1),
               category_id=s["cat"], person_id=s["person"], note=note.value, end_date=end.value or None)
        n = rc.run_due(ui.today)
        if n:
            ui.toast(f"سُجّلت {n} معاملة مستحقة")
        return True

    form = FormSheet(ui, "قاعدة تكرارية جديدة", controls, save).open()


def edit_form(ui, r):
    rc = Recurring(ui.repo)
    amount = kit.field("المبلغ", str(money.from_minor(r["amount"], r["currency"])), thousands=True)
    note = kit.field("وصف", r["note"])
    end = date_field(ui, "تنتهي في (اختياري)", r["end_date"] or "", clearable=True)

    def save():
        rc.update(r["id"], amount=money.parse_input(amount.value), note=note.value, end_date=end.value or None)
        return True

    def toggle(e):
        rc.set_active(r["id"], not r["active"])
        form.close()
        ui.refresh()

    def delete(e):
        def do():
            rc.delete(r["id"])
            form.close()
            ui.refresh()
        kit.confirm(ui.page, "حذف القاعدة", "المعاملات اللي سُجّلت سابقاً تبقى.", do)

    extra = kit.col([kit.big_button("إيقاف مؤقت" if r["active"] else "استئناف", toggle, outline=True),
                     kit.big_button("حذف القاعدة", delete, bg=T.EXPENSE)], spacing=10)
    form = FormSheet(ui, "تعديل القاعدة", lambda: [kit.txt(f"{_freq_text(r)} · من {r['start_date']}", 13, color=T.MUTED), amount, note, end.control],
                     save, extra=extra).open()
