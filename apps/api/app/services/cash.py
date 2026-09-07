"""Caja: efectivo esperado = fondo inicial + pagos cash de ventas vigentes + depósitos − retiros/gastos/devoluciones
en efectivo (`cash_movements`); resumen de ventas. Las ventas canceladas no cuentan (docs/INDICADORES.md)."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ops import CashMovement, CashSession
from app.models.sales import Payment, Sale, SaleCancellation, SaleLine


def sales_summary(db: Session, shift_id: uuid.UUID) -> dict:
    """Totales del turno considerando sólo ventas con status 'recorded' (las canceladas no cuentan)."""
    count, total = db.execute(
        select(func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(
            Sale.shift_id == shift_id, Sale.status == "recorded"
        )
    ).one()
    rows = db.execute(
        select(Payment.method, func.coalesce(func.sum(Payment.amount_cents), 0))
        .join(Sale, Sale.id == Payment.sale_id)
        .where(Payment.shift_id == shift_id, Sale.status == "recorded")
        .group_by(Payment.method)
    ).all()
    by_method = {m: int(a) for m, a in rows}
    cash = by_method.get("cash", 0)
    digital = sum(v for k, v in by_method.items() if k != "cash")
    cancelled_count, cancelled_total = db.execute(
        select(func.count(SaleCancellation.id), func.coalesce(func.sum(SaleCancellation.amount_cents), 0)).where(
            SaleCancellation.shift_id == shift_id
        )
    ).one()
    units = db.execute(
        select(func.coalesce(func.sum(SaleLine.qty), 0))
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(Sale.shift_id == shift_id, Sale.status == "recorded")
    ).scalar_one()
    cs = db.execute(select(CashSession).where(CashSession.shift_id == shift_id)).scalar_one_or_none()
    opening = int(cs.opening_cents) if cs else 0
    mov = db.execute(select(CashMovement.kind, func.coalesce(func.sum(CashMovement.amount_cents), 0)).where(CashMovement.shift_id == shift_id).group_by(CashMovement.kind)).all()
    movements = {k: int(a) for k, a in mov}
    cash_in = movements.get("deposit", 0)
    cash_out = sum(v for k, v in movements.items() if k != "deposit")
    return {
        "sales_count": int(count),
        "sales_total_cents": int(total),
        "cash_sales_cents": cash,
        "opening_cents": opening,
        "cash_in_cents": cash_in,
        "cash_out_cents": cash_out,
        "cash_movements": movements,
        "cash_expected_cents": opening + cash + cash_in - cash_out,
        "digital_total_cents": digital,
        "by_method": by_method,
        "cancelled_count": int(cancelled_count),
        "cancelled_total_cents": int(cancelled_total),
        "units_sold": int(units),
    }


def cash_expected(db: Session, shift_id: uuid.UUID) -> int:
    return sales_summary(db, shift_id)["cash_expected_cents"]
