"""Backup / restore.

A backup is one JSON file holding every table, so it is human-readable, diff-able
and survives schema upgrades. Restore has two modes:
  - "replace": wipe the app data, then load the file (exact copy, ids preserved)
  - "merge":   add what is missing, matching wallets/categories/people by name and
               skipping transactions/debts/notes that already exist.
"""
import json
import os
from datetime import datetime
from typing import Optional

from .db import SCHEMA_VERSION
from .repo import AppError, Repo

APP_ID = "masarif"
# dependency order: parents before children
TABLES = ["settings", "wallets", "people", "categories", "transactions", "notes", "debts", "debt_payments", "budgets", "recurring"]


def export_data(repo: Repo) -> dict:
    tables = {}
    for t in TABLES:
        tables[t] = [dict(r) for r in repo.conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
    return {"app": APP_ID, "schema": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"), "tables": tables}


def _validate(data: dict) -> None:
    if not isinstance(data, dict) or data.get("app") != APP_ID or not isinstance(data.get("tables"), dict):
        raise AppError("هذا الملف مو نسخة احتياطية من التطبيق")
    if int(data.get("schema", 0)) > SCHEMA_VERSION:
        raise AppError("النسخة من إصدار أحدث من التطبيق. حدّث التطبيق أولاً")


def _insert(conn, table: str, row: dict) -> int:
    cols = list(row)
    cur = conn.execute(
        f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
        [row[c] for c in cols])
    return cur.lastrowid


def import_data(repo: Repo, data: dict, mode: str = "merge") -> dict:
    """Load a backup dict. Returns counts of what was added. All-or-nothing."""
    _validate(data)
    if mode not in ("merge", "replace"):
        raise AppError("وضع الاستعادة غير معروف")
    tables = data["tables"]
    conn = repo.conn
    added = {t: 0 for t in TABLES}
    with conn:
        if mode == "replace":
            for t in reversed(TABLES):
                conn.execute(f"DELETE FROM {t}")
            conn.execute("DELETE FROM sqlite_sequence")
            for t in TABLES:
                rows = tables.get(t, [])
                if t == "categories":  # parents first so the foreign key is satisfied
                    rows = sorted(rows, key=lambda r: (r.get("parent_id") is not None, r["id"]))
                for r in rows:
                    _insert(conn, t, r)
                    added[t] += 1
            return added

        # ---- merge: remap ids by natural keys
        wmap, pmap, cmap, dmap = {}, {}, {}, {}
        for w in tables.get("wallets", []):
            row = conn.execute("SELECT id FROM wallets WHERE name=? AND currency=?",
                               (w["name"], w["currency"])).fetchone()
            if row:
                wmap[w["id"]] = row["id"]
            else:
                wmap[w["id"]] = _insert(conn, "wallets", {k: v for k, v in w.items() if k != "id"})
                added["wallets"] += 1
        for p in tables.get("people", []):
            row = conn.execute("SELECT id FROM people WHERE name=?", (p["name"],)).fetchone()
            if row:
                pmap[p["id"]] = row["id"]
            else:
                pmap[p["id"]] = _insert(conn, "people", {"name": p["name"]})
                added["people"] += 1
        old_cats = {c["id"]: c for c in tables.get("categories", [])}
        for c in sorted(old_cats.values(), key=lambda r: (r["parent_id"] is not None, r["id"])):
            parent_new = cmap.get(c["parent_id"]) if c["parent_id"] else None
            row = conn.execute("SELECT id FROM categories WHERE kind=? AND name=? AND parent_id IS ?",
                               (c["kind"], c["name"], parent_new)).fetchone()
            if row:
                cmap[c["id"]] = row["id"]
            else:
                new = {k: v for k, v in c.items() if k != "id"}
                new["parent_id"] = parent_new
                cmap[c["id"]] = _insert(conn, "categories", new)
                added["categories"] += 1
        for t in tables.get("transactions", []):
            new = {k: v for k, v in t.items() if k != "id"}
            new["wallet_id"] = wmap[t["wallet_id"]]
            new["to_wallet_id"] = wmap.get(t["to_wallet_id"]) if t.get("to_wallet_id") else None
            new["category_id"] = cmap.get(t["category_id"]) if t.get("category_id") else None
            new["person_id"] = pmap.get(t["person_id"]) if t.get("person_id") else None
            new["recurring_id"] = None
            dup = conn.execute(
                "SELECT 1 FROM transactions WHERE date=? AND kind=? AND amount=? AND wallet_id=? "
                "AND to_wallet_id IS ? AND note=?",
                (new["date"], new["kind"], new["amount"], new["wallet_id"], new["to_wallet_id"], new["note"])).fetchone()
            if not dup:
                dmap[("tx", t["id"])] = _insert(conn, "transactions", new)
                added["transactions"] += 1
        for n in tables.get("notes", []):
            if not conn.execute("SELECT 1 FROM notes WHERE text=?", (n["text"],)).fetchone():
                _insert(conn, "notes", {k: v for k, v in n.items() if k != "id"})
                added["notes"] += 1
        for d in tables.get("debts", []):
            person = pmap.get(d["person_id"])
            if person is None:
                continue
            dup = conn.execute(
                "SELECT 1 FROM debts WHERE direction=? AND person_id=? AND currency=? AND total=? AND due_date IS ?",
                (d["direction"], person, d["currency"], d["total"], d["due_date"])).fetchone()
            if dup:
                continue
            new = {k: v for k, v in d.items() if k != "id"}
            new["person_id"] = person
            new["wallet_id"] = wmap.get(d.get("wallet_id")) if d.get("wallet_id") else None
            new["open_tx_id"] = dmap.get(("tx", d.get("open_tx_id"))) if d.get("open_tx_id") else None
            new_id = _insert(conn, "debts", new)
            added["debts"] += 1
            for pay in tables.get("debt_payments", []):
                if pay["debt_id"] == d["id"]:
                    row = {k: v for k, v in pay.items() if k != "id"}
                    row["debt_id"] = new_id
                    row["transaction_id"] = dmap.get(("tx", pay["transaction_id"])) if pay.get("transaction_id") else None
                    _insert(conn, "debt_payments", row)
                    added["debt_payments"] += 1
        for b in tables.get("budgets", []):
            cat = cmap.get(b["category_id"]) if b.get("category_id") else None
            if b.get("category_id") and cat is None:
                continue
            if not conn.execute("SELECT 1 FROM budgets WHERE category_id IS ?", (cat,)).fetchone():
                _insert(conn, "budgets", {"category_id": cat, "currency": b["currency"], "amount": b["amount"]})
                added["budgets"] += 1
        for r in tables.get("recurring", []):
            if r["wallet_id"] not in wmap:
                continue
            new = {k: v for k, v in r.items() if k != "id"}
            new["wallet_id"] = wmap[r["wallet_id"]]
            new["category_id"] = cmap.get(r["category_id"]) if r.get("category_id") else None
            new["person_id"] = pmap.get(r["person_id"]) if r.get("person_id") else None
            if conn.execute("SELECT 1 FROM recurring WHERE kind=? AND wallet_id=? AND amount=? AND frequency=? "
                            "AND start_date=? AND note=?", (new["kind"], new["wallet_id"], new["amount"],
                                                             new["frequency"], new["start_date"], new["note"])).fetchone():
                continue
            _insert(conn, "recurring", new)
            added["recurring"] += 1
        return added


# ------------------------------------------------------------------ files
def write_json_atomic(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def create_backup(repo: Repo, directory: str, keep: int = 7, prefix: str = "masarif",
                  now: Optional[datetime] = None) -> str:
    """Write `<prefix>-YYYYmmdd-HHMMSS.json` into `directory`; keep only the newest `keep`
    files of that prefix. Returns the new file's path."""
    os.makedirs(directory, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory, f"{prefix}-{stamp}.json")
    write_json_atomic(path, export_data(repo))
    old = [b for b in list_backups(directory) if b["name"].startswith(prefix + "-")]
    for b in old[keep:]:
        os.remove(b["path"])
    return path


def list_backups(directory: str) -> list:
    """Backups in `directory`, newest first."""
    if not os.path.isdir(directory):
        return []
    out = []
    for name in os.listdir(directory):
        if name.endswith(".json"):
            p = os.path.join(directory, name)
            st = os.stat(p)
            out.append({"name": name, "path": p, "size": st.st_size, "mtime": st.st_mtime})
    return sorted(out, key=lambda b: (b["name"][-20:], b["mtime"]), reverse=True)


def restore_file(repo: Repo, path: str, mode: str = "merge") -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise AppError("ما كدرت أقرأ ملف النسخة الاحتياطية")
    return import_data(repo, data, mode)


def auto_backup_due(directory: str, every_days: int = 1, now: Optional[datetime] = None) -> bool:
    """True if the newest 'masarif-' backup is older than `every_days` (or none exists)."""
    backups = [b for b in list_backups(directory) if b["name"].startswith("masarif-")]
    if not backups:
        return True
    age = ((now or datetime.now()).timestamp() - backups[0]["mtime"]) / 86400
    return age >= every_days


# -------------------------------------------------------------------- wipe
def wipe(repo: Repo, everything: bool, backup_dir: Optional[str] = None) -> Optional[str]:
    """Start over. A safety backup is written first (returned path).

    everything=False: delete only the transactions, debts and recurring rules; wallets, categories,
                      people, budgets, notes and settings stay (balances go back to the initial amounts).
    everything=True : empty the whole database, then re-create the first-run defaults.
    """
    path = create_backup(repo, backup_dir, keep=3, prefix="pre-wipe") if backup_dir else None
    conn = repo.conn
    with conn:
        tables = TABLES if everything else ["transactions", "debts", "debt_payments", "recurring"]
        for t in reversed(TABLES):
            if t in tables:
                conn.execute(f"DELETE FROM {t}")
        conn.execute("DELETE FROM sqlite_sequence" if everything else
                     "DELETE FROM sqlite_sequence WHERE name IN ('transactions','debts','debt_payments','recurring')")
    if everything:
        from .seed import ensure_defaults
        ensure_defaults(repo)
    return path
