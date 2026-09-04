"""Casos, alertas y acciones. Incluye "NECESITO AYUDA" con clasificación IA trazable."""
import uuid
from datetime import datetime

from sqlalchemy.orm import Session, object_session

from app.ai.classifier import classify_help_text
from app.core.config import settings
from app.core.errors import ApiError
from app.core.timeutil import iso, local_today, utcnow
from app.models.cases import Action, AIRecommendation, Alert, Case, Rule
from app.models.ops import Shift
from app.models.org import Point, User
from app.services import audit, events
from app.services import evidence as evidence_svc
from app.services.priority import age_minutes, priority_score

# Umbrales de caja e inventario viven en `settings` (B6): cash_difference_threshold_cents,
# cash_difference_severe_cents, inventory_count_tolerance_units. Si se definen explícitamente en
# rules.params (`threshold_cents`, `severe_cents`, `units`) tienen precedencia sobre settings.
DEFAULT_RULE_PARAMS = {
    "no_open": {"grace_minutes": 20},
    "out_of_geofence": {"minutes": 10},
    "low_sales_trajectory": {"pct": 60, "min_hours": 2},
    "high_waste": {"pct": 4},
    "cash_difference": {},
    "inventory_inconsistent": {},
    "low_battery": {"warn": 25, "critical": 10},
    "anomalous_cancellations": {"count": 3, "pct": 10},
    "sync_stale": {"minutes": 30},
    "maintenance_overdue": {},
    "stock_critical": {"min_units": 10},
}

HELP_SEVERITY = {
    "security": "urgent",
    "battery": "review",
    "cart": "review",
    "payment": "review",
    "product": "review",
    "other": "normal",
}
HELP_IMPACT = {"security": 50, "battery": 20, "cart": 15, "payment": 20, "product": 10, "other": 5}
HELP_TITLES = {
    "security": "Incidente de seguridad",
    "battery": "Problema de batería",
    "cart": "Problema con el carrito",
    "product": "Problema con producto",
    "payment": "Problema de cobro",
    "other": "Solicitud de ayuda",
}


def get_rule_params(db: Session, key: str) -> dict:
    rule = db.get(Rule, key)
    params = dict(DEFAULT_RULE_PARAMS.get(key, {}))
    if rule is not None:
        params.update(rule.params or {})
    return params


def dedupe_key_for(rule_key: str, point_id: uuid.UUID | None, when: datetime | None = None) -> str:
    d = (when or utcnow()).astimezone(settings.tz).date().isoformat()
    return f"{rule_key}:{point_id}:{d}"


def find_open_case(db: Session, dedupe_key: str) -> Case | None:
    return (
        db.query(Case)
        .filter(Case.dedupe_key == dedupe_key, Case.status.in_(("open", "in_progress")))
        .first()
    )


def open_case_if_new(
    db: Session,
    *,
    rule_key: str,
    point_id: uuid.UUID | None,
    severity: str,
    title: str,
    description: str,
    shift_id: uuid.UUID | None = None,
    impact_score: float = 0,
    source: str = "rule",
    payload: dict | None = None,
    dedupe_date: datetime | None = None,
    actor_id: uuid.UUID | None = None,
    category: str | None = None,
) -> Case | None:
    """Crea Alert + Case si no existe caso abierto con el mismo dedupe_key. Devuelve None si ya existía."""
    dk = dedupe_key_for(rule_key, point_id, dedupe_date)
    if find_open_case(db, dk) is not None:
        return None
    now = utcnow()
    case = Case(
        category=category or rule_key,
        severity=severity,
        status="open",
        title=title,
        description=description,
        source=source,
        rule_key=rule_key,
        dedupe_key=dk,
        point_id=point_id,
        shift_id=shift_id,
        opened_at=now,
        impact_score=impact_score,
        created_by=actor_id,
        payload=payload or {},
    )
    db.add(case)
    db.flush()
    alert = Alert(
        rule_key=rule_key, severity=severity, message=title, dedupe_key=dk, point_id=point_id, shift_id=shift_id,
        case_id=case.id, raised_at=now, payload=payload or {},
    )
    db.add(alert)
    db.flush()
    events.emit(
        db, "AlertRaised", actor_id=actor_id, point_id=point_id, shift_id=shift_id, entity="alert", entity_id=alert.id,
        payload={"rule_key": rule_key, "severity": severity, "case_id": case.id, "title": title},
    )
    return case


def create_help_case(db: Session, user: User, data, shift: Shift | None) -> Case:
    """Botón NECESITO AYUDA. Seguridad → urgente. "otro" → clasificador IA (sólo sugiere)."""
    now = utcnow()
    occurred = data.occurred_at or now
    category = data.category
    severity = HELP_SEVERITY[category]
    point_id = shift.point_id if shift else None
    ai_info = None
    if category == "other":
        ai_info = classify_help_text(data.note or "")
    case = Case(
        category=category,
        severity=severity,
        status="open",
        title=HELP_TITLES[category],
        description=data.note or "",
        source="operator",
        point_id=point_id,
        shift_id=shift.id if shift else None,
        opened_at=occurred,
        impact_score=HELP_IMPACT[category],
        created_by=user.id,
        payload={
            "gps": data.gps.model_dump(mode="json") if data.gps else None,
            "has_photo": bool(data.photo_base64),
            "idempotency_key": data.idempotency_key,
        },
    )
    if ai_info and ai_info["category"] != "other":
        case.ai_suggested_category = ai_info["category"]
        case.ai_confidence = ai_info["confidence"]
        # Si la confianza es alta, la sugerencia eleva la severidad pero no cambia la categoría sin humano.
        if ai_info["confidence"] >= 0.7:
            case.severity = HELP_SEVERITY[ai_info["category"]]
    db.add(case)
    db.flush()
    if data.photo_base64:
        ev = evidence_svc.store_photo(
            db, data.photo_base64, kind="help_case", entity="case", entity_id=case.id, uploaded_by=user.id,
            point_id=point_id, shift_id=case.shift_id, taken_at=occurred, field="photo_base64",
        )
        if ev is not None:
            case.payload = {**case.payload, "evidence_ids": [str(ev.id)]}
    if ai_info is not None:
        rec = AIRecommendation(
            entity="case", entity_id=case.id, model_version=ai_info["model_version"],
            inputs={"text": data.note or ""}, output={"category": ai_info["category"]},
            confidence=ai_info["confidence"], created_at=now,
        )
        db.add(rec)
        db.flush()
        events.emit(
            db, "AIRecommendationCreated", actor_id=user.id, point_id=point_id, shift_id=case.shift_id,
            entity="ai_recommendation", entity_id=rec.id,
            payload={"case_id": case.id, "category": ai_info["category"], "confidence": ai_info["confidence"], "model_version": ai_info["model_version"]},
        )
    events.emit(
        db, "HelpRequested", actor_id=user.id, point_id=point_id, shift_id=case.shift_id, entity="case",
        entity_id=case.id, payload={"category": category, "severity": case.severity}, occurred_at=occurred,
    )
    if shift is not None:
        shift.last_seen_at = now
    return case


def serialize_action(a: Action) -> dict:
    return {
        "id": str(a.id),
        "case_id": str(a.case_id) if a.case_id else None,
        "audit_id": str(a.audit_id) if a.audit_id else None,
        "description": a.description,
        "owner_id": str(a.owner_id) if a.owner_id else None,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "status": a.status,
        "done_at": iso(a.done_at),
    }


def serialize_case(c: Case, now: datetime | None = None) -> dict:
    now = now or utcnow()
    point = c.point
    assignee = c.assignee
    return {
        "id": str(c.id),
        "category": c.category,
        "severity": c.severity,
        "status": c.status,
        "title": c.title,
        "description": c.description,
        "source": c.source,
        "rule_key": c.rule_key,
        "point": {"id": str(point.id), "name": point.display_name} if point else None,
        "shift_id": str(c.shift_id) if c.shift_id else None,
        "opened_at": iso(c.opened_at),
        "resolved_at": iso(c.resolved_at),
        "age_minutes": age_minutes(c.opened_at, now),
        "impact_score": c.impact_score,
        "priority_score": priority_score(c.severity, c.impact_score, c.opened_at, now),
        "assignee": {"id": str(assignee.id), "name": assignee.name} if assignee else None,
        "actions": [serialize_action(a) for a in c.actions],
        "ai": {"suggested_category": c.ai_suggested_category, "confidence": c.ai_confidence}
        if c.ai_suggested_category
        else None,
        "resolution": c.resolution,
        "payload": c.payload,
        "evidence": _case_evidence(c),
    }


def _case_evidence(c: Case) -> list[dict]:
    db = object_session(c)
    if db is None:
        return []
    return evidence_svc.serialize_for(db, "case", c.id)


def update_case(db: Session, case: Case, actor_id: uuid.UUID, patch: dict, ip: str | None = None) -> Case:
    before = {"status": case.status, "severity": case.severity, "category": case.category, "assignee_id": str(case.assignee_id) if case.assignee_id else None}
    if "assignee_id" in patch and patch["assignee_id"] is not None:
        if db.get(User, patch["assignee_id"]) is None:
            raise ApiError("NOT_FOUND", "Usuario asignado no encontrado")
    for field in ("status", "assignee_id", "resolution", "severity", "category"):
        if field in patch and patch[field] is not None:
            setattr(case, field, patch[field])
    if patch.get("category") and case.ai_suggested_category:
        rec = db.query(AIRecommendation).filter(AIRecommendation.entity == "case", AIRecommendation.entity_id == case.id).first()
        if rec is not None:
            rec.accepted = rec.output.get("category") == patch["category"]
    if patch.get("status") in ("resolved", "closed") and case.resolved_at is None:
        case.resolved_at = utcnow()
        for alert in db.query(Alert).filter(Alert.case_id == case.id, Alert.status == "open").all():
            alert.status = "resolved"
            alert.resolved_at = utcnow()
            events.emit(db, "AlertResolved", actor_id=actor_id, point_id=case.point_id, shift_id=case.shift_id, entity="alert", entity_id=alert.id, payload={"case_id": case.id})
    elif patch.get("status") in ("open", "in_progress"):
        case.resolved_at = None
    after = {"status": case.status, "severity": case.severity, "category": case.category, "assignee_id": str(case.assignee_id) if case.assignee_id else None}
    audit.log(db, actor_id=actor_id, action="case.update", entity="case", entity_id=case.id, before=before, after=after, reason=patch.get("resolution"), ip=ip)
    return case


def scope_cases_query(db: Session, current) -> "Query":  # noqa: F821
    q = db.query(Case)
    if current.role == "supervisor":
        q = q.join(Point, Point.id == Case.point_id).filter(Point.zone_id == current.zone_id)
    elif current.role == "operator":
        q = q.filter(Case.created_by == current.id)
    return q


def today_str() -> str:
    return local_today().isoformat()
