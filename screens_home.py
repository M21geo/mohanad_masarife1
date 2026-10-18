"""Home: total balance (IQD/USD toggle), this month's income/expense, wallets, recent transactions."""
import flet as ft

from .. import money
from ..budgets import Budgets
from . import kit, theme as T, vm
from .rows import empty_state, tx_tile


def _hero_toggle(ui):
    def pill(code, label):
        on = ui.currency == code

        def pick(e):
            ui.currency = code
            ui.refresh()

        return ft.Container(
            content=kit.txt(label, 13, True, T.HERO if on else T.HERO_TEXT),
            padding=ft.padding.symmetric(horizontal=14, vertical=7), border_radius=9, ink=True,
            bgcolor=T.MINT if on else None, on_click=pick)

    return ft.Container(content=kit.row([pill("IQD", "دينار"), pill("USD", "دولار")], spacing=0),
                        bgcolor=T.HERO_CARD, border_radius=12, padding=3)


def _stat(label, value, color):
    return ft.Container(
        content=kit.col([kit.txt(label, 12, color=T.HERO_TEXT), kit.txt(value, 16, True, color)], spacing=3),
        bgcolor=T.HERO_CARD, border_radius=16, padding=12, expand=True)


def _wallet_card(ui, w):
    def open_wallet(e):
        ui.filters = ui.default_filters()
        ui.filters["wallets"] = {w["id"]}
        ui.go(1)

    tag_fg, tag_bg = (T.PRIMARY, T.PRIMARY_SOFT) if w["currency"] == "USD" else (T.MUTED, T.SOFT)
    return kit.box(
        kit.col([
            kit.between(kit.txt(w["name"], 14, True),
                        ft.Container(kit.txt(w["currency"], 11, True, tag_fg), bgcolor=tag_bg, border_radius=8,
                                     padding=ft.padding.symmetric(horizontal=8, vertical=2))),
            kit.txt(ui.shown(w["balance_text"], w), 18, True)], spacing=10),
        width=156, on_click=open_wallet)


def build_home(ui):
    d = vm.home(ui.repo, ui.currency, ui.today)
    hero = ft.Container(
        content=kit.col([
            kit.between(kit.row([kit.txt("إجمالي الأرصدة", 14, color=T.HERO_TEXT),
                                 kit.icon_btn("visibility" if ui.hide_balances else "visibility_off", lambda e: ui.toggle_hide(),
                                              "إخفاء/إظهار الأرصدة", color=T.HERO_TEXT, size=20)], spacing=2),
                        _hero_toggle(ui)),
            kit.row([kit.txt(ui.shown(d["total_text"]), 36, True, "#FFFFFF"), kit.txt(d["unit"], 16, True, T.HERO_TEXT)],
                    spacing=8, v_align=ft.CrossAxisAlignment.END),
            kit.txt(ui.shown(d["equiv_text"]) if not ui.hide_balances else "", 13, color=T.HERO_TEXT),
            kit.row([_stat("دخل الشهر", d["income_text"], T.MINT), _stat("مصروف الشهر", d["expense_text"], "#FFB4A8")],
                    spacing=10),
        ], spacing=12),
        bgcolor=T.HERO, border_radius=24, padding=20)

    recent = [tx_tile(ui, r) for r in d["recent"]] or [empty_state("ما في معاملات بعد. اضغط + لإضافة أول معاملة")]
    content = kit.col([
        kit.col([kit.txt(d["month_label"], 13, color=T.MUTED), kit.txt("نظرة عامة", 24, True)], spacing=2),
        hero,
        _budget_card(ui),
        kit.section("المحافظ"),
        kit.hscroll([_wallet_card(ui, w) for w in d["wallets"]], spacing=10),
        kit.section("آخر المعاملات", "عرض الكل", lambda e: ui.go(1)),
        kit.col(recent, spacing=0),
        ft.Container(height=90),  # room for the floating + button
    ], spacing=18, scroll=True, expand=True)
    return ft.Container(content, padding=ft.padding.only(left=20, right=20, top=20), expand=True)


def _budget_card(ui):
    """Overall monthly budget progress (or a hint to create one)."""
    def open_budgets(e):
        ui.more_page = "budgets"
        ui.go(2)

    st = Budgets(ui.repo).status(ui.today[:7], ui.today)["overall"]
    if not st:
        return kit.box(kit.row([kit.icon("savings", 22, T.PRIMARY), kit.col([kit.txt("حدد ميزانية شهرية", 14, True),
                                                                           kit.txt("تابع صرفك وياك حد معين", 12, color=T.MUTED)], spacing=1, expand=True),
                                kit.icon("chevron_left", 20, T.FAINT)], spacing=10), on_click=open_budgets)
    color = {"ok": T.PRIMARY, "warn": "#B77700", "over": T.EXPENSE}[st["state"]]
    left = (f"المتبقي {money.fmt(st['remaining'], st['currency'])}" if st["remaining"] >= 0
            else f"تجاوزت بـ {money.fmt(-st['remaining'], st['currency'])}")
    extra = f" · {money.fmt(st['daily_left'], st['currency'])} باليوم" if st["daily_left"] and st["remaining"] > 0 else ""
    return kit.box(kit.col([
        kit.between(kit.txt("ميزانية الشهر", 14, True), kit.txt(f"{st['pct']}%", 14, True, color)),
        kit.progress(st["pct"] / 100, color, ui.w - 40 - 28, 10),
        kit.txt(left + extra, 12, color=T.MUTED)], spacing=8), on_click=open_budgets)
