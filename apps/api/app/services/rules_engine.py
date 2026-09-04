"""Motor de reglas determinísticas (§6).

`run_rules(db, now) -> {"alerts_created": n, "cases_created": n}`
Cada regla habilitada evalúa la red y, si dispara y no hay caso abierto con el mismo
`dedupe_key = rule_key:point_id:date`, crea Alert + Case (vía `open_case_if_new`).
"""
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import local_day_bounds, local_today, utcnow
from app.models.cases import Alert, Case, Rule
from app.models.catalog import DailyTarget
from app.models.inventory import InventoryCount, InventoryMovement, Waste
from app.models.ops import GpsPing, Shift
from app.models.org import Assignment, Asset, Point
from app.models.sales import Sale, SaleCancellation, SaleLine
from app.models.system import Event
from app.services import events
from app.services.cases import DEFAULT_RULE_PARAMS, open_case_if_new
from app.services.settings import cash_thresholds, get_int, inventory_tolerance
from app.services.geo import haversine_m
from app.services.inventory import balances_all

log = logging.getLogger("pepito.rules")


class Ctx:
    def __init__(self, db: Session, now: datetime, rule: Rule):
        self.db = db
        self.now = now
        self.rule = rule
        self.params = {**DEFAULT_RULE_PARAMS.get(rule.key, {}), **(rule.params or {})}
        self.today = local_today(now)
        self.day_start, self.day_end = local_day_bounds(self.today)
        self.created = 0
        self.resolved = 0
        self.firing: set = set()  # puntos donde la condición sigue vigente en esta corrida

    def case(self, *, point_id, severity=None, title, description, shift_id=None, impact=0.0, payload=None, event=None):
        self.firing.add(point_id)
        c = open_case_if_new(
            self.db, rule_key=self.rule.key, point_id=point_id, shift_id=shift_id, severity=severity or self.rule.severity,
            title=title, description=description, impact_score=impact, source="rule", payload=payload or {}, dedupe_date=self.now,
        )
        if c is not None:
            self.created += 1
            if event:
                events.emit(self.db, event, point_id=point_id, shift_id=shift_id, entity="case", entity_id=c.id, payload=payload or {}, occurred_at=self.now)
        return c


def _open_shifts(db: Session) -> list[Shift]:
    return db.query(Shift).filter(Shift.status == "open").all()


def _last_ping(db: Session, shift_id: uuid.UUID) -> GpsPing | None:
    return db.query(GpsPing).filter(GpsPing.shift_id == shift_id).order_by(GpsPing.at.desc()).first()


def _target_cents(db: Session, point: Point, day) -> int:
    t = db.query(DailyTarget).filter(DailyTarget.point_id == point.id, DailyTarget.target_date == day).first()
    if t:
        return t.target_cents
    return point.daily_target_cents or get_int(db, "daily_sales_target_default_cents")


# ---------------- Reglas ----------------
def rule_no_open(ctx: Ctx) -> None:
    grace = int(ctx.params.get("grace_minutes", 20))
    limit = ctx.now - timedelta(minutes=grace)
    assignments = ctx.db.query(Assignment).filter(Assignment.shift_date == ctx.today, Assignment.planned_start <= limit).all()
    for a in assignments:
        has_shift = ctx.db.query(Shift).filter(Shift.assignment_id == a.id).first()
        if has_shift:
            continue
        late_min = int((ctx.now - a.planned_start).total_seconds() // 60)
        point = ctx.db.get(Point, a.point_id)
        ctx.case(
            point_id=a.point_id, title=f"Punto sin abrir: {point.display_name if point else ''}",
            description=f"El operador {a.operator.name} no ha abierto; {late_min} min después de la hora planeada",
            impact=min(late_min / 10, 30), payload={"assignment_id": str(a.id), "operator_id": str(a.operator_id), "late_minutes": late_min},
            event="PointLate",
        )


def rule_out_of_geofence(ctx: Ctx) -> None:
    minutes = int(ctx.params.get("minutes", 10))
    for shift in _open_shifts(ctx.db):
        pings = ctx.db.query(GpsPing).filter(GpsPing.shift_id == shift.id).order_by(GpsPing.at.desc()).limit(200).all()
        if not pings or pings[0].in_geofence is not False:
            continue
        # inicio de la racha fuera de geocerca
        streak_start = pings[0].at
        for p in pings:
            if p.in_geofence is False:
                streak_start = p.at
            else:
                break
        if (pings[0].at - streak_start) >= timedelta(minutes=minutes) or (ctx.now - streak_start) >= timedelta(minutes=minutes) and len(pings) > 1:
            point = ctx.db.get(Point, shift.point_id)
            dist = haversine_m(pings[0].lat, pings[0].lng, point.lat, point.lng) if point else 0
            ctx.case(
                point_id=shift.point_id, shift_id=shift.id, title=f"Fuera de geocerca: {point.display_name if point else ''}",
                description=f"Último GPS a {int(dist)} m del punto por más de {minutes} min", impact=20,
                payload={"distance_m": int(dist), "since": streak_start.isoformat(), "mocked": pings[0].mocked},
            )


def rule_low_sales_trajectory(ctx: Ctx) -> None:
    pct = float(ctx.params.get("pct", 60))
    min_hours = float(ctx.params.get("min_hours", 2))
    for shift in _open_shifts(ctx.db):
        hours_open = (ctx.now - shift.opened_at).total_seconds() / 3600
        if hours_open < min_hours:
            continue
        point = ctx.db.get(Point, shift.point_id)
        target = _target_cents(ctx.db, point, ctx.today)
        planned_hours = 10.0
        if shift.assignment_id:
            a = ctx.db.get(Assignment, shift.assignment_id)
            if a:
                planned_hours = max(1.0, (a.planned_end - a.planned_start).total_seconds() / 3600)
        prorated = target * min(hours_open, planned_hours) / planned_hours
        sales = ctx.db.execute(select(func.coalesce(func.sum(Sale.total_cents), 0)).where(Sale.shift_id == shift.id, Sale.status == "recorded")).scalar_one()
        if prorated > 0 and sales < prorated * pct / 100:
            ctx.case(
                point_id=shift.point_id, shift_id=shift.id, title=f"Ventas bajo trayectoria: {point.display_name}",
                description=f"${sales / 100:,.0f} vs ${prorated / 100:,.0f} esperados a esta hora ({int(sales * 100 / prorated)}%)",
                impact=min((prorated - sales) / 1000, 30), payload={"sales_cents": int(sales), "prorated_target_cents": int(prorated)},
            )


def rule_high_waste(ctx: Ctx) -> None:
    pct = float(ctx.params.get("pct", 4))
    waste_rows = ctx.db.execute(
        select(Waste.point_id, func.sum(Waste.qty)).where(Waste.occurred_at >= ctx.day_start, Waste.occurred_at < ctx.day_end).group_by(Waste.point_id)
    ).all()
    for point_id, waste_units in waste_rows:
        sold = ctx.db.execute(
            select(func.coalesce(func.sum(SaleLine.qty), 0)).join(Sale, Sale.id == SaleLine.sale_id).where(
                Sale.point_id == point_id, Sale.status == "recorded", Sale.occurred_at >= ctx.day_start, Sale.occurred_at < ctx.day_end
            )
        ).scalar_one()
        total = int(sold) + int(waste_units)
        if total == 0:
            continue
        ratio = int(waste_units) * 100 / total
        if ratio > pct:
            point = ctx.db.get(Point, point_id)
            ctx.case(
                point_id=point_id, title=f"Merma alta: {point.display_name if point else ''}",
                description=f"Merma {ratio:.1f}% del día ({waste_units} unidades sobre {total})", impact=min(ratio, 30),
                payload={"waste_units": int(waste_units), "sold_units": int(sold), "pct": round(ratio, 1)},
            )


def rule_cash_difference(ctx: Ctx) -> None:
    # Precedencia: rules.params (si está definido explícitamente) > settings > default
    threshold, severe = cash_thresholds(ctx.db)
    shifts = ctx.db.query(Shift).filter(
        Shift.status.in_(("closed", "transferred")), Shift.closed_at >= ctx.day_start, Shift.closed_at < ctx.day_end,
        Shift.difference_cents.isnot(None),
    ).all()
    for shift in shifts:
        diff = shift.difference_cents or 0
        if abs(diff) > threshold:
            ctx.case(
                point_id=shift.point_id, shift_id=shift.id, severity="urgent" if abs(diff) > severe else "review",
                title=f"Diferencia de caja de ${abs(diff) / 100:,.2f}",
                description=f"Esperado ${(shift.cash_expected_cents or 0) / 100:,.2f}, contado ${(shift.cash_counted_cents or 0) / 100:,.2f}",
                impact=min(abs(diff) / 100, 50), payload={"difference_cents": diff},
            )


def rule_inventory_inconsistent(ctx: Ctx) -> None:
    units = inventory_tolerance(ctx.db)  # rules.params.units > settings > default
    counts = ctx.db.query(InventoryCount).filter(InventoryCount.occurred_at >= ctx.day_start, InventoryCount.occurred_at < ctx.day_end).all()
    for ic in counts:
        worst = max((abs(int(v)) for v in (ic.differences or {}).values()), default=0)
        if worst > units:
            ctx.case(
                point_id=ic.point_id, shift_id=ic.shift_id, title="Inventario inconsistente",
                description=f"Diferencia máxima de {worst} unidades entre conteo y teórico", impact=min(worst * 2, 40),
                payload={"count_id": str(ic.id), "differences": ic.differences},
            )


def rule_low_battery(ctx: Ctx) -> None:
    warn = int(ctx.params.get("warn", 25))
    critical = int(ctx.params.get("critical", 10))
    for shift in _open_shifts(ctx.db):
        ping = ctx.db.query(GpsPing).filter(GpsPing.shift_id == shift.id, GpsPing.battery_pct.isnot(None)).order_by(GpsPing.at.desc()).first()
        if ping is None or ping.battery_pct >= warn:
            continue
        point = ctx.db.get(Point, shift.point_id)
        ctx.case(
            point_id=shift.point_id, shift_id=shift.id, severity="urgent" if ping.battery_pct < critical else ctx.rule.severity,
            title=f"Batería baja ({ping.battery_pct}%): {point.display_name if point else ''}",
            description=f"Último reporte {ping.battery_pct}% de batería", impact=max(0, warn - ping.battery_pct),
            payload={"battery_pct": ping.battery_pct, "at": ping.at.isoformat()},
        )


def rule_anomalous_cancellations(ctx: Ctx) -> None:
    max_count = int(ctx.params.get("count", 3))
    max_pct = float(ctx.params.get("pct", 10))
    shifts = ctx.db.query(Shift).filter(Shift.opened_at >= ctx.day_start, Shift.opened_at < ctx.day_end).all()
    for shift in shifts:
        cancels = ctx.db.execute(select(func.count(SaleCancellation.id)).where(SaleCancellation.shift_id == shift.id)).scalar_one()
        if cancels == 0:
            continue
        total_sales = ctx.db.execute(select(func.count(Sale.id)).where(Sale.shift_id == shift.id)).scalar_one()
        pct = cancels * 100 / total_sales if total_sales else 100
        if cancels > max_count or pct > max_pct:
            point = ctx.db.get(Point, shift.point_id)
            ctx.case(
                point_id=shift.point_id, shift_id=shift.id, title=f"Cancelaciones anómalas: {point.display_name if point else ''}",
                description=f"{cancels} cancelaciones sobre {total_sales} ventas ({pct:.0f}%)", impact=min(cancels * 5, 30),
                payload={"cancellations": int(cancels), "sales": int(total_sales), "pct": round(pct, 1)},
            )


# Sólo eventos originados por el dispositivo del operador cuentan como "actividad" para sync_stale.
ACTIVITY_EVENTS = (
    "ShiftOpened", "ShiftTransferred", "SaleRecorded", "SaleCancelled", "PaymentRecorded", "WasteRecorded",
    "InventoryMoved", "HelpRequested",
)


def rule_sync_stale(ctx: Ctx) -> None:
    minutes = int(ctx.params.get("minutes", 30))
    limit = ctx.now - timedelta(minutes=minutes)
    for shift in _open_shifts(ctx.db):
        last_event = ctx.db.execute(
            select(func.max(Event.occurred_at)).where(Event.shift_id == shift.id, Event.type.in_(ACTIVITY_EVENTS))
        ).scalar_one()
        last_ping = ctx.db.execute(select(func.max(GpsPing.at)).where(GpsPing.shift_id == shift.id)).scalar_one()
        candidates = [x for x in (last_event, last_ping, shift.last_seen_at, shift.opened_at) if x is not None]
        last_seen = max(candidates)
        if last_seen < limit:
            point = ctx.db.get(Point, shift.point_id)
            stale_min = int((ctx.now - last_seen).total_seconds() // 60)
            ctx.case(
                point_id=shift.point_id, shift_id=shift.id, title=f"Sin sincronizar: {point.display_name if point else ''}",
                description=f"Turno abierto sin eventos ni GPS desde hace {stale_min} min", impact=min(stale_min / 10, 20),
                payload={"last_seen_at": last_seen.isoformat(), "stale_minutes": stale_min}, event="PointOffline",
            )


def rule_maintenance_overdue(ctx: Ctx) -> None:
    assets = ctx.db.query(Asset).filter(Asset.next_maintenance_at.isnot(None), Asset.next_maintenance_at < ctx.now, Asset.status == "active").all()
    for asset in assets:
        point_id = None
        if asset.cart_id:
            a = ctx.db.query(Assignment).filter(Assignment.cart_id == asset.cart_id, Assignment.shift_date == ctx.today).first()
            point_id = a.point_id if a else None
        days = int((ctx.now - asset.next_maintenance_at).total_seconds() // 86400)
        # dedupe por activo (no por punto): usamos el id del activo dentro del punto ficticio
        c = open_case_if_new(
            ctx.db, rule_key=ctx.rule.key, point_id=point_id, shift_id=None, severity=ctx.rule.severity,
            title=f"Mantenimiento vencido: {asset.code}", description=f"Preventivo vencido hace {days} días ({asset.asset_type})",
            impact_score=min(days, 20), source="rule", payload={"asset_id": str(asset.id), "asset_code": asset.code},
            dedupe_date=ctx.now, category="maintenance",
        )
        if c is not None:
            c.dedupe_key = f"{ctx.rule.key}:{asset.id}:{ctx.today.isoformat()}"
            ctx.created += 1


def rule_stock_critical(ctx: Ctx) -> None:
    min_units = int(ctx.params.get("min_units", 10))
    shifts = _open_shifts(ctx.db)
    balances = balances_all(ctx.db, [s.point_id for s in shifts])
    for shift in shifts:
        point_balances = balances.get(shift.point_id, {})
        low = {str(pid): q for pid, q in point_balances.items() if q < min_units}
        if not low:
            continue
        point = ctx.db.get(Point, shift.point_id)
        ctx.case(
            point_id=shift.point_id, shift_id=shift.id, title=f"Stock crítico: {point.display_name if point else ''}",
            description=f"{len(low)} presentación(es) por debajo de {min_units} unidades", impact=10 * len(low),
            payload={"low": low, "min_units": min_units},
        )


RULES = {
    "no_open": rule_no_open,
    "out_of_geofence": rule_out_of_geofence,
    "low_sales_trajectory": rule_low_sales_trajectory,
    "high_waste": rule_high_waste,
    "cash_difference": rule_cash_difference,
    "inventory_inconsistent": rule_inventory_inconsistent,
    "low_battery": rule_low_battery,
    "anomalous_cancellations": rule_anomalous_cancellations,
    "sync_stale": rule_sync_stale,
    "maintenance_overdue": rule_maintenance_overdue,
    "stock_critical": rule_stock_critical,
}


# Reglas cuya condición es transitoria: si deja de cumplirse, el caso creado por la regla se resuelve solo
# (p. ej. el punto ya abrió, volvió a sincronizar, regresó a la geocerca, cargó batería).
TRANSIENT_RULES = {"no_open", "sync_stale", "out_of_geofence", "low_battery"}


def _auto_resolve(ctx: "Ctx") -> int:
    if ctx.rule.key not in TRANSIENT_RULES:
        return 0
    q = ctx.db.query(Case).filter(
        Case.rule_key == ctx.rule.key, Case.status.in_(("open", "in_progress")), Case.assignee_id.is_(None),
        Case.opened_at >= ctx.day_start,
    )
    n = 0
    for c in q.all():
        if c.point_id in ctx.firing:
            continue
        c.status = "resolved"
        c.resolved_at = ctx.now
        c.resolution = "Resuelto automáticamente: la condición dejó de cumplirse"
        for alert in ctx.db.query(Alert).filter(Alert.case_id == c.id, Alert.status == "open").all():
            alert.status = "resolved"
            alert.resolved_at = ctx.now
            events.emit(ctx.db, "AlertResolved", point_id=c.point_id, shift_id=c.shift_id, entity="alert", entity_id=alert.id, payload={"case_id": c.id, "auto": True}, occurred_at=ctx.now)
        n += 1
    return n


def run_rules(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    alerts_created = 0
    cases_created = 0
    cases_resolved = 0
    rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()
    for rule in rules:
        fn = RULES.get(rule.key)
        if fn is None:
            continue
        ctx = Ctx(db, now, rule)
        try:
            fn(ctx)
            cases_resolved += _auto_resolve(ctx)
            db.commit()
        except Exception:  # una regla que falla no detiene las demás
            log.exception("Fallo evaluando regla %s", rule.key)
            db.rollback()
            continue
        cases_created += ctx.created
        alerts_created += ctx.created
    # Ranking de vendedores (día/mes/año) guardado en users.
    from app.services.ranking import recompute_rankings

    try:
        ranking = recompute_rankings(db, now)
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("Fallo recalculando ranking de vendedores")
        db.rollback()
        ranking = {}
    return {"alerts_created": alerts_created, "cases_created": cases_created, "cases_resolved": cases_resolved, "ranking": ranking}


def purge_old_gps(db: Session, now: datetime | None = None) -> int:
    """Borra `gps_pings` más antiguos que `settings.gps_retention_days`."""
    now = now or utcnow()
    days = get_int(db, "gps_retention_days")
    limit = now - timedelta(days=days)
    n = db.query(GpsPing).filter(GpsPing.at < limit).delete(synchronize_session=False)
    db.flush()
    return int(n or 0)


def run_maintenance(db: Session, now: datetime | None = None) -> dict:
    """Purgas periódicas (evidencias vencidas y GPS antiguo). Cada una en su propia transacción."""
    from app.services.evidence import purge_expired_evidence

    now = now or utcnow()
    out = {"evidence_purged": 0, "gps_purged": 0}
    for name, fn in (("evidence_purged", purge_expired_evidence), ("gps_purged", purge_old_gps)):
        try:
            out[name] = fn(db, now)
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("Fallo en purga %s", name)
            db.rollback()
    return out


def run_rules_job() -> None:
    """Job de APScheduler: sesión propia. Corre las reglas y las purgas de retención."""
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        result = run_rules(db)
        result.update(run_maintenance(db))
        log.info("rules run: %s", result)
    finally:
        db.close()
