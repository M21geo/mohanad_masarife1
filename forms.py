"""Small form helpers: a re-renderable bottom sheet and chip pickers."""
import flet as ft

from . import kit, theme as T


class FormSheet:
    """Bottom sheet whose controls are rebuilt on render() (so chips can show selection).

    controls_fn() -> list of controls; save_fn() -> True to close (False/None keeps it open).
    Text fields should be created ONCE by the caller (so typed text survives render())."""

    def __init__(self, ui, title, controls_fn, save_fn, save_label="حفظ", extra=None, height=None):
        self.ui, self.controls_fn, self.save_fn = ui, controls_fn, save_fn
        self.title, self.save_label, self.extra, self.height = title, save_label, extra, height
        self.body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        self.sheet = None

    def open(self):
        self.sheet = self.ui.open_sheet(self.body, height=self.height)
        self.render()
        return self

    def close(self):
        self.ui.page.close(self.sheet)

    def render(self):
        parts = [kit.txt(self.title, 20, True)] + list(self.controls_fn())
        parts.append(kit.big_button(self.save_label, self._save))
        if self.extra:
            parts.append(self.extra)
        self.body.controls = parts
        self.ui.page.update()

    def _save(self, e):
        ok = self.ui.guard(self.save_fn)
        if ok:
            self.close()
            self.ui.refresh()


def label(text):
    return kit.txt(text, 13, True, T.MUTED)


def choices(options, selected, on_pick, color=T.PRIMARY):
    """options: [(key, label)] -> wrapped row of chips."""
    return ft.Row([kit.chip(l, k == selected, lambda e, k=k: on_pick(k), color=color) for k, l in options],
                  wrap=True, spacing=8, run_spacing=8)


def date_field(ui, label_text, value="", clearable=False):
    """Calendar-based date input (use .control in layouts, .value for the ISO date)."""
    return kit.DateInput(ui, label_text, value, clearable)
