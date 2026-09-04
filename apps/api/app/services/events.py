"""Outbox de eventos de dominio (§7). Append-only."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.system import Event

EVENT_TYPES = {
    "ShiftOpened", "ShiftClosed", "ShiftTransferred", "SaleRecorded", "SaleCancelled", "PaymentRecorded",
    "WasteRecorded", "InventoryMoved", "CashDifferenceDetected", "PointLate", "PointOffline", "HelpRequested",
    "AlertRaised", "AlertResolved", "AuditCompleted", "MaintenanceTicketCreated", "LotBlocked",
    "ApprovalRequested", "ApprovalDecided", "AIRecommendationCreated",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {(str(k) if isinstance(k, uuid.UUID) else k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def emit(
    db: Session,
    type_: str,
    *,
    actor_id: uuid.UUID | None = None,
    point_id: uuid.UUID | None = None,
    shift_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict | None = None,
    occurred_at: datetime | None = None,
) -> Event:
    assert type_ in EVENT_TYPES, f"Tipo de evento desconocido: {type_}"
    ev = Event(
        type=type_,
        occurred_at=occurred_at or utcnow(),
        actor_id=actor_id,
        point_id=point_id,
        shift_id=shift_id,
        entity=entity,
        entity_id=entity_id,
        payload=_jsonable(payload or {}),
        created_at=utcnow(),
    )
    db.add(ev)
    return ev
