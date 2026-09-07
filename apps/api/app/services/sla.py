"""SLA por severidad de caso: un caso URGENTE debe ser tomado (asignado o en progreso) en `sla_urgent_minutes`; uno
REVISAR en `sla_review_minutes`. Al vencer sin tomar, se marca `payload.sla_breached_at`, se escala (severity → urgent
si era review) y se notifica a Operaciones. NORMAL no tiene SLA."""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.models.cases import Case
from app.services import events
from app.services.settings import get_int


def sla_minutes(db: Session, severity: str) -> int | None:
    if severity == "urgent":
        return get_int(db, "sla_urgent_minutes")
    if severity == "review":
        return get_int(db, "sla_review_minutes")
    return None


def sla_info(c: Case, minutes: int | None, now: datetime | None = None) -> dict:
    """{due_at, remaining_min, breached, taken} para mostrar en Excepciones/Supervisor/Control Tower."""
    now = now or utcnow()
    taken = c.assignee_id is not None or c.status in ("in_progress", "resolved", "closed")
    if minutes is None or c.status in ("resolved", "closed"):
        return {"due_at": None, "remaining_min": None, "breached": False, "taken": taken, "minutes": minutes}
    due = c.opened_at + timedelta(minutes=minutes)
    remaining = int((due - now).total_seconds() // 60)
    breached = bool((c.payload or {}).get("sla_breached_at")) or (not taken and remaining < 0)
    return {"due_at": iso(due), "remaining_min": remaining, "breached": breached, "taken": taken, "minutes": minutes}


def check_sla(db: Session, now: datetime | None = None) -> list[Case]:
    """Escala los casos abiertos sin tomar cuyo SLA venció. Devuelve los casos escalados en esta corrida."""
    now = now or utcnow()
    limits = {"urgent": get_int(db, "sla_urgent_minutes"), "review": get_int(db, "sla_review_minutes")}
    q = db.query(Case).filter(Case.status == "open", Case.assignee_id.is_(None), Case.severity.in_(list(limits)))
    escalated = []
    for c in q.all():
        if (c.payload or {}).get("sla_breached_at"):
            continue
        due = c.opened_at + timedelta(minutes=limits[c.severity])
        if due > now:
            continue
        payload = dict(c.payload or {})
        payload["sla_breached_at"] = iso(now)
        payload["sla_original_severity"] = c.severity
        c.payload = payload
        if c.severity == "review":
            c.severity = "urgent"
        c.impact_score = float(c.impact_score or 0) + 10
        events.emit(db, "CaseSlaBreached", point_id=c.point_id, shift_id=c.shift_id, entity="case", entity_id=c.id,
                    payload={"severity": c.severity, "minutes": limits[payload["sla_original_severity"]], "title": c.title}, occurred_at=now)
        escalated.append(c)
    db.flush()
    return escalated
