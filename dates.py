"""Date helpers shared by installments and recurring rules (ISO 'YYYY-MM-DD' strings)."""
import calendar
from datetime import date, timedelta


def add_months(iso: str, n: int) -> str:
    d = date.fromisoformat(iso)
    idx = d.year * 12 + (d.month - 1) + n
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def add_period(start: str, frequency: str, k: int) -> str:
    """The k-th occurrence after `start` (k=0 is start itself). Month/year steps keep the original
    day-of-month (31 Jan -> 28 Feb -> 31 Mar)."""
    if frequency == "daily":
        return (date.fromisoformat(start) + timedelta(days=k)).isoformat()
    if frequency == "weekly":
        return (date.fromisoformat(start) + timedelta(weeks=k)).isoformat()
    if frequency == "monthly":
        return add_months(start, k)
    if frequency == "yearly":
        return add_months(start, 12 * k)
    raise ValueError(f"unknown frequency {frequency}")
