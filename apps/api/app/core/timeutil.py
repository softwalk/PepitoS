"""Utilidades de tiempo: DB en UTC, "hoy" en la zona configurada (America/Mexico_City)."""
from datetime import date, datetime, time, timedelta, timezone

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_today(now: datetime | None = None) -> date:
    now = now or utcnow()
    return now.astimezone(settings.tz).date()


def local_day_bounds(d: date) -> tuple[datetime, datetime]:
    """Inicio/fin (UTC) del día local `d`."""
    start = datetime.combine(d, time.min, tzinfo=settings.tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def local_dt(d: date, hhmm: str) -> datetime:
    h, m = [int(x) for x in hhmm.split(":")]
    return datetime.combine(d, time(h, m), tzinfo=settings.tz).astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return to_utc(dt).isoformat().replace("+00:00", "Z")


def parse_date(s: str | None) -> date:
    if not s:
        return local_today()
    return date.fromisoformat(s)
