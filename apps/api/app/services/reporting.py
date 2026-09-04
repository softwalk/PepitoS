"""Módulo de Reportes (BI): periodos, alcance por rol, agregaciones y hallazgos.

Cada reporte devuelve un payload declarativo que el backoffice renderiza de forma genérica:
    {key, title, category, period, compare, filters, scope, kpis[], charts[], tables[], insights[], hidden[]}

Principios (docs/REPORTES.md):
- La autorización y el alcance se aplican aquí: el supervisor sólo recibe filas de su zona; el operador sólo las suyas.
- Sin tablas de agregados: todo se calcula sobre la fuente de verdad (sales, payments, shifts, inventory_movements…),
  con los índices de la migración 0008. Los rangos personalizados se limitan a 366 días.
- Los hallazgos ("insights") se generan a partir de los datos y se etiquetan: fact · trend · alert · hypothesis ·
  recommendation. Nunca afirman causas que los datos no demuestran.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import Date, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.timeutil import iso, local_today, utcnow
from app.models.cases import Action, Approval, Audit, Case, MaintenanceTicket
from app.models.catalog import Presentation
from app.models.inventory import InventoryCount, InventoryMovement, Lot, Waste
from app.models.ops import GpsPing, Shift
from app.models.org import Asset, Assignment, Attendance, Cart, Point, User, Zone
from app.models.sales import Payment, Sale, SaleCancellation, SaleLine
from app.services.points_import import load_catalog
from app.services.settings import get_int

MAX_CUSTOM_DAYS = 366
TABLE_LIMIT = 200

# ───────────────────────────── Catálogo de reportes ─────────────────────────────

REPORTS: dict[str, dict[str, Any]] = {
    "executive": {"title": "Resumen ejecutivo", "category": "Ejecutivo", "perm": "reports.executive", "orientation": "portrait",
                  "description": "Ventas, avance vs meta, puntos activos, caja, alertas y tendencia vs periodo anterior.",
                  "decision": "Dónde poner la atención hoy: red, zona o punto.", "frequency": "Tiempo real / diaria"},
    "sales": {"title": "Ventas y desempeño comercial", "category": "Comercial", "perm": "reports.sales", "orientation": "landscape",
              "description": "Ventas por día, zona, punto, vendedor, presentación, hora y medio de pago; ticket promedio y precio vencido.",
              "decision": "Mezcla de producto, horarios y puntos donde empujar la venta.", "frequency": "Diaria / semanal"},
    "cash": {"title": "Caja y conciliación", "category": "Finanzas", "perm": "reports.cash", "orientation": "landscape",
             "description": "Esperado vs contado, diferencias por punto y vendedor, reaperturas, arqueos y aprobaciones.",
             "decision": "Qué diferencias conciliar, escalar o aprobar.", "frequency": "Diaria"},
    "points": {"title": "Ranking de puntos y ubicaciones", "category": "Comercial", "perm": "reports.points", "orientation": "landscape",
               "description": "Ventas, avance vs meta, ticket, merma, casos y score estratégico por punto; mejores y peores.",
               "decision": "Qué puntos reforzar, auditar o reubicar.", "frequency": "Semanal"},
    "people": {"title": "Productividad de vendedores", "category": "Operaciones", "perm": "reports.people", "orientation": "landscape",
               "description": "Ventas por hora abierta, ticket, merma, diferencias de caja, asistencia, cancelaciones y ranking.",
               "decision": "A quién capacitar, reconocer o reasignar.", "frequency": "Semanal / mensual"},
    "inventory": {"title": "Inventario, consumo y merma", "category": "Inventarios", "perm": "reports.inventory", "orientation": "landscape",
                  "description": "Entradas, ventas, merma por motivo, ajustes de conteo, existencias, días de inventario y lotes bloqueados.",
                  "decision": "Qué reponer, qué lote revisar y dónde está la merma.", "frequency": "Diaria"},
    "quality": {"title": "Calidad y auditorías", "category": "Calidad", "perm": "reports.quality", "orientation": "portrait",
                "description": "Auditorías, no conformidades por ítem y punto, acciones correctivas y excepciones de apertura.",
                "decision": "Qué puntos auditar y qué acciones están vencidas.", "frequency": "Semanal"},
    "maintenance": {"title": "Mantenimiento y disponibilidad", "category": "Mantenimiento", "perm": "reports.maintenance", "orientation": "portrait",
                    "description": "Activos, preventivos vencidos, tickets correctivos, tiempo fuera de servicio, disponibilidad y batería.",
                    "decision": "Qué carrito atender antes de que deje de vender.", "frequency": "Semanal"},
    "compliance": {"title": "Cumplimiento operativo y GPS", "category": "Operaciones", "perm": "reports.compliance", "orientation": "landscape",
                   "description": "Aperturas tarde o sin abrir, aperturas fuera del punto (50 m), geocerca, sincronización y fotos.",
                   "decision": "Qué operadores y puntos incumplen el protocolo.", "frequency": "Diaria"},
    "expansion": {"title": "Expansión y ubicaciones", "category": "Expansión", "perm": "reports.expansion", "orientation": "landscape",
                  "description": "Puntos activos vs catálogo de 100 ubicaciones, ventas reales vs esperadas y semáforo GO / AJUSTAR / NO GO.",
                  "decision": "Dónde abrir, cerrar o reubicar.", "frequency": "Mensual"},
}
CATEGORY_ORDER = ["Ejecutivo", "Comercial", "Finanzas", "Operaciones", "Inventarios", "Calidad", "Mantenimiento", "Expansión"]

PRESETS = ("today", "yesterday", "last7", "week", "month", "prev_month", "year", "custom")
PRESET_LABELS = {
    "today": "Hoy", "yesterday": "Ayer", "last7": "Últimos 7 días", "week": "Semana actual", "month": "Mes actual",
    "prev_month": "Mes anterior", "year": "Año actual", "custom": "Rango personalizado",
}


# ───────────────────────────── Periodo y alcance ─────────────────────────────


@dataclass
class Period:
    preset: str
    start_day: date
    end_day: date  # inclusivo
    start: datetime
    end: datetime  # exclusivo (UTC)

    @property
    def days(self) -> int:
        return (self.end_day - self.start_day).days + 1

    @property
    def label(self) -> str:
        if self.start_day == self.end_day:
            return self.start_day.strftime("%d/%m/%Y")
        return f"{self.start_day.strftime('%d/%m/%Y')} – {self.end_day.strftime('%d/%m/%Y')}"

    @property
    def hourly(self) -> bool:
        return self.days == 1

    def to_dict(self) -> dict:
        return {"preset": self.preset, "preset_label": PRESET_LABELS.get(self.preset, self.preset), "from": self.start_day.isoformat(),
                "to": self.end_day.isoformat(), "label": self.label, "days": self.days, "start": iso(self.start), "end": iso(self.end)}


def _bounds(d0: date, d1: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d0, time.min, tzinfo=settings.tz)
    end = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=settings.tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def parse_period(preset: str | None, date_from: str | None, date_to: str | None, now: datetime | None = None) -> Period:
    now = now or utcnow()
    today = local_today(now)
    preset = preset or ("custom" if (date_from or date_to) else "today")
    if preset not in PRESETS:
        raise ApiError("VALIDATION", f"period debe ser uno de: {', '.join(PRESETS)}")
    if preset == "today":
        d0 = d1 = today
    elif preset == "yesterday":
        d0 = d1 = today - timedelta(days=1)
    elif preset == "last7":
        d1, d0 = today, today - timedelta(days=6)
    elif preset == "week":
        d0, d1 = today - timedelta(days=today.weekday()), today
    elif preset == "month":
        d0, d1 = today.replace(day=1), today
    elif preset == "prev_month":
        first = today.replace(day=1)
        d1 = first - timedelta(days=1)
        d0 = d1.replace(day=1)
    elif preset == "year":
        d0, d1 = today.replace(month=1, day=1), today
    else:
        try:
            d0 = date.fromisoformat(date_from) if date_from else today
            d1 = date.fromisoformat(date_to) if date_to else d0
        except ValueError:
            raise ApiError("VALIDATION", "from/to deben ser fechas YYYY-MM-DD")
        if d1 < d0:
            raise ApiError("VALIDATION", "`to` debe ser mayor o igual que `from`")
        if (d1 - d0).days + 1 > MAX_CUSTOM_DAYS:
            raise ApiError("VALIDATION", f"El rango personalizado no puede exceder {MAX_CUSTOM_DAYS} días")
    s, e = _bounds(d0, d1)
    return Period(preset, d0, d1, s, e)


def previous_period(p: Period) -> Period:
    """Periodo comparable inmediatamente anterior (misma longitud; mes vs mes, año vs año)."""
    if p.preset in ("month", "prev_month"):
        d1 = p.start_day - timedelta(days=1)
        d0 = d1.replace(day=1)
        # mes parcial → misma cantidad de días del mes anterior
        if p.preset == "month":
            d1 = min(d1, d0 + timedelta(days=p.days - 1))
    elif p.preset == "year":
        d0 = p.start_day.replace(year=p.start_day.year - 1)
        d1 = min(p.end_day.replace(year=p.end_day.year - 1), d0.replace(month=12, day=31))
    else:
        d1 = p.start_day - timedelta(days=1)
        d0 = d1 - timedelta(days=p.days - 1)
    s, e = _bounds(d0, d1)
    return Period("previous", d0, d1, s, e)


@dataclass
class Scope:
    """Alcance efectivo de la consulta. `zone_id` y `operator_id` fijos por rol no se pueden ampliar desde la URL."""
    role: str
    user_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    operator_id: uuid.UUID | None = None
    point_id: uuid.UUID | None = None
    cart_id: uuid.UUID | None = None
    presentation_id: uuid.UUID | None = None
    method: str | None = None
    zone_locked: bool = False
    operator_locked: bool = False

    def to_dict(self) -> dict:
        return {
            "role": self.role, "zone_id": str(self.zone_id) if self.zone_id else None, "operator_id": str(self.operator_id) if self.operator_id else None,
            "point_id": str(self.point_id) if self.point_id else None, "cart_id": str(self.cart_id) if self.cart_id else None,
            "presentation_id": str(self.presentation_id) if self.presentation_id else None, "method": self.method,
            "zone_locked": self.zone_locked, "operator_locked": self.operator_locked,
        }


def build_scope(current, filters: dict[str, Any]) -> Scope:
    """Combina el alcance fijo del rol con los filtros de la URL. El supervisor no sale de su zona aunque manipule la URL."""
    sc = Scope(role=current.role, user_id=current.id)
    if current.role == "supervisor":
        sc.zone_id, sc.zone_locked = current.zone_id, True
    elif current.role == "operator":
        sc.operator_id, sc.operator_locked = current.id, True
        sc.zone_id = current.zone_id
    else:
        sc.zone_id = filters.get("zone_id")
    if not sc.operator_locked:
        sc.operator_id = filters.get("operator_id")
    sc.point_id = filters.get("point_id")
    sc.cart_id = filters.get("cart_id")
    sc.presentation_id = filters.get("presentation_id")
    sc.method = filters.get("method")
    return sc


def _point_ids(db: Session, sc: Scope) -> list[uuid.UUID] | None:
    """Puntos dentro del alcance (None = todos)."""
    if sc.point_id is not None:
        if sc.zone_id is not None:
            p = db.get(Point, sc.point_id)
            if p is None or p.zone_id != sc.zone_id:
                return []
        return [sc.point_id]
    if sc.zone_id is not None:
        return [r[0] for r in db.execute(select(Point.id).where(Point.zone_id == sc.zone_id)).all()]
    return None


def _apply_sale_scope(q, sc: Scope, point_ids: list[uuid.UUID] | None):
    if point_ids is not None:
        q = q.where(Sale.point_id.in_(point_ids))
    if sc.operator_id is not None:
        q = q.where(Sale.operator_id == sc.operator_id)
    if sc.cart_id is not None:
        q = q.where(Sale.cart_id == sc.cart_id)
    return q


def _apply_shift_scope(q, sc: Scope, point_ids: list[uuid.UUID] | None):
    if point_ids is not None:
        q = q.where(Shift.point_id.in_(point_ids))
    if sc.operator_id is not None:
        q = q.where(Shift.operator_id == sc.operator_id)
    if sc.cart_id is not None:
        q = q.where(Shift.cart_id == sc.cart_id)
    return q


# ───────────────────────────── Utilidades de payload ─────────────────────────────


def _pct(cur: float, prev: float) -> float | None:
    if not prev:
        return None
    return round((cur - prev) * 100.0 / prev, 1)


def _trend(delta: float | None, invert: bool = False) -> str:
    if delta is None or abs(delta) < 1:
        return "flat"
    up = delta > 0
    if invert:
        up = not up
    return "up" if up else "down"


def kpi(key: str, label: str, value: Any, fmt: str = "int", prev: Any = None, tone: str = "neutral", hint: str | None = None, invert: bool = False) -> dict:
    delta = _pct(value or 0, prev or 0) if (prev is not None and isinstance(value, (int, float))) else None
    return {"key": key, "label": label, "value": value, "format": fmt, "prev": prev, "delta_pct": delta,
            "delta_abs": (value - prev) if (prev is not None and isinstance(value, (int, float))) else None,
            "trend": _trend(delta, invert), "tone": tone, "hint": hint}


def insight(kind: str, text: str, link: str | None = None) -> dict:
    assert kind in ("fact", "trend", "alert", "hypothesis", "recommendation")
    return {"kind": kind, "text": text, "link": link}


def _tone_sales_tx(tx: int, days: int) -> str:
    per_day = tx / max(days, 1)
    return "ok" if per_day >= 60 else "warn" if per_day >= 45 else "bad"


def _tone_ticket(cents: float) -> str:
    return "ok" if cents >= 3900 else "warn" if cents >= 3600 else "bad"


def _tone_waste(pct: float) -> str:
    return "ok" if pct <= 2 else "warn" if pct <= 4 else "bad"


def _tone_target(pct: float) -> str:
    return "ok" if pct >= 100 else "warn" if pct >= 75 else "bad"


def _money(c: int | float) -> str:
    return f"${c / 100:,.0f}"


def _local_bucket(col, hourly: bool):
    local = func.timezone(settings.TZ_NAME, col)
    return func.date_trunc("hour" if hourly else "day", local)


def _bucket_label(dt: datetime, hourly: bool) -> str:
    return dt.strftime("%H:00") if hourly else dt.strftime("%d/%m")


def _series_by_bucket(db: Session, p: Period, base_where, sc: Scope, point_ids) -> list[dict]:
    b = _local_bucket(Sale.occurred_at, p.hourly)
    q = select(b.label("b"), func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(base_where).group_by("b").order_by("b")
    q = _apply_sale_scope(q, sc, point_ids)
    rows = db.execute(q).all()
    got = {r[0]: (int(r[1]), int(r[2])) for r in rows}
    out = []
    if p.hourly:
        for h in range(24):
            key = datetime.combine(p.start_day, time(h))
            tx, cents = got.get(key, (0, 0))
            out.append({"label": f"{h:02d}:00", "tx": tx, "sales_cents": cents})
    else:
        d = p.start_day
        while d <= p.end_day:
            key = datetime.combine(d, time.min)
            tx, cents = got.get(key, (0, 0))
            out.append({"label": d.strftime("%d/%m"), "date": d.isoformat(), "tx": tx, "sales_cents": cents})
            d += timedelta(days=1)
    return out


def _sales_where(p: Period):
    return and_(Sale.status == "recorded", Sale.occurred_at >= p.start, Sale.occurred_at < p.end)


def _totals(db: Session, p: Period, sc: Scope, point_ids) -> dict:
    q = select(func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(_sales_where(p))
    q = _apply_sale_scope(q, sc, point_ids)
    tx, cents = db.execute(q).one()
    return {"tx": int(tx), "sales_cents": int(cents), "ticket_cents": int(cents / tx) if tx else 0}


def _waste_units(db: Session, p: Period, sc: Scope, point_ids) -> int:
    q = select(func.coalesce(func.sum(Waste.qty), 0)).where(Waste.occurred_at >= p.start, Waste.occurred_at < p.end)
    if point_ids is not None:
        q = q.where(Waste.point_id.in_(point_ids))
    if sc.operator_id is not None:
        q = q.where(Waste.operator_id == sc.operator_id)
    return int(db.execute(q).scalar_one())


def _units_sold(db: Session, p: Period, sc: Scope, point_ids) -> int:
    q = select(func.coalesce(func.sum(SaleLine.qty), 0)).join(Sale, Sale.id == SaleLine.sale_id).where(_sales_where(p))
    q = _apply_sale_scope(q, sc, point_ids)
    return int(db.execute(q).scalar_one())


def _waste_pct(units: int, waste: int) -> float:
    return round(waste * 100 / (units + waste), 1) if (units + waste) else 0.0


def _targets(db: Session, p: Period, point_ids) -> tuple[int, int]:
    """Meta acumulada del periodo (centavos, tx) = meta diaria del punto × días con turno en el periodo.
    Así la meta refleja la operación real y no los 100 puntos del catálogo que aún no abren."""
    days_q = (
        select(Shift.point_id, func.count(func.distinct(cast(func.timezone(settings.TZ_NAME, Shift.opened_at), Date))))
        .where(Shift.opened_at >= p.start, Shift.opened_at < p.end).group_by(Shift.point_id)
    )
    if point_ids is not None:
        days_q = days_q.where(Shift.point_id.in_(point_ids))
    days = {r[0]: int(r[1]) for r in db.execute(days_q).all()}
    if not days:
        return 0, 0
    pts = db.execute(select(Point.id, Point.daily_target_cents, Point.daily_target_tx).where(Point.id.in_(list(days)))).all()
    return sum(c * days[i] for i, c, _ in pts), sum(t * days[i] for i, _, t in pts)


def _shifts_in(db: Session, p: Period, sc: Scope, point_ids) -> list[Shift]:
    q = select(Shift).where(Shift.opened_at >= p.start, Shift.opened_at < p.end)
    q = _apply_shift_scope(q, sc, point_ids)
    return list(db.execute(q.order_by(Shift.opened_at)).scalars().all())


def _open_hours(s: Shift, now: datetime) -> float:
    end = s.closed_at or now
    return max((end - s.opened_at).total_seconds() / 3600.0, 0.0)


def _names(db: Session, model, ids: set) -> dict:
    if not ids:
        return {}
    return {r.id: r for r in db.execute(select(model).where(model.id.in_(ids))).scalars().all()}


def _compare_block(cur: dict, prev: dict) -> dict:
    return {k: {"current": cur.get(k), "previous": prev.get(k), "delta_pct": _pct(cur.get(k) or 0, prev.get(k) or 0)} for k in cur}


def _empty_payload(key: str, p: Period, prev: Period, sc: Scope, filters: dict) -> dict:
    meta = REPORTS[key]
    return {
        "key": key, "title": meta["title"], "category": meta["category"], "description": meta["description"], "decision": meta["decision"],
        "frequency": meta["frequency"], "orientation": meta["orientation"], "generated_at": iso(utcnow()),
        "period": p.to_dict(), "compare": prev.to_dict(), "filters": {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in filters.items() if v is not None},
        "scope": sc.to_dict(), "kpis": [], "charts": [], "tables": [], "insights": [], "hidden": [],
    }


# ───────────────────────────── 1. Resumen ejecutivo ─────────────────────────────


def report_executive(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    now = utcnow()
    out = _empty_payload("executive", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    cur, old = _totals(db, p, sc, pids), _totals(db, prev, sc, pids)
    target_cents, target_tx = _targets(db, p, pids)
    target_pct = round(cur["sales_cents"] * 100 / target_cents, 1) if target_cents else 0.0
    units, waste = _units_sold(db, p, sc, pids), _waste_units(db, p, sc, pids)
    waste_pct = _waste_pct(units, waste)
    shifts = _shifts_in(db, p, sc, pids)
    open_now = sum(1 for s in shifts if s.status == "open")
    pq = select(func.count(Point.id)).where(Point.is_active.is_(True))
    if pids is not None:
        pq = pq.where(Point.id.in_(pids))
    active_points = int(db.execute(pq).scalar_one())
    points_with_sales = len({s.point_id for s in shifts})
    diffs = [s for s in shifts if s.difference_cents is not None]
    diff_total = sum(s.difference_cents for s in diffs)
    diff_count = sum(1 for s in diffs if s.close_status == "difference")
    cq = select(Case.severity, func.count(Case.id)).where(Case.status.in_(("open", "in_progress")))
    if pids is not None:
        cq = cq.where(Case.point_id.in_(pids))
    cases = {sev: int(n) for sev, n in db.execute(cq.group_by(Case.severity)).all()}

    out["kpis"] = [
        kpi("sales", "Ventas", cur["sales_cents"], "money", old["sales_cents"], _tone_target(target_pct) if target_cents else "neutral", f"Meta {_money(target_cents)}" if target_cents else "sin turnos en el periodo"),
        kpi("target_pct", "Avance vs meta", target_pct, "pct", None, _tone_target(target_pct) if target_cents else "neutral", f"{cur['tx']} de {target_tx} tx · meta = días con turno × meta diaria"),
        kpi("tx", "Transacciones", cur["tx"], "int", old["tx"], _tone_sales_tx(cur["tx"], p.days * max(points_with_sales, 1))),
        kpi("ticket", "Ticket promedio", cur["ticket_cents"], "money", old["ticket_cents"], _tone_ticket(cur["ticket_cents"])),
        kpi("points", "Puntos con turno", points_with_sales, "int", None, "ok" if points_with_sales >= active_points else "warn", f"{open_now} abiertos ahora · {active_points} activos"),
        kpi("cash_diff", "Diferencias de caja", diff_total, "money", None, "ok" if diff_count == 0 else "warn" if diff_count <= 2 else "bad", f"{diff_count} turnos con diferencia", invert=True),
        kpi("waste", "Merma", waste_pct, "pct", None, _tone_waste(waste_pct), f"{waste} u. de {units + waste}", invert=True),
        kpi("cases", "Casos abiertos", sum(cases.values()), "int", None, "bad" if cases.get("urgent") else "warn" if cases else "ok", f"{cases.get('urgent', 0)} urgentes · {cases.get('review', 0)} por revisar"),
    ]
    series = _series_by_bucket(db, p, _sales_where(p), sc, pids)
    prev_series = _series_by_bucket(db, prev, _sales_where(prev), sc, pids)
    for i, row in enumerate(series):
        row["prev_sales_cents"] = prev_series[i]["sales_cents"] if i < len(prev_series) else None
    out["charts"].append({"key": "trend", "title": "Ventas del periodo vs periodo anterior", "type": "line", "x": "label", "data": series,
                          "series": [{"key": "sales_cents", "label": p.label, "format": "money"}, {"key": "prev_sales_cents", "label": prev.label, "format": "money", "dashed": True}]})

    # Zonas
    zq = (
        select(Zone.id, Zone.name, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0))
        .join(Point, Point.zone_id == Zone.id).join(Sale, Sale.point_id == Point.id).where(_sales_where(p)).group_by(Zone.id, Zone.name)
    )
    zq = _apply_sale_scope(zq, sc, pids)
    zrows = db.execute(zq.order_by(func.sum(Sale.total_cents).desc())).all()
    out["charts"].append({"key": "zones", "title": "Ventas por zona", "type": "bar", "x": "label",
                          "data": [{"label": z[1], "sales_cents": int(z[3]), "tx": int(z[2]), "zone_id": str(z[0])} for z in zrows],
                          "series": [{"key": "sales_cents", "label": "Ventas", "format": "money"}]})

    # Top/bottom puntos
    top = _points_rows(db, p, prev, sc, pids, now)[:TABLE_LIMIT]
    out["tables"].append({"key": "top_points", "title": "Top 5 puntos", "columns": _POINT_COLS, "rows": [r for r in top if r["tx"] > 0][:5], "link": {"route": "/reportes/points", "param": "point_id"}})
    out["tables"].append({"key": "bottom_points", "title": "Bottom 5 puntos (con turno)", "columns": _POINT_COLS, "rows": [r for r in reversed(top) if r["tx"] > 0][:5], "link": {"route": "/reportes/points", "param": "point_id"}})

    ins = out["insights"]
    d = _pct(cur["sales_cents"], old["sales_cents"])
    if d is not None:
        ins.append(insight("trend", f"Las ventas {'subieron' if d >= 0 else 'cayeron'} {abs(d):.0f} % vs {prev.label} ({_money(old['sales_cents'])} → {_money(cur['sales_cents'])})."))
    if target_cents:
        ins.append(insight("fact", f"Avance vs meta: {target_pct:.1f} % ({_money(cur['sales_cents'])} de {_money(target_cents)}; meta = días con turno × meta diaria)."))
    if target_cents and target_pct < 75 and cur["tx"]:
        ins.append(insight("alert", f"El avance vs meta está en rojo (< 75 %). Ticket promedio {_money(cur['ticket_cents'])}; {cur['tx']} transacciones."))
    if diff_count:
        ins.append(insight("alert", f"{diff_count} turno(s) cerraron con diferencia de caja; neto {_money(diff_total)}.", "/reportes/cash"))
    if waste_pct > 4:
        ins.append(insight("alert", f"La merma del periodo es {waste_pct:.1f} % (umbral rojo > 4 %).", "/reportes/inventory"))
    if cases.get("urgent"):
        ins.append(insight("recommendation", f"Hay {cases['urgent']} caso(s) urgente(s) abiertos: atenderlos antes que cualquier otra revisión.", "/excepciones"))
    if top and top[0]["tx"]:
        ins.append(insight("fact", f"Mejor punto: {top[0]['point']} con {_money(top[0]['sales_cents'])}."))
    worst = [r for r in top if r["tx"] > 0]
    if len(worst) >= 3 and worst[-1]["target_pct"] < 50:
        ins.append(insight("hypothesis", f"{worst[-1]['point']} lleva {worst[-1]['target_pct']:.0f} % de meta; evaluar afluencia u horario antes de decidir reubicación.", "/reportes/expansion"))
    return out


_POINT_COLS = [
    {"key": "point", "label": "Punto", "format": "text", "link": "/reportes/points?point_id={point_id}"},
    {"key": "zone", "label": "Zona", "format": "text"},
    {"key": "score", "label": "Score", "format": "int"},
    {"key": "sales_cents", "label": "Ventas", "format": "money"},
    {"key": "prev_sales_cents", "label": "Periodo ant.", "format": "money"},
    {"key": "delta_pct", "label": "Δ %", "format": "delta"},
    {"key": "target_pct", "label": "vs meta", "format": "pct", "tone": "target"},
    {"key": "tx", "label": "Tx", "format": "int"},
    {"key": "ticket_cents", "label": "Ticket", "format": "money", "tone": "ticket"},
    {"key": "waste_pct", "label": "Merma", "format": "pct", "tone": "waste"},
    {"key": "open_cases", "label": "Casos", "format": "int"},
]


def _points_rows(db: Session, p: Period, prev: Period, sc: Scope, pids, now: datetime) -> list[dict]:
    """Filas por punto con ventas del periodo, periodo anterior, meta, ticket, merma y casos. Orden: ventas desc."""
    pq = select(Point).where(Point.is_active.is_(True))
    if pids is not None:
        pq = pq.where(Point.id.in_(pids))
    points = list(db.execute(pq).scalars().all())
    zones = {z.id: z.name for z in db.execute(select(Zone)).scalars().all()}

    def agg(period: Period) -> dict:
        q = select(Sale.point_id, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(_sales_where(period)).group_by(Sale.point_id)
        q = _apply_sale_scope(q, sc, pids)
        return {r[0]: (int(r[1]), int(r[2])) for r in db.execute(q).all()}

    cur, old = agg(p), agg(prev)
    uq = select(Sale.point_id, func.coalesce(func.sum(SaleLine.qty), 0)).join(Sale, Sale.id == SaleLine.sale_id).where(_sales_where(p)).group_by(Sale.point_id)
    units = {r[0]: int(r[1]) for r in db.execute(_apply_sale_scope(uq, sc, pids)).all()}
    wq = select(Waste.point_id, func.coalesce(func.sum(Waste.qty), 0)).where(Waste.occurred_at >= p.start, Waste.occurred_at < p.end).group_by(Waste.point_id)
    waste = {r[0]: int(r[1]) for r in db.execute(wq).all()}
    cq = select(Case.point_id, func.count(Case.id)).where(Case.status.in_(("open", "in_progress"))).group_by(Case.point_id)
    cases = {r[0]: int(r[1]) for r in db.execute(cq).all()}
    # Días con turno por punto: la meta del periodo es proporcional a los días realmente operados.
    dq = select(Shift.point_id, func.count(func.distinct(cast(func.timezone(settings.TZ_NAME, Shift.opened_at), Date)))).where(Shift.opened_at >= p.start, Shift.opened_at < p.end).group_by(Shift.point_id)
    days_open = {r[0]: int(r[1]) for r in db.execute(_apply_shift_scope(dq, sc, pids)).all()}
    rows = []
    for pt in points:
        tx, cents = cur.get(pt.id, (0, 0))
        otx, ocents = old.get(pt.id, (0, 0))
        target = pt.daily_target_cents * days_open.get(pt.id, 0)
        rows.append({
            "point_id": str(pt.id), "point": pt.display_name, "zone": zones.get(pt.zone_id, "—"), "score": pt.score,
            "sales_cents": cents, "prev_sales_cents": ocents, "delta_pct": _pct(cents, ocents), "target_pct": round(cents * 100 / target, 1) if target else None,
            "tx": tx, "ticket_cents": int(cents / tx) if tx else None, "waste_pct": _waste_pct(units.get(pt.id, 0), waste.get(pt.id, 0)) if (units.get(pt.id, 0) or waste.get(pt.id, 0)) else None,
            "waste_units": waste.get(pt.id, 0), "open_cases": cases.get(pt.id, 0), "lat": pt.lat, "lng": pt.lng, "geo_verified": pt.geo_verified,
            "meta": pt.meta or {}, "daily_target_cents": pt.daily_target_cents, "days_open": days_open.get(pt.id, 0),
        })
    rows.sort(key=lambda r: (-r["sales_cents"], r["point"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


# ───────────────────────────── 2. Ventas y desempeño comercial ─────────────────────────────


def report_sales(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("sales", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    base = _sales_where(p)
    if sc.presentation_id is not None:
        base = and_(base, Sale.id.in_(select(SaleLine.sale_id).where(SaleLine.presentation_id == sc.presentation_id)))
    if sc.method:
        base = and_(base, Sale.id.in_(select(Payment.sale_id).where(Payment.method == sc.method)))
    cur, old = _totals(db, p, sc, pids), _totals(db, prev, sc, pids)
    stale = int(db.execute(_apply_sale_scope(select(func.count(Sale.id)).where(base, Sale.price_version_stale.is_(True)), sc, pids)).scalar_one())
    cancelled = db.execute(
        _apply_sale_scope(select(func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(Sale.status == "cancelled", Sale.occurred_at >= p.start, Sale.occurred_at < p.end), sc, pids)
    ).one()
    offline = int(db.execute(_apply_sale_scope(select(func.count(Sale.id)).where(base, Sale.offline_created.is_(True)), sc, pids)).scalar_one())
    units = _units_sold(db, p, sc, pids)
    pm = select(Payment.method, func.coalesce(func.sum(Payment.amount_cents), 0), func.count(Payment.id)).join(Sale, Sale.id == Payment.sale_id).where(base).group_by(Payment.method)
    methods = {m: (int(a), int(n)) for m, a, n in db.execute(_apply_sale_scope(pm, sc, pids)).all()}
    digital = sum(a for m, (a, _) in methods.items() if m != "cash")
    total_pay = sum(a for a, _ in methods.values()) or 1

    out["kpis"] = [
        kpi("sales", "Ventas", cur["sales_cents"], "money", old["sales_cents"], "neutral"),
        kpi("tx", "Transacciones", cur["tx"], "int", old["tx"], "neutral"),
        kpi("ticket", "Ticket promedio", cur["ticket_cents"], "money", old["ticket_cents"], _tone_ticket(cur["ticket_cents"])),
        kpi("units", "Unidades", units, "int", None, "neutral"),
        kpi("digital_pct", "Pago digital", round(digital * 100 / total_pay, 1), "pct", None, "neutral", f"{_money(digital)} en QR/tarjeta"),
        kpi("cancelled", "Cancelaciones", int(cancelled[0]), "int", None, "ok" if not cancelled[0] else "warn", _money(int(cancelled[1])), invert=True),
        kpi("stale", "Precio vencido", stale, "int", None, "ok" if not stale else "bad", "ventas con versión de precio vencida", invert=True),
        kpi("offline", "Creadas offline", offline, "int", None, "neutral"),
    ]
    series = _series_by_bucket(db, p, base, sc, pids)
    out["charts"].append({"key": "trend", "title": "Ventas por " + ("hora" if p.hourly else "día"), "type": "bar", "x": "label", "data": series,
                          "series": [{"key": "sales_cents", "label": "Ventas", "format": "money"}, {"key": "tx", "label": "Tx", "format": "int", "axis": "right"}]})
    # Presentación
    prq = (
        select(Presentation.id, Presentation.name, func.coalesce(func.sum(SaleLine.qty), 0), func.coalesce(func.sum(SaleLine.line_total_cents), 0))
        .join(SaleLine, SaleLine.presentation_id == Presentation.id).join(Sale, Sale.id == SaleLine.sale_id).where(base).group_by(Presentation.id, Presentation.name)
    )
    pres = [{"presentation_id": str(r[0]), "label": r[1], "units": int(r[2]), "sales_cents": int(r[3])} for r in db.execute(_apply_sale_scope(prq, sc, pids).order_by(func.sum(SaleLine.line_total_cents).desc())).all()]
    out["charts"].append({"key": "presentations", "title": "Mezcla por presentación", "type": "donut", "x": "label", "data": pres, "series": [{"key": "sales_cents", "label": "Ventas", "format": "money"}]})
    out["charts"].append({"key": "methods", "title": "Medio de pago", "type": "donut", "x": "label",
                          "data": [{"label": {"cash": "Efectivo", "qr": "QR", "card": "Tarjeta"}.get(m, m), "sales_cents": a, "tx": n} for m, (a, n) in methods.items()],
                          "series": [{"key": "sales_cents", "label": "Monto", "format": "money"}]})
    # Heatmap hora × día de la semana
    local = func.timezone(settings.TZ_NAME, Sale.occurred_at)
    hq = select(func.extract("dow", local), func.extract("hour", local), func.coalesce(func.sum(Sale.total_cents), 0)).where(base).group_by(func.extract("dow", local), func.extract("hour", local))
    heat = [{"y": int(d), "x": int(h), "value": int(v)} for d, h, v in db.execute(_apply_sale_scope(hq, sc, pids)).all()]
    out["charts"].append({"key": "heat", "title": "Ventas por hora × día de la semana", "type": "heatmap", "data": heat, "x_labels": [f"{h:02d}" for h in range(24)],
                          "y_labels": ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"], "format": "money"})
    # Tablas: por zona / punto / vendedor
    now = utcnow()
    prow = _points_rows(db, p, prev, sc, pids, now)
    out["tables"].append({"key": "points", "title": "Por punto (con turno en el periodo)", "columns": _POINT_COLS, "rows": [r for r in prow if r["days_open"] or r["tx"]][:TABLE_LIMIT], "link": {"route": "/reportes/points", "param": "point_id"}})
    oq = select(User.id, User.name, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).join(Sale, Sale.operator_id == User.id).where(base).group_by(User.id, User.name)
    orows = [{"operator_id": str(r[0]), "operator": r[1], "tx": int(r[2]), "sales_cents": int(r[3]), "ticket_cents": int(r[3] / r[2]) if r[2] else 0}
             for r in db.execute(_apply_sale_scope(oq, sc, pids).order_by(func.sum(Sale.total_cents).desc())).all()]
    out["tables"].append({"key": "operators", "title": "Por vendedor", "columns": [
        {"key": "operator", "label": "Vendedor", "format": "text", "link": "/reportes/people?operator_id={operator_id}"}, {"key": "sales_cents", "label": "Ventas", "format": "money"},
        {"key": "tx", "label": "Tx", "format": "int"}, {"key": "ticket_cents", "label": "Ticket", "format": "money", "tone": "ticket"}], "rows": orows[:TABLE_LIMIT]})
    out["tables"].append({"key": "presentations", "title": "Por presentación", "columns": [
        {"key": "label", "label": "Presentación", "format": "text"}, {"key": "units", "label": "Unidades", "format": "int"}, {"key": "sales_cents", "label": "Ventas", "format": "money"}], "rows": pres})

    ins = out["insights"]
    d = _pct(cur["sales_cents"], old["sales_cents"])
    if d is not None:
        ins.append(insight("trend", f"Ventas {'+' if d >= 0 else ''}{d:.0f} % vs {prev.label}."))
    if pres:
        ins.append(insight("fact", f"La presentación de {pres[0]['label']} es el mayor ingreso del periodo ({_money(pres[0]['sales_cents'])}, {pres[0]['units']} u.)."))
    if series and not p.hourly:
        best = max(series, key=lambda r: r["sales_cents"])
        if best["sales_cents"]:
            ins.append(insight("fact", f"Mejor día: {best['label']} con {_money(best['sales_cents'])}."))
    if heat:
        hb = max(heat, key=lambda r: r["value"])
        ins.append(insight("fact", f"Hora pico: {['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'][hb['y']]} {hb['x']:02d}:00 ({_money(hb['value'])})."))
    if cur["ticket_cents"] and cur["ticket_cents"] < 3600:
        ins.append(insight("alert", f"Ticket promedio {_money(cur['ticket_cents'])} por debajo de $36 (rojo). Revisar mezcla: empujar 75 g / 100 g."))
    if stale:
        ins.append(insight("alert", f"{stale} venta(s) con precio vencido: revisar la versión de precios activa y la sincronización de las PWA.", "/admin"))
    if cancelled[0] and cur["tx"] and cancelled[0] * 100 / (cur["tx"] + cancelled[0]) > 5:
        ins.append(insight("alert", f"Cancelaciones {cancelled[0] * 100 / (cur['tx'] + cancelled[0]):.0f} % de las ventas: revisar motivos.", "/reportes/quality"))
    if len(orows) >= 3:
        avg = sum(r["sales_cents"] for r in orows) / len(orows)
        low = orows[-1]
        if avg and low["sales_cents"] < avg * 0.6:
            ins.append(insight("hypothesis", f"{low['operator']} vende {100 - low['sales_cents'] * 100 / avg:.0f} % menos que el promedio ({_money(avg)}); revisar punto y horario asignados antes de concluir.", f"/reportes/people?operator_id={low['operator_id']}"))
    return out


# ───────────────────────────── 3. Caja y conciliación ─────────────────────────────


def report_cash(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("cash", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    shifts = _shifts_in(db, p, sc, pids)
    closed = [s for s in shifts if s.closed_at is not None or s.status in ("closed", "transferred")]
    with_diff = [s for s in closed if s.close_status == "difference"]
    expected = sum(s.cash_expected_cents or 0 for s in closed)
    counted = sum(s.cash_counted_cents or 0 for s in closed)
    diff_total = sum(s.difference_cents or 0 for s in closed)
    shortage = sum(s.difference_cents for s in closed if (s.difference_cents or 0) < 0)
    surplus = sum(s.difference_cents for s in closed if (s.difference_cents or 0) > 0)
    threshold, severe = get_int(db, "cash_difference_threshold_cents"), get_int(db, "cash_difference_severe_cents")
    severe_n = sum(1 for s in closed if abs(s.difference_cents or 0) >= severe)
    from app.models.system import AuditLog
    rq = select(func.count(AuditLog.id)).where(AuditLog.action == "shift.reopen", AuditLog.at >= p.start, AuditLog.at < p.end)
    if shifts:
        rq = rq.where(AuditLog.entity_id.in_([s.id for s in shifts]))
    reopened = int(db.execute(rq).scalar_one())
    aq = select(func.count(Audit.id)).where(Audit.performed_at >= p.start, Audit.performed_at < p.end, Audit.cash_counted_cents.is_not(None))
    if pids is not None:
        aq = aq.where(Audit.point_id.in_(pids))
    surprise = int(db.execute(aq).scalar_one())
    prev_shifts = _shifts_in(db, prev, sc, pids)
    prev_diff_n = sum(1 for s in prev_shifts if s.close_status == "difference")

    out["kpis"] = [
        kpi("expected", "Efectivo esperado", expected, "money"),
        kpi("counted", "Efectivo contado", counted, "money"),
        kpi("diff", "Diferencia neta", diff_total, "money", None, "ok" if not with_diff else "warn" if severe_n == 0 else "bad", f"faltante {_money(shortage)} · sobrante {_money(surplus)}", invert=True),
        kpi("diff_shifts", "Turnos con diferencia", len(with_diff), "int", prev_diff_n, "ok" if not with_diff else "warn", f"de {len(closed)} cerrados · umbral {_money(threshold)}", invert=True),
        kpi("severe", "Diferencias graves", severe_n, "int", None, "ok" if not severe_n else "bad", f"≥ {_money(severe)} → aprobación Finanzas", invert=True),
        kpi("reopened", "Turnos continuados", reopened, "int", None, "neutral", "reaperturas por administrador"),
        kpi("surprise", "Arqueos sorpresa", surprise, "int", None, "neutral"),
    ]
    # Serie: diferencia por día
    by_day: dict[str, dict] = {}
    for s in closed:
        d = (s.closed_at or s.opened_at).astimezone(settings.tz).strftime("%d/%m")
        b = by_day.setdefault(d, {"label": d, "shortage_cents": 0, "surplus_cents": 0, "shifts": 0})
        b["shifts"] += 1
        if (s.difference_cents or 0) < 0:
            b["shortage_cents"] += s.difference_cents
        else:
            b["surplus_cents"] += s.difference_cents or 0
    out["charts"].append({"key": "diff_trend", "title": "Diferencias por día (faltante / sobrante)", "type": "stacked", "x": "label", "data": list(by_day.values()),
                          "series": [{"key": "shortage_cents", "label": "Faltante", "format": "money", "color": "bad"}, {"key": "surplus_cents", "label": "Sobrante", "format": "money", "color": "ok"}]})
    points = _names(db, Point, {s.point_id for s in shifts})
    users = _names(db, User, {s.operator_id for s in shifts})
    rows = [{
        "shift_id": str(s.id), "date": s.opened_at.astimezone(settings.tz).strftime("%d/%m %H:%M"), "point_id": str(s.point_id), "point": points[s.point_id].display_name if s.point_id in points else "—",
        "operator_id": str(s.operator_id), "operator": users[s.operator_id].name if s.operator_id in users else "—",
        "expected_cents": s.cash_expected_cents, "counted_cents": s.cash_counted_cents, "difference_cents": s.difference_cents,
        "status": s.close_status or s.status, "severe": abs(s.difference_cents or 0) >= severe,
    } for s in sorted(closed, key=lambda x: abs(x.difference_cents or 0), reverse=True)]
    cols = [
        {"key": "date", "label": "Apertura", "format": "text"}, {"key": "point", "label": "Punto", "format": "text"}, {"key": "operator", "label": "Vendedor", "format": "text", "link": "/reportes/people?operator_id={operator_id}"},
        {"key": "expected_cents", "label": "Esperado", "format": "money"}, {"key": "counted_cents", "label": "Contado", "format": "money"},
        {"key": "difference_cents", "label": "Diferencia", "format": "money", "tone": "diff"}, {"key": "status", "label": "Estado", "format": "status"},
    ]
    out["tables"].append({"key": "shifts", "title": "Turnos cerrados (mayor diferencia primero)", "columns": cols, "rows": rows[:TABLE_LIMIT]})
    # Por vendedor
    byop: dict[uuid.UUID, dict] = {}
    for s in closed:
        b = byop.setdefault(s.operator_id, {"operator_id": str(s.operator_id), "operator": users[s.operator_id].name if s.operator_id in users else "—", "shifts": 0, "diff_shifts": 0, "difference_cents": 0})
        b["shifts"] += 1
        b["difference_cents"] += s.difference_cents or 0
        b["diff_shifts"] += 1 if s.close_status == "difference" else 0
    oprows = sorted(byop.values(), key=lambda r: r["difference_cents"])
    out["tables"].append({"key": "operators", "title": "Por vendedor", "columns": [
        {"key": "operator", "label": "Vendedor", "format": "text", "link": "/reportes/people?operator_id={operator_id}"}, {"key": "shifts", "label": "Turnos", "format": "int"},
        {"key": "diff_shifts", "label": "Con diferencia", "format": "int"}, {"key": "difference_cents", "label": "Neto", "format": "money", "tone": "diff"}], "rows": oprows})
    # Aprobaciones (no para ops)
    if current.role == "ops":
        out["hidden"].append("approvals")
    else:
        apq = select(Approval).where(Approval.created_at >= p.start, Approval.created_at < p.end).order_by(Approval.created_at.desc())
        aps = list(db.execute(apq).scalars().all())
        if sc.zone_id is not None:
            # las aprobaciones de diferencia de caja apuntan al turno: filtrar por puntos de la zona
            sid = {s.id for s in shifts}
            aps = [a for a in aps if a.entity != "shift" or a.entity_id in sid]
        pending = sum(1 for a in aps if a.status == "pending")
        out["kpis"].append(kpi("approvals_pending", "Aprobaciones pendientes", pending, "int", None, "ok" if not pending else "warn", f"de {len(aps)} en el periodo", invert=True))
        out["tables"].append({"key": "approvals", "title": "Aprobaciones de Finanzas", "columns": [
            {"key": "title", "label": "Solicitud", "format": "text"}, {"key": "type", "label": "Tipo", "format": "text"}, {"key": "amount_cents", "label": "Monto", "format": "money"},
            {"key": "status", "label": "Estado", "format": "status"}, {"key": "decided_at", "label": "Decidida", "format": "text"}],
            "rows": [{"approval_id": str(a.id), "title": a.title, "type": a.approval_type, "amount_cents": a.amount_cents, "status": a.status,
                      "decided_at": a.decided_at.astimezone(settings.tz).strftime("%d/%m %H:%M") if a.decided_at else "—"} for a in aps[:TABLE_LIMIT]]})
        if pending:
            out["insights"].append(insight("recommendation", f"{pending} aprobación(es) pendiente(s) de Finanzas.", "/aprobaciones"))
    ins = out["insights"]
    ins.append(insight("fact", f"{len(closed)} turnos cerrados: {len(with_diff)} con diferencia (umbral {_money(threshold)}); neto {_money(diff_total)}."))
    if rows and rows[0]["severe"]:
        ins.append(insight("alert", f"Diferencia grave en {rows[0]['point']} ({rows[0]['operator']}): {_money(rows[0]['difference_cents'])}."))
    if oprows and oprows[0]["diff_shifts"] >= 2:
        ins.append(insight("trend", f"{oprows[0]['operator']} acumula {oprows[0]['diff_shifts']} turnos con diferencia ({_money(oprows[0]['difference_cents'])})."))
        ins.append(insight("recommendation", f"Programar arqueo sorpresa a {oprows[0]['operator']} en la próxima visita de supervisión."))
    if prev_diff_n and len(with_diff) > prev_diff_n:
        ins.append(insight("trend", f"Los turnos con diferencia subieron de {prev_diff_n} a {len(with_diff)} vs {prev.label}."))
    if reopened:
        ins.append(insight("fact", f"{reopened} turno(s) continuados por un administrador en el periodo."))
    return out


# ───────────────────────────── 4. Ranking de puntos ─────────────────────────────


def report_points(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("points", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    now = utcnow()
    rows = _points_rows(db, p, prev, sc, pids, now)
    with_sales = [r for r in rows if r["tx"]]
    total = sum(r["sales_cents"] for r in rows)
    avg = total / len(with_sales) if with_sales else 0
    for r in rows:
        r["vs_network_pct"] = _pct(r["sales_cents"], avg) if avg else None
    on_target = sum(1 for r in with_sales if r["target_pct"] >= 100)
    out["kpis"] = [
        kpi("points", "Puntos con ventas", len(with_sales), "int", None, "neutral", f"de {len(rows)} activos"),
        kpi("avg", "Promedio por punto", int(avg), "money", None, "neutral"),
        kpi("on_target", "Puntos en meta", on_target, "int", None, _tone_target(on_target * 100 / len(with_sales)) if with_sales else "neutral", f"{on_target * 100 // len(with_sales) if with_sales else 0} %"),
        kpi("red", "Puntos en rojo (< 75 %)", sum(1 for r in with_sales if r["target_pct"] < 75), "int", None, "neutral", invert=True),
        kpi("waste_red", "Puntos con merma > 4 %", sum(1 for r in with_sales if r["waste_pct"] > 4), "int", None, "neutral", invert=True),
    ]
    out["charts"].append({"key": "top", "title": "Top 10 por ventas", "type": "bar", "x": "point", "layout": "vertical",
                          "data": [{"point": r["point"], "sales_cents": r["sales_cents"], "point_id": r["point_id"]} for r in with_sales[:10]],
                          "series": [{"key": "sales_cents", "label": "Ventas", "format": "money"}]})
    out["charts"].append({"key": "scatter", "title": "Score estratégico vs avance de meta", "type": "scatter", "x": "score", "y": "target_pct",
                          "data": [{"point": r["point"], "score": r["score"], "target_pct": r["target_pct"], "point_id": r["point_id"]} for r in with_sales if r["score"] is not None],
                          "x_label": "Score /100", "y_label": "% meta"})
    cols = _POINT_COLS + [{"key": "vs_network_pct", "label": "vs red", "format": "delta"}]
    out["tables"].append({"key": "ranking", "title": "Ranking completo", "columns": [{"key": "rank", "label": "#", "format": "int"}] + cols, "rows": rows[:TABLE_LIMIT]})
    out["tables"].append({"key": "bottom", "title": "Bottom 5 (con turno)", "columns": cols, "rows": list(reversed(with_sales))[:5]})
    ins = out["insights"]
    if with_sales:
        ins.append(insight("fact", f"{with_sales[0]['point']} lidera con {_money(with_sales[0]['sales_cents'])} ({with_sales[0]['target_pct']:.0f} % de meta)."))
        drops = sorted([r for r in with_sales if r["delta_pct"] is not None and r["delta_pct"] <= -15], key=lambda r: r["delta_pct"])
        for r in drops[:3]:
            ins.append(insight("trend", f"{r['point']} cayó {abs(r['delta_pct']):.0f} % vs {prev.label}.", f"/reportes/points?point_id={r['point_id']}"))
        red_waste = [r for r in with_sales if r["waste_pct"] > 4]
        for r in red_waste[:3]:
            ins.append(insight("alert", f"Merma de {r['point']} en rojo: {r['waste_pct']:.1f} %.", "/reportes/inventory"))
        high_score_low = [r for r in with_sales if (r["score"] or 0) >= 85 and r["target_pct"] < 50]
        for r in high_score_low[:2]:
            ins.append(insight("hypothesis", f"{r['point']} tiene score {r['score']} pero sólo {r['target_pct']:.0f} % de meta: el potencial del lugar no se está capturando (horario, vendedor o ubicación exacta).", "/reportes/expansion"))
        low = with_sales[-1]
        if len(with_sales) >= 5 and low["target_pct"] < 40 and (low["delta_pct"] or 0) <= 0:
            ins.append(insight("recommendation", f"{low['point']} debería evaluarse para reubicación: {low['target_pct']:.0f} % de meta y sin mejora vs periodo anterior.", "/reportes/expansion"))
    idle = [r for r in rows if not r["tx"]]
    if idle:
        ins.append(insight("fact", f"{len(idle)} punto(s) activos sin ventas en el periodo."))
    return out


# ───────────────────────────── 5. Productividad de vendedores ─────────────────────────────


def report_people(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("people", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    now = utcnow()
    shifts = _shifts_in(db, p, sc, pids)
    uq = select(User).where(User.role == "operator", User.is_active.is_(True))
    if sc.operator_id is not None:
        uq = uq.where(User.id == sc.operator_id)
    elif sc.zone_id is not None:
        uq = uq.where(User.zone_id == sc.zone_id)
    ops = {u.id: u for u in db.execute(uq).scalars().all()}
    # incluir operadores con turno en alcance aunque estén en otra zona
    for u in _names(db, User, {s.operator_id for s in shifts} - set(ops)).values():
        ops[u.id] = u
    sq = select(Sale.operator_id, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(_sales_where(p)).group_by(Sale.operator_id)
    sales = {r[0]: (int(r[1]), int(r[2])) for r in db.execute(_apply_sale_scope(sq, sc, pids)).all()}
    psq = select(Sale.operator_id, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(_sales_where(prev)).group_by(Sale.operator_id)
    prev_sales = {r[0]: (int(r[1]), int(r[2])) for r in db.execute(_apply_sale_scope(psq, sc, pids)).all()}
    uq2 = select(Sale.operator_id, func.coalesce(func.sum(SaleLine.qty), 0)).join(Sale, Sale.id == SaleLine.sale_id).where(_sales_where(p)).group_by(Sale.operator_id)
    units = {r[0]: int(r[1]) for r in db.execute(_apply_sale_scope(uq2, sc, pids)).all()}
    wq = select(Waste.operator_id, func.coalesce(func.sum(Waste.qty), 0)).where(Waste.occurred_at >= p.start, Waste.occurred_at < p.end).group_by(Waste.operator_id)
    waste = {r[0]: int(r[1]) for r in db.execute(wq).all()}
    cq = select(SaleCancellation.actor_id, func.count(SaleCancellation.id)).where(SaleCancellation.cancelled_at >= p.start, SaleCancellation.cancelled_at < p.end).group_by(SaleCancellation.actor_id)
    cancels = {r[0]: int(r[1]) for r in db.execute(cq).all()}
    caq = select(Shift.operator_id, func.count(Case.id)).join(Shift, Shift.id == Case.shift_id).where(Case.opened_at >= p.start, Case.opened_at < p.end).group_by(Shift.operator_id)
    cases = {r[0]: int(r[1]) for r in db.execute(caq).all()}
    att_rows = list(db.execute(select(Attendance).where(Attendance.work_date >= p.start_day, Attendance.work_date <= p.end_day)).scalars().all())
    att: dict[uuid.UUID, dict] = {}
    for a in att_rows:
        b = att.setdefault(a.user_id, {"days": 0, "late": 0, "late_minutes": 0, "absent": 0})
        b["days"] += 1
        b["late"] += 1 if a.status == "late" else 0
        b["absent"] += 1 if a.status == "absent" else 0
        b["late_minutes"] += a.late_minutes or 0
    asq = select(Assignment.operator_id, func.count(Assignment.id)).where(Assignment.shift_date >= p.start_day, Assignment.shift_date <= p.end_day).group_by(Assignment.operator_id)
    planned = {r[0]: int(r[1]) for r in db.execute(asq).all()}
    hours: dict[uuid.UUID, float] = {}
    diffs: dict[uuid.UUID, tuple[int, int]] = {}
    for s in shifts:
        hours[s.operator_id] = hours.get(s.operator_id, 0.0) + _open_hours(s, now)
        d = diffs.get(s.operator_id, (0, 0))
        diffs[s.operator_id] = (d[0] + (1 if s.close_status == "difference" else 0), d[1] + (s.difference_cents or 0))
    hide_attendance = current.role == "finance"
    if hide_attendance:
        out["hidden"].append("attendance")
    rows = []
    for uid, u in ops.items():
        tx, cents = sales.get(uid, (0, 0))
        ptx, pcents = prev_sales.get(uid, (0, 0))
        h = hours.get(uid, 0.0)
        a = att.get(uid, {"days": 0, "late": 0, "late_minutes": 0, "absent": 0})
        row = {
            "operator_id": str(uid), "operator": u.name, "sales_cents": cents, "prev_sales_cents": pcents, "delta_pct": _pct(cents, pcents), "tx": tx,
            "ticket_cents": int(cents / tx) if tx else 0, "hours": round(h, 1), "per_hour_cents": int(cents / h) if h else 0,
            "waste_pct": _waste_pct(units.get(uid, 0), waste.get(uid, 0)), "diff_shifts": diffs.get(uid, (0, 0))[0], "difference_cents": diffs.get(uid, (0, 0))[1],
            "cancellations": cancels.get(uid, 0), "cases": cases.get(uid, 0), "shifts": sum(1 for s in shifts if s.operator_id == uid),
            "rank_day": u.sales_rank_day, "rank_month": u.sales_rank_month, "rank_year": u.sales_rank_year,
        }
        if not hide_attendance:
            row.update({"planned": planned.get(uid, 0), "attended": a["days"] - a["absent"], "late": a["late"], "late_minutes": a["late_minutes"], "absent": a["absent"]})
        rows.append(row)
    rows.sort(key=lambda r: (-r["sales_cents"], r["operator"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    active = [r for r in rows if r["tx"]]
    total_cents = sum(r["sales_cents"] for r in active)
    total_h = sum(r["hours"] for r in active)
    avg_ph = int(total_cents / total_h) if total_h else 0
    for r in rows:
        r["vs_avg_pct"] = _pct(r["per_hour_cents"], avg_ph) if avg_ph and r["hours"] else None
    out["kpis"] = [
        kpi("operators", "Vendedores con ventas", len(active), "int", None, "neutral", f"de {len(rows)}"),
        kpi("per_hour", "Venta por hora abierta", avg_ph, "money", None, "neutral", f"{total_h:.0f} h abiertas"),
        kpi("ticket", "Ticket promedio", int(total_cents / sum(r["tx"] for r in active)) if active else 0, "money", None, "neutral"),
        kpi("diff", "Turnos con diferencia", sum(r["diff_shifts"] for r in rows), "int", None, "neutral", invert=True),
        kpi("cancel", "Cancelaciones", sum(r["cancellations"] for r in rows), "int", None, "neutral", invert=True),
    ]
    if not hide_attendance:
        late_total = sum(r["late"] for r in rows)
        absent_total = sum(r["absent"] for r in rows)
        out["kpis"] += [kpi("late", "Llegadas tarde", late_total, "int", None, "ok" if not late_total else "warn", invert=True),
                        kpi("absent", "Ausencias", absent_total, "int", None, "ok" if not absent_total else "bad", invert=True)]
    out["charts"].append({"key": "per_hour", "title": "Venta por hora abierta (Top 10)", "type": "bar", "x": "operator", "layout": "vertical",
                          "data": [{"operator": r["operator"], "per_hour_cents": r["per_hour_cents"], "operator_id": r["operator_id"]} for r in sorted(active, key=lambda r: -r["per_hour_cents"])[:10]],
                          "series": [{"key": "per_hour_cents", "label": "$/h", "format": "money"}]})
    cols = [
        {"key": "rank", "label": "#", "format": "int"}, {"key": "operator", "label": "Vendedor", "format": "text", "link": "/reportes/people?operator_id={operator_id}"},
        {"key": "sales_cents", "label": "Ventas", "format": "money"}, {"key": "delta_pct", "label": "Δ %", "format": "delta"}, {"key": "tx", "label": "Tx", "format": "int"},
        {"key": "ticket_cents", "label": "Ticket", "format": "money", "tone": "ticket"}, {"key": "hours", "label": "Horas", "format": "float"},
        {"key": "per_hour_cents", "label": "$/h", "format": "money"}, {"key": "vs_avg_pct", "label": "vs prom.", "format": "delta"},
        {"key": "waste_pct", "label": "Merma", "format": "pct", "tone": "waste"}, {"key": "difference_cents", "label": "Dif. caja", "format": "money", "tone": "diff"},
        {"key": "cancellations", "label": "Cancel.", "format": "int"}, {"key": "cases", "label": "Casos", "format": "int"},
        {"key": "rank_day", "label": "Rk día", "format": "int"}, {"key": "rank_month", "label": "Rk mes", "format": "int"}, {"key": "rank_year", "label": "Rk año", "format": "int"},
    ]
    if not hide_attendance:
        cols += [{"key": "attended", "label": "Asist.", "format": "int"}, {"key": "late", "label": "Tarde", "format": "int"}, {"key": "absent", "label": "Faltas", "format": "int"}]
    out["tables"].append({"key": "operators", "title": "Vendedores", "columns": cols, "rows": rows[:TABLE_LIMIT]})
    ins = out["insights"]
    if active:
        ins.append(insight("fact", f"{active[0]['operator']} lidera con {_money(active[0]['sales_cents'])} ({_money(active[0]['per_hour_cents'])}/h)."))
        for r in sorted([r for r in active if r["vs_avg_pct"] is not None and r["vs_avg_pct"] <= -20], key=lambda r: r["vs_avg_pct"])[:3]:
            ins.append(insight("trend", f"{r['operator']} vende {abs(r['vs_avg_pct']):.0f} % menos por hora que el promedio ({_money(avg_ph)}/h)."))
        for r in [r for r in active if r["diff_shifts"] >= 2][:3]:
            ins.append(insight("alert", f"{r['operator']}: {r['diff_shifts']} turnos con diferencia de caja ({_money(r['difference_cents'])}).", "/reportes/cash"))
        for r in [r for r in active if r["waste_pct"] > 4][:3]:
            ins.append(insight("alert", f"Merma de {r['operator']} en rojo: {r['waste_pct']:.1f} %."))
        if not hide_attendance:
            for r in [r for r in rows if r["late"] >= 2 or r["absent"] >= 1][:3]:
                ins.append(insight("alert", f"{r['operator']}: {r['late']} llegada(s) tarde y {r['absent']} falta(s)."))
        low = [r for r in active if r["vs_avg_pct"] is not None and r["vs_avg_pct"] <= -30]
        if low:
            ins.append(insight("recommendation", f"Acompañar en campo a {low[0]['operator']}: su venta por hora está muy por debajo del promedio; revisar técnica de venta y punto asignado."))
    return out


# ───────────────────────────── 6. Inventario, consumo y merma ─────────────────────────────


def report_inventory(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("inventory", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    only_waste = current.role == "finance"
    pres = {pr.id: pr for pr in db.execute(select(Presentation)).scalars().all()}
    # precio vigente por presentación (para valorizar merma): último precio vendido en el periodo o el máximo unit_price
    price_q = select(SaleLine.presentation_id, func.max(SaleLine.unit_price_cents)).join(Sale, Sale.id == SaleLine.sale_id).where(Sale.occurred_at < p.end).group_by(SaleLine.presentation_id)
    prices = {r[0]: int(r[1]) for r in db.execute(price_q).all()}
    wq = select(Waste.presentation_id, Waste.reason_code, func.coalesce(func.sum(Waste.qty), 0), func.count(Waste.id)).where(Waste.occurred_at >= p.start, Waste.occurred_at < p.end).group_by(Waste.presentation_id, Waste.reason_code)
    if pids is not None:
        wq = wq.where(Waste.point_id.in_(pids))
    if sc.operator_id is not None:
        wq = wq.where(Waste.operator_id == sc.operator_id)
    waste_rows = db.execute(wq).all()
    waste_units = sum(int(r[2]) for r in waste_rows)
    waste_value = sum(int(r[2]) * prices.get(r[0], 0) for r in waste_rows)
    units = _units_sold(db, p, sc, pids)
    waste_pct = _waste_pct(units, waste_units)
    prev_waste = _waste_units(db, prev, sc, pids)
    prev_units = _units_sold(db, prev, sc, pids)
    by_reason: dict[str, int] = {}
    for r in waste_rows:
        by_reason[r[1]] = by_reason.get(r[1], 0) + int(r[2])
    out["kpis"] = [
        kpi("waste_pct", "Merma", waste_pct, "pct", _waste_pct(prev_units, prev_waste), _tone_waste(waste_pct), f"{waste_units} u. de {units + waste_units}", invert=True),
        kpi("waste_value", "Merma valorizada", waste_value, "money", None, "neutral", "a precio de venta", invert=True),
        kpi("units", "Unidades vendidas", units, "int", prev_units, "neutral"),
    ]
    out["charts"].append({"key": "reasons", "title": "Merma por motivo", "type": "donut", "x": "label",
                          "data": [{"label": k, "units": v} for k, v in sorted(by_reason.items(), key=lambda x: -x[1])], "series": [{"key": "units", "label": "Unidades", "format": "int"}]})
    if only_waste:
        out["hidden"] += ["movements", "stock", "lots", "counts"]
    else:
        mq = select(InventoryMovement.movement_type, func.coalesce(func.sum(InventoryMovement.qty), 0), func.count(InventoryMovement.id)).where(
            InventoryMovement.occurred_at >= p.start, InventoryMovement.occurred_at < p.end).group_by(InventoryMovement.movement_type)
        if pids is not None:
            mq = mq.where(InventoryMovement.point_id.in_(pids))
        mov = {r[0]: (int(r[1]), int(r[2])) for r in db.execute(mq).all()}
        receipts = mov.get("receipt", (0, 0))[0]
        adjust = mov.get("count_adjustment", (0, 0))[0]
        out["kpis"] += [
            kpi("receipts", "Entradas (u.)", receipts, "int", None, "neutral", f"{mov.get('receipt', (0, 0))[1]} recepciones"),
            kpi("adjust", "Ajustes por conteo (u.)", adjust, "int", None, "ok" if abs(adjust) <= 3 else "warn", f"{mov.get('count_adjustment', (0, 0))[1]} ajustes", invert=True),
        ]
        # Existencias por punto/presentación y días de inventario (consumo promedio diario del periodo)
        bq = select(InventoryMovement.point_id, InventoryMovement.presentation_id, func.coalesce(func.sum(InventoryMovement.qty), 0)).group_by(InventoryMovement.point_id, InventoryMovement.presentation_id)
        if pids is not None:
            bq = bq.where(InventoryMovement.point_id.in_(pids))
        bal = db.execute(bq).all()
        cq = select(Sale.point_id, SaleLine.presentation_id, func.coalesce(func.sum(SaleLine.qty), 0)).join(Sale, Sale.id == SaleLine.sale_id).where(_sales_where(p)).group_by(Sale.point_id, SaleLine.presentation_id)
        cons = {(r[0], r[1]): int(r[2]) for r in db.execute(_apply_sale_scope(cq, sc, pids)).all()}
        points = _names(db, Point, {r[0] for r in bal})
        stock_rows = []
        for pid, prid, q in bal:
            daily = cons.get((pid, prid), 0) / p.days
            stock_rows.append({"point_id": str(pid), "point": points[pid].display_name if pid in points else "—", "presentation": pres[prid].name if prid in pres else "—",
                               "stock": int(q), "daily_consumption": round(daily, 1), "days_of_stock": round(int(q) / daily, 1) if daily else None})
        stock_rows.sort(key=lambda r: (r["days_of_stock"] if r["days_of_stock"] is not None else 999, r["stock"]))
        out["tables"].append({"key": "stock", "title": "Existencias y días de inventario", "columns": [
            {"key": "point", "label": "Punto", "format": "text"}, {"key": "presentation", "label": "Presentación", "format": "text"}, {"key": "stock", "label": "Existencia", "format": "int"},
            {"key": "daily_consumption", "label": "Consumo/día", "format": "float"}, {"key": "days_of_stock", "label": "Días", "format": "float", "tone": "days"}], "rows": stock_rows[:TABLE_LIMIT]})
        # Movimientos por día
        dq = select(_local_bucket(InventoryMovement.occurred_at, False).label("b"), InventoryMovement.movement_type, func.coalesce(func.sum(InventoryMovement.qty), 0)).where(
            InventoryMovement.occurred_at >= p.start, InventoryMovement.occurred_at < p.end).group_by("b", InventoryMovement.movement_type).order_by("b")
        if pids is not None:
            dq = dq.where(InventoryMovement.point_id.in_(pids))
        days: dict[str, dict] = {}
        for b, mt, q in db.execute(dq).all():
            lbl = b.strftime("%d/%m")
            d = days.setdefault(lbl, {"label": lbl, "receipt": 0, "sale": 0, "waste": 0, "count_adjustment": 0})
            d[mt] = d.get(mt, 0) + abs(int(q))
        out["charts"].append({"key": "movements", "title": "Movimientos por día (unidades)", "type": "stacked", "x": "label", "data": list(days.values()),
                              "series": [{"key": "receipt", "label": "Entradas", "format": "int", "color": "ok"}, {"key": "sale", "label": "Ventas", "format": "int", "color": "info"},
                                         {"key": "waste", "label": "Merma", "format": "int", "color": "bad"}, {"key": "count_adjustment", "label": "Ajustes", "format": "int", "color": "warn"}]})
        lots = list(db.execute(select(Lot).where(Lot.status == "blocked")).scalars().all())
        out["kpis"].append(kpi("lots_blocked", "Lotes bloqueados", len(lots), "int", None, "ok" if not lots else "warn", invert=True))
        out["tables"].append({"key": "lots", "title": "Lotes bloqueados", "columns": [
            {"key": "code", "label": "Lote", "format": "text"}, {"key": "presentation", "label": "Presentación", "format": "text"}, {"key": "reason", "label": "Motivo", "format": "text"}, {"key": "blocked_at", "label": "Desde", "format": "text"}],
            "rows": [{"code": lot.code, "presentation": pres[lot.presentation_id].name if lot.presentation_id in pres else "—", "reason": lot.blocked_reason, "blocked_at": lot.blocked_at.astimezone(settings.tz).strftime("%d/%m %H:%M") if lot.blocked_at else "—"} for lot in lots]})
        ccq = select(InventoryCount).where(InventoryCount.occurred_at >= p.start, InventoryCount.occurred_at < p.end)
        if pids is not None:
            ccq = ccq.where(InventoryCount.point_id.in_(pids))
        counts = list(db.execute(ccq.order_by(InventoryCount.occurred_at.desc())).scalars().all())
        cpoints = _names(db, Point, {c.point_id for c in counts})
        out["tables"].append({"key": "counts", "title": "Conteos con diferencia", "columns": [
            {"key": "at", "label": "Fecha", "format": "text"}, {"key": "point", "label": "Punto", "format": "text"}, {"key": "kind", "label": "Tipo", "format": "text"}, {"key": "diff_units", "label": "Dif. (u.)", "format": "int"}],
            "rows": [{"at": c.occurred_at.astimezone(settings.tz).strftime("%d/%m %H:%M"), "point": cpoints[c.point_id].display_name if c.point_id in cpoints else "—", "kind": c.kind,
                      "diff_units": sum(abs(int(v)) for v in (c.differences or {}).values())} for c in counts if any((c.differences or {}).values())][:TABLE_LIMIT]})
        low = [r for r in stock_rows if r["days_of_stock"] is not None and r["days_of_stock"] < 1.5]
        if low:
            out["insights"].append(insight("alert", f"{len(low)} punto/presentación con menos de 1.5 días de inventario; el primero: {low[0]['point']} · {low[0]['presentation']} ({low[0]['stock']} u.)."))
            out["insights"].append(insight("recommendation", "Programar reposición hoy desde almacén para los puntos con < 1.5 días de inventario."))
        if lots:
            out["insights"].append(insight("alert", f"{len(lots)} lote(s) bloqueado(s): {', '.join(lot.code for lot in lots[:3])}."))
    # Merma por punto y presentación
    wpq = select(Waste.point_id, func.coalesce(func.sum(Waste.qty), 0)).where(Waste.occurred_at >= p.start, Waste.occurred_at < p.end).group_by(Waste.point_id)
    if pids is not None:
        wpq = wpq.where(Waste.point_id.in_(pids))
    wp = db.execute(wpq).all()
    upq = select(Sale.point_id, func.coalesce(func.sum(SaleLine.qty), 0)).join(Sale, Sale.id == SaleLine.sale_id).where(_sales_where(p)).group_by(Sale.point_id)
    up = {r[0]: int(r[1]) for r in db.execute(_apply_sale_scope(upq, sc, pids)).all()}
    wpoints = _names(db, Point, {r[0] for r in wp})
    wrows = sorted([{"point_id": str(pid), "point": wpoints[pid].display_name if pid in wpoints else "—", "waste_units": int(q), "units": up.get(pid, 0), "waste_pct": _waste_pct(up.get(pid, 0), int(q))} for pid, q in wp], key=lambda r: -r["waste_pct"])
    out["tables"].insert(0, {"key": "waste_points", "title": "Merma por punto", "columns": [
        {"key": "point", "label": "Punto", "format": "text", "link": "/reportes/points?point_id={point_id}"}, {"key": "units", "label": "Vendidas", "format": "int"}, {"key": "waste_units", "label": "Merma (u.)", "format": "int"}, {"key": "waste_pct", "label": "Merma %", "format": "pct", "tone": "waste"}], "rows": wrows[:TABLE_LIMIT]})
    out["tables"].insert(1, {"key": "waste_presentations", "title": "Merma por presentación y motivo", "columns": [
        {"key": "presentation", "label": "Presentación", "format": "text"}, {"key": "reason", "label": "Motivo", "format": "text"}, {"key": "units", "label": "Unidades", "format": "int"}, {"key": "value_cents", "label": "Valor", "format": "money"}],
        "rows": sorted([{"presentation": pres[r[0]].name if r[0] in pres else "—", "reason": r[1], "units": int(r[2]), "value_cents": int(r[2]) * prices.get(r[0], 0)} for r in waste_rows], key=lambda r: -r["units"])})
    ins = out["insights"]
    ins.insert(0, insight("fact", f"Merma del periodo {waste_pct:.1f} % ({waste_units} u., {_money(waste_value)} a precio de venta)."))
    if by_reason:
        top_reason = max(by_reason.items(), key=lambda x: x[1])
        ins.insert(1, insight("fact", f"Motivo principal de merma: {top_reason[0]} ({top_reason[1]} u., {top_reason[1] * 100 // max(waste_units, 1)} %)."))
    for r in [r for r in wrows if r["waste_pct"] > 4][:3]:
        ins.append(insight("alert", f"{r['point']}: merma {r['waste_pct']:.1f} % (rojo).", f"/reportes/points?point_id={r['point_id']}"))
    d = _pct(waste_pct, _waste_pct(prev_units, prev_waste))
    if d is not None and abs(d) >= 20:
        ins.append(insight("trend", f"La merma {'subió' if d > 0 else 'bajó'} {abs(d):.0f} % vs {prev.label}."))
    return out


# ───────────────────────────── 7. Calidad y auditorías ─────────────────────────────


def report_quality(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("quality", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    aq = select(Audit).where(Audit.performed_at >= p.start, Audit.performed_at < p.end)
    if pids is not None:
        aq = aq.where(Audit.point_id.in_(pids))
    audits = list(db.execute(aq.order_by(Audit.performed_at.desc())).scalars().all())
    paq = select(func.count(Audit.id)).where(Audit.performed_at >= prev.start, Audit.performed_at < prev.end)
    if pids is not None:
        paq = paq.where(Audit.point_id.in_(pids))
    prev_audits = int(db.execute(paq).scalar_one())
    points = _names(db, Point, {a.point_id for a in audits})
    users = _names(db, User, {a.auditor_id for a in audits})
    items_total = sum(len(a.checklist or {}) for a in audits)
    nc_total = sum(len(a.non_conformities or []) for a in audits)
    by_item: dict[str, int] = {}
    by_point: dict[uuid.UUID, dict] = {}
    for a in audits:
        for k in a.non_conformities or []:
            by_item[k] = by_item.get(k, 0) + 1
        b = by_point.setdefault(a.point_id, {"point_id": str(a.point_id), "point": points[a.point_id].display_name if a.point_id in points else "—", "audits": 0, "nc": 0, "cash_diff_cents": 0})
        b["audits"] += 1
        b["nc"] += len(a.non_conformities or [])
        if a.cash_counted_cents is not None and a.cash_expected_cents is not None:
            b["cash_diff_cents"] += a.cash_counted_cents - a.cash_expected_cents
    acts_q = select(Action).where(Action.created_at >= p.start, Action.created_at < p.end)
    actions = list(db.execute(acts_q).scalars().all())
    if pids is not None:
        aud_ids = {a.id for a in audits}
        case_pts = {c.id: c.point_id for c in db.execute(select(Case).where(Case.id.in_([x.case_id for x in actions if x.case_id]) if actions else literal(False))).scalars().all()} if actions else {}
        actions = [x for x in actions if (x.audit_id in aud_ids) or (x.case_id and case_pts.get(x.case_id) in pids)]
    today = local_today()
    overdue = [x for x in actions if x.status != "done" and x.due_date and x.due_date < today]
    done = [x for x in actions if x.status == "done"]
    # Excepciones de apertura
    shifts = _shifts_in(db, p, sc, pids)
    exc_count: dict[str, int] = {}
    shifts_with_exc = 0
    for s in shifts:
        if s.open_exceptions:
            shifts_with_exc += 1
            for e in s.open_exceptions:
                exc_count[e.get("code", "?")] = exc_count.get(e.get("code", "?"), 0) + 1
    from app.services.shifts import OPEN_EXCEPTION_MESSAGES
    cq = select(Case.category, func.count(Case.id)).where(Case.opened_at >= p.start, Case.opened_at < p.end)
    if pids is not None:
        cq = cq.where(Case.point_id.in_(pids))
    cases_by_cat = {r[0]: int(r[1]) for r in db.execute(cq.group_by(Case.category)).all()}
    conf_pct = round((items_total - nc_total) * 100 / items_total, 1) if items_total else None
    out["kpis"] = [
        kpi("audits", "Auditorías", len(audits), "int", prev_audits, "neutral"),
        kpi("conformity", "Conformidad", conf_pct if conf_pct is not None else 0, "pct", None, "ok" if (conf_pct or 0) >= 90 else "warn" if (conf_pct or 0) >= 75 else "bad", f"{nc_total} no conformidades de {items_total} ítems"),
        kpi("actions_open", "Acciones pendientes", sum(1 for x in actions if x.status != "done"), "int", None, "ok" if not overdue else "bad", f"{len(overdue)} vencidas · {len(done)} cerradas", invert=True),
        kpi("open_exc", "Turnos con excepción de apertura", shifts_with_exc, "int", None, "ok" if not shifts_with_exc else "warn", f"de {len(shifts)} turnos", invert=True),
        kpi("cases", "Casos abiertos en el periodo", sum(cases_by_cat.values()), "int", None, "neutral"),
    ]
    out["charts"].append({"key": "nc_items", "title": "No conformidades por ítem", "type": "bar", "x": "label", "layout": "vertical",
                          "data": [{"label": k, "count": v} for k, v in sorted(by_item.items(), key=lambda x: -x[1])], "series": [{"key": "count", "label": "Veces", "format": "int"}]})
    out["charts"].append({"key": "exceptions", "title": "Excepciones de apertura", "type": "bar", "x": "label", "layout": "vertical",
                          "data": [{"label": OPEN_EXCEPTION_MESSAGES.get(k, k).split(":")[0], "count": v} for k, v in sorted(exc_count.items(), key=lambda x: -x[1])], "series": [{"key": "count", "label": "Turnos", "format": "int"}]})
    out["charts"].append({"key": "cases", "title": "Casos por categoría", "type": "donut", "x": "label", "data": [{"label": k, "count": v} for k, v in sorted(cases_by_cat.items(), key=lambda x: -x[1])], "series": [{"key": "count", "label": "Casos", "format": "int"}]})
    out["tables"].append({"key": "points", "title": "Por punto", "columns": [
        {"key": "point", "label": "Punto", "format": "text", "link": "/reportes/points?point_id={point_id}"}, {"key": "audits", "label": "Auditorías", "format": "int"}, {"key": "nc", "label": "No conf.", "format": "int"}, {"key": "cash_diff_cents", "label": "Dif. arqueo", "format": "money", "tone": "diff"}],
        "rows": sorted(by_point.values(), key=lambda r: -r["nc"])})
    out["tables"].append({"key": "audits", "title": "Auditorías del periodo", "columns": [
        {"key": "at", "label": "Fecha", "format": "text"}, {"key": "point", "label": "Punto", "format": "text"}, {"key": "auditor", "label": "Auditor", "format": "text"}, {"key": "nc", "label": "No conf.", "format": "int"}, {"key": "photos", "label": "Fotos", "format": "int"}, {"key": "audit_id", "label": "", "format": "link", "link": "/auditorias/{audit_id}", "label_text": "Ver"}],
        "rows": [{"audit_id": str(a.id), "at": a.performed_at.astimezone(settings.tz).strftime("%d/%m %H:%M"), "point": points[a.point_id].display_name if a.point_id in points else "—", "auditor": users[a.auditor_id].name if a.auditor_id in users else "—",
                  "nc": len(a.non_conformities or []), "photos": len(a.photos or [])} for a in audits[:TABLE_LIMIT]]})
    owners = _names(db, User, {x.owner_id for x in actions if x.owner_id})
    out["tables"].append({"key": "actions", "title": "Acciones correctivas", "columns": [
        {"key": "description", "label": "Acción", "format": "text"}, {"key": "owner", "label": "Responsable", "format": "text"}, {"key": "due", "label": "Vence", "format": "text"}, {"key": "status", "label": "Estado", "format": "status"}, {"key": "case_id", "label": "", "format": "link", "link": "/casos/{case_id}", "label_text": "Caso"}],
        "rows": [{"description": x.description, "owner": owners[x.owner_id].name if x.owner_id in owners else "—", "due": x.due_date.strftime("%d/%m") if x.due_date else "—",
                  "status": "overdue" if x in overdue else x.status, "case_id": str(x.case_id) if x.case_id else None} for x in sorted(actions, key=lambda x: (x.status == "done", x.due_date or today))[:TABLE_LIMIT]]})
    ins = out["insights"]
    ins.append(insight("fact", f"{len(audits)} auditoría(s) con {nc_total} no conformidad(es); conformidad {conf_pct if conf_pct is not None else '—'} %."))
    if by_item:
        top = max(by_item.items(), key=lambda x: x[1])
        ins.append(insight("fact", f"El ítem que más falla es «{top[0]}» ({top[1]} veces)."))
    for r in sorted(by_point.values(), key=lambda r: -r["nc"])[:2]:
        if r["nc"] >= 2:
            ins.append(insight("alert", f"{r['point']} acumula {r['nc']} no conformidades en {r['audits']} auditoría(s).", f"/reportes/points?point_id={r['point_id']}"))
    if overdue:
        ins.append(insight("alert", f"{len(overdue)} acción(es) correctiva(s) vencida(s)."))
        ins.append(insight("recommendation", "Reasignar o cerrar las acciones vencidas esta semana; una acción vencida sin dueño no corrige nada."))
    if shifts and shifts_with_exc * 100 / len(shifts) > 20:
        ins.append(insight("trend", f"{shifts_with_exc * 100 // len(shifts)} % de los turnos abrieron con alguna excepción."))
    if len(audits) == 0 and len(shifts) > 5:
        ins.append(insight("recommendation", "No hubo auditorías en el periodo: programar al menos una visita por zona."))
    return out


# ───────────────────────────── 8. Mantenimiento y disponibilidad ─────────────────────────────


def report_maintenance(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("maintenance", p, prev, sc, filters)
    now = utcnow()
    pids = _point_ids(db, sc)
    # Carritos en alcance: los usados por turnos/asignaciones de la zona en el periodo (supervisor) o todos.
    cart_ids: set[uuid.UUID] | None = None
    if sc.zone_id is not None or sc.cart_id is not None:
        q = select(Assignment.cart_id).where(Assignment.shift_date >= p.start_day - timedelta(days=30), Assignment.shift_date <= p.end_day)
        if pids is not None:
            q = q.where(Assignment.point_id.in_(pids))
        cart_ids = {r[0] for r in db.execute(q).all()}
        if sc.cart_id is not None:
            cart_ids = cart_ids & {sc.cart_id} if sc.zone_id is not None else {sc.cart_id}
    carts = {c.id: c for c in db.execute(select(Cart)).scalars().all()}
    aq = select(Asset)
    if cart_ids is not None:
        aq = aq.where(Asset.cart_id.in_(cart_ids))
    assets = list(db.execute(aq).scalars().all())
    asset_ids = {a.id for a in assets}
    tq = select(MaintenanceTicket).where(or_(and_(MaintenanceTicket.created_at >= p.start, MaintenanceTicket.created_at < p.end), MaintenanceTicket.status.in_(("open", "in_progress"))))
    if cart_ids is not None:
        tq = tq.where(MaintenanceTicket.asset_id.in_(asset_ids) if asset_ids else literal(False))
    tickets = list(db.execute(tq.order_by(MaintenanceTicket.created_at.desc())).scalars().all())
    open_t = [t for t in tickets if t.status in ("open", "in_progress")]
    overdue = [a for a in assets if a.next_maintenance_at and a.next_maintenance_at < now and a.status == "active"]
    # Tiempo fuera de servicio: tickets urgentes/correctivos desde creación hasta resolución (acotado al periodo)
    downtime_h: dict[uuid.UUID, float] = {}
    mttr = []
    for t in tickets:
        if t.kind != "corrective":
            continue
        s0 = max(t.created_at, p.start)
        s1 = min(t.resolved_at or now, p.end)
        if s1 > s0:
            downtime_h[t.asset_id] = downtime_h.get(t.asset_id, 0.0) + (s1 - s0).total_seconds() / 3600
        if t.resolved_at:
            mttr.append((t.resolved_at - t.created_at).total_seconds() / 3600)
    period_h = p.days * 24.0
    # Disponibilidad por carrito: tiempo fuera = tickets correctivos de sus activos (batería, cargador, POS, carrito).
    scope_carts = [c for c in carts.values() if c.is_active and (cart_ids is None or c.id in cart_ids)]
    avail_rows = []
    for c in scope_carts:
        c_assets = [a for a in assets if a.cart_id == c.id]
        d = min(sum(downtime_h.get(a.id, 0.0) for a in c_assets), period_h)
        avail = round(max(period_h - d, 0) * 100 / period_h, 1) if period_h else 100.0
        c_overdue = [a for a in c_assets if a in overdue]
        nxt = min((a.next_maintenance_at for a in c_assets if a.next_maintenance_at), default=None)
        avail_rows.append({"cart_id": str(c.id), "cart": c.code, "assets": len(c_assets), "status": "maintenance" if any(t.asset_id in {a.id for a in c_assets} and t.severity == "urgent" for t in open_t) else "active",
                           "availability_pct": avail, "downtime_h": round(d, 1),
                           "next_maintenance": nxt.astimezone(settings.tz).strftime("%d/%m/%Y") if nxt else "—",
                           "overdue_days": max((int((now - a.next_maintenance_at).total_seconds() // 86400) for a in c_overdue), default=0),
                           "open_tickets": sum(1 for t in open_t if t.asset_id in {a.id for a in c_assets})})
    avail_rows.sort(key=lambda r: (r["availability_pct"], -r["overdue_days"]))
    low_avail = [r for r in avail_rows if r["availability_pct"] < 95]
    # Batería: pings del periodo
    bq = select(GpsPing.shift_id, func.min(GpsPing.battery_pct), func.avg(GpsPing.battery_pct)).where(GpsPing.at >= p.start, GpsPing.at < p.end, GpsPing.battery_pct.is_not(None)).group_by(GpsPing.shift_id)
    shifts = {s.id: s for s in _shifts_in(db, p, sc, pids)}
    bat = [(shifts[r[0]], int(r[1]), float(r[2])) for r in db.execute(bq).all() if r[0] in shifts]
    low_bat = [b for b in bat if b[1] < 25]
    out["kpis"] = [
        kpi("assets", "Activos", len(assets), "int", None, "neutral", f"{len(scope_carts)} carritos"),
        kpi("availability", "Disponibilidad promedio", round(sum(r["availability_pct"] for r in avail_rows) / len(avail_rows), 1) if avail_rows else 100.0, "pct", None, "ok" if not low_avail else "warn" if len(low_avail) <= 2 else "bad", f"{len(low_avail)} carritos < 95 %"),
        kpi("overdue", "Preventivos vencidos", len(overdue), "int", None, "ok" if not overdue else "bad", invert=True),
        kpi("tickets_open", "Tickets abiertos", len(open_t), "int", None, "ok" if not open_t else "warn", f"{sum(1 for t in open_t if t.severity == 'urgent')} urgentes", invert=True),
        kpi("mttr", "MTTR (h)", round(sum(mttr) / len(mttr), 1) if mttr else 0, "float", None, "neutral", f"{len(mttr)} tickets resueltos"),
        kpi("low_battery", "Turnos con batería < 25 %", len(low_bat), "int", None, "ok" if not low_bat else "warn", f"de {len(bat)} con lectura", invert=True),
    ]
    out["charts"].append({"key": "availability", "title": "Disponibilidad por carrito", "type": "bar", "x": "cart", "layout": "vertical",
                          "data": [{"cart": r["cart"], "availability_pct": r["availability_pct"]} for r in avail_rows[:15]], "series": [{"key": "availability_pct", "label": "%", "format": "pct"}], "domain": [0, 100]})
    sev: dict[str, int] = {}
    for t in tickets:
        sev[t.severity] = sev.get(t.severity, 0) + 1
    out["charts"].append({"key": "tickets", "title": "Tickets por severidad", "type": "donut", "x": "label", "data": [{"label": k, "count": v} for k, v in sev.items()], "series": [{"key": "count", "label": "Tickets", "format": "int"}]})
    out["tables"].append({"key": "carts", "title": "Carritos", "columns": [
        {"key": "cart", "label": "Carrito", "format": "text"}, {"key": "assets", "label": "Activos", "format": "int"}, {"key": "status", "label": "Estado", "format": "status"}, {"key": "availability_pct", "label": "Disponib.", "format": "pct", "tone": "avail"},
        {"key": "downtime_h", "label": "Horas fuera", "format": "float"}, {"key": "next_maintenance", "label": "Próx. preventivo", "format": "text"}, {"key": "overdue_days", "label": "Vencido (d)", "format": "int"}, {"key": "open_tickets", "label": "Tickets", "format": "int"}], "rows": avail_rows})
    anames = {a.id: a for a in assets}
    out["tables"].append({"key": "tickets", "title": "Tickets", "columns": [
        {"key": "created", "label": "Creado", "format": "text"}, {"key": "asset", "label": "Activo", "format": "text"}, {"key": "title", "label": "Título", "format": "text"}, {"key": "kind", "label": "Tipo", "format": "text"},
        {"key": "severity", "label": "Severidad", "format": "status"}, {"key": "status", "label": "Estado", "format": "status"}, {"key": "hours", "label": "Horas", "format": "float"}],
        "rows": [{"created": t.created_at.astimezone(settings.tz).strftime("%d/%m %H:%M"), "asset": anames[t.asset_id].code if t.asset_id in anames else "—", "title": t.title, "kind": t.kind, "severity": t.severity, "status": t.status,
                  "hours": round(((t.resolved_at or now) - t.created_at).total_seconds() / 3600, 1)} for t in tickets[:TABLE_LIMIT]]})
    ins = out["insights"]
    if low_avail:
        ins.append(insight("alert", f"{len(low_avail)} carrito(s) con disponibilidad < 95 %: {', '.join(r['cart'] for r in low_avail[:3])}."))
    for a in overdue[:3]:
        ins.append(insight("alert", f"Preventivo vencido: {a.code} desde hace {int((now - a.next_maintenance_at).total_seconds() // 86400)} día(s)."))
    if overdue:
        ins.append(insight("recommendation", "Programar los preventivos vencidos esta semana; un carrito parado no vende."))
    if low_bat:
        worst = min(low_bat, key=lambda b: b[1])
        ins.append(insight("fact", f"{len(low_bat)} turno(s) con batería < 25 %; mínimo {worst[1]} % en el carrito {carts[worst[0].cart_id].code if worst[0].cart_id in carts else '—'}."))
        if len(low_bat) >= 3:
            ins.append(insight("hypothesis", "Baterías bajas recurrentes: revisar ciclo de carga nocturna o reemplazo de baterías antes de asumir mal uso."))
    if mttr:
        ins.append(insight("fact", f"MTTR {sum(mttr) / len(mttr):.1f} h en {len(mttr)} ticket(s) correctivo(s) resuelto(s)."))
    if not tickets and not overdue:
        ins.append(insight("fact", "Sin tickets ni preventivos vencidos en el periodo."))
    return out


# ───────────────────────────── 9. Cumplimiento operativo y GPS ─────────────────────────────


def report_compliance(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    from app.routers.me import require_open_photo
    from app.services.cases import get_rule_params
    from app.services.shifts import OPEN_EXCEPTION_MESSAGES

    out = _empty_payload("compliance", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    now = utcnow()
    aq = select(Assignment).where(Assignment.shift_date >= p.start_day, Assignment.shift_date <= p.end_day)
    if pids is not None:
        aq = aq.where(Assignment.point_id.in_(pids))
    if sc.operator_id is not None:
        aq = aq.where(Assignment.operator_id == sc.operator_id)
    if sc.cart_id is not None:
        aq = aq.where(Assignment.cart_id == sc.cart_id)
    assignments = list(db.execute(aq).scalars().all())
    shifts = _shifts_in(db, p, sc, pids)
    by_assignment: dict[uuid.UUID, Shift] = {}
    for s in shifts:
        if s.assignment_id and s.assignment_id not in by_assignment:
            by_assignment[s.assignment_id] = s
    grace = int(get_rule_params(db, "no_open").get("grace_minutes", 20))
    sampling = get_int(db, "photo_sampling_pct")
    points = _names(db, Point, {a.point_id for a in assignments} | {s.point_id for s in shifts})
    users = _names(db, User, {a.operator_id for a in assignments} | {s.operator_id for s in shifts})
    from app.models.system import Evidence
    photo_shift_ids = {r[0] for r in db.execute(select(Evidence.shift_id).where(Evidence.kind == "shift_open", Evidence.shift_id.in_([s.id for s in shifts]) if shifts else literal(False))).all()} if shifts else set()
    late = no_open = on_time = 0
    photo_req = photo_ok = 0
    rows = []
    per_op: dict[uuid.UUID, dict] = {}
    per_point: dict[uuid.UUID, dict] = {}
    for a in assignments:
        s = by_assignment.get(a.id)
        planned_end_passed = a.planned_end < now
        op = per_op.setdefault(a.operator_id, {"operator_id": str(a.operator_id), "operator": users[a.operator_id].name if a.operator_id in users else "—", "assigned": 0, "on_time": 0, "late": 0, "no_open": 0, "out_of_point": 0, "geofence_out": 0, "stale": 0})
        pt = per_point.setdefault(a.point_id, {"point_id": str(a.point_id), "point": points[a.point_id].display_name if a.point_id in points else "—", "assigned": 0, "on_time": 0, "late": 0, "no_open": 0, "out_of_point": 0})
        op["assigned"] += 1
        pt["assigned"] += 1
        if s is None:
            status = "no_open" if (a.status == "absent" or planned_end_passed or (now - a.planned_start).total_seconds() > grace * 60) else "pending"
            if status == "no_open":
                no_open += 1
                op["no_open"] += 1
                pt["no_open"] += 1
            late_min = None
            exc = []
        else:
            late_min = max(int((s.opened_at - a.planned_start).total_seconds() // 60), 0)
            status = "late" if late_min > grace else "on_time"
            if status == "late":
                late += 1
                op["late"] += 1
                pt["late"] += 1
            else:
                on_time += 1
                op["on_time"] += 1
                pt["on_time"] += 1
            exc = [e.get("code") for e in (s.open_exceptions or [])]
            if "out_of_geofence" in exc:
                op["out_of_point"] += 1
                pt["out_of_point"] += 1
            if require_open_photo(a.id, sampling):
                photo_req += 1
                if s.id in photo_shift_ids:
                    photo_ok += 1
        dist = next((e.get("distance_m") for e in (s.open_exceptions or []) if e.get("code") == "out_of_geofence"), None) if s else None
        rows.append({"assignment_id": str(a.id), "shift_id": str(s.id) if s else None, "date": a.shift_date.strftime("%d/%m"), "point_id": str(a.point_id), "point": pt["point"], "operator_id": str(a.operator_id), "operator": op["operator"],
                     "planned": a.planned_start.astimezone(settings.tz).strftime("%H:%M"), "opened": s.opened_at.astimezone(settings.tz).strftime("%H:%M") if s else "—", "late_minutes": late_min, "status": status,
                     "distance_m": dist, "exceptions": ", ".join(OPEN_EXCEPTION_MESSAGES.get(c, c).split(":")[0] for c in exc) if exc else "", "synced": s.status != "open" or (s.last_seen_at is not None and (now - s.last_seen_at).total_seconds() < 3600) if s else None})
    # Geocerca durante el turno
    gq = select(GpsPing.shift_id, func.count(GpsPing.id), func.sum(case((GpsPing.in_geofence.is_(False), 1), else_=0)), func.sum(case((GpsPing.mocked.is_(True), 1), else_=0))).where(GpsPing.at >= p.start, GpsPing.at < p.end).group_by(GpsPing.shift_id)
    shift_ids = {s.id: s for s in shifts}
    pings = {r[0]: (int(r[1]), int(r[2] or 0), int(r[3] or 0)) for r in db.execute(gq).all() if r[0] in shift_ids}
    total_pings = sum(v[0] for v in pings.values())
    out_pings = sum(v[1] for v in pings.values())
    mocked = sum(v[2] for v in pings.values())
    for sid, (n, o, m) in pings.items():
        if o * 100 / n > 20:
            s = shift_ids[sid]
            per_op.setdefault(s.operator_id, {"operator_id": str(s.operator_id), "operator": users[s.operator_id].name if s.operator_id in users else "—", "assigned": 0, "on_time": 0, "late": 0, "no_open": 0, "out_of_point": 0, "geofence_out": 0, "stale": 0})["geofence_out"] += 1
    # Sin sincronizar: casos sync_stale del periodo
    sq = select(Case).where(Case.rule_key == "sync_stale", Case.opened_at >= p.start, Case.opened_at < p.end)
    if pids is not None:
        sq = sq.where(Case.point_id.in_(pids))
    stale_cases = list(db.execute(sq).scalars().all())
    for c in stale_cases:
        s = shift_ids.get(c.shift_id)
        if s and s.operator_id in per_op:
            per_op[s.operator_id]["stale"] += 1
    total_assign = len(assignments)
    out_of_point = sum(r["out_of_point"] for r in per_point.values())
    comp_pct = round(on_time * 100 / total_assign, 1) if total_assign else 0.0
    out["kpis"] = [
        kpi("compliance", "Aperturas a tiempo", comp_pct, "pct", None, "ok" if comp_pct >= 90 else "warn" if comp_pct >= 75 else "bad", f"{on_time} de {total_assign} asignaciones (gracia {grace} min)"),
        kpi("late", "Aperturas tarde", late, "int", None, "ok" if not late else "warn", invert=True),
        kpi("no_open", "Sin abrir", no_open, "int", None, "ok" if not no_open else "bad", invert=True),
        kpi("out", "Fuera del punto (> 50 m)", out_of_point, "int", None, "ok" if not out_of_point else "bad", "aperturas con out_of_geofence", invert=True),
        kpi("geofence", "Pings fuera de geocerca", round(out_pings * 100 / total_pings, 1) if total_pings else 0.0, "pct", None, "ok" if not out_pings else "warn", f"{out_pings} de {total_pings} pings · {mocked} simulados", invert=True),
        kpi("stale", "Casos sin sincronizar", len(stale_cases), "int", None, "ok" if not stale_cases else "warn", invert=True),
        kpi("photos", "Fotos de muestreo", round(photo_ok * 100 / photo_req, 1) if photo_req else 100.0, "pct", None, "ok" if photo_ok == photo_req else "warn", f"{photo_ok} de {photo_req} requeridas ({sampling} %)"),
    ]
    by_day: dict[str, dict] = {}
    for r in rows:
        d = by_day.setdefault(r["date"], {"label": r["date"], "on_time": 0, "late": 0, "no_open": 0, "pending": 0})
        d[r["status"]] += 1
    out["charts"].append({"key": "days", "title": "Aperturas por día", "type": "stacked", "x": "label", "data": list(by_day.values()),
                          "series": [{"key": "on_time", "label": "A tiempo", "format": "int", "color": "ok"}, {"key": "late", "label": "Tarde", "format": "int", "color": "warn"}, {"key": "no_open", "label": "Sin abrir", "format": "int", "color": "bad"}]})
    op_rows = sorted(per_op.values(), key=lambda r: (-(r["no_open"] + r["late"] + r["out_of_point"]), r["operator"]))
    out["tables"].append({"key": "operators", "title": "Por vendedor", "columns": [
        {"key": "operator", "label": "Vendedor", "format": "text", "link": "/reportes/people?operator_id={operator_id}"}, {"key": "assigned", "label": "Asignados", "format": "int"}, {"key": "on_time", "label": "A tiempo", "format": "int"},
        {"key": "late", "label": "Tarde", "format": "int"}, {"key": "no_open", "label": "Sin abrir", "format": "int"}, {"key": "out_of_point", "label": "Fuera del punto", "format": "int"}, {"key": "geofence_out", "label": "Turnos fuera de geocerca", "format": "int"}, {"key": "stale", "label": "Sin sync", "format": "int"}], "rows": op_rows})
    out["tables"].append({"key": "points", "title": "Por punto", "columns": [
        {"key": "point", "label": "Punto", "format": "text", "link": "/reportes/points?point_id={point_id}"}, {"key": "assigned", "label": "Asignados", "format": "int"}, {"key": "on_time", "label": "A tiempo", "format": "int"}, {"key": "late", "label": "Tarde", "format": "int"}, {"key": "no_open", "label": "Sin abrir", "format": "int"}, {"key": "out_of_point", "label": "Fuera del punto", "format": "int"}],
        "rows": sorted(per_point.values(), key=lambda r: -(r["no_open"] + r["late"] + r["out_of_point"]))})
    out["tables"].append({"key": "detail", "title": "Detalle de aperturas (incidencias primero)", "columns": [
        {"key": "date", "label": "Día", "format": "text"}, {"key": "point", "label": "Punto", "format": "text"}, {"key": "operator", "label": "Vendedor", "format": "text"}, {"key": "planned", "label": "Plan", "format": "text"}, {"key": "opened", "label": "Abrió", "format": "text"},
        {"key": "late_minutes", "label": "Retraso (min)", "format": "int"}, {"key": "status", "label": "Estado", "format": "status"}, {"key": "distance_m", "label": "Distancia (m)", "format": "int"}, {"key": "exceptions", "label": "Excepciones", "format": "text"}],
        "rows": sorted(rows, key=lambda r: (r["status"] in ("on_time", "pending"), r["date"]))[:TABLE_LIMIT]})
    ins = out["insights"]
    ins.append(insight("fact", f"{comp_pct:.0f} % de aperturas a tiempo: {late} tarde y {no_open} sin abrir de {total_assign} asignaciones."))
    if out_of_point:
        ins.append(insight("alert", f"{out_of_point} apertura(s) a más de la distancia permitida del punto asignado (regla de 50 m).", "/excepciones"))
    for r in op_rows[:3]:
        if r["no_open"] + r["late"] >= 2:
            ins.append(insight("alert", f"{r['operator']}: {r['late']} tarde y {r['no_open']} sin abrir de {r['assigned']} asignaciones."))
    if mocked:
        ins.append(insight("alert", f"{mocked} ping(s) con ubicación simulada."))
    if photo_req and photo_ok < photo_req:
        ins.append(insight("fact", f"Faltan {photo_req - photo_ok} foto(s) de muestreo en aperturas que la requerían."))
    if op_rows and (op_rows[0]["no_open"] + op_rows[0]["late"]) >= 3:
        ins.append(insight("recommendation", f"Hablar hoy con {op_rows[0]['operator']} y revisar su asignación; reincidencia en puntualidad."))
    return out


# ───────────────────────────── 10. Expansión y ubicaciones ─────────────────────────────


def report_expansion(db: Session, p: Period, prev: Period, sc: Scope, current, filters: dict) -> dict:
    out = _empty_payload("expansion", p, prev, sc, filters)
    pids = _point_ids(db, sc)
    now = utcnow()
    rows = _points_rows(db, p, prev, sc, pids, now)
    cat = load_catalog()
    cat_by_rank = {int(r["ranking"]): r for r in cat["points"]}
    active_ranks = {int(r["meta"].get("ranking")) for r in rows if r["meta"].get("ranking") is not None}
    verdicts = {"GO": 0, "AJUSTAR": 0, "NO GO": 0, "SIN DATOS": 0}
    for r in rows:
        d = r["days_open"]
        # Meta proporcional a los días con turno (no al periodo completo)
        r["target_pct_open_days"] = round(r["sales_cents"] * 100 / (r["daily_target_cents"] * d), 1) if (d and r["daily_target_cents"]) else 0.0
        eff = r["target_pct_open_days"] if d else 0.0
        if d < 3:
            v, why = "SIN DATOS", f"sólo {d} día(s) con turno"
        elif eff >= 90 and (r["ticket_cents"] or 0) >= 3600 and (r["waste_pct"] or 0) <= 4 and r["open_cases"] <= 2:
            v, why = "GO", f"{eff:.0f} % de meta, ticket {_money(r['ticket_cents'] or 0)}, merma {(r['waste_pct'] or 0):.1f} %"
        elif eff >= 60:
            v, why = "AJUSTAR", f"{eff:.0f} % de meta" + (", ticket bajo" if (r["ticket_cents"] or 0) < 3600 else "") + (", merma alta" if (r["waste_pct"] or 0) > 4 else "") + (f", {r['open_cases']} casos" if r["open_cases"] > 2 else "")
        else:
            v, why = "NO GO", f"{eff:.0f} % de meta en {d} días con turno"
        r["verdict"], r["verdict_why"] = v, why
        verdicts[v] += 1
        m = r["meta"]
        r.update({"alcaldia": m.get("alcaldia"), "node_type": m.get("node_type"), "risk": m.get("riesgo"), "catalog_rank": m.get("ranking"), "afluencia": m.get("afluencia")})
        # Fase 2: rentabilidad (costos / renta / payback) — campos preparados
        r.update({"cost_cents": None, "rent_cents": None, "margin_cents": None, "payback_days": None})
    # Candidatos del catálogo aún sin punto activo
    candidates = [c for rk, c in sorted(cat_by_rank.items()) if rk not in active_ranks]
    out["kpis"] = [
        kpi("active", "Puntos activos", len(rows), "int", None, "neutral", f"{len(active_ranks)} del catálogo de {len(cat_by_rank)}"),
        kpi("go", "GO", verdicts["GO"], "int", None, "ok"),
        kpi("adjust", "AJUSTAR", verdicts["AJUSTAR"], "int", None, "warn"),
        kpi("nogo", "NO GO", verdicts["NO GO"], "int", None, "bad" if verdicts["NO GO"] else "ok", invert=True),
        kpi("nodata", "Sin datos", verdicts["SIN DATOS"], "int", None, "neutral", "< 3 días con turno"),
        kpi("candidates", "Ubicaciones sin abrir", len(candidates), "int", None, "neutral", f"mejor score disponible: {candidates[0]['score'] if candidates else '—'}"),
    ]
    out["charts"].append({"key": "verdicts", "title": "Semáforo de puntos", "type": "donut", "x": "label", "data": [{"label": k, "count": v} for k, v in verdicts.items() if v], "series": [{"key": "count", "label": "Puntos", "format": "int"}]})
    by_alc: dict[str, dict] = {}
    for r in rows:
        a = by_alc.setdefault(r["alcaldia"] or r["zone"], {"label": r["alcaldia"] or r["zone"], "sales_cents": 0, "points": 0})
        a["sales_cents"] += r["sales_cents"]
        a["points"] += 1
    out["charts"].append({"key": "alcaldias", "title": "Ventas por alcaldía", "type": "bar", "x": "label", "data": sorted(by_alc.values(), key=lambda x: -x["sales_cents"]), "series": [{"key": "sales_cents", "label": "Ventas", "format": "money"}]})
    out["charts"].append({"key": "scatter", "title": "Score del catálogo vs % de meta (días con turno)", "type": "scatter", "x": "score", "y": "target_pct_open_days",
                          "data": [{"point": r["point"], "score": r["score"], "target_pct_open_days": r["target_pct_open_days"], "verdict": r["verdict"]} for r in rows if r["score"] is not None and r["days_open"]], "x_label": "Score /100", "y_label": "% meta"})
    cols = [
        {"key": "verdict", "label": "Semáforo", "format": "verdict"}, {"key": "point", "label": "Punto", "format": "text", "link": "/reportes/points?point_id={point_id}"}, {"key": "alcaldia", "label": "Alcaldía", "format": "text"}, {"key": "node_type", "label": "Tipo de nodo", "format": "text"},
        {"key": "score", "label": "Score", "format": "int"}, {"key": "risk", "label": "Riesgo", "format": "text"}, {"key": "days_open", "label": "Días c/turno", "format": "int"}, {"key": "sales_cents", "label": "Ventas", "format": "money"},
        {"key": "target_pct_open_days", "label": "% meta", "format": "pct", "tone": "target"}, {"key": "ticket_cents", "label": "Ticket", "format": "money", "tone": "ticket"}, {"key": "waste_pct", "label": "Merma", "format": "pct", "tone": "waste"},
        {"key": "open_cases", "label": "Casos", "format": "int"}, {"key": "verdict_why", "label": "Criterio", "format": "text"},
    ]
    order = {"NO GO": 0, "AJUSTAR": 1, "GO": 2, "SIN DATOS": 3}
    out["tables"].append({"key": "verdicts", "title": "Decisión por punto", "columns": cols, "rows": sorted(rows, key=lambda r: (order[r["verdict"]], -r["sales_cents"]))[:TABLE_LIMIT]})
    out["tables"].append({"key": "candidates", "title": "Ubicaciones del catálogo aún sin punto (mejor score primero)", "columns": [
        {"key": "ranking", "label": "#", "format": "int"}, {"key": "name", "label": "Ubicación", "format": "text"}, {"key": "alcaldia", "label": "Alcaldía", "format": "text"}, {"key": "node_type", "label": "Tipo", "format": "text"},
        {"key": "score", "label": "Score", "format": "int"}, {"key": "afluencia", "label": "Afluencia", "format": "text"}, {"key": "riesgo", "label": "Riesgo", "format": "text"}, {"key": "horario_sugerido", "label": "Horario", "format": "text"}],
        "rows": [{k: c.get(k) for k in ("ranking", "name", "alcaldia", "node_type", "score", "afluencia", "riesgo", "horario_sugerido")} for c in candidates[:25]]})
    ins = out["insights"]
    ins.append(insight("fact", f"{verdicts['GO']} GO · {verdicts['AJUSTAR']} AJUSTAR · {verdicts['NO GO']} NO GO · {verdicts['SIN DATOS']} sin datos, sobre {len(rows)} puntos activos ({p.label})."))
    for r in [r for r in rows if r["verdict"] == "NO GO"][:3]:
        ins.append(insight("recommendation", f"{r['point']} debería evaluarse para reubicación o cierre: {r['verdict_why']}.", f"/reportes/points?point_id={r['point_id']}"))
    for r in [r for r in rows if r["verdict"] == "AJUSTAR" and (r["score"] or 0) >= 85][:2]:
        ins.append(insight("hypothesis", f"{r['point']} (score {r['score']}) está en AJUSTAR: el lugar tiene potencial; probar horario sugerido o cambio de vendedor antes de reubicar."))
    if candidates:
        c = candidates[0]
        ins.append(insight("recommendation", f"Siguiente apertura sugerida: #{c['ranking']} {c['name']} ({c['alcaldia']}, score {c['score']}, riesgo {c.get('riesgo', '—')}). Validar en campo: {c.get('validacion', 'permiso y resguardo')}."))
    ins.append(insight("fact", "Rentabilidad por punto (costos, renta, payback) queda en fase 2: los campos existen en el payload pero no hay captura de costos todavía."))
    return out


# ───────────────────────────── Dispatcher ─────────────────────────────

BUILDERS: dict[str, Callable] = {
    "executive": report_executive, "sales": report_sales, "cash": report_cash, "points": report_points, "people": report_people,
    "inventory": report_inventory, "quality": report_quality, "maintenance": report_maintenance, "compliance": report_compliance, "expansion": report_expansion,
}


def allowed_reports(current) -> list[str]:
    """Claves de reporte que el usuario puede consultar. `reports.self` (operador) habilita sales y people en modo propio."""
    out = []
    for key, meta in REPORTS.items():
        if current.has(meta["perm"]) or (key in ("sales", "people") and current.has("reports.self")):
            out.append(key)
    return out


def catalog_for(current) -> dict:
    allowed = set(allowed_reports(current))
    cats: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
    for key, meta in REPORTS.items():
        if key in allowed:
            cats[meta["category"]].append({"key": key, **{k: meta[k] for k in ("title", "description", "decision", "frequency", "orientation")},
                                           "scope": "zone" if current.role == "supervisor" else "self" if current.role == "operator" else "network"})
    return {"categories": [{"name": c, "reports": r} for c, r in cats.items() if r], "presets": [{"key": k, "label": PRESET_LABELS[k]} for k in PRESETS]}


def can_view(current, key: str) -> bool:
    return key in allowed_reports(current)


def build_report(db: Session, key: str, current, *, period: str | None, date_from: str | None, date_to: str | None, filters: dict[str, Any]) -> dict:
    if key not in REPORTS:
        raise ApiError("NOT_FOUND", "Reporte no encontrado")
    p = parse_period(period, date_from, date_to)
    prev = previous_period(p)
    sc = build_scope(current, filters)
    return BUILDERS[key](db, p, prev, sc, current, filters)
