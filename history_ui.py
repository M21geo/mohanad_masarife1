"""A read-only 'UI context' for browsing a history archive with the same screens as the main data."""
from .app import AppUI
from .sheet_tx import show_tx


class HistoryUI(AppUI):
    allow_all_time = True
    cacheable = True  # archive is read-only: scope/statistics results can be reused

    def __init__(self, parent: AppUI, repo, meta: dict):
        super().__init__(parent.page, repo, parent.today)
        self.parent, self.meta = parent, meta
        self.title = meta["name"]
        self.all_time = True
        last = repo.conn.execute("SELECT MAX(date) FROM transactions").fetchone()[0]
        if last:
            self.stats_ym = last[:7]
        self.currency = "IQD"
        self.tx_view = "list"

    def refresh(self) -> None:
        self.parent.refresh()

    def show_tx(self, tx_id: int):
        show_tx(self, tx_id, readonly=True)

    def add_transaction(self, tx=None, kind=None):
        self.toast("هذا أرشيف للعرض فقط")
