"""Evidencias (fotos) en object storage (B4).

Entrada: data URL (`data:image/jpeg;base64,...`) o base64 puro. Se valida el tipo real por firma
(JPEG/PNG/WebP), el tamaño (`EVIDENCE_MAX_BYTES`) y se guarda sólo la referencia en `evidence`.
"""
import base64
import binascii
import hashlib
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.timeutil import iso, utcnow
from app.models.org import Point
from app.models.system import Evidence
from app.services import settings as settings_svc
from app.services.storage import get_storage

KINDS = {"help_case", "shift_open", "shift_close", "audit", "case_note"}
ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_DATA_URL = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+)?(?:;[\w-]+=[\w-]+)*(?:;base64)?,(?P<data>.*)$", re.DOTALL)


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_image(raw: str, *, field: str = "photo") -> tuple[bytes, str]:
    """Devuelve (bytes, content_type). 422 VALIDATION si no es una imagen válida o excede el máximo."""
    if not isinstance(raw, str) or not raw.strip():
        raise ApiError("VALIDATION", "La foto está vacía", details={"field": field})
    s = raw.strip()
    m = _DATA_URL.match(s)
    if m:
        s = m.group("data")
    # base64 "puro": tolera saltos de línea/espacios y URL-safe
    s = re.sub(r"\s+", "", s).replace("-", "+").replace("_", "/")
    max_bytes = settings.EVIDENCE_MAX_BYTES
    # 4 chars base64 = 3 bytes; corta antes de decodificar algo enorme
    if len(s) * 3 // 4 > max_bytes + 3:
        raise ApiError("VALIDATION", f"La foto excede el máximo de {max_bytes // (1024 * 1024)} MB", details={"field": field, "max_bytes": max_bytes})
    s += "=" * (-len(s) % 4)
    try:
        data = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("VALIDATION", "La foto no es base64 válido", details={"field": field})
    if len(data) > max_bytes:
        raise ApiError("VALIDATION", f"La foto excede el máximo de {max_bytes // (1024 * 1024)} MB", details={"field": field, "max_bytes": max_bytes, "size_bytes": len(data)})
    ctype = sniff(data)
    if ctype not in ALLOWED_TYPES:
        raise ApiError("VALIDATION", "Formato de imagen no permitido (JPEG, PNG o WebP)", details={"field": field})
    return data, ctype


def store_photo(
    db: Session,
    raw: str,
    *,
    kind: str,
    entity: str,
    entity_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    point_id: uuid.UUID | None = None,
    shift_id: uuid.UUID | None = None,
    taken_at: datetime | None = None,
    field: str = "photo",
) -> Evidence | None:
    """Valida, sube al storage y crea la fila `evidence`. Con `STORAGE_BACKEND=none` valida y descarta (None)."""
    assert kind in KINDS, kind
    data, ctype = decode_image(raw, field=field)
    storage = get_storage()
    if storage.backend == "none":
        return None
    ev_id = uuid.uuid4()
    now = utcnow()
    key = f"{ev_id}/{now:%Y/%m/%d}/{entity}-{entity_id}.{ALLOWED_TYPES[ctype]}"
    storage.put(key, data, ctype)
    days = settings_svc.get_int(db, "evidence_retention_days", settings.EVIDENCE_RETENTION_DAYS)
    ev = Evidence(
        id=ev_id, kind=kind, entity=entity, entity_id=entity_id, point_id=point_id, shift_id=shift_id, uploaded_by=uploaded_by,
        storage_key=key, content_type=ctype, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        taken_at=taken_at or now, created_at=now, retention_until=now + timedelta(days=days),
    )
    db.add(ev)
    db.flush()
    return ev


def store_photos(db: Session, photos, **kw) -> list[Evidence]:
    """`photos`: lista de str (base64/data URL) o de objetos/dicts con `.base64`/`['base64']`."""
    out = []
    for i, p in enumerate(photos or []):
        raw = p if isinstance(p, str) else (p.get("base64") if isinstance(p, dict) else getattr(p, "base64", None))
        if not raw:
            continue
        ev = store_photo(db, raw, field=f"photos[{i}]", **kw)
        if ev is not None:
            out.append(ev)
    return out


def serialize(ev: Evidence, expires: int = 900) -> dict:
    return {
        "id": str(ev.id),
        "kind": ev.kind,
        "entity": ev.entity,
        "entity_id": str(ev.entity_id),
        "content_type": ev.content_type,
        "size_bytes": ev.size_bytes,
        "sha256": ev.sha256,
        "taken_at": iso(ev.taken_at),
        "url": None if ev.deleted_at else (get_storage().get_url(ev.storage_key, expires) or f"/v1/evidence/{ev.id}/file"),
    }


def for_entity(db: Session, entity: str, entity_id: uuid.UUID) -> list[Evidence]:
    return (
        db.query(Evidence)
        .filter(Evidence.entity == entity, Evidence.entity_id == entity_id, Evidence.deleted_at.is_(None))
        .order_by(Evidence.created_at)
        .all()
    )


def serialize_for(db: Session, entity: str, entity_id: uuid.UUID) -> list[dict]:
    return [serialize(e) for e in for_entity(db, entity, entity_id)]


def check_access(db: Session, ev: Evidence, current) -> None:
    """Operador: sólo las suyas. Supervisor: su zona. ops/finance/admin: todo."""
    if current.role == "operator":
        if ev.uploaded_by != current.id:
            raise ApiError("FORBIDDEN", "Esta evidencia no es tuya")
    elif current.role == "supervisor":
        point = db.get(Point, ev.point_id) if ev.point_id else None
        if point is None or point.zone_id != current.zone_id:
            raise ApiError("FORBIDDEN", "La evidencia no pertenece a tu zona")


def purge_expired_evidence(db: Session, now: datetime | None = None) -> int:
    """Borra del storage y marca `deleted_at` las evidencias con `retention_until` vencido."""
    now = now or utcnow()
    storage = get_storage()
    rows = db.query(Evidence).filter(Evidence.deleted_at.is_(None), Evidence.retention_until.isnot(None), Evidence.retention_until <= now).all()
    n = 0
    for ev in rows:
        storage.delete(ev.storage_key)
        ev.deleted_at = now
        n += 1
    db.flush()
    return n
