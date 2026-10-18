"""Daily reminder: settings + what to remind about. (System/background notifications are NOT part of this
module - see README; this drives the in-app reminder card and the 'time reached' toast.)"""
from datetime import datetime
from typing import Optional

from . import money
from .budgets import Budgets
from .debts import Debts
from .recurring import Recurring
from .repo import AppError, Repo

DEFAULT_TIME = "21:00"


def get_config(repo: Repo) -> dict:
    return {"enabled": repo.get_setting("reminder_enabled", "0") == "1",
            "time": repo.get_setting("reminder_time", DEFAULT_TIME) or DEFAULT_TIME}


def set_config(repo: Repo, enabled: Optional[bool] = None, time: Optional[str] = None) -> None:
    if time is not None:
        try:
            datetime.strptime(time, "%H:%M")
        except ValueError:
            raise AppError("وقت التذكير غير صحيح")
        repo.set_setting("reminder_time", time)
    if enabled is not None:
        repo.set_setting("reminder_enabled", "1" if enabled else "0")


def time_reached(cfg: dict, now: datetime) -> bool:
    return cfg["enabled"] and now.strftime("%H:%M") >= cfg["time"]


def items(repo: Repo, now: datetime) -> list:
    """What to remind about today: [{'icon','text','tone'}]. Empty when reminders are off."""
    cfg = get_config(repo)
    if not cfg["enabled"]:
        return []
    today = now.date().isoformat()
    out = []
    if time_reached(cfg, now) and not repo.list_transactions(date_from=today, date_to=today, limit=1):
        out.append({"icon": "edit_note", "tone": "warn", "text": "ما سجلت أي معاملة اليوم. سجّل مصاريفك قبل ما تنسى"})
    for d in Debts(repo).list_debts(include_settled=False, today=today):
        if not d["due_date"] or d["due_date"] > today:
            continue
        amt = d["next_amount"] or d["remaining"]
        who = d["person_name"]
        what = ("قسط عليك لـ " if d["direction"] == "on" else "قسط لك على ") if d["inst_count"] else ("دين عليك لـ " if d["direction"] == "on" else "دين لك على ")
        when = "يستحق اليوم" if d["due_date"] == today else "متأخر منذ " + d["due_date"]
        out.append({"icon": "event_busy" if d["overdue"] else "event", "tone": "bad" if d["overdue"] else "warn",
                    "text": f"{what}{who}: {money.fmt(amt, d['currency'])} ({when})"})
    ov = Budgets(repo).status(today[:7], today)["overall"]
    if ov and ov["state"] != "ok":
        out.append({"icon": "savings", "tone": "bad" if ov["state"] == "over" else "warn",
                    "text": ("تجاوزت" if ov["state"] == "over" else "اقتربت من") + f" ميزانية الشهر ({ov['pct']}%)"})
    for r in Recurring(repo).list():
        if r["active"] and r["next_date"]:
            days = (datetime.fromisoformat(r["next_date"]).date() - now.date()).days
            if 0 < days <= 3:
                out.append({"icon": "autorenew", "tone": "neutral",
                            "text": f"{r['note'] or r['category_name'] or 'معاملة تكرارية'}: {money.fmt(r['amount'], r['currency'])} بعد {days} يوم"})
    return out


def message(repo: Repo, now: datetime) -> str:
    its = items(repo, now)
    return " · ".join(i["text"] for i in its[:2]) if its else "تذكير: سجّل مصاريفك اليوم"
