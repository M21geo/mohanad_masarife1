"""History archives: old data kept in SEPARATE database files ("هستوري 1", "هستوري 2", ...).

An archive has its own wallets, categories and people (taken from the imported file) and never touches
the main app's balances, categories, people, budgets or backups. It can be opened and browsed with the same
list / filters / statistics as the main data.
"""
import json
import os
from datetime import datetime
from typing import Optional

from .db import connect
from .repo import AppError, NotFound, Repo


class Histories:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self._index_path = os.path.join(folder, "index.json")

    # ----------------------------------------------------------- index file
    def _load(self) -> dict:
        try:
            with open(self._index_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
        except (OSError, ValueError):
            pass
        return {"next": 1, "items": []}

    def _save(self, data: dict) -> None:
        tmp = self._index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._index_path)

    def _path(self, item: dict) -> str:
        return os.path.join(self.folder, item["file"])

    # ------------------------------------------------------------------ API
    def create(self, name: Optional[str] = None, rate: Optional[float] = None, draft: bool = False) -> dict:
        """New empty archive (numbered). `draft` ones are hidden until finalize() (used while previewing an import)."""
        data = self._load()
        n = data["next"]
        item = {"id": n, "name": (name or "").strip() or f"هستوري {n}", "file": f"history_{n}.db",
                "created": datetime.now().isoformat(timespec="seconds"), "draft": draft}
        data["next"] = n + 1
        data["items"].append(item)
        self._save(data)
        repo = self.open(n)
        if rate:
            repo.set_rate(rate)
        repo.conn.close()
        return item

    def get(self, hid: int) -> dict:
        item = next((i for i in self._load()["items"] if i["id"] == hid), None)
        if not item:
            raise NotFound("الهستوري غير موجود")
        return item

    def open(self, hid: int) -> Repo:
        return Repo(connect(self._path(self.get(hid))))

    def finalize(self, hid: int) -> None:
        data = self._load()
        for i in data["items"]:
            if i["id"] == hid:
                i["draft"] = False
        self._save(data)

    def list(self, include_drafts: bool = False) -> list:
        out = []
        for item in self._load()["items"]:
            if item.get("draft") and not include_drafts:
                continue
            info = dict(item, tx_count=0, date_from=None, date_to=None)
            try:
                repo = self.open(item["id"])
                row = repo.conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM transactions").fetchone()
                info.update(tx_count=row[0], date_from=row[1], date_to=row[2])
                repo.conn.close()
            except Exception:
                pass
            out.append(info)
        return out

    def rename(self, hid: int, name: str) -> None:
        if not name.strip():
            raise AppError("اسم الهستوري مطلوب")
        data = self._load()
        for i in data["items"]:
            if i["id"] == hid:
                i["name"] = name.strip()
                self._save(data)
                return
        raise NotFound("الهستوري غير موجود")

    def delete(self, hid: int) -> None:
        item = self.get(hid)
        data = self._load()
        data["items"] = [i for i in data["items"] if i["id"] != hid]
        self._save(data)
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                os.remove(self._path(item) + suffix)
            except OSError:
                pass

    def purge_drafts(self) -> None:
        for i in self._load()["items"]:
            if i.get("draft"):
                self.delete(i["id"])
