"""Evidencias (fotos) — B4. Lista por entidad y sirve/redirige el archivo."""
import uuid

from fastapi import Response, APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.errors import ApiError
from app.models.system import Evidence
from app.services import evidence as evidence_svc
from app.services.storage import LocalStorage, get_storage

router = APIRouter(prefix="/v1/evidence", tags=["evidencias"])
ENTITIES = {"case", "shift", "audit"}


@router.get("")
def list_evidence(entity: str, entity_id: uuid.UUID, current: CurrentUser = Depends(require("help.create", "cases.read")), db: Session = Depends(get_db)):
    """Operador: sólo las que subió. Supervisor: su zona. ops/finance/admin: todo."""
    if entity not in ENTITIES:
        raise ApiError("VALIDATION", "entity debe ser case | shift | audit", details={"entity": entity})
    out = []
    for ev in evidence_svc.for_entity(db, entity, entity_id):
        try:
            evidence_svc.check_access(db, ev, current)
        except ApiError:
            continue
        out.append(evidence_svc.serialize(ev))
    return out


@router.get("/{evidence_id}")
def get_evidence(evidence_id: uuid.UUID, current: CurrentUser = Depends(require("help.create", "cases.read")), db: Session = Depends(get_db)):
    ev = _get(db, evidence_id, current)
    return evidence_svc.serialize(ev)


@router.get("/{evidence_id}/file")
def get_file(evidence_id: uuid.UUID, current: CurrentUser = Depends(require("help.create", "cases.read")), db: Session = Depends(get_db)):
    """Backend local: sirve el archivo. s3: 302 a la URL presignada. none: 404."""
    ev = _get(db, evidence_id, current)
    storage = get_storage()
    if isinstance(storage, LocalStorage):
        path = storage.get_path(ev.storage_key)
        if not path.is_file():
            raise ApiError("NOT_FOUND", "Archivo de evidencia no disponible")
        return FileResponse(path, media_type=ev.content_type, headers={"Cache-Control": "private, max-age=300"})
    url = storage.get_url(ev.storage_key)
    if url:
        return RedirectResponse(url, status_code=302)
    if hasattr(storage, "get_bytes"):  # s3 sin URL pública: la API sirve el archivo
        try:
            data = storage.get_bytes(ev.storage_key)
        except Exception:  # noqa: BLE001
            raise ApiError("NOT_FOUND", "Archivo de evidencia no disponible")
        return Response(content=data, media_type=ev.content_type, headers={"Cache-Control": "private, max-age=300"})
    raise ApiError("NOT_FOUND", "Archivo de evidencia no disponible")


def _get(db: Session, evidence_id: uuid.UUID, current: CurrentUser) -> Evidence:
    ev = db.get(Evidence, evidence_id)
    if ev is None or ev.deleted_at is not None:
        raise ApiError("NOT_FOUND", "Evidencia no encontrada")
    evidence_svc.check_access(db, ev, current)
    return ev
