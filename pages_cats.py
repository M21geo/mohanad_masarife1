"""More > Categories manager: add, edit, reorder, move up/down, delete (with reassignment)."""
import flet as ft

from . import kit, theme as T
from .forms import FormSheet, choices, label
from .rows import empty_state, page_frame, small_btn

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#7a5af8", "#0b6b58", "#b42318", "#5e6e69", "#12201d"]
ICONS = ["restaurant", "directions_car", "bolt", "shopping_bag", "favorite", "home", "school", "pets", "flight", "sports_esports",
         "phone_android", "local_cafe", "payments", "work", "card_giftcard", "savings", "build", "child_care", "movie", "category"]


def build_cats(ui):
    repo, kind = ui.repo, ui.cat_kind

    def set_kind(k):
        ui.cat_kind = k
        ui.refresh()

    def row(c, sub=False):
        acts = [small_btn("arrow_upward", lambda e, c=c: move(c, -1)), small_btn("arrow_downward", lambda e, c=c: move(c, 1))]
        if not sub:
            acts.append(small_btn("add", lambda e, c=c: cat_form(ui, None, kind, c["id"]), "فئة فرعية"))
        acts += [small_btn("edit", lambda e, c=c: cat_form(ui, c, kind, c["parent_id"])),
                 small_btn("delete_outline", lambda e, c=c: delete(c), color=T.EXPENSE)]
        left = kit.row([kit.icon_tile(c["icon"], c["color"], 34 if sub else 42), kit.txt(c["name"], 14 if sub else 15, not sub)], spacing=10)
        return ft.Container(kit.between(left, kit.row(acts, spacing=0)), padding=ft.padding.only(left=28 if sub else 0))

    def move(c, d):
        repo.move_category(c["id"], d)
        ui.refresh()

    def delete(c):
        used = repo.category_usage(c["id"])
        if not used:
            kit.confirm(ui.page, "حذف الفئة", f"حذف «{c['name']}» وفئاتها الفرعية؟", lambda: (repo.delete_category(c["id"]), ui.refresh()))
            return
        reassign_form(ui, c, used)

    tree = repo.category_tree(kind)
    items = []
    for top in tree:
        items.append(row(top))
        items += [row(ch, True) for ch in top["children"]]
    seg = kit.segmented([("expense", "مصاريف"), ("income", "دخل")], kind, set_kind)
    return page_frame(ui, "الفئات", [seg, kit.big_button("+ فئة رئيسية", lambda e: cat_form(ui, None, kind, None)),
                                     kit.box(kit.col(items, spacing=6)) if items else empty_state("ما في فئات")])


def cat_form(ui, c, kind, parent_id):
    repo = ui.repo
    s = {"color": c["color"] if c else COLORS[0], "icon": c["icon"] if c else "category"}
    name = kit.field("اسم الفئة", c["name"] if c else "")

    def pick(key, v):
        s[key] = v
        form.render()

    def controls():
        color_row = ft.Row([ft.Container(width=34, height=34, bgcolor=col, border_radius=17, ink=True,
                                         border=ft.border.all(3, T.INK) if col == s["color"] else None,
                                         on_click=lambda e, col=col: pick("color", col)) for col in COLORS], wrap=True, spacing=8, run_spacing=8)
        icon_row = ft.Row([ft.Container(kit.icon(i, 22, s["color"] if i == s["icon"] else T.MUTED), width=42, height=42, border_radius=12,
                                        bgcolor=T.PRIMARY_SOFT if i == s["icon"] else T.SOFT, ink=True, alignment=ft.alignment.center,
                                        on_click=lambda e, i=i: pick("icon", i)) for i in ICONS], wrap=True, spacing=8, run_spacing=8)
        return [name, label("اللون"), color_row, label("الأيقونة"), icon_row]

    def save():
        if c:
            repo.update_category(c["id"], name=name.value, icon=s["icon"], color=s["color"])
        else:
            repo.add_category(kind, name.value, parent_id=parent_id, icon=s["icon"], color=s["color"])
        return True

    form = FormSheet(ui, "تعديل فئة" if c else ("فئة فرعية جديدة" if parent_id else "فئة جديدة"), controls, save).open()


def reassign_form(ui, c, used):
    repo, s = ui.repo, {"to": None}
    options = []
    for top in repo.category_tree(c["kind"]):
        for x in [top] + top["children"]:
            if x["id"] != c["id"] and x["parent_id"] != c["id"]:
                options.append((x["id"], x["name"]))

    def pick(v):
        s["to"] = v
        form.render()

    def controls():
        return [kit.txt(f"الفئة مستخدمة في {used} معاملة. اختر فئة بديلة تنتقل لها هذه المعاملات:", 14, color=T.MUTED),
                choices(options, s["to"], pick)]

    def save():
        if s["to"] is None:
            ui.toast("اختر فئة بديلة")
            return False
        repo.delete_category(c["id"], reassign_to=s["to"])
        return True

    form = FormSheet(ui, f"حذف «{c['name']}»", controls, save, save_label="حذف ونقل المعاملات").open()
