"""Where the app keeps its files (app-private storage on Android, ~/.masarif elsewhere)."""
import os


def data_dir() -> str:
    # Flet sets FLET_APP_STORAGE_DATA to the app's private, persistent folder on mobile/desktop builds.
    base = os.environ.get("FLET_APP_STORAGE_DATA") or os.path.join(os.path.expanduser("~"), ".masarif")
    os.makedirs(base, exist_ok=True)
    return base


def db_path() -> str:
    return os.path.join(data_dir(), "masarif.db")


def backup_dir() -> str:
    path = os.path.join(data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def history_dir() -> str:
    path = os.path.join(data_dir(), "history")
    os.makedirs(path, exist_ok=True)
    return path
