"""Idempotencia de escrituras (§4).

`run_idempotent(db, key, user_id, payload, fn)`:
- si la clave no existe: ejecuta `fn()` (que escribe en la sesión), guarda la respuesta y hace commit;
- si existe con el mismo hash de payload: devuelve la respuesta guardada con `duplicate: true`;
- si existe con payload distinto: 409 IDEMPOTENCY_CONFLICT.
Si `fn` falla no se guarda la clave (el cliente puede reintentar).
"""
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.models.system import IdempotencyKey
from app.services.events import _jsonable


@dataclass
class IdemResult:
    body: dict
    status_code: int
    duplicate: bool


def request_hash(payload: Any) -> str:
    data = _jsonable(payload)
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != "idempotency_key"}
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_idempotent(
    db: Session,
    key: str,
    user_id: uuid.UUID | None,
    payload: Any,
    fn: Callable[[], tuple[dict, int]],
) -> IdemResult:
    h = request_hash(payload)
    existing = db.get(IdempotencyKey, key)
    if existing is not None:
        return _replay(existing, h, user_id)

    body, status = fn()
    body = _jsonable(body)
    db.add(IdempotencyKey(key=key, user_id=user_id, request_hash=h, response=body, status_code=status, created_at=utcnow()))
    try:
        db.commit()
    except IntegrityError:
        # Carrera: otra petición con la misma clave ganó. Devolvemos su resultado.
        db.rollback()
        existing = db.get(IdempotencyKey, key)
        if existing is None:
            raise
        return _replay(existing, h, user_id)
    return IdemResult(body=body, status_code=status, duplicate=False)


def _replay(existing: IdempotencyKey, h: str, user_id: uuid.UUID | None) -> IdemResult:
    # La clave pertenece a quien la creó: otro usuario con la misma clave nunca recibe su respuesta.
    if existing.user_id != user_id:
        raise ApiError("IDEMPOTENCY_CONFLICT", "La clave de idempotencia pertenece a otro usuario", details={"idempotency_key": existing.key})
    if existing.request_hash != h:
        raise ApiError("IDEMPOTENCY_CONFLICT", details={"idempotency_key": existing.key})
    body = dict(existing.response)
    body["duplicate"] = True
    return IdemResult(body=body, status_code=200, duplicate=True)
