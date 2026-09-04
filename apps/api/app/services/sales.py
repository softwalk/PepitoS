"""Ventas (ledger append-only) y cancelaciones."""
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.models.catalog import Flavor, Presentation, PriceItem, PriceVersion
from app.models.ops import Shift
from app.models.sales import Payment, Sale, SaleCancellation, SaleLine
from app.core.config import settings
from app.services import audit, events
from app.services import settings as settings_svc
from app.services.inventory import add_movement


def current_price_version(db: Session, at=None) -> PriceVersion | None:
    at = at or utcnow()
    return (
        db.query(PriceVersion)
        .filter(PriceVersion.is_active.is_(True), PriceVersion.valid_from <= at)
        .order_by(PriceVersion.valid_from.desc())
        .first()
    )


def price_map(db: Session, version_id: uuid.UUID) -> dict[uuid.UUID, int]:
    return {pi.presentation_id: pi.amount_cents for pi in db.query(PriceItem).filter(PriceItem.price_version_id == version_id)}


def validate_price_version(version: PriceVersion | None, occurred, requested_id) -> bool:
    """Ventana tolerante para ventas offline (B8). Devuelve `True` si la versión entra por la gracia
    (desactivada hace menos de `PRICE_OFFLINE_GRACE_HOURS`), `False` si está vigente; 422 si no aplica."""
    rid = str(requested_id)
    if version is None:
        raise ApiError("PRICE_VERSION_INVALID", "La versión de precio no existe", details={"price_version_id": rid})
    if version.valid_from > occurred + timedelta(minutes=5):
        raise ApiError("PRICE_VERSION_INVALID", "La versión de precio todavía no estaba vigente cuando ocurrió la venta", details={"price_version_id": rid, "valid_from": version.valid_from.isoformat(), "occurred_at": occurred.isoformat()})
    if version.is_active:
        return False
    grace = timedelta(hours=settings.PRICE_OFFLINE_GRACE_HOURS)
    deactivated = version.deactivated_at or version.updated_at
    if deactivated is not None and occurred <= deactivated + grace:
        return True
    raise ApiError(
        "PRICE_VERSION_INVALID",
        f"La versión de precio fue desactivada hace más de {settings.PRICE_OFFLINE_GRACE_HOURS} h; sincroniza el catálogo y vuelve a registrar la venta",
        details={"price_version_id": rid, "deactivated_at": deactivated.isoformat() if deactivated else None, "grace_hours": settings.PRICE_OFFLINE_GRACE_HOURS, "occurred_at": occurred.isoformat()},
    )


def create_sale(db: Session, shift: Shift, user_id: uuid.UUID, device_id: str | None, data) -> Sale:
    if shift.status != "open":
        raise ApiError("SHIFT_NOT_OPEN")
    occurred = data.occurred_at or utcnow()
    version = db.get(PriceVersion, data.price_version_id)
    stale = validate_price_version(version, occurred, data.price_version_id)
    prices = price_map(db, version.id)

    total = 0
    lines: list[SaleLine] = []
    for line in data.lines:
        pres = db.get(Presentation, line.presentation_id)
        if pres is None or not pres.is_active:
            raise ApiError("NOT_FOUND", "Presentación no encontrada", details={"presentation_id": str(line.presentation_id)})
        if line.presentation_id not in prices:
            raise ApiError("PRICE_VERSION_INVALID", "La presentación no tiene precio en esta versión", details={"presentation_id": str(line.presentation_id)})
        if line.flavor_id is not None and db.get(Flavor, line.flavor_id) is None:
            raise ApiError("NOT_FOUND", "Sabor no encontrado", details={"flavor_id": str(line.flavor_id)})
        unit = prices[line.presentation_id]
        line_total = unit * line.qty
        total += line_total
        lines.append(SaleLine(presentation_id=pres.id, flavor_id=line.flavor_id, qty=line.qty, unit_price_cents=unit, line_total_cents=line_total))

    paid = sum(p.amount_cents for p in data.payments)
    if paid != total:
        raise ApiError("VALIDATION", "La suma de pagos no coincide con el total", details={"total_cents": total, "paid_cents": paid})

    sale = Sale(
        shift_id=shift.id, point_id=shift.point_id, cart_id=shift.cart_id, operator_id=shift.operator_id,
        device_id=device_id, price_version_id=version.id, idempotency_key=data.idempotency_key, occurred_at=occurred,
        total_cents=total, status="recorded", offline_created=data.offline_created, price_version_stale=stale,
        gps=data.gps.model_dump(mode="json") if data.gps else None, folio="PENDING",
    )
    sale.lines = lines
    sale.payments = [Payment(shift_id=shift.id, method=p.method, amount_cents=p.amount_cents, occurred_at=occurred) for p in data.payments]
    db.add(sale)
    db.flush()
    sale.folio = f"F-{sale.folio_num:06d}"

    for line in lines:
        add_movement(
            db, point_id=shift.point_id, presentation_id=line.presentation_id, qty=-line.qty, movement_type="sale",
            shift_id=shift.id, actor_id=user_id, ref_entity="sale", ref_id=sale.id, occurred_at=occurred,
        )
    events.emit(
        db, "SaleRecorded", actor_id=user_id, point_id=shift.point_id, shift_id=shift.id, entity="sale", entity_id=sale.id,
        payload={
            "sale_id": sale.id, "folio": sale.folio, "idempotency_key": data.idempotency_key, "cart_id": shift.cart_id,
            "operator_id": shift.operator_id, "price_version_id": version.id, "occurred_at": occurred,
            "lines": [{"presentation_id": l.presentation_id, "qty": l.qty, "unit_price_cents": l.unit_price_cents} for l in lines],
            "payments": [{"method": p.method, "amount_cents": p.amount_cents} for p in data.payments],
            "offline_created": data.offline_created, "total_cents": total, "price_version_stale": stale,
        },
        occurred_at=occurred,
    )
    for p in sale.payments:
        events.emit(
            db, "PaymentRecorded", actor_id=user_id, point_id=shift.point_id, shift_id=shift.id, entity="payment",
            entity_id=p.id, payload={"sale_id": sale.id, "method": p.method, "amount_cents": p.amount_cents}, occurred_at=occurred,
        )
    shift.last_seen_at = utcnow()
    return sale


def cancel_sale(db: Session, sale: Sale, current, data, cancel_window_minutes: int | None = None, ip: str | None = None) -> SaleCancellation:
    if sale.status == "cancelled":
        raise ApiError("CANCEL_NOT_ALLOWED", "La venta ya está cancelada")
    if cancel_window_minutes is None:
        cancel_window_minutes = settings_svc.get_int(db, "cancel_window_minutes")
    shift = db.get(Shift, sale.shift_id)
    now = utcnow()
    if current.role == "operator":
        if sale.operator_id != current.id:
            raise ApiError("CANCEL_NOT_ALLOWED", "Sólo puedes cancelar tus propias ventas")
        if shift is None or shift.status != "open":
            raise ApiError("CANCEL_NOT_ALLOWED", "El turno ya no está abierto")
        if now - sale.created_at > timedelta(minutes=cancel_window_minutes):
            raise ApiError("CANCEL_NOT_ALLOWED", f"Sólo puedes cancelar dentro de {cancel_window_minutes} minutos", details={"cancel_window_minutes": cancel_window_minutes})
    elif not current.has("sale.cancel"):
        raise ApiError("FORBIDDEN")
    if not data.reason_code:
        raise ApiError("VALIDATION", "Se requiere motivo de cancelación")

    c = SaleCancellation(
        sale_id=sale.id, shift_id=sale.shift_id, actor_id=current.id, idempotency_key=data.idempotency_key,
        reason_code=data.reason_code, note=data.note, cancelled_at=now, amount_cents=sale.total_cents,
    )
    db.add(c)
    before = {"status": sale.status}
    sale.status = "cancelled"
    db.flush()
    for line in sale.lines:
        add_movement(
            db, point_id=sale.point_id, presentation_id=line.presentation_id, qty=line.qty, movement_type="return",
            shift_id=sale.shift_id, actor_id=current.id, ref_entity="sale_cancellation", ref_id=c.id, occurred_at=now,
            note=f"Cancelación {sale.folio}",
        )
    events.emit(
        db, "SaleCancelled", actor_id=current.id, point_id=sale.point_id, shift_id=sale.shift_id, entity="sale", entity_id=sale.id,
        payload={"cancellation_id": c.id, "reason_code": data.reason_code, "note": data.note, "amount_cents": sale.total_cents, "folio": sale.folio},
    )
    audit.log(
        db, actor_id=current.id, action="sale.cancel", entity="sale", entity_id=sale.id, before=before,
        after={"status": "cancelled", "reason_code": data.reason_code}, reason=data.note or data.reason_code, ip=ip, device_id=current.device_id,
    )
    if shift is not None:
        shift.last_seen_at = now
    return c
