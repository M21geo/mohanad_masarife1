"""Daily reminder content. Pure logic; the UI decides how to show it (in-app dialog)."""
from datetime import datetime, timedelta
from typing import Optional

from . import money
from .debts import Debts
from .repo import Repo


def settings(repo: Repo) -> dict:
    return {"enabled": repo.get_setting("reminder_enabled", "0") == "1",
            "time": repo.get_setting("reminder_time", "21:00") or "21:00"}


def lines(repo: Repo, today: str) -> list:
    """What is worth reminding about right now (empty = nothing)."""
    out = []
    if not repo.conn.execute("SELECT 1 FROM transactions WHERE date=? LIMIT 1", (today,)).fetchone():
        out.append("ما سجلت أي معاملة اليوم. سجّل مصاريفك قبل لا تنسى 📝")
    tomorrow = (datetime.fromisoformat(today) + timedelta(days=1)).date().isoformat()
    for d in Debts(repo).list_debts(include_settled=False, today=today):
        if d["due_date"] and d["due_date"] <= tomorrow:
            amt = money.fmt(d["next_amount"] or d["remaining"], d["currency"])
            when = "متأخر" if d["due_date"] < today else ("يستحق اليوم" if d["due_date"] == today else "يستحق غداً")
            who = "عليك لـ" if d["direction"] == "on" else "لك عند"
            out.append(f"دين {who} {d['person_name']} ({amt}) {when}")
    return out


def due(repo: Repo, now: Optional[datetime] = None) -> list:
    """Reminder lines to show now, or [] (disabled, too early, already shown today, or nothing to say).
    Does NOT mark as shown - call mark_shown() when the user actually saw it."""
    now = now or datetime.now()
    cfg = settings(repo)
    if not cfg["enabled"] or now.strftime("%H:%M") < cfg["time"]:
        return []
    today = now.date().isoformat()
    if repo.get_setting("reminder_last") == today:
        return []
    return lines(repo, today)


def mark_shown(repo: Repo, now: Optional[datetime] = None) -> None:
    repo.set_setting("reminder_last", (now or datetime.now()).date().isoformat())
