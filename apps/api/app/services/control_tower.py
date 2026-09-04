"""Estado de red (PointStatus), resumen y briefing del Control Tower."""
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import iso, local_day_bounds, utcnow
from app.models.cases import Alert, Case
from app.models.catalog import DailyTarget
from app.models.ops import GpsPing, Shift
from app.models.org import Assignment, Point, User
from app.models.sales import Sale
from app.services.cases import get_rule_params, serialize_case
from app.services.settings import get_int
from app.services.inventory import balances_all
from app.services.priority import priority_score


def _sales_by_shift(db: Session, shift_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not shift_ids:
        return {}
    rows = db.execute(
        select(Sale.shift_id, func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0))
        .where(Sale.shift_id.in_(shift_ids), Sale.status == "recorded")
        .group_by(Sale.shift_id)
    ).all()
    return {sid: (int(c), int(t)) for sid, c, t in rows}


def _open_cases_by_point(db: Session) -> dict[uuid.UUID, dict[str, int]]:
    rows = db.execute(
        select(Case.point_id, Case.severity, func.count(Case.id))
        .where(Case.status.in_(("open", "in_progress")))
        .group_by(Case.point_id, Case.severity)
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {}
    for pid, sev, n in rows:
        out.setdefault(pid, {"urgent": 0, "review": 0, "normal": 0})[sev] = int(n)
    return out


def point_statuses(db: Session, day: date, zone_id: uuid.UUID | None = None, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    day_start, day_end = local_day_bounds(day)
    grace = int(get_rule_params(db, "no_open").get("grace_minutes", 20))
    stale_min = int(get_rule_params(db, "sync_stale").get("minutes", 30))
    min_units = int(get_rule_params(db, "stock_critical").get("min_units", 10))

    q = db.query(Point).filter(Point.is_active.is_(True))
    if zone_id is not None:
        q = q.filter(Point.zone_id == zone_id)
    points = q.order_by(Point.name).all()
    assignments = {a.point_id: a for a in db.query(Assignment).filter(Assignment.shift_date == day).all()}
    shifts = (
        db.query(Shift)
        .filter(Shift.opened_at >= day_start, Shift.opened_at < day_end)
        .order_by(Shift.opened_at.desc())
        .all()
    )
    shift_by_point: dict[uuid.UUID, Shift] = {}
    for s in shifts:  # prioriza turno abierto; si no, el más reciente
        cur = shift_by_point.get(s.point_id)
        if cur is None or (s.status == "open" and cur.status != "open"):
            shift_by_point[s.point_id] = s
    sales = _sales_by_shift(db, [s.id for s in shift_by_point.values()])
    targets = {t.point_id: t for t in db.query(DailyTarget).filter(DailyTarget.target_date == day).all()}
    cases = _open_cases_by_point(db)
    balances = balances_all(db, [p.id for p in points])
    users = {u.id: u for u in db.query(User).all()}

    out = []
    for p in points:
        a = assignments.get(p.id)
        s = shift_by_point.get(p.id)
        status = "not_scheduled"
        if s is not None:
            if s.status == "open":
                status = "open"
                last_seen = s.last_seen_at or s.opened_at
                if now - last_seen > timedelta(minutes=stale_min):
                    status = "offline"
            else:
                status = "closed"
        elif a is not None:
            status = "late" if now > a.planned_start + timedelta(minutes=grace) else "closed"
        last_gps = None
        battery = None
        if s is not None:
            ping = db.query(GpsPing).filter(GpsPing.shift_id == s.id).order_by(GpsPing.at.desc()).first()
            if ping is not None:
                last_gps = {"lat": ping.lat, "lng": ping.lng, "at": iso(ping.at), "in_geofence": ping.in_geofence}
                battery = ping.battery_pct
        tx, cents = sales.get(s.id, (0, 0)) if s else (0, 0)
        t = targets.get(p.id)
        target_cents = t.target_cents if t else (p.daily_target_cents or get_int(db, "daily_sales_target_default_cents"))
        cash_status = "pending"
        if s is not None and s.status in ("closed", "transferred"):
            cash_status = "ok" if s.close_status == "reconciled" else "difference"
        pb = balances.get(p.id, {})
        stock_risk = "ok"
        if pb:
            lowest = min(pb.values())
            if lowest < min_units:
                stock_risk = "critical"
            elif lowest < min_units * 2:
                stock_risk = "low"
        operator = None
        if s is not None:
            u = users.get(s.operator_id)
            operator = {"id": str(u.id), "name": u.name} if u else None
        elif a is not None:
            u = users.get(a.operator_id)
            operator = {"id": str(u.id), "name": u.name} if u else None
        pc = cases.get(p.id, {})
        out.append(
            {
                "point": {"id": str(p.id), "name": p.name, "lat": p.lat, "lng": p.lng, "zone_id": str(p.zone_id) if p.zone_id else None},
                "status": status,
                "shift_id": str(s.id) if s else None,
                "operator": operator,
                "opened_at": iso(s.opened_at) if s else None,
                "last_seen_at": iso(s.last_seen_at) if s else None,
                "last_gps": last_gps,
                "battery_pct": battery,
                "sales_cents": cents,
                "target_cents": target_cents,
                "tx": tx,
                "ticket_cents": int(cents / tx) if tx else 0,
                "cash_status": cash_status,
                "stock_risk": stock_risk,
                "open_cases": {"urgent": pc.get("urgent", 0), "review": pc.get("review", 0)},
                "planned_start": iso(a.planned_start) if a else None,
            }
        )
    return out


def serialize_alert(a: Alert) -> dict:
    return {
        "id": str(a.id), "rule_key": a.rule_key, "severity": a.severity, "status": a.status, "message": a.message,
        "point_id": str(a.point_id) if a.point_id else None, "shift_id": str(a.shift_id) if a.shift_id else None,
        "case_id": str(a.case_id) if a.case_id else None, "raised_at": iso(a.raised_at), "resolved_at": iso(a.resolved_at),
    }


def summary(db: Session, day: date, now: datetime | None = None) -> dict:
    now = now or utcnow()
    points = point_statuses(db, day, now=now)
    scheduled = [p for p in points if p["status"] != "not_scheduled"]
    sales_cents = sum(p["sales_cents"] for p in points)
    tx = sum(p["tx"] for p in points)
    target = sum(p["target_cents"] for p in scheduled)
    # Proyección de cierre: ritmo actual de puntos abiertos extrapolado a su jornada planeada.
    forecast = sales_cents
    for p in points:
        if p["status"] in ("open", "offline") and p["opened_at"]:
            opened = datetime.fromisoformat(p["opened_at"].replace("Z", "+00:00"))
            hours = (now - opened).total_seconds() / 3600
            remaining = max(0.0, 10 - hours)
            # Ritmo amortiguado: con menos de 1 h abierta el ritmo se calcula sobre 1 h para no extrapolar
            # unas pocas ventas a toda la jornada; además se acota a 1.5× la meta del punto.
            rate = p["sales_cents"] / max(1.0, hours)
            projected = p["sales_cents"] + int(rate * remaining)
            if p["target_cents"]:
                projected = min(projected, int(p["target_cents"] * 1.5))
            forecast += projected - p["sales_cents"]
    exc = db.execute(select(Case.severity, func.count(Case.id)).where(Case.status.in_(("open", "in_progress"))).group_by(Case.severity)).all()
    exc_map = {"urgent": 0, "review": 0, "normal": 0}
    for sev, n in exc:
        exc_map[sev] = int(n)
    alerts = db.query(Alert).order_by(Alert.raised_at.desc()).limit(20).all()
    return {
        "date": day.isoformat(),
        "totals": {
            "points": len(scheduled),
            "open": sum(1 for p in points if p["status"] == "open"),
            "late": sum(1 for p in points if p["status"] == "late"),
            "closed": sum(1 for p in points if p["status"] == "closed"),
            "offline": sum(1 for p in points if p["status"] == "offline"),
            "sales_cents": sales_cents,
            "target_cents": target,
            "tx": tx,
            "ticket_cents": int(sales_cents / tx) if tx else 0,
            "forecast_close_cents": forecast,
        },
        "exceptions": exc_map,
        "points": points,
        "alerts_recent": [serialize_alert(a) for a in alerts],
    }


def briefing(db: Session, day: date, now: datetime | None = None) -> dict:
    now = now or utcnow()
    s = summary(db, day, now)
    t = s["totals"]
    open_cases = db.query(Case).filter(Case.status.in_(("open", "in_progress"))).all()
    open_cases.sort(key=lambda c: priority_score(c.severity, c.impact_score, c.opened_at, now), reverse=True)
    decisions = []
    for c in open_cases[:8]:
        rec = RECOMMENDATIONS.get(c.rule_key or c.category, "Revisar con el supervisor de zona y registrar resolución")
        decisions.append({"title": c.title, "why": c.description or c.title, "recommendation": rec, "case_id": str(c.id), "severity": c.severity, "priority_score": priority_score(c.severity, c.impact_score, c.opened_at, now)})
    pct = int(t["sales_cents"] * 100 / t["target_cents"]) if t["target_cents"] else 0
    headline = (
        f"{t['open']} de {t['points']} puntos abiertos, ventas ${t['sales_cents'] / 100:,.0f} ({pct}% de la meta), "
        f"{s['exceptions']['urgent']} urgentes y {s['exceptions']['review']} por revisar."
    )
    return {
        "date": day.isoformat(),
        "headline": headline,
        "decisions": decisions,
        "numbers": {**t, "target_pct": pct, "exceptions": s["exceptions"], "cash_differences": sum(1 for p in s["points"] if p["cash_status"] == "difference")},
    }


RECOMMENDATIONS = {
    "no_open": "Llamar al operador; si no responde en 15 min, enviar flotante o supervisor",
    "out_of_geofence": "Contactar al operador y verificar ubicación; considerar visita",
    "low_sales_trajectory": "Revisar afluencia y producto; evaluar reubicación temporal",
    "high_waste": "Revisar manejo de producto y calidad del lote; auditar en la próxima visita",
    "cash_difference": "Conciliar con el operador; si es grave, escalar a Finanzas y bloquear pagos pendientes",
    "inventory_inconsistent": "Recontar en visita del supervisor y ajustar con evidencia",
    "low_battery": "Enviar batería de reemplazo o indicar carga inmediata",
    "anomalous_cancellations": "Revisar motivos de cancelación y autorización del supervisor",
    "sync_stale": "Verificar conectividad del dispositivo; llamar al operador",
    "maintenance_overdue": "Programar preventivo con mantenimiento esta semana",
    "stock_critical": "Programar reposición hoy desde almacén",
    "security": "Aplicar protocolo de seguridad; contactar al operador de inmediato",
    "battery": "Enviar batería de reemplazo",
    "cart": "Enviar mantenimiento o carrito de respaldo",
    "product": "Reponer o retirar producto según el reporte",
    "payment": "Revisar terminal; autorizar cobro sólo en efectivo mientras tanto",
    "other": "Revisar el reporte y clasificar",
    "opening": "Atender la excepción de apertura antes de vender",
}


def serialize_cases(cases: list[Case], now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    data = [serialize_case(c, now) for c in cases]
    data.sort(key=lambda c: c["priority_score"], reverse=True)
    return data
