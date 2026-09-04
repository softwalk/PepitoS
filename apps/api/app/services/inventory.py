"""Inventario reconstruible desde `inventory_movements`. Balance = SUM(qty) por punto/presentación."""
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.models.cases import Rule
from app.models.catalog import Presentation
from app.models.inventory import MOVEMENT_TYPES, InventoryCount, InventoryMovement, Lot, Receipt, Waste
from app.models.ops import Shift
from app.services import audit, events
from app.services.cases import open_case_if_new
from app.services.settings import inventory_tolerance


def add_movement(
    db: Session,
    *,
    point_id: uuid.UUID,
    presentation_id: uuid.UUID,
    qty: int,
    movement_type: str,
    shift_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    ref_entity: str | None = None,
    ref_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    note: str | None = None,
    emit_event: bool = True,
) -> InventoryMovement:
    assert movement_type in MOVEMENT_TYPES, movement_type
    mv = InventoryMovement(
        point_id=point_id,
        presentation_id=presentation_id,
        qty=qty,
        movement_type=movement_type,
        shift_id=shift_id,
        actor_id=actor_id,
        ref_entity=ref_entity,
        ref_id=ref_id,
        lot_id=lot_id,
        occurred_at=occurred_at or utcnow(),
        note=note,
        created_at=utcnow(),
    )
    db.add(mv)
    if emit_event:
        events.emit(
            db,
            "InventoryMoved",
            actor_id=actor_id,
            point_id=point_id,
            shift_id=shift_id,
            entity="inventory_movement",
            entity_id=mv.id,
            payload={"presentation_id": presentation_id, "qty": qty, "movement_type": movement_type, "ref_entity": ref_entity, "ref_id": ref_id},
            occurred_at=mv.occurred_at,
        )
    return mv


def balance(db: Session, point_id: uuid.UUID, presentation_id: uuid.UUID) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(InventoryMovement.qty), 0)).where(
            InventoryMovement.point_id == point_id, InventoryMovement.presentation_id == presentation_id
        )
    ).scalar_one()
    return int(total)


def balances_for_point(db: Session, point_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Balance por presentación activa del punto (incluye 0 para presentaciones sin movimientos)."""
    rows = db.execute(
        select(InventoryMovement.presentation_id, func.sum(InventoryMovement.qty))
        .where(InventoryMovement.point_id == point_id)
        .group_by(InventoryMovement.presentation_id)
    ).all()
    result = {pid: int(q) for pid, q in rows}
    for p in db.query(Presentation).filter(Presentation.is_active.is_(True)).all():
        result.setdefault(p.id, 0)
    return result


def balances_all(db: Session, point_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, dict[uuid.UUID, int]]:
    """Balance por punto y presentación. Si se pasan `point_ids`, rellena con 0 las presentaciones
    activas sin movimientos en esos puntos (un punto sin stock de una presentación cuenta como 0)."""
    rows = db.execute(
        select(InventoryMovement.point_id, InventoryMovement.presentation_id, func.sum(InventoryMovement.qty)).group_by(
            InventoryMovement.point_id, InventoryMovement.presentation_id
        )
    ).all()
    out: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    for point_id, pres_id, q in rows:
        out.setdefault(point_id, {})[pres_id] = int(q)
    if point_ids:
        active = [p.id for p in db.query(Presentation).filter(Presentation.is_active.is_(True)).all()]
        for pid in point_ids:
            for pres_id in active:
                out.setdefault(pid, {}).setdefault(pres_id, 0)
    return out


def shift_units(db: Session, shift_id: uuid.UUID, movement_type: str) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(InventoryMovement.qty), 0)).where(
            InventoryMovement.shift_id == shift_id, InventoryMovement.movement_type == movement_type
        )
    ).scalar_one()
    return abs(int(total))


# ---------- Merma ----------
def create_waste(db: Session, shift: Shift, actor_id: uuid.UUID, data) -> Waste:
    if shift.status != "open":
        raise ApiError("SHIFT_NOT_OPEN")
    pres = db.get(Presentation, data.presentation_id)
    if pres is None:
        raise ApiError("NOT_FOUND", "Presentación no encontrada")
    occurred = data.occurred_at or utcnow()
    w = Waste(
        shift_id=shift.id,
        point_id=shift.point_id,
        operator_id=actor_id,
        presentation_id=pres.id,
        qty=data.qty,
        reason_code=data.reason_code,
        note=data.note,
        idempotency_key=data.idempotency_key,
        occurred_at=occurred,
        created_at=utcnow(),
    )
    db.add(w)
    db.flush()
    add_movement(
        db, point_id=shift.point_id, presentation_id=pres.id, qty=-data.qty, movement_type="waste",
        shift_id=shift.id, actor_id=actor_id, ref_entity="waste", ref_id=w.id, occurred_at=occurred,
    )
    events.emit(
        db, "WasteRecorded", actor_id=actor_id, point_id=shift.point_id, shift_id=shift.id, entity="waste",
        entity_id=w.id, payload={"presentation_id": pres.id, "qty": data.qty, "reason_code": data.reason_code},
        occurred_at=occurred,
    )
    shift.last_seen_at = utcnow()
    return w


# ---------- Recepción ----------
def create_receipt(db: Session, shift: Shift, actor_id: uuid.UUID, data) -> Receipt:
    if shift.status != "open":
        raise ApiError("SHIFT_NOT_OPEN")
    occurred = data.occurred_at or utcnow()
    lines_json = []
    resolved: list[tuple[Presentation, int, Lot | None]] = []
    for line in data.lines:
        pres = db.get(Presentation, line.presentation_id)
        if pres is None:
            raise ApiError("NOT_FOUND", "Presentación no encontrada", details={"presentation_id": str(line.presentation_id)})
        lot = None
        if line.lot_code:
            lot = db.query(Lot).filter(Lot.code == line.lot_code).first()
            if lot is None:
                lot = Lot(code=line.lot_code, presentation_id=pres.id)
                db.add(lot)
                db.flush()
            if lot.status == "blocked":
                raise ApiError("LOT_BLOCKED", details={"lot_code": lot.code, "reason": lot.blocked_reason})
        resolved.append((pres, line.qty, lot))
        lines_json.append({"presentation_id": str(pres.id), "qty": line.qty, "lot_code": line.lot_code})
    r = Receipt(
        shift_id=shift.id, point_id=shift.point_id, actor_id=actor_id, qr_code=data.qr_code, lines=lines_json,
        idempotency_key=data.idempotency_key, occurred_at=occurred, created_at=utcnow(),
    )
    db.add(r)
    db.flush()
    for pres, qty, lot in resolved:
        add_movement(
            db, point_id=shift.point_id, presentation_id=pres.id, qty=qty, movement_type="receipt", shift_id=shift.id,
            actor_id=actor_id, ref_entity="receipt", ref_id=r.id, lot_id=lot.id if lot else None, occurred_at=occurred,
        )
    shift.last_seen_at = utcnow()
    return r


# ---------- Conteo ----------
def apply_count(
    db: Session,
    shift: Shift,
    actor_id: uuid.UUID,
    counts: dict[uuid.UUID, int],
    *,
    kind: str = "manual",
    idempotency_key: str | None = None,
    occurred_at: datetime | None = None,
    create_case: bool = True,
) -> tuple[InventoryCount, dict[uuid.UUID, int], uuid.UUID | None]:
    """Compara conteo físico vs teórico, registra `count_adjustment` y abre caso si supera `units`."""
    occurred = occurred_at or utcnow()
    theoretical = balances_for_point(db, shift.point_id)
    differences: dict[uuid.UUID, int] = {}
    for pres_id, counted in counts.items():
        if db.get(Presentation, pres_id) is None:
            raise ApiError("NOT_FOUND", "Presentación no encontrada", details={"presentation_id": str(pres_id)})
        diff = int(counted) - theoretical.get(pres_id, 0)
        differences[pres_id] = diff
    ic = InventoryCount(
        shift_id=shift.id, point_id=shift.point_id, actor_id=actor_id, kind=kind,
        counts={str(k): v for k, v in counts.items()},
        theoretical={str(k): v for k, v in theoretical.items()},
        differences={str(k): v for k, v in differences.items()},
        idempotency_key=idempotency_key, occurred_at=occurred, created_at=utcnow(),
    )
    db.add(ic)
    db.flush()
    for pres_id, diff in differences.items():
        if diff != 0:
            add_movement(
                db, point_id=shift.point_id, presentation_id=pres_id, qty=diff, movement_type="count_adjustment",
                shift_id=shift.id, actor_id=actor_id, ref_entity="inventory_count", ref_id=ic.id, occurred_at=occurred,
                note=f"Ajuste por conteo ({kind})",
            )
    audit.log(
        db, actor_id=actor_id, action="inventory.count_adjustment", entity="inventory_count", entity_id=ic.id,
        before={str(k): v for k, v in theoretical.items()}, after={str(k): v for k, v in counts.items()},
        reason=f"Conteo {kind}",
    )
    case_id = None
    if create_case:
        units = inventory_tolerance(db)  # rules.params.units > settings.inventory_count_tolerance_units > default
        worst = max((abs(d) for d in differences.values()), default=0)
        if worst > units:
            rule = db.get(Rule, "inventory_inconsistent")
            case = open_case_if_new(
                db, rule_key="inventory_inconsistent", point_id=shift.point_id, shift_id=shift.id,
                severity=(rule.severity if rule else "review"),
                title="Inventario inconsistente",
                description=f"Diferencia máxima de {worst} unidades entre conteo y teórico",
                impact_score=min(worst * 2, 40), source="rule",
                payload={"differences": {str(k): v for k, v in differences.items()}, "count_id": str(ic.id)},
                dedupe_date=occurred,
            )
            case_id = case.id if case else None
    shift.last_seen_at = utcnow()
    return ic, differences, case_id
