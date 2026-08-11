from __future__ import annotations

from datetime import date, datetime


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def playlist_for_day(base_date: str | date, today: date | None = None) -> int:
    """Return 1 or 2. Base date maps to playlist 1 and alternates daily."""
    if isinstance(base_date, str):
        base_date = parse_date(base_date)
    today = today or date.today()
    days = (today - base_date).days
    return (days % 2) + 1
