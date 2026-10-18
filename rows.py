"""Reusable list rows shared by several screens."""
import flet as ft

from . import kit, theme as T

TONE_COLOR = {"income": T.INCOME, "expense": T.EXPENSE, "neutral": T.INK}


def tx_tile(ui, r: dict, show_note: bool = True):
    """A transaction row (icon tile, title/subtitle/note, amount). Tap -> details sheet."""
    middle = [kit.txt(r["title"], 15, True), kit.txt(r["subtitle"], 12, color=T.MUTED)]
    if show_note and r["note"]:
        middle.append(kit.txt(r["note"], 12, color=T.PRIMARY, max_lines=2))
    right = [kit.txt(r["amount_text"], 15, True, TONE_COLOR[r["tone"]])]
    if r["recv_text"]:
        right.append(kit.txt(r["recv_text"], 12, color=T.MUTED))
    return ft.Container(
        content=kit.row([kit.icon_tile(r["icon"], r["color"]),
                         kit.col(middle, spacing=2, expand=True),
                         kit.col(right, spacing=2, h_align=ft.CrossAxisAlignment.END)], spacing=12),
        padding=ft.padding.symmetric(vertical=8), ink=True, border_radius=12,
        on_click=lambda e, tx_id=r["id"]: ui.show_tx(tx_id))


def empty_state(message: str):
    return ft.Container(kit.txt(message, 15, color=T.MUTED, align=ft.TextAlign.CENTER),
                        padding=40, alignment=ft.alignment.center)


def page_frame(ui, title, controls, action=None):
    """Sub-page of the More tab: back arrow + title (+ optional action button) over a scrolling body."""
    def back(e):
        ui.more_page = None
        ui.refresh()

    head = kit.between(kit.row([kit.icon_btn("arrow_forward", back), kit.txt(title, 22, True)], spacing=4),
                       action or ft.Container())
    return ft.Container(
        kit.col([head, kit.col(list(controls) + [ft.Container(height=90)], spacing=12, scroll=True, expand=True)],
                spacing=10, expand=True),
        padding=ft.padding.only(left=20, right=20, top=14), expand=True)


def small_btn(icon_name, on_click, tooltip=None, color=T.MUTED):
    return kit.icon_btn(icon_name, on_click, tooltip, color=color, size=20)
