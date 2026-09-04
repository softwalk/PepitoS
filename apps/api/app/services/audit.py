"""audit_log para cambios críticos (§7)."""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.system import AuditLog
from app.services.events import _jsonable


def log(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
    ip: str | None = None,
    device_id: str | None = None,
) -> AuditLog:
    row = AuditLog(
        at=utcnow(),
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=_jsonable(before) if before is not None else None,
        after=_jsonable(after) if after is not None else None,
        reason=reason,
        ip=ip,
        device_id=device_id,
    )
    db.add(row)
    return row
