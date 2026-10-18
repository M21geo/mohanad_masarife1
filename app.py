"""App shell: page setup, bottom navigation, FAB, shared state, sheet helpers.

Screens live in screens_*.py / sheet_*.py and are plain functions `build(ui) -> control`.
"""
import traceback
from datetime import date

import flet as ft

from .. import backup, paths, reminder
from ..db import connect
from ..recurring import Recurring
from ..repo import AppError, Repo
from ..seed import ensure_defaults
from . import kit, theme as T
from .screens_home import build_home
from .screens_more import build_more
from .screens_txs import build_txs
from .sheet_add import open_add_sheet
from .sheet_tx import show_tx

TABS = [("الرئيسية", "HOME_OUTLINED", "HOME"), ("المعاملات", "BAR_CHART_OUTLINED", "BAR_CHART"),
        ("المزيد", "GRID_VIEW_OUTLINED", "GRID_VIEW")]


class AppUI:
    def __init__(self, page: ft.Page, repo: Repo, today: str = None):
        self.page = page
        self.repo = repo
        self.today = today or date.today().isoformat()
        # shared UI state
        self.currency = repo.get_setting("display_currency", "IQD") or "IQD"  # display currency
        self.tab = 0
        self.more_page = None           # which sub-page of the More tab is open
        self.debt_dir = "on"
        self.budget_ym = self.today[:7]
        self.cat_kind = "expense"
        self.stats_ym = self.today[:7]     # month shown when no filter is active
        self.tx_view = "list"              # list | summary | cats | analysis
        self.stats_kind = "expense"
        self.stats_open_cat = None
        self.search = ""
        self.filters = self.default_filters()
        self.body = ft.Container(expand=True)

    # ------------------------------------------------------ hidden balances
    @property
    def hide_balances(self) -> bool:
        return self.repo.get_setting("hide_balances", "0") == "1"

    def toggle_hide(self) -> None:
        self.repo.set_setting("hide_balances", "0" if self.hide_balances else "1")
        self.refresh()

    def shown(self, text: str, wallet: dict = None) -> str:
        """A balance as text, or •••• when hidden (globally, or for this wallet)."""
        return "••••••" if (self.hide_balances or (wallet and wallet.get("hide_balance"))) else text

    # ----------------------------------------------------------- geometry
    @property
    def w(self) -> float:
        return float(self.page.width or T.DEFAULT_WIDTH)

    @property
    def h(self) -> float:
        return float(self.page.height or 800)

    # ------------------------------------------------------------ filters
    @staticmethod
    def default_filters() -> dict:
        return {"kinds": set(), "wallets": set(), "categories": set(), "exclude_categories": False,
                "people": set(), "period": "all", "date_from": "", "date_to": "",
                "min": "", "max": "", "order": "newest"}

    def filters_active(self) -> int:
        f, n = self.filters, 0
        n += bool(f["kinds"]) + bool(f["wallets"]) + bool(f["categories"]) + bool(f["people"])
        n += f["period"] != "all" or bool(f["date_from"] or f["date_to"])
        n += bool(f["min"] or f["max"]) + (f["order"] != "newest")
        return n

    # ------------------------------------------------------------ plumbing
    def toast(self, message: str) -> None:
        kit.toast(self.page, message)

    def guard(self, fn, *args):
        """Run an action; show repo rule violations (AppError) as a toast instead of crashing."""
        try:
            return fn(*args)
        except AppError as e:
            self.toast(str(e))
        return None

    def refresh(self) -> None:
        """Rebuild the current tab (called after any data change)."""
        builders = [build_home, build_txs, build_more]
        self.last_error = None
        try:
            self.body.content = builders[self.tab](self)
        except Exception:  # show the problem on screen so it can be reported
            self.last_error = traceback.format_exc()
            self.body.content = ft.Container(
                ft.Text("حصل خطأ في عرض هذه الشاشة:\n\n" + traceback.format_exc(), selectable=True, size=12, color=T.EXPENSE),
                padding=20)
        self.page.update()

    def go(self, index: int) -> None:
        self.tab = index
        if index != 2:
            self.more_page = None
        self.refresh()

    def open_sheet(self, content, height=None):
        """Show `content` in a bottom sheet. Returns the sheet (page.close(sheet) to dismiss)."""
        sheet = ft.BottomSheet(
            content=ft.Container(content, padding=ft.padding.only(left=20, right=20, top=14, bottom=20),
                                 height=height or min(self.h * 0.92, 760), bgcolor=T.BG),
            is_scroll_controlled=True, show_drag_handle=True, bgcolor=T.BG)
        self.page.open(sheet)
        return sheet

    def check_reminder(self) -> None:
        """Show the daily reminder dialog once per day (after the chosen time) if there is something to say."""
        lines = reminder.due(self.repo)
        if not lines:
            return
        reminder.mark_shown(self.repo)
        dlg = ft.AlertDialog(title=ft.Text("🔔 تذكير اليوم"),
                             content=ft.Column([ft.Text(l) for l in lines], tight=True, spacing=8),
                             actions=[ft.TextButton("لاحقاً", on_click=lambda e: self.page.close(dlg)),
                                      ft.TextButton("سجّل الآن", on_click=lambda e: (self.page.close(dlg), self.add_transaction()))])
        self.page.open(dlg)

    def add_transaction(self, tx=None, kind=None):
        open_add_sheet(self, tx, kind)

    def show_tx(self, tx_id: int):
        show_tx(self, tx_id)


def build_shell(page: ft.Page, repo: Repo, today: str = None) -> AppUI:
    ui = AppUI(page, repo, today)
    page.title = "مصاريفي"
    page.padding = 0
    page.bgcolor = T.BG
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=T.PRIMARY)
    try:  # right-to-left layout for Arabic
        page.rtl = True
        page.locale_configuration = ft.LocaleConfiguration(
            supported_locales=[ft.Locale("ar", "IQ")], current_locale=ft.Locale("ar", "IQ"))
    except Exception:
        pass
    page.navigation_bar = ft.NavigationBar(
        selected_index=0, bgcolor=T.CARD, indicator_color=T.PRIMARY_SOFT,
        destinations=[ft.NavigationBarDestination(icon=getattr(ft.Icons, i), selected_icon=getattr(ft.Icons, s), label=l)
                      for l, i, s in TABS],
        on_change=lambda e: ui.go(int(e.control.selected_index)))
    page.floating_action_button = ft.FloatingActionButton(
        icon=ft.Icons.ADD, bgcolor=T.PRIMARY, foreground_color="#FFFFFF", on_click=lambda e: ui.add_transaction())
    page.floating_action_button_location = ft.FloatingActionButtonLocation.CENTER_DOCKED
    page.add(ft.SafeArea(ui.body, expand=True))
    ui.refresh()
    return ui


def main(page: ft.Page) -> None:
    """Entry point used by main.py (and `flet build apk`)."""
    conn = connect(paths.db_path())
    repo = Repo(conn)
    ensure_defaults(repo)
    try:  # daily automatic backup (kept inside the app's private storage)
        if repo.get_setting("auto_backup", "1") == "1" and backup.auto_backup_due(paths.backup_dir(), 1):
            backup.create_backup(repo, paths.backup_dir(), keep=7)
    except Exception:
        pass
    try:  # create recurring transactions that came due
        n = Recurring(repo).run_due(date.today().isoformat())
    except Exception:
        n = 0
    ui = build_shell(page, repo)
    if n:
        ui.toast(f"سُجّلت {n} معاملة تكرارية")
    try:
        from ..history import Histories
        Histories(paths.history_dir()).purge_drafts()
    except Exception:
        pass

    async def reminder_loop():
        import asyncio
        while True:
            try:
                ui.check_reminder()
            except Exception:
                pass
            await asyncio.sleep(60)

    try:
        page.run_task(reminder_loop)
    except Exception:
        ui.check_reminder()
