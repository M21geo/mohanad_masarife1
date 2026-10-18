"""More > Debts: I owe ('on') / owed to me ('for'), payments, optional posting to a wallet."""
import flet as ft

from .. import money
from ..debts import Debts
from . import kit, theme as T, vm
from .forms import FormSheet, choices, date_field, label
from .rows import empty_state, page_frame

DIRS = [("on", "عليّ"), ("for", "لي")]


def build_debts(ui):
    deb = Debts(ui.repo)
    d = ui.debt_dir

    def set_dir(k):
        ui.debt_dir = k
        ui.refresh()

    sm = deb.summary(d)
    head = kit.box(kit.col([
        kit.txt("إجمالي المتبقي " + ("عليك" if d == "on" else "لك"), 13, color=T.HERO_TEXT),
        kit.txt(money.fmt(sm["IQD"], "IQD"), 22, True, "#FFFFFF"),
        kit.txt(money.fmt(sm["USD"], "USD"), 16, True, T.MINT),
        kit.txt(f"{sm['open']} دين مفتوح" + (f" · {sm['overdue']} متأخر" if sm["overdue"] else ""), 12, color=T.HERO_TEXT),
    ], spacing=4), bg=T.HERO, border=None, padding=18)

    cards = []
    for x in deb.list_debts(direction=d, today=ui.today):
        frac = (x["paid"] / x["total"]) if x["total"] else 0
        badges = []
        if x["settled"]:
            badges.append(kit.badge("مسدّد", "good"))
        elif x["overdue"]:
            badges.append(kit.badge("متأخر", "bad"))
        if x["due_date"] and not x["settled"]:
            badges.append(kit.badge(("القسط القادم " if x["next_due"] else "يستحق ") + x["due_date"], "neutral"))
        if x["inst_count"]:
            badges.append(kit.badge(f"{x['inst_count']} قسط", "neutral"))
        pays = deb.list_payments(x["id"])
        opened = x["id"] in ui.__dict__.setdefault("debt_open", set())

        def toggle(e, i=x["id"]):
            ui.debt_open ^= {i}
            ui.refresh()

        extra = []
        if pays:
            extra.append(ft.Container(kit.row([kit.icon("expand_less" if opened else "expand_more", 18, T.PRIMARY),
                                               kit.txt(f"الدفعات المسدّدة ({len(pays)})", 13, True, T.PRIMARY)], spacing=4),
                                      ink=True, border_radius=8, on_click=toggle, padding=ft.padding.symmetric(vertical=4)))
            if opened:
                extra += [ft.Divider(height=1, color=T.LINE)] + payment_rows(ui, x, pays)
        cards.append(kit.box(kit.col([
            kit.between(kit.txt(x["person_name"], 16, True), kit.txt(money.fmt(x["remaining"], x["currency"]), 16, True,
                                                                     T.INCOME if x["settled"] else T.EXPENSE if d == "on" else T.INCOME)),
            kit.progress(frac, T.PRIMARY, ui.w - 40 - 28),
            kit.row([kit.txt(f"من أصل {money.fmt(x['total'], x['currency'])}", 12, color=T.MUTED)] + badges, spacing=8, wrap=True),
            *extra],
            spacing=8), on_click=lambda e, x=x: debt_sheet(ui, x["id"])))
    return page_frame(ui, "الديون", [kit.segmented(DIRS, d, set_dir), head,
                                     kit.big_button("+ دين جديد", lambda e: debt_form(ui, None))] +
                      (cards or [empty_state("ما في ديون")]))


def payment_rows(ui, x, pays, on_delete=None):
    """Detailed list of what was paid/received: number, date, amount, wallet, note, balance left after it."""
    word = "دفعة" if x["direction"] == "on" else "دفعة مستلمة"
    out = []
    for p in pays:
        sub = vm.day_label(p["date"], ui.today)
        if p.get("wallet_name"):
            sub += f" · {p['wallet_name']}"
        mid = [kit.txt(f"{word} {p['n']}", 13, True), kit.txt(sub, 12, color=T.MUTED),
               kit.txt("المتبقي بعدها " + money.fmt(p["remaining_after"], x["currency"]), 12, color=T.MUTED)]
        if p["note"]:
            mid.append(kit.txt(p["note"], 12, color=T.PRIMARY, max_lines=2))
        right = [kit.txt(money.fmt(p["amount"], x["currency"]), 14, True, T.INCOME)]
        if on_delete:
            right.append(kit.icon_btn("delete_outline", lambda e, p=p: on_delete(p), color=T.EXPENSE, size=20))
        out.append(kit.between(kit.col(mid, spacing=2, expand=True), kit.col(right, spacing=0, h_align=ft.CrossAxisAlignment.END)))
    return out


def wallet_choices(repo, currency):
    return [(None, "بدون ربط بمحفظة")] + [(w["id"], w["name"]) for w in repo.list_wallets() if w["currency"] == currency]


def debt_form(ui, x):
    repo, deb = ui.repo, Debts(ui.repo)
    people = repo.list_people()
    s = {"dir": x["direction"] if x else ui.debt_dir, "person": x["person_id"] if x else (people[0]["id"] if people else None),
         "cur": x["currency"] if x else "IQD", "wallet": None, "mode": "one", "period": "monthly"}
    amount = kit.field("المبلغ", str(money.from_minor(x["total"], x["currency"])) if x else "", thousands=True)
    day = date_field(ui, "تاريخ الدين", ui.today)
    due = date_field(ui, "تاريخ الاستحقاق (اختياري)", (x["due_date"] or "") if x else "", clearable=True)
    first = date_field(ui, "تاريخ أول قسط", "")
    count = kit.field("عدد الأقساط", "3", number=True)
    note = kit.field("ملاحظة", x["note"] if x else "", multiline=True)
    newp = kit.field("أو اسم شخص جديد", "")

    def pick(k, v):
        s[k] = v
        if k == "cur":
            s["wallet"] = None
        form.render()

    def controls():
        out = []
        if x:
            out += [amount]
            if not x["inst_count"]:
                out += [due.control]
            else:
                out += [kit.txt(f"مقسّط على {x['inst_count']} قسط، لتغيير الجدول احذف الدين وأنشئه من جديد.", 12, color=T.MUTED)]
            return out + [note]
        out += [choices(DIRS, s["dir"], lambda v: pick("dir", v)),
                label("الشخص"), choices([(p["id"], p["name"]) for p in people], s["person"], lambda v: pick("person", v)), newp,
                label("العملة"), choices([("IQD", "دينار"), ("USD", "دولار")], s["cur"], lambda v: pick("cur", v)), amount,
                label("استلمت المبلغ بمحفظة؟" if s["dir"] == "on" else "سلّمت المبلغ من محفظة؟"),
                choices(wallet_choices(repo, s["cur"]), s["wallet"], lambda v: pick("wallet", v)), day.control,
                label("طريقة السداد"),
                choices([("one", "دفعة واحدة"), ("inst", "تقسيط")], s["mode"], lambda v: pick("mode", v))]
        if s["mode"] == "inst":
            out += [count, choices([("monthly", "شهري"), ("weekly", "أسبوعي")], s["period"], lambda v: pick("period", v)), first.control]
        else:
            out += [due.control]
        return out + [note]

    def save():
        a = money.parse_input(amount.value)
        if a <= 0:
            ui.toast("اكتب المبلغ")
            return False
        if x:
            deb.update_debt(x["id"], due_date=(due.value or None) if not x["inst_count"] else ..., note=note.value, total=a)
            return True
        pid = repo.add_person(newp.value) if newp.value.strip() else s["person"]
        if pid is None:
            ui.toast("اختر شخصاً")
            return False
        inst = int(money.parse_input(count.value)) if s["mode"] == "inst" else 0
        deb.add_debt(s["dir"], pid, a, s["cur"], due.value or None, note.value, wallet_id=s["wallet"], date=day.value or ui.today,
                     installments=inst, first_due=first.value or None, period=s["period"])
        ui.debt_dir = s["dir"]
        return True

    form = FormSheet(ui, "تعديل دين" if x else "دين جديد", controls, save).open()


def more_form(ui, x):
    """Increase an existing debt (borrow / lend more), optionally through a wallet."""
    repo, deb, s = ui.repo, Debts(ui.repo), {"wallet": None}
    amount = kit.field("المبلغ الإضافي", "", thousands=True)
    day = date_field(ui, "التاريخ", ui.today)

    def pick(v):
        s["wallet"] = v
        form.render()

    def controls():
        return [amount, label("بمحفظة"), choices(wallet_choices(repo, x["currency"]), s["wallet"], pick), day.control]

    def save():
        deb.add_to_debt(x["id"], money.parse_input(amount.value), s["wallet"], day.value or ui.today)
        return True

    form = FormSheet(ui, "زيادة الدين", controls, save).open()


def debt_sheet(ui, debt_id):
    deb = Debts(ui.repo)
    x = deb.get_debt(debt_id)
    ref = {}

    def close():
        ui.page.close(ref["s"])

    def pay(e):
        close()
        pay_form(ui, x)

    def edit(e):
        close()
        debt_form(ui, x)

    def delete(e):
        def do():
            ui.guard(deb.delete_debt, debt_id)
            close()
            ui.refresh()
        kit.confirm(ui.page, "حذف الدين", "يحذف الدين ودفعاته (المعاملات المرتبطة بالمحافظ تنحذف أيضاً).", do)

    def del_pay(p):
        def do():
            ui.guard(deb.delete_payment, p["id"])
            close()
            ui.refresh()
            debt_sheet(ui, debt_id)
        kit.confirm(ui.page, "حذف الدفعة", "متأكد؟", do)

    pays = payment_rows(ui, x, deb.list_payments(debt_id), del_pay)
    sched = []
    tone = {"paid": ("good", "مدفوع"), "late": ("bad", "متأخر"), "partial": ("warn", "جزئي"), "due": ("neutral", "قادم")}
    for q in x["schedule"]:
        t, name = tone[q["status"]]
        sched.append(kit.between(kit.txt(f"قسط {q['n']} · {q['due']}", 13), kit.row([kit.txt(money.fmt(q["amount"], x["currency"]), 13, True),
                                                                                   kit.badge(name, t)], spacing=6)))
    content = kit.col([
        kit.txt(x["person_name"], 20, True),
        kit.txt(("عليّ" if x["direction"] == "on" else "لي") + " · " + (x["note"] or "بدون ملاحظة"), 13, color=T.MUTED),
        kit.between(kit.txt("المتبقي", 14, color=T.MUTED), kit.txt(money.fmt(x["remaining"], x["currency"]), 18, True)),
        kit.between(kit.txt("الإجمالي", 14, color=T.MUTED), kit.txt(money.fmt(x["total"], x["currency"]), 14, True)),
        *([kit.txt("جدول الأقساط", 15, True), *sched] if sched else []),
        kit.txt(f"الدفعات المسدّدة ({len(pays)})", 15, True), *(pays or [kit.txt("ما في دفعات بعد", 13, color=T.MUTED)]),
        kit.row([ft.Container(kit.big_button("تسديد دفعة" if x["direction"] == "on" else "استلام دفعة", pay, enabled=not x["settled"]), expand=True),
                 ft.Container(kit.big_button("تعديل", edit, outline=True), expand=True)], spacing=10),
        kit.big_button("زيادة الدين", lambda e: (close(), more_form(ui, x)), outline=True),
        kit.big_button("حذف الدين", delete, bg=T.EXPENSE),
    ], spacing=12, scroll=True)
    ref["s"] = ui.open_sheet(content)


def pay_form(ui, x):
    repo, deb = ui.repo, Debts(ui.repo)
    wallets = [w for w in repo.list_wallets() if w["currency"] == x["currency"]]
    s = {"wallet": None}
    suggest = x["next_amount"] or x["remaining"]
    amount = kit.field("المبلغ", str(money.from_minor(suggest, x["currency"])), thousands=True)
    date = date_field(ui, "التاريخ", ui.today)
    note = kit.field("ملاحظة", "")

    def pick(v):
        s["wallet"] = v
        form.render()

    def controls():
        opts = [(None, "بدون ربط بمحفظة")] + [(w["id"], w["name"]) for w in wallets]
        return [amount, label("سجّلها كمعاملة بمحفظة"), choices(opts, s["wallet"], pick), date.control, note]

    def save():
        deb.pay(x["id"], money.parse_input(amount.value), s["wallet"], date.value or ui.today, note.value)
        return True

    form = FormSheet(ui, "تسديد دفعة" if x["direction"] == "on" else "استلام دفعة", controls, save).open()
