"""More > Wallets: balances, add/edit, reorder, archive, delete, transfer."""
import flet as ft

from .. import money
from . import kit, theme as T
from .forms import FormSheet, choices, label
from .rows import empty_state, page_frame, small_btn


def build_wallets(ui):
    repo = ui.repo
    wallets = repo.balances(include_archived=True)
    active = [w for w in wallets if not w["archived"]]

    def move(w, d):
        ids = [x["id"] for x in active]
        i = ids.index(w["id"])
        j = i + d
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            repo.reorder_wallets(ids)
            ui.refresh()

    def archive(w, flag):
        ui.guard(repo.archive_wallet, w["id"], flag)
        ui.refresh()

    def delete(w):
        def do():
            ui.guard(repo.delete_wallet, w["id"])
            ui.refresh()
        kit.confirm(ui.page, "حذف المحفظة", f"حذف «{w['name']}»؟ (ما تنحذف إذا فيها معاملات)", do)

    def card(w):
        arch = bool(w["archived"])
        acts = [small_btn("edit", lambda e, w=w: wallet_form(ui, w), "تعديل")]
        if not arch:
            acts += [small_btn("arrow_upward", lambda e, w=w: move(w, -1)), small_btn("arrow_downward", lambda e, w=w: move(w, 1))]
        acts += [small_btn("unarchive" if arch else "archive", lambda e, w=w: archive(w, not arch)),
                 small_btn("delete_outline", lambda e, w=w: delete(w), color=T.EXPENSE)]
        return kit.box(kit.col([
            kit.between(kit.row([kit.txt(w["name"], 16, True), kit.badge(w["currency"], "neutral")] +
                                ([kit.badge("مؤرشفة", "warn")] if arch else []), spacing=8),
                        kit.txt(ui.shown(money.fmt(w["balance"], w["currency"]), w), 17, True)),
            kit.row(acts, spacing=0)], spacing=6), bg=T.SOFT if arch else T.CARD)

    items = [card(w) for w in wallets] or [empty_state("ما في محافظ")]
    top = kit.row([ft.Container(kit.big_button("+ محفظة", lambda e: wallet_form(ui, None)), expand=True),
                   ft.Container(kit.big_button("تحويل بين محافظ", lambda e: ui.add_transaction(kind="transfer"), outline=True),
                                expand=True)], spacing=10)
    eye = kit.icon_btn("visibility" if ui.hide_balances else "visibility_off", lambda e: ui.toggle_hide(), "إخفاء/إظهار الأرصدة")
    return page_frame(ui, "المحافظ", [top] + items, action=eye)


def wallet_form(ui, w):
    repo, s = ui.repo, {"cur": w["currency"] if w else "IQD"}
    name = kit.field("اسم المحفظة", w["name"] if w else "")
    hide = ft.Switch(label="إخفاء رصيد هذه المحفظة دائماً", value=bool(w and w["hide_balance"]))
    initial = kit.field("الرصيد الابتدائي", str(money.from_minor(w["initial_balance"], w["currency"])) if w else "0", thousands=True)

    def controls():
        out = [name]
        if not w:
            out += [label("العملة"), choices([("IQD", "دينار عراقي"), ("USD", "دولار")], s["cur"], pick)]
        return out + [initial, hide]

    def pick(c):
        s["cur"] = c
        form.render()

    def save():
        if w:
            repo.update_wallet(w["id"], name=name.value, initial=money.parse_input(initial.value), hide_balance=hide.value)
        else:
            wid = repo.add_wallet(name.value, s["cur"], money.parse_input(initial.value))
            repo.update_wallet(wid, hide_balance=hide.value)
        return True

    form = FormSheet(ui, "تعديل محفظة" if w else "محفظة جديدة", controls, save).open()
