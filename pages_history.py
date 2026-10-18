"""More > History: isolated archives of old data (هستوري 1, 2, ...). Browse with filters and statistics."""
import flet as ft

from .. import paths
from ..history import Histories
from . import kit, theme as T
from .rows import empty_state, page_frame, small_btn
from .screens_txs import build_txs


def histories():
    return Histories(paths.history_dir())


def open_archive(ui, hid):
    from .history_ui import HistoryUI  # lazy: history_ui imports app, which imports this module
    h = histories()
    meta = h.get(hid)
    ui.hist = HistoryUI(ui, h.open(hid), meta)
    ui.more_page = "history_view"
    ui.refresh()


def close_archive(ui):
    try:
        ui.hist.repo.conn.close()
    except Exception:
        pass
    ui.hist = None
    ui.more_page = "history"
    ui.refresh()


def build_history(ui):
    h = histories()
    h.purge_drafts()

    def rename(item):
        f = kit.field("الاسم", item["name"])

        def ok(e):
            if ui.guard(h.rename, item["id"], f.value) is not False:
                ui.page.close(dlg)
                ui.refresh()

        dlg = ft.AlertDialog(title=ft.Text("اسم الهستوري"), content=f,
                             actions=[ft.TextButton("إلغاء", on_click=lambda e: ui.page.close(dlg)), ft.TextButton("حفظ", on_click=ok)])
        ui.page.open(dlg)

    def delete(item):
        kit.confirm_typed(ui.page, f"حذف «{item['name']}»", "يحذف الأرشيف وكل بياناته نهائياً. (ما يأثر على التطبيق الرئيسي)", "حذف",
                          lambda: (h.delete(item["id"]), ui.refresh()), yes_label="حذف")

    def new_import(e):
        ui.imp = None
        from .pages_import import _state
        _state(ui)["dest"] = "history"
        ui.more_page = "import"
        ui.refresh()

    cards = []
    for it in h.list():
        rng = f"{it['date_from']} ← {it['date_to']}" if it["date_from"] else "فارغ"
        cards.append(kit.box(kit.col([
            kit.between(kit.col([kit.txt(it["name"], 16, True), kit.txt(f"{it['tx_count']} معاملة · {rng}", 12, color=T.MUTED)], spacing=2),
                        kit.row([small_btn("edit", lambda e, it=it: rename(it)),
                                 small_btn("delete_outline", lambda e, it=it: delete(it), color=T.EXPENSE)], spacing=0)),
            kit.big_button("فتح", lambda e, it=it: open_archive(ui, it["id"]), outline=True)], spacing=8)))
    return page_frame(ui, "الهستوري", [
        kit.box(kit.txt("أرشيفات لبياناتك القديمة، معزولة تماماً عن التطبيق الرئيسي: ما تغيّر الأرصدة ولا الفئات ولا الأشخاص. "
                        "كل أرشيف له فئاته وأشخاصه من الملف اللي رفعته، وتكدر تتصفحه بالفلتر والإحصائيات.", 13, color=T.MUTED), bg=T.SOFT, border=None),
        kit.big_button("+ رفع ملف قديم كهستوري جديد", new_import),
        *(cards or [empty_state("ما في أرشيفات بعد")])])


def build_history_view(ui):
    h = ui.hist
    head = ft.Container(kit.between(kit.row([kit.icon_btn("arrow_forward", lambda e: close_archive(ui)),
                                             kit.txt(h.meta["name"], 18, True)], spacing=4),
                                    kit.badge("للعرض فقط", "neutral")),
                        padding=ft.padding.only(left=12, right=20, top=8))
    return kit.col([head, build_txs(h)], spacing=0, expand=True)
