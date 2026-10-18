"""Start over: clear data from the main app (a safety backup should be written first by the caller)."""
from .backup import TABLES
from .repo import Repo
from .seed import ensure_defaults


def clear_transactions(repo: Repo) -> None:
    """Delete every transaction and debt. Wallets (back to their opening balance), categories, people,
    notes, budgets and recurring rules stay."""
    with repo.conn:
        for t in ("debt_payments", "debts", "transactions"):
            repo.conn.execute(f"DELETE FROM {t}")


def factory_reset(repo: Repo) -> None:
    """Wipe everything and re-create the starter wallets and categories. Keeps the exchange rate and display choices."""
    keep = {k: repo.get_setting(k) for k in ("rate", "display_currency", "hide_balances", "auto_backup",
                                             "reminder_enabled", "reminder_time")}
    with repo.conn:
        for t in reversed(TABLES):
            repo.conn.execute(f"DELETE FROM {t}")
        repo.conn.execute("DELETE FROM sqlite_sequence")
    ensure_defaults(repo)
    for k, v in keep.items():
        if v is not None:
            repo.set_setting(k, v)
