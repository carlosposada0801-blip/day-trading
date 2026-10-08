"""US equity market hours (NYSE/Nasdaq regular session)."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
OPEN, CLOSE, EARLY_CLOSE = time(9, 30), time(16, 0), time(13, 0)

# Full-day closures. Update yearly from https://www.nyse.com/markets/hours-calendars
HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
}
EARLY_CLOSES = {date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26)}
KNOWN_YEARS = {d.year for d in HOLIDAYS}


def session(now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """Today's (open, close) in ET, or None if the market is closed all day."""
    now = (now or datetime.now(ET)).astimezone(ET)
    d = now.date()
    if d.weekday() >= 5 or d in HOLIDAYS:
        return None
    close = EARLY_CLOSE if d in EARLY_CLOSES else CLOSE
    return datetime.combine(d, OPEN, ET), datetime.combine(d, close, ET)


def is_open(now: datetime | None = None) -> bool:
    now = (now or datetime.now(ET)).astimezone(ET)
    s = session(now)
    return bool(s) and s[0] <= now < s[1]


def minutes_since_open(now: datetime) -> float:
    s = session(now)
    return (now.astimezone(ET) - s[0]).total_seconds() / 60 if s else -1


def minutes_to_close(now: datetime) -> float:
    s = session(now)
    return (s[1] - now.astimezone(ET)).total_seconds() / 60 if s else -1


def calendar_known(now: datetime | None = None) -> bool:
    return (now or datetime.now(ET)).year in KNOWN_YEARS
