"""Aprobaciones (human-in-the-loop)."""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.core.errors import ApiError
from app.core.timeutil import iso, utcnow
from app.models.cases import Approval
from app.schemas.backoffice import ApprovalDecisionIn, ApprovalIn
from app.services import audit, events

router = APIRouter(prefix="/v1/approvals", tags=["aprobaciones"])


def _ser(a: Approval) -> dict:
    return {
        "id": str(a.id), "approval_type": a.approval_type, "entity": a.entity, "entity_id": str(a.entity_id) if a.entity_id else None,
        "title": a.title, "amount_cents": a.amount_cents, "status": a.status, "requested_by": str(a.requested_by) if a.requested_by else None,
        "decided_by": str(a.decided_by) if a.decided_by else None, "decided_at": iso(a.decided_at), "note": a.note, "decision_note": a.decision_note,
        "created_at": iso(a.created_at), "payload": a.payload,
    }


@router.get("")
def list_approvals(status: str | None = None, _: CurrentUser = Depends(require("approvals.read")), db: Session = Depends(get_db)):
    q = db.query(Approval)
    if status:
        q = q.filter(Approval.status == status)
    return [_ser(a) for a in q.order_by(Approval.created_at.desc()).all()]


@router.post("", status_code=201)
def create_approval(data: ApprovalIn, current: CurrentUser = Depends(require("approvals.read", "cases.update")), db: Session = Depends(get_db)):
    a = Approval(approval_type=data.approval_type, title=data.title, amount_cents=data.amount_cents, entity=data.entity, entity_id=data.entity_id, note=data.note, requested_by=current.id)
    db.add(a)
    db.flush()
    events.emit(db, "ApprovalRequested", actor_id=current.id, entity="approval", entity_id=a.id, payload={"type": a.approval_type, "amount_cents": a.amount_cents})
    db.commit()
    return _ser(a)


@router.post("/{approval_id}/decision")
def decide(approval_id: uuid.UUID, data: ApprovalDecisionIn, request: Request, current: CurrentUser = Depends(require("approvals.decide")), db: Session = Depends(get_db)):
    a = db.get(Approval, approval_id)
    if a is None:
        raise ApiError("NOT_FOUND", "Aprobación no encontrada")
    if a.status != "pending":
        raise ApiError("CONFLICT", "La aprobación ya fue decidida")
    if a.requested_by == current.id and current.role != "admin":
        raise ApiError("FORBIDDEN", "Quien solicita no puede aprobar (segregación de funciones)")
    before = a.status
    a.status = "approved" if data.decision == "approve" else "rejected"
    a.decided_by = current.id
    a.decided_at = utcnow()
    a.decision_note = data.note
    events.emit(db, "ApprovalDecided", actor_id=current.id, entity="approval", entity_id=a.id, payload={"decision": data.decision, "note": data.note})
    audit.log(db, actor_id=current.id, action="approval.decide", entity="approval", entity_id=a.id, before={"status": before}, after={"status": a.status}, reason=data.note, ip=client_ip(request))
    db.commit()
    return _ser(a)
