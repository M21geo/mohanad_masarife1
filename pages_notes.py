"""More > Notes (pinned first)."""
import flet as ft

from . import kit, theme as T
from .rows import empty_state, page_frame, small_btn


def build_notes(ui):
    repo = ui.repo

    def edit(n):
        f = kit.field("الملاحظة", n["text"] if n else "", multiline=True)

        def ok(e):
            r = ui.guard(repo.update_note, n["id"], f.value) if n else ui.guard(repo.add_note, f.value)
            if n or r is not None:
                ui.page.close(dlg)
                ui.refresh()

        dlg = ft.AlertDialog(title=ft.Text("تعديل ملاحظة" if n else "ملاحظة جديدة"), content=ft.Container(f, width=320),
                             actions=[ft.TextButton("إلغاء", on_click=lambda e: ui.page.close(dlg)), ft.TextButton("حفظ", on_click=ok)])
        ui.page.open(dlg)

    def pin(n):
        repo.toggle_note_pin(n["id"])
        ui.refresh()

    def delete(n):
        kit.confirm(ui.page, "حذف الملاحظة", "متأكد؟", lambda: (repo.delete_note(n["id"]), ui.refresh()))

    cards = []
    for n in repo.list_notes():
        pinned = bool(n["pinned"])
        cards.append(kit.box(kit.col([
            kit.txt(n["text"], 15),
            kit.row([small_btn("push_pin" if pinned else "push_pin_outlined", lambda e, n=n: pin(n), color=T.PRIMARY if pinned else T.MUTED),
                     small_btn("edit", lambda e, n=n: edit(n)),
                     small_btn("delete_outline", lambda e, n=n: delete(n), color=T.EXPENSE)], spacing=0)], spacing=4),
            bg=T.PRIMARY_SOFT if pinned else T.CARD))
    return page_frame(ui, "الملاحظات", [kit.big_button("+ ملاحظة", lambda e: edit(None))] + (cards or [empty_state("ما في ملاحظات")]))
