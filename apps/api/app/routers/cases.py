"""Casos y acciones correctivas."""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.models.cases import Action, Case
from app.models.org import Point, User
from app.schemas.backoffice import ActionPatch, CasePatch, CorrectiveActionIn
from app.services import audit
from app.services.cases import scope_cases_query, serialize_action, serialize_case, update_case
from app.services.control_tower import serialize_cases

router = APIRouter(prefix="/v1", tags=["casos"])


def _get_case(db: Session, current: CurrentUser, case_id: uuid.UUID) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise ApiError("NOT_FOUND", "Caso no encontrado")
    if current.role == "supervisor":
        point = db.get(Point, case.point_id) if case.point_id else None
        if point is None or point.zone_id != current.zone_id:
            raise ApiError("FORBIDDEN", "El caso no pertenece a tu zona")
    if current.role == "operator" and case.created_by != current.id:
        raise ApiError("FORBIDDEN")
    return case


@router.get("/cases")
def list_cases(status: str | None = None, severity: str | None = None, point_id: uuid.UUID | None = None, current: CurrentUser = Depends(require("cases.read")), db: Session = Depends(get_db)):
    q = scope_cases_query(db, current)
    if status:
        q = q.filter(Case.status.in_(status.split(",")))
    if severity:
        q = q.filter(Case.severity == severity)
    if point_id:
        q = q.filter(Case.point_id == point_id)
    return serialize_cases(q.order_by(Case.opened_at.desc()).limit(500).all(), utcnow())


@router.get("/cases/{case_id}")
def get_case(case_id: uuid.UUID, current: CurrentUser = Depends(require("cases.read", "help.create")), db: Session = Depends(get_db)):
    return serialize_case(_get_case(db, current, case_id))


@router.patch("/cases/{case_id}")
def patch_case(case_id: uuid.UUID, data: CasePatch, request: Request, current: CurrentUser = Depends(require("cases.update")), db: Session = Depends(get_db)):
    case = _get_case(db, current, case_id)
    update_case(db, case, current.id, data.model_dump(exclude_unset=True), ip=client_ip(request))
    db.commit()
    db.refresh(case)
    return serialize_case(case)


@router.post("/cases/{case_id}/actions", status_code=201)
def add_action(case_id: uuid.UUID, data: CorrectiveActionIn, current: CurrentUser = Depends(require("cases.update")), db: Session = Depends(get_db)):
    case = _get_case(db, current, case_id)
    if data.owner_id and db.get(User, data.owner_id) is None:
        raise ApiError("NOT_FOUND", "Responsable no encontrado")
    a = Action(case_id=case.id, description=data.description, owner_id=data.owner_id, due_date=data.due_date, created_by=current.id)
    db.add(a)
    audit.log(db, actor_id=current.id, action="case.action_create", entity="case", entity_id=case.id, after={"description": data.description, "owner_id": str(data.owner_id) if data.owner_id else None, "due_date": data.due_date.isoformat() if data.due_date else None})
    db.commit()
    db.refresh(a)
    return serialize_action(a)


@router.patch("/actions/{action_id}")
def patch_action(action_id: uuid.UUID, data: ActionPatch, current: CurrentUser = Depends(require("cases.update")), db: Session = Depends(get_db)):
    a = db.get(Action, action_id)
    if a is None:
        raise ApiError("NOT_FOUND", "Acción no encontrada")
    if a.case_id:
        _get_case(db, current, a.case_id)
    before = a.status
    a.status = data.status
    a.done_at = utcnow() if data.status == "done" else None
    audit.log(db, actor_id=current.id, action="action.update", entity="action", entity_id=a.id, before={"status": before}, after={"status": a.status})
    db.commit()
    db.refresh(a)
    return serialize_action(a)


from datetime import date as _date  # noqa: E402

from pydantic import BaseModel as _BM, Field as _F  # noqa: E402


class CaseCreateIn(_BM):
    """Caso manual desde el backoffice (p. ej. a partir de un hallazgo de reporte): título, punto, severidad,
    responsable y acción sugerida con fecha."""
    title: str = _F(min_length=4, max_length=200)
    description: str | None = None
    point_id: uuid.UUID | None = None
    severity: str = _F(default="review", pattern="^(urgent|review|normal)$")
    category: str = _F(default="other", max_length=40)
    assignee_id: uuid.UUID | None = None
    action: str | None = _F(default=None, max_length=300)
    action_due_date: _date | None = None
    source_ref: str | None = _F(default=None, max_length=200)  # p. ej. "report:points?point_id=…"


@router.post("/cases", status_code=201)
def create_case(data: CaseCreateIn, request: Request, current: CurrentUser = Depends(require("cases.update")), db: Session = Depends(get_db)):
    from app.services.cases import open_case_if_new

    if data.point_id is not None:
        point = db.get(Point, data.point_id)
        if point is None:
            raise ApiError("NOT_FOUND", "Punto no encontrado")
        if current.role == "supervisor" and point.zone_id != current.zone_id:
            raise ApiError("FORBIDDEN", "El punto no pertenece a tu zona")
    now = utcnow()
    case = open_case_if_new(
        db, rule_key=f"manual:{uuid.uuid4().hex[:8]}", point_id=data.point_id, severity=data.severity, category=data.category, title=data.title,
        description=data.description or data.title, source="supervisor", actor_id=current.id, dedupe_date=now, payload={"source_ref": data.source_ref} if data.source_ref else {},
    )
    assert case is not None
    if data.assignee_id is not None:
        if db.get(User, data.assignee_id) is None:
            raise ApiError("NOT_FOUND", "Responsable no encontrado")
        case.assignee_id = data.assignee_id
        case.status = "in_progress"
    if data.action:
        db.add(Action(case_id=case.id, description=data.action, owner_id=data.assignee_id or current.id, due_date=data.action_due_date, status="pending", created_by=current.id))
    audit.log(db, actor_id=current.id, action="case.create", entity="case", entity_id=case.id, after={"title": data.title, "severity": data.severity, "point_id": str(data.point_id) if data.point_id else None, "source_ref": data.source_ref}, ip=client_ip(request))
    db.commit()
    db.refresh(case)
    return serialize_case(case)
