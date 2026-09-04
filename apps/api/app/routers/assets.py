"""Activos, tickets de mantenimiento y bloqueo de lotes."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.core.errors import ApiError
from app.core.timeutil import iso, utcnow
from app.models.cases import MaintenanceTicket
from app.models.inventory import InventoryMovement, Lot
from app.models.org import Asset, Cart, Point
from app.schemas.backoffice import LotBlockIn, MaintenanceTicketIn, MaintenanceTicketPatch
from app.services import audit, events
from app.services.inventory import add_movement

router = APIRouter(prefix="/v1", tags=["activos"])


def _asset(a: Asset, cart_code: str | None) -> dict:
    return {
        "id": str(a.id), "code": a.code, "asset_type": a.asset_type, "cart_id": str(a.cart_id) if a.cart_id else None, "cart_code": cart_code,
        "status": a.status, "maintenance_interval_days": a.maintenance_interval_days, "last_maintenance_at": iso(a.last_maintenance_at),
        "next_maintenance_at": iso(a.next_maintenance_at), "overdue": bool(a.next_maintenance_at and a.next_maintenance_at < utcnow()), "meta": a.meta,
    }


def _ticket(t: MaintenanceTicket) -> dict:
    return {
        "id": str(t.id), "asset_id": str(t.asset_id), "severity": t.severity, "status": t.status, "title": t.title, "description": t.description,
        "kind": t.kind, "evidence": t.evidence, "resolution": t.resolution, "created_at": iso(t.created_at), "resolved_at": iso(t.resolved_at),
    }


@router.get("/assets")
def list_assets(_: CurrentUser = Depends(require("assets.read", "maintenance.read")), db: Session = Depends(get_db)):
    carts = {c.id: c.code for c in db.query(Cart).all()}
    tickets = db.query(MaintenanceTicket).filter(MaintenanceTicket.status.in_(("open", "in_progress"))).all()
    open_by_asset: dict = {}
    for t in tickets:
        open_by_asset.setdefault(t.asset_id, []).append(_ticket(t))
    return [{**_asset(a, carts.get(a.cart_id)), "open_tickets": open_by_asset.get(a.id, [])} for a in db.query(Asset).order_by(Asset.code).all()]


@router.get("/maintenance/tickets")
def list_tickets(status: str | None = None, _: CurrentUser = Depends(require("maintenance.read")), db: Session = Depends(get_db)):
    q = db.query(MaintenanceTicket)
    if status:
        q = q.filter(MaintenanceTicket.status == status)
    return [_ticket(t) for t in q.order_by(MaintenanceTicket.created_at.desc()).all()]


@router.post("/maintenance/tickets", status_code=201)
def create_ticket(data: MaintenanceTicketIn, current: CurrentUser = Depends(require("maintenance.manage", "cases.update")), db: Session = Depends(get_db)):
    asset = db.get(Asset, data.asset_id)
    if asset is None:
        raise ApiError("NOT_FOUND", "Activo no encontrado")
    t = MaintenanceTicket(asset_id=asset.id, severity=data.severity, title=data.title, description=data.description, kind=data.kind, evidence=data.evidence or [], created_by=current.id)
    db.add(t)
    db.flush()
    events.emit(db, "MaintenanceTicketCreated", actor_id=current.id, entity="maintenance_ticket", entity_id=t.id, payload={"asset_id": asset.id, "severity": data.severity, "title": data.title})
    db.commit()
    return _ticket(t)


@router.patch("/maintenance/tickets/{ticket_id}")
def patch_ticket(ticket_id: uuid.UUID, data: MaintenanceTicketPatch, current: CurrentUser = Depends(require("maintenance.manage")), db: Session = Depends(get_db)):
    t = db.get(MaintenanceTicket, ticket_id)
    if t is None:
        raise ApiError("NOT_FOUND", "Ticket no encontrado")
    before = {"status": t.status, "severity": t.severity}
    if data.status:
        t.status = data.status
        if data.status in ("resolved", "closed"):
            t.resolved_at = utcnow()
            asset = db.get(Asset, t.asset_id)
            if asset is not None and t.kind == "preventive":
                asset.last_maintenance_at = utcnow()
                if asset.maintenance_interval_days:
                    asset.next_maintenance_at = utcnow() + timedelta(days=asset.maintenance_interval_days)
    if data.resolution is not None:
        t.resolution = data.resolution
    if data.severity:
        t.severity = data.severity
    audit.log(db, actor_id=current.id, action="maintenance_ticket.update", entity="maintenance_ticket", entity_id=t.id, before=before, after={"status": t.status, "severity": t.severity}, reason=data.resolution)
    db.commit()
    return _ticket(t)


@router.get("/lots")
def list_lots(_: CurrentUser = Depends(require("inventory.read")), db: Session = Depends(get_db)):
    return [{"id": str(l.id), "code": l.code, "presentation_id": str(l.presentation_id) if l.presentation_id else None, "status": l.status, "blocked_reason": l.blocked_reason, "blocked_at": iso(l.blocked_at)} for l in db.query(Lot).order_by(Lot.code).all()]


@router.post("/lots/{lot_id}/block")
def block_lot(lot_id: uuid.UUID, data: LotBlockIn, request: Request, current: CurrentUser = Depends(require("lots.block")), db: Session = Depends(get_db)):
    """Bloquea un lote (decisión humana): identifica puntos afectados, registra movimiento `blocked` y evita nuevas entregas."""
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise ApiError("NOT_FOUND", "Lote no encontrado")
    if lot.status == "blocked":
        raise ApiError("CONFLICT", "El lote ya está bloqueado")
    now = utcnow()
    lot.status = "blocked"
    lot.blocked_reason = data.reason
    lot.blocked_at = now
    lot.blocked_by = current.id
    # Puntos afectados: donde hubo recepciones de este lote
    movs = db.query(InventoryMovement).filter(InventoryMovement.lot_id == lot.id, InventoryMovement.movement_type == "receipt").all()
    affected: dict = {}
    for m in movs:
        affected.setdefault((m.point_id, m.presentation_id), 0)
        affected[(m.point_id, m.presentation_id)] += m.qty
    points = []
    for (point_id, pres_id), qty in affected.items():
        p = db.get(Point, point_id)
        points.append({"point_id": str(point_id), "point_name": p.name if p else None, "presentation_id": str(pres_id), "received_units": qty})
        # Movimiento "blocked": retira del balance las unidades recibidas de ese lote (política MVP: retiro completo).
        add_movement(db, point_id=point_id, presentation_id=pres_id, qty=-qty, movement_type="blocked", lot_id=lot.id, actor_id=current.id, ref_entity="lot", ref_id=lot.id, occurred_at=now, note=f"Lote bloqueado: {data.reason}")
    events.emit(db, "LotBlocked", actor_id=current.id, entity="lot", entity_id=lot.id, payload={"reason": data.reason, "affected_points": points})
    audit.log(db, actor_id=current.id, action="lot.block", entity="lot", entity_id=lot.id, before={"status": "active"}, after={"status": "blocked"}, reason=data.reason, ip=client_ip(request))
    db.commit()
    return {"lot_id": str(lot.id), "status": "blocked", "affected_points": points}
