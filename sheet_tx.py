"""Transaction details sheet (edit / delete)."""
import flet as ft

from . import kit, theme as T, vm
from .rows import TONE_COLOR


def show_tx(ui, tx_id: int, readonly: bool = False):
    t = ui.guard(ui.repo.get_transaction, tx_id)
    if not t:
        return
    r = vm.tx_row(t, ui.today)
    sheet = {}

    def close():
        ui.page.close(sheet["s"])

    def edit(e):
        close()
        ui.add_transaction(t)

    def delete(e):
        def do():
            ui.guard(ui.repo.delete_transaction, tx_id)
            close()
            ui.toast("تم الحذف")
            ui.refresh()
        kit.confirm(ui.page, "حذف المعاملة", "متأكد؟ هذا الإجراء يغيّر رصيد المحفظة.", do)

    def line(label, value):
        return kit.between(kit.txt(label, 14, color=T.MUTED), kit.txt(value, 14, True))

    lines = [line("النوع", vm.KIND_LABELS[t["kind"]]), line("التاريخ", f"{r['date_label']} · {t['date']}"),
             line("المحفظة", t["wallet_name"] + (f" ← {t['to_wallet_name']}" if t["kind"] == "transfer" else ""))]
    if t["kind"] != "transfer":
        if t["category_name"]:
            lines.append(line("الفئة", r["title"]))
        if t["person_name"]:
            lines.append(line("الشخص", t["person_name"]))
    if r["recv_text"]:
        lines.append(line("المستلم", r["recv_text"]))
    if t["note"]:
        lines.append(kit.box(kit.txt(t["note"], 14), bg=T.SOFT, border=None))
    content = kit.col([
        kit.row([kit.icon_tile(r["icon"], r["color"], 52), kit.col([kit.txt(r["title"], 17, True)], expand=True)], spacing=12),
        kit.txt(r["amount_text"], 30, True, TONE_COLOR[r["tone"]]),
        *lines,
        *([] if readonly else [kit.row([ft.Container(kit.big_button("تعديل", edit), expand=True),
                                        ft.Container(kit.big_button("حذف", delete, bg=T.EXPENSE), expand=True)], spacing=10)]),
    ], spacing=14, scroll=True)
    sheet["s"] = ui.open_sheet(content, height=min(ui.h * 0.8, 620))
