"""Prioridad de casos (§6): severity_weight + impact_score + min(age_minutes/30, 20)."""
from datetime import datetime

from app.core.timeutil import utcnow

SEVERITY_WEIGHT = {"urgent": 100, "review": 50, "normal": 10}


def age_minutes(opened_at: datetime, now: datetime | None = None) -> int:
    now = now or utcnow()
    return max(0, int((now - opened_at).total_seconds() // 60))


def priority_score(severity: str, impact_score: float, opened_at: datetime, now: datetime | None = None) -> float:
    age = age_minutes(opened_at, now)
    return round(SEVERITY_WEIGHT.get(severity, 10) + float(impact_score or 0) + min(age / 30, 20), 2)
