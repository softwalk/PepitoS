"""Ranking de ventas por vendedor (operador): día, mes y año locales.

Se guarda en `users` (sales_rank_* / sales_*_cents / sales_rank_at) para que el operador lo vea en su app y el backoffice
en Personas sin recalcular en cada consulta. Lo recalcula el motor de reglas en cada corrida (cada 5 min), cada cierre de
turno y `POST /v1/rules/run`. Criterio: suma de ventas `recorded` (total_cents) por `occurred_at` dentro del periodo local;
rango denso (empates comparten lugar); operadores activos sin ventas quedan al final con el mismo lugar.
"""
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.org import User
from app.models.sales import Sale

PERIODS = ("day", "month", "year")


def period_bounds(now: datetime, period: str) -> tuple[datetime, datetime]:
    local = now.astimezone(settings.tz)
    if period == "day":
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period == "month":
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
    elif period == "year":
        start = local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
    else:
        raise ValueError(period)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def totals_by_operator(db: Session, now: datetime, period: str) -> dict[uuid.UUID, int]:
    start, end = period_bounds(now, period)
    rows = db.execute(
        select(Sale.operator_id, func.coalesce(func.sum(Sale.total_cents), 0))
        .where(Sale.status == "recorded", Sale.occurred_at >= start, Sale.occurred_at < end)
        .group_by(Sale.operator_id)
    ).all()
    return {r[0]: int(r[1]) for r in rows}


def dense_ranks(totals: dict[uuid.UUID, int], operator_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """1 = mayor total. Empates comparten lugar (1, 2, 2, 3). Sin ventas → último lugar compartido."""
    values = sorted({totals.get(o, 0) for o in operator_ids}, reverse=True)
    rank_of_value = {v: i + 1 for i, v in enumerate(values)}
    return {o: rank_of_value[totals.get(o, 0)] for o in operator_ids}


def recompute_rankings(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    operators = db.query(User).filter(User.role == "operator", User.is_active.is_(True)).all()
    ids = [u.id for u in operators]
    out = {}
    for period in PERIODS:
        totals = totals_by_operator(db, now, period)
        ranks = dense_ranks(totals, ids)
        for u in operators:
            setattr(u, f"sales_rank_{period}", ranks[u.id])
            setattr(u, f"sales_{period}_cents", totals.get(u.id, 0))
        out[period] = {"operators": len(ids), "with_sales": sum(1 for o in ids if totals.get(o, 0) > 0)}
    for u in operators:
        u.sales_rank_at = now
    db.flush()
    return out


def serialize_ranking(u: User, total_operators: int | None = None) -> dict:
    return {
        "day": {"rank": u.sales_rank_day, "total_cents": u.sales_day_cents},
        "month": {"rank": u.sales_rank_month, "total_cents": u.sales_month_cents},
        "year": {"rank": u.sales_rank_year, "total_cents": u.sales_year_cents},
        "of": total_operators,
        "computed_at": u.sales_rank_at.isoformat() if u.sales_rank_at else None,
    }


def leaderboard(db: Session, period: str, zone_id: uuid.UUID | None = None, limit: int = 100) -> list[dict]:
    if period not in PERIODS:
        raise ValueError(period)
    q = db.query(User).filter(User.role == "operator", User.is_active.is_(True))
    if zone_id is not None:
        q = q.filter(User.zone_id == zone_id)
    rank_col = getattr(User, f"sales_rank_{period}")
    cents_col = getattr(User, f"sales_{period}_cents")
    rows = q.order_by(rank_col.asc().nullslast(), cents_col.desc(), User.name).limit(limit).all()
    return [
        {
            "operator": {"id": str(u.id), "name": u.name, "username": u.username, "zone_id": str(u.zone_id) if u.zone_id else None},
            "rank": getattr(u, f"sales_rank_{period}"), "total_cents": getattr(u, f"sales_{period}_cents"),
            "ranking": serialize_ranking(u),
        }
        for u in rows
    ]
