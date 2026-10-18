"""More tab: menu of secondary screens, each opened as a sub-page (back arrow returns here)."""
import flet as ft

from . import kit, theme as T
from .pages_backup import build_backup
from .pages_budgets import build_budgets
from .pages_cats import build_cats
from .pages_debts import build_debts
from .pages_history import build_history, build_history_view
from .pages_import import build_import
from .pages_notes import build_notes
from .pages_people import build_people
from .pages_recurring import build_recurring
from .pages_settings import build_settings
from .pages_wallets import build_wallets

PAGES = {"wallets": build_wallets, "debts": build_debts, "notes": build_notes, "cats": build_cats,
         "people": build_people, "budgets": build_budgets, "history": build_history, "history_view": build_history_view, "recurring": build_recurring, "import": build_import, "backup": build_backup, "settings": build_settings}

ITEMS = [
    ("wallets", "account_balance_wallet", "المحافظ", "الأرصدة والتحويل بين المحافظ"),
    ("budgets", "savings", "الميزانية", "حد شهري كلي ولكل فئة"),
    ("recurring", "autorenew", "معاملات تكرارية", "إيجار، راتب، اشتراكات"),
    ("debts", "handshake", "الديون", "ديون عليّ ولي"),
    ("notes", "sticky_note_2", "الملاحظات", "ملاحظات سريعة ومثبّتة"),
    ("cats", "category", "الفئات", "إضافة وتعديل وترتيب الفئات"),
    ("people", "groups", "الأشخاص", "إدارة الأشخاص"),
    ("history", "history", "الهستوري", "أرشيفات بيانات قديمة معزولة"),
    ("import", "upload_file", "استيراد", "من ملفات CSV / Excel / JSON"),
    ("backup", "backup", "النسخ الاحتياطي", "نسخ واسترجاع"),
    ("settings", "settings", "الإعدادات", "العملة وسعر الصرف"),
]


def build_more(ui):
    if ui.more_page == "history_view" and getattr(ui, "hist", None) is None:
        ui.more_page = "history"
    if ui.more_page in PAGES:
        return PAGES[ui.more_page](ui)

    def open_page(key):
        ui.more_page = key
        ui.refresh()

    tiles = [kit.box(kit.row([kit.icon_tile(i, T.PRIMARY), kit.col([kit.txt(t, 15, True), kit.txt(sub, 12, color=T.MUTED)], spacing=2, expand=True),
                              kit.icon("chevron_left", 20, T.FAINT)], spacing=12), on_click=lambda e, k=key: open_page(k))
             for key, i, t, sub in ITEMS]
    return ft.Container(kit.col([kit.txt("المزيد", 24, True), kit.col(tiles + [ft.Container(height=90)], spacing=10, scroll=True, expand=True)],
                                spacing=14, expand=True),
                        padding=ft.padding.only(left=20, right=20, top=20), expand=True)
