"""Reportes: diario, asistencia y audit log."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.timeutil import iso, local_day_bounds, parse_date
from sqlalchemy import func, select

from app.models.ops import Shift
from app.models.sales import Sale
from app.models.org import Assignment, Attendance, Point, User
from app.models.system import AuditLog
from app.services.cash import sales_summary
from app.services.inventory import shift_units

router = APIRouter(prefix="/v1", tags=["reportes"])


@router.get("/reports/daily")
def daily(date: str | None = None, current: CurrentUser = Depends(require("reports.read")), db: Session = Depends(get_db)):
    day = parse_date(date)
    start, end = local_day_bounds(day)
    q = db.query(Shift).filter(Shift.opened_at >= start, Shift.opened_at < end)
    if current.role == "supervisor":
        q = q.join(Point, Point.id == Shift.point_id).filter(Point.zone_id == current.zone_id)
    rows = []
    for s in q.order_by(Shift.opened_at).all():
        summ = sales_summary(db, s.id)
        waste = shift_units(db, s.id, "waste")
        units = summ["units_sold"]
        stale = int(db.execute(select(func.count(Sale.id)).where(Sale.shift_id == s.id, Sale.price_version_stale.is_(True))).scalar_one())
        rows.append({
            "point": {"id": str(s.point.id), "name": s.point.name},
            "shift_id": str(s.id),
            "operator": {"id": str(s.operator.id), "name": s.operator.name},
            "opened_at": iso(s.opened_at), "closed_at": iso(s.closed_at),
            "sales_cents": summ["sales_total_cents"], "tx": summ["sales_count"],
            "cash_expected_cents": s.cash_expected_cents if s.cash_expected_cents is not None else summ["cash_expected_cents"],
            "cash_counted_cents": s.cash_counted_cents, "difference_cents": s.difference_cents,
            "digital_cents": summ["digital_total_cents"], "cancelled_count": summ["cancelled_count"],
            "stale_price_sales": stale,
            "waste_units": waste, "waste_pct": round(waste * 100 / (units + waste), 1) if (units + waste) else 0.0,
            "status": s.close_status or s.status,
        })
    totals = {"sales_cents": sum(r["sales_cents"] for r in rows), "tx": sum(r["tx"] for r in rows), "difference_cents": sum(r["difference_cents"] or 0 for r in rows), "waste_units": sum(r["waste_units"] for r in rows), "stale_price_sales": sum(r["stale_price_sales"] for r in rows)}
    return {"date": day.isoformat(), "rows": rows, "totals": totals}


@router.get("/people/attendance")
def attendance(date: str | None = None, current: CurrentUser = Depends(require("people.read", "supervisor.read")), db: Session = Depends(get_db)):
    day = parse_date(date)
    assignments = db.query(Assignment).filter(Assignment.shift_date == day).all()
    att = {a.assignment_id: a for a in db.query(Attendance).filter(Attendance.work_date == day).all() if a.assignment_id}
    rows = []
    for a in assignments:
        if current.role == "supervisor" and a.point.zone_id != current.zone_id:
            continue
        r = att.get(a.id)
        rows.append({
            "assignment_id": str(a.id), "operator": {"id": str(a.operator.id), "name": a.operator.name},
            "point": {"id": str(a.point.id), "name": a.point.name}, "planned_start": iso(a.planned_start), "planned_end": iso(a.planned_end),
            "check_in_at": iso(r.check_in_at) if r else None, "check_out_at": iso(r.check_out_at) if r else None,
            "late_minutes": r.late_minutes if r else None, "status": r.status if r else ("absent" if a.status == "absent" else "pending"),
        })
    return {"date": day.isoformat(), "rows": rows}


@router.get("/audit-log")
def audit_log(entity: str | None = None, entity_id: uuid.UUID | None = None, limit: int = 100, _: CurrentUser = Depends(require("audit_log.read")), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    users = {u.id: u.name for u in db.query(User).all()}
    return [
        {"id": str(r.id), "at": iso(r.at), "actor_id": str(r.actor_id) if r.actor_id else None, "actor_name": users.get(r.actor_id), "action": r.action,
         "entity": r.entity, "entity_id": str(r.entity_id) if r.entity_id else None, "before": r.before, "after": r.after, "reason": r.reason, "ip": r.ip, "device_id": r.device_id}
        for r in q.order_by(AuditLog.at.desc()).limit(min(limit, 1000)).all()
    ]
