"""Movimientos de efectivo del turno: fondo inicial, retiros/gastos autorizados y devoluciones en efectivo.

Regla: todo movimiento lleva actor, motivo y hora; un retiro/gasto por encima de `cash_out_max_cents` abre un caso de
revisión para el supervisor (no se bloquea: el operador no debe quedar sin poder registrar lo que ocurrió).
"""
import uuid

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import iso, utcnow
from app.models.ops import CashMovement, Shift
from app.services import audit, events
from app.services import settings as settings_svc
from app.services.cases import open_case_if_new

KIND_LABEL = {"deposit": "Depósito / fondo", "withdrawal": "Retiro", "expense": "Gasto", "refund": "Devolución en efectivo"}


def create_movement(db: Session, shift: Shift, current, data, ip: str | None = None) -> CashMovement:
    if shift.status != "open":
        raise ApiError("CONFLICT", "El turno no está abierto")
    existing = db.query(CashMovement).filter(CashMovement.idempotency_key == data.idempotency_key).first()
    if existing is not None:
        return existing
    now = utcnow()
    if data.kind != "deposit":
        from app.services.cash import cash_expected

        available = cash_expected(db, shift.id)
        if int(data.amount_cents) > available:
            raise ApiError("CONFLICT", f"No hay efectivo suficiente en caja: disponible ${available / 100:,.2f}", details={"available_cents": available})
    m = CashMovement(
        shift_id=shift.id, point_id=shift.point_id, actor_id=current.id, kind=data.kind, amount_cents=int(data.amount_cents),
        reason=data.reason, note=data.note, idempotency_key=data.idempotency_key, occurred_at=data.occurred_at or now, created_at=now,
    )
    db.add(m)
    db.flush()
    limit = settings_svc.get_int(db, "cash_out_max_cents")
    if data.kind in ("withdrawal", "expense") and m.amount_cents >= limit:
        case = open_case_if_new(
            db, rule_key="cash_out_review", point_id=shift.point_id, shift_id=shift.id, severity="review", category="cash",
            title=f"{KIND_LABEL[data.kind]} de ${m.amount_cents / 100:,.0f}: {data.reason}",
            description=f"Movimiento de efectivo registrado por el operador (≥ ${limit / 100:,.0f}). Verificar comprobante y autorización.",
            source="operator", actor_id=current.id, dedupe_date=now, payload={"cash_movement_id": str(m.id), "amount_cents": m.amount_cents, "kind": data.kind},
        )
        if case is not None:
            m.case_id = case.id
    events.emit(
        db, "CashMovementRecorded", actor_id=current.id, point_id=shift.point_id, shift_id=shift.id, entity="cash_movement", entity_id=m.id,
        payload={"kind": m.kind, "amount_cents": m.amount_cents, "reason": m.reason}, occurred_at=m.occurred_at,
    )
    audit.log(db, actor_id=current.id, action="cash_movement.create", entity="cash_movement", entity_id=m.id, after={"kind": m.kind, "amount_cents": m.amount_cents, "reason": m.reason, "shift_id": str(shift.id)}, reason=data.note, ip=ip, device_id=current.device_id)
    shift.last_seen_at = now
    return m


def serialize(m: CashMovement) -> dict:
    return {
        "id": str(m.id), "shift_id": str(m.shift_id), "kind": m.kind, "kind_label": KIND_LABEL.get(m.kind, m.kind), "amount_cents": m.amount_cents,
        "signed_cents": m.signed_cents, "reason": m.reason, "note": m.note, "occurred_at": iso(m.occurred_at), "actor_id": str(m.actor_id),
        "case_id": str(m.case_id) if m.case_id else None, "idempotency_key": m.idempotency_key,
    }


def list_for_shift(db: Session, shift_id: uuid.UUID) -> list[dict]:
    rows = db.query(CashMovement).filter(CashMovement.shift_id == shift_id).order_by(CashMovement.occurred_at).all()
    return [serialize(m) for m in rows]
