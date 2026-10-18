"""Small widget toolkit. EVERY direct Flet call lives here or in the screens' layout code,
so if a Flet release renames something there is one obvious place to fix it.

Written for the flet==0.28.3 API (ft.Colors / ft.Icons / page.open()). NOT yet run against real Flet - see README.
"""
import flet as ft

from .. import money
from . import theme as T


# ------------------------------------------------------------- primitives
def icon_name(name: str):
    """'restaurant' -> ft.Icons.RESTAURANT (falls back to a generic icon)."""
    return getattr(ft.Icons, (name or "category").upper(), ft.Icons.CATEGORY)


def txt(value, size=14, bold=False, color=T.INK, align=None, weight=None, expand=False, max_lines=None, **kw):
    if weight is None:
        weight = ft.FontWeight.W_800 if bold else ft.FontWeight.W_500
    return ft.Text(str(value), size=size, weight=weight, color=color, text_align=align,
                   expand=expand, max_lines=max_lines, **kw)


def row(controls, spacing=8, align=None, v_align=None, wrap=False, expand=False, scroll=None, **kw):
    return ft.Row(controls=list(controls), spacing=spacing, wrap=wrap, expand=expand, scroll=scroll,
                  alignment=align or ft.MainAxisAlignment.START,
                  vertical_alignment=v_align or ft.CrossAxisAlignment.CENTER, **kw)


def col(controls, spacing=8, scroll=False, expand=False, align=None, h_align=None, **kw):
    return ft.Column(controls=list(controls), spacing=spacing, expand=expand,
                     scroll=ft.ScrollMode.AUTO if scroll else None,
                     alignment=align or ft.MainAxisAlignment.START,
                     horizontal_alignment=h_align or ft.CrossAxisAlignment.START, **kw)


def between(*controls, **kw):
    """Row with items pushed to both ends (RTL-aware: first item on the reading start)."""
    return row(controls, align=ft.MainAxisAlignment.SPACE_BETWEEN, **kw)


def box(content=None, padding=14, bg=T.CARD, border=T.LINE, radius=18, on_click=None,
        width=None, height=None, expand=False, margin=None, align=None):
    return ft.Container(content=content, padding=padding, bgcolor=bg, border_radius=radius,
                        border=ft.border.all(1, border) if border else None, on_click=on_click,
                        ink=bool(on_click), width=width, height=height, expand=expand, margin=margin,
                        alignment=align)


def icon(name, size=22, color=T.INK):
    return ft.Icon(name=icon_name(name), size=size, color=color)


def icon_btn(name, on_click, tooltip=None, color=T.INK, size=22):
    return ft.IconButton(icon=icon_name(name), icon_color=color, icon_size=size, on_click=on_click, tooltip=tooltip)


def icon_tile(name, color, size=44):
    """Rounded tile with a tinted background (category icons)."""
    return ft.Container(content=icon(name, 22, color), width=size, height=size, border_radius=14,
                        bgcolor=ft.Colors.with_opacity(0.15, color), alignment=ft.alignment.center)


def hscroll(controls, spacing=8):
    return ft.Row(controls=list(controls), spacing=spacing, scroll=ft.ScrollMode.HIDDEN)


# ---------------------------------------------------------------- widgets
def chip(label, selected, on_click, color=T.PRIMARY, dashed=False):
    return ft.Container(
        content=txt(label, 14, True, "#FFFFFF" if selected else T.INK),
        padding=ft.padding.symmetric(horizontal=14, vertical=11), border_radius=14, ink=True,
        bgcolor=color if selected else T.CARD, on_click=on_click,
        border=ft.border.all(1, color if selected else T.LINE))


def segmented(options, selected, on_select):
    """options: [(key, label)]; a tray of equal-width buttons (period / type switches)."""
    def btn(key, label):
        on = key == selected
        return ft.Container(
            content=txt(label, 14, True, T.INK if on else T.MUTED, align=ft.TextAlign.CENTER),
            expand=True, padding=ft.padding.symmetric(vertical=11), border_radius=12, ink=True,
            bgcolor=T.CARD if on else None, on_click=lambda e, k=key: on_select(k),
            shadow=ft.BoxShadow(blur_radius=3, color=ft.Colors.with_opacity(0.12, T.INK), offset=ft.Offset(0, 1)) if on else None)
    return ft.Container(content=row([btn(k, l) for k, l in options], spacing=4), padding=4,
                        bgcolor=T.LINE, border_radius=16)


def badge(text, tone="neutral"):
    fg, bg = T.TONE.get(tone, T.TONE["neutral"])
    return ft.Container(content=txt(text, 11, True, fg), bgcolor=bg, border_radius=8,
                        padding=ft.padding.symmetric(horizontal=7, vertical=2))


def section(title, action=None, on_action=None):
    items = [txt(title, 17, True)]
    if action:
        items.append(ft.TextButton(action, on_click=on_action))
    return between(*items)


def progress(fraction, color, width, height=8, track=T.SOFT):
    """Horizontal bar made of two containers (no dependency on ProgressBar styling)."""
    fraction = max(0.0, min(1.0, fraction))
    return ft.Container(
        content=ft.Container(width=max(0, width * fraction), height=height, bgcolor=color, border_radius=height / 2),
        width=width, height=height, bgcolor=track, border_radius=height / 2, alignment=ft.alignment.center_left)


def field(label, value="", on_change=None, number=False, multiline=False, hint=None, width=None, expand=False,
          thousands=False):
    """Text field. thousands=True formats digits live as 10,000,000 (and accepts Arabic digits)."""
    handler = on_change
    if thousands:
        value = money.format_input(value)

        def handler(e):
            new = money.format_input(e.control.value)
            if new != e.control.value:
                e.control.value = new
                e.control.update()
            if on_change:
                on_change(e)

    return ft.TextField(
        label=label, hint_text=hint, value=value, on_change=handler, width=width, expand=expand,
        keyboard_type=ft.KeyboardType.NUMBER if (number or thousands) else ft.KeyboardType.TEXT,
        multiline=multiline, min_lines=2 if multiline else 1, max_lines=4 if multiline else 1,
        border_radius=14, border_color=T.LINE, focused_border_color=T.PRIMARY, bgcolor=T.CARD, filled=True,
        text_size=15, content_padding=ft.padding.symmetric(horizontal=14, vertical=12))


def columns_chart(points, width, height=110, label_every=1, gap=3):
    """Vertical bar chart from containers. points: [{'label','top','bars':[(fraction,color),...]}]."""
    n = max(1, len(points))
    nb = max(1, max((len(p["bars"]) for p in points), default=1))
    slot = width / n
    bw = max(3, min(26, (slot - gap * 2) / nb - 1))
    cols = []
    for i, p in enumerate(points):
        bars = ft.Row([ft.Container(width=bw, height=max(2, height * f) if f > 0 else 2, bgcolor=c if f > 0 else T.SOFT,
                                    border_radius=min(5, bw / 2)) for f, c in p["bars"]],
                      spacing=1, vertical_alignment=ft.CrossAxisAlignment.END, alignment=ft.MainAxisAlignment.CENTER,
                      height=height)
        lab = p["label"] if i % label_every == 0 else ""
        cols.append(ft.Container(kit_col([txt(p.get("top", ""), 10, color=T.MUTED), bars, txt(lab, 10, color=T.MUTED)],
                                         spacing=3, h_align=ft.CrossAxisAlignment.CENTER,
                                         align=ft.MainAxisAlignment.END), width=slot, alignment=ft.alignment.bottom_center))
    return ft.Row(cols, spacing=0, vertical_alignment=ft.CrossAxisAlignment.END, width=width)


def kit_col(*a, **k):
    return col(*a, **k)


def big_button(label, on_click, enabled=True, bg=T.PRIMARY, fg="#FFFFFF", outline=False):
    return ft.Container(
        content=txt(label, 16, True, T.PRIMARY if outline else fg, align=ft.TextAlign.CENTER),
        padding=ft.padding.symmetric(vertical=15), border_radius=18, ink=enabled,
        bgcolor=None if outline else (bg if enabled else "#9DB0AA"),
        border=ft.border.all(1.5, T.PRIMARY) if outline else None,
        on_click=on_click if enabled else None, alignment=ft.alignment.center)


def donut(slices, size=170, hole=52):
    """Pie chart of [{'value','color'}]; falls back to a segmented bar if PieChart is unavailable."""
    total = sum(s["value"] for s in slices) or 1
    try:
        sections = [ft.PieChartSection(s["value"], color=s["color"], radius=size / 2 - hole - 2, title="")
                    for s in slices if s["value"] > 0]
        return ft.PieChart(sections=sections, sections_space=2, center_space_radius=hole, width=size, height=size)
    except Exception:  # pragma: no cover - depends on the installed flet version
        return ft.Row([ft.Container(expand=max(1, round(s["value"] / total * 100)), height=18, bgcolor=s["color"])
                       for s in slices if s["value"] > 0], spacing=2, width=size)


# ------------------------------------------------------- page-level helpers
def toast(page, message):
    page.open(ft.SnackBar(ft.Text(str(message))))


def confirm(page, title, message, on_yes, yes_label="حذف"):
    dlg = ft.AlertDialog(modal=True, title=ft.Text(title), content=ft.Text(message))

    def yes(e):
        page.close(dlg)
        on_yes()

    dlg.actions = [ft.TextButton("إلغاء", on_click=lambda e: page.close(dlg)),
                   ft.TextButton(yes_label, on_click=yes, style=ft.ButtonStyle(color=T.EXPENSE))]
    page.open(dlg)
    return dlg


# ----------------------------------------------------------------- file dialogs
def _picker(ui):
    """One FilePicker per page (re-adding a new one on every click is what made later picks unreliable)."""
    fp = getattr(ui.page, "_masarif_picker", None)
    if fp is None:
        fp = ft.FilePicker()
        ui.page.overlay.append(fp)
        ui.page._masarif_picker = fp
        ui.page.update()
    return fp


def pick_file(ui, on_path, extensions=None, title="اختر ملف"):
    """Open the system file picker; on_path(path) is called with the chosen file path.
    Any exception inside on_path is shown on screen instead of vanishing silently in the handler thread."""
    def result(e):
        if not e.files:
            return
        path = e.files[0].path
        if not path:
            ui.toast("هذا الجهاز ما أعطانا مسار الملف. انسخ الملف لمجلد عادي وجرب مرة ثانية")
            return
        try:
            on_path(path)
        except Exception as ex:  # pragma: no cover - UI safety net
            import traceback
            ui.toast(f"خطأ بقراءة الملف: {type(ex).__name__}: {ex}")
            print(traceback.format_exc())

    fp = _picker(ui)
    fp.on_result = result
    fp.pick_files(dialog_title=title, allowed_extensions=extensions, allow_multiple=False)


def save_file(ui, file_name, on_path, extensions=None, title="احفظ الملف"):
    def result(e):
        if e.path:
            on_path(e.path)

    fp = _picker(ui)
    fp.on_result = result
    fp.save_file(dialog_title=title, file_name=file_name, allowed_extensions=extensions)


def dropdown(label_text, options, value, on_change):
    """options: [(key, text)]."""
    return ft.Dropdown(label=label_text, value=value, on_change=on_change, border_radius=14, border_color=T.LINE,
                       bgcolor=T.CARD, filled=True, text_size=14,
                       options=[ft.dropdown.Option(key=k, text=t) for k, t in options])


# ------------------------------------------------------------------- calendar
def pick_date(ui, initial, on_pick):
    """Open the calendar; on_pick('YYYY-MM-DD') is called with the chosen day."""
    from datetime import datetime, timedelta
    try:
        init = datetime.strptime(initial or "", "%Y-%m-%d")
    except ValueError:
        init = datetime.now()

    def changed(e):
        d = e.control.value
        if d is None:
            return
        if getattr(d, "hour", 0) >= 12:  # some platforms return local midnight as the previous evening in UTC
            d = d + timedelta(days=1)
        on_pick(d.strftime("%Y-%m-%d"))

    dp = ft.DatePicker(first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31), value=init, on_change=changed)
    ui.page.open(dp)


class DateInput:
    """A field-looking tile that opens the calendar. Read .value ('' when empty) and put .control in a layout."""

    def __init__(self, ui, label_text, value="", clearable=False, on_change=None):
        self.ui, self.label, self.value, self.on_change = ui, label_text, value or "", on_change
        self.text = ft.Text(self.value or "اختر التاريخ", size=15, weight=ft.FontWeight.W_500,
                            color=T.INK if self.value else T.FAINT)
        right = [icon("calendar_month", 22, T.PRIMARY)]
        if clearable:
            right.insert(0, icon_btn("close", self._clear, color=T.MUTED, size=18))
        self.control = ft.Container(
            content=between(col([txt(label_text, 12, color=T.MUTED), self.text], spacing=1), row(right, spacing=0)),
            padding=ft.padding.symmetric(horizontal=14, vertical=9), border_radius=14, bgcolor=T.CARD, ink=True,
            border=ft.border.all(1, T.LINE), on_click=self._open)

    def _open(self, e):
        pick_date(self.ui, self.value, self.set)

    def _clear(self, e):
        self.set("")

    def set(self, iso):
        self.value = iso
        self.text.value = iso or "اختر التاريخ"
        self.text.color = T.INK if iso else T.FAINT
        if self.on_change:
            self.on_change(iso)
        self.ui.page.update()


def confirm_typed(page, title, message, word, on_yes, yes_label="مسح"):
    """Destructive confirmation: the action button only works after typing `word`."""
    box = ft.TextField(hint_text=f"اكتب «{word}» للتأكيد", border_radius=12, text_size=14)
    dlg = ft.AlertDialog(modal=True, title=ft.Text(title), content=ft.Column([ft.Text(message), box], tight=True, spacing=12))

    def yes(e):
        if box.value.strip() != word:
            box.error_text = f"اكتب {word} بالضبط"
            page.update()
            return
        page.close(dlg)
        on_yes()

    dlg.actions = [ft.TextButton("إلغاء", on_click=lambda e: page.close(dlg)),
                   ft.TextButton(yes_label, on_click=yes, style=ft.ButtonStyle(color=T.EXPENSE))]
    page.open(dlg)


def pick_time(ui, initial, on_pick):
    """Clock picker; on_pick('HH:MM')."""
    from datetime import time
    try:
        h, m = (int(x) for x in (initial or "21:00").split(":"))
    except ValueError:
        h, m = 21, 0

    def changed(e):
        v = e.control.value
        if v is not None:
            on_pick(f"{v.hour:02d}:{v.minute:02d}")

    ui.page.open(ft.TimePicker(value=time(h, m), on_change=changed))
