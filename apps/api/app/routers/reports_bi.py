"""Módulo de Reportes (BI): catálogo por rol y payload declarativo por reporte.

- `GET /v1/reports/bi` → catálogo de reportes permitidos al rol (para el Centro de Reportes).
- `GET /v1/reports/bi/{key}` → reporte con periodo, filtros y alcance. Cada consulta y exportación queda en `audit_log`
  (`report.view` / `report.export`, con resultado permitido o denegado). Sin permiso → 403 FORBIDDEN.
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, get_current_user
from app.core.errors import ApiError
from app.services import audit
from app.services.reporting import REPORTS, build_report, can_view, catalog_for

router = APIRouter(prefix="/v1/reports/bi", tags=["reportes-bi"])

FILTER_KEYS = ("zone_id", "point_id", "operator_id", "cart_id", "presentation_id")


@router.get("")
def catalog(current: CurrentUser = Depends(get_current_user)):
    return catalog_for(current)


@router.get("/options")
def options(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Valores para los filtros de dimensión dentro del alcance del rol (zonas, puntos, vendedores, carritos, presentaciones)."""
    from sqlalchemy import select

    from app.models.catalog import Presentation
    from app.models.org import Cart, Point, User, Zone

    zone_id = current.zone_id if current.role in ("supervisor", "operator") else None
    zq = select(Zone).where(Zone.is_active.is_(True))
    pq = select(Point).where(Point.is_active.is_(True))
    uq = select(User).where(User.role == "operator", User.is_active.is_(True))
    if zone_id is not None:
        zq, pq, uq = zq.where(Zone.id == zone_id), pq.where(Point.zone_id == zone_id), uq.where(User.zone_id == zone_id)
    if current.role == "operator":
        uq = uq.where(User.id == current.id)
    return {
        "zones": [{"id": str(z.id), "name": z.name} for z in db.execute(zq.order_by(Zone.name)).scalars().all()],
        "points": [{"id": str(p.id), "name": p.display_name, "zone_id": str(p.zone_id) if p.zone_id else None} for p in db.execute(pq.order_by(Point.name)).scalars().all()],
        "operators": [{"id": str(u.id), "name": u.name, "zone_id": str(u.zone_id) if u.zone_id else None} for u in db.execute(uq.order_by(User.name)).scalars().all()],
        "carts": [{"id": str(c.id), "name": c.code} for c in db.execute(select(Cart).where(Cart.is_active.is_(True)).order_by(Cart.code)).scalars().all()],
        "presentations": [{"id": str(p.id), "name": p.name} for p in db.execute(select(Presentation).where(Presentation.is_active.is_(True)).order_by(Presentation.sort)).scalars().all()],
        "methods": [{"id": "cash", "name": "Efectivo"}, {"id": "qr", "name": "QR"}, {"id": "card", "name": "Tarjeta"}],
    }


@router.get("/{key}")
def report(
    key: str,
    request: Request,
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    zone_id: uuid.UUID | None = None,
    point_id: uuid.UUID | None = None,
    operator_id: uuid.UUID | None = None,
    cart_id: uuid.UUID | None = None,
    presentation_id: uuid.UUID | None = None,
    method: str | None = None,
    export: bool = False,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = {"zone_id": zone_id, "point_id": point_id, "operator_id": operator_id, "cart_id": cart_id, "presentation_id": presentation_id, "method": method}
    applied = {k: str(v) for k, v in filters.items() if v is not None}
    applied.update({k: v for k, v in (("period", period), ("from", date_from), ("to", date_to)) if v})
    action = "report.export" if export else "report.view"
    if key not in REPORTS:
        raise ApiError("NOT_FOUND", "Reporte no encontrado")
    if not can_view(current, key):
        audit.log(db, actor_id=current.id, action=action, entity="report", after={"report": key, "filters": applied, "result": "denied", "role": current.role}, ip=client_ip(request), device_id=current.device_id)
        db.commit()
        raise ApiError("FORBIDDEN", details={"required": [REPORTS[key]["perm"]], "role": current.role})
    payload = build_report(db, key, current, period=period, date_from=date_from, date_to=date_to, filters=filters)
    audit.log(db, actor_id=current.id, action=action, entity="report", after={"report": key, "filters": applied, "result": "allowed", "role": current.role, "scope": payload["scope"]}, ip=client_ip(request), device_id=current.device_id)
    db.commit()
    return payload
