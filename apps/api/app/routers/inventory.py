"""Inventario: recepciones, conteos y estado por punto (unidades y kilogramos teóricos)."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.timeutil import iso, utcnow
from app.models.catalog import Presentation
from app.models.inventory import InventoryCount, Receipt
from app.models.org import Point, User
from app.schemas.operator import CountIn, ReceiptIn
from app.services import evidence as evidence_svc
from app.services import sync as cmd
from app.services.cases import get_rule_params
from app.services.inventory import balances_all, grams_of

router = APIRouter(prefix="/v1/inventory", tags=["inventario"])


@router.post("/receipts", status_code=201)
def create_receipt(data: ReceiptIn, current: CurrentUser = Depends(require("inventory.receipt")), db: Session = Depends(get_db)):
    res = cmd.cmd_receipt(db, current, data)
    return JSONResponse(status_code=res.status_code, content=res.body)


@router.post("/counts")
def create_count(data: CountIn, current: CurrentUser = Depends(require("inventory.count")), db: Session = Depends(get_db)):
    res = cmd.cmd_count(db, current, data)
    return JSONResponse(status_code=res.status_code, content=res.body)


@router.get("/status")
def status(current: CurrentUser = Depends(require("inventory.read", "supervisor.read")), db: Session = Depends(get_db)):
    """Por punto: balance por presentación (reconstruido desde movimientos), teórico y riesgo de quiebre."""
    min_units = int(get_rule_params(db, "stock_critical").get("min_units", 10))
    balances = balances_all(db)
    presentations = db.query(Presentation).filter(Presentation.is_active.is_(True)).order_by(Presentation.sort).all()
    q = db.query(Point).filter(Point.is_active.is_(True))
    if current.role == "supervisor":
        q = q.filter(Point.zone_id == current.zone_id)
    rows = []
    for p in q.order_by(Point.name).all():
        pb = balances.get(p.id, {})
        items = [{"presentation_id": str(pr.id), "name": pr.name, "grams": pr.grams, "balance": pb.get(pr.id, 0), "theoretical": pb.get(pr.id, 0), "min_units": min_units,
                  "kg": round(pb.get(pr.id, 0) * pr.grams / 1000, 3)} for pr in presentations]
        lowest = min((i["balance"] for i in items), default=0)
        risk = "critical" if lowest < min_units else ("low" if lowest < min_units * 2 else "ok")
        rows.append({"point": {"id": str(p.id), "name": p.display_name}, "stock_risk": risk, "items": items, "total_units": sum(i["balance"] for i in items),
                     "total_kg": round(sum(i["balance"] * i["grams"] for i in items) / 1000, 3)})
    return {"points": rows, "min_units": min_units, "total_units": sum(r["total_units"] for r in rows), "total_kg": round(sum(r["total_kg"] for r in rows), 3)}


def _points_query(db: Session, current: CurrentUser, point_id: uuid.UUID | None):
    q = db.query(Point.id)
    if current.role == "supervisor":
        q = q.filter(Point.zone_id == current.zone_id)
    if point_id is not None:
        q = q.filter(Point.id == point_id)
    return [r[0] for r in q.all()]


@router.get("/counts")
def list_counts(days: int = Query(7, ge=1, le=90), point_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500),
                current: CurrentUser = Depends(require("inventory.read", "supervisor.read")), db: Session = Depends(get_db)):
    """Conteos físicos recientes: piezas y kilogramos teóricos contados/esperados, diferencia y fotos (evidencias)."""
    since = utcnow() - timedelta(days=days)
    pids = _points_query(db, current, point_id)
    grams = grams_of(db)
    rows = db.query(InventoryCount).filter(InventoryCount.occurred_at >= since, InventoryCount.point_id.in_(pids)).order_by(InventoryCount.occurred_at.desc()).limit(limit).all()
    names = {p.id: p.display_name for p in db.query(Point).filter(Point.id.in_({r.point_id for r in rows})).all()} if rows else {}
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_({r.actor_id for r in rows})).all()} if rows else {}
    out = []
    for c in rows:
        counted_units = sum(int(v) for v in (c.counts or {}).values())
        counted_g = sum(int(v) * grams.get(k, 0) for k, v in (c.counts or {}).items())
        expected_g = sum(int(v) * grams.get(k, 0) for k, v in (c.theoretical or {}).items())
        diff_units = sum(abs(int(v)) for v in (c.differences or {}).values())
        out.append({
            "id": str(c.id), "occurred_at": iso(c.occurred_at), "kind": c.kind, "shift_id": str(c.shift_id),
            "point": {"id": str(c.point_id), "name": names.get(c.point_id, "—")}, "actor": {"id": str(c.actor_id), "name": users.get(c.actor_id, "—")},
            "counts": c.counts, "theoretical": c.theoretical, "differences": c.differences,
            "counted_units": counted_units, "counted_kg": round(counted_g / 1000, 3), "expected_kg": round(expected_g / 1000, 3),
            "diff_units": diff_units, "diff_kg": round((counted_g - expected_g) / 1000, 3),
            "evidence": evidence_svc.serialize_for(db, "inventory_count", c.id),
        })
    return {"counts": out, "days": days}


@router.get("/receipts")
def list_receipts(days: int = Query(7, ge=1, le=90), point_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500),
                  current: CurrentUser = Depends(require("inventory.read", "supervisor.read")), db: Session = Depends(get_db)):
    """Recepciones recientes con piezas, kilogramos teóricos y fotos."""
    since = utcnow() - timedelta(days=days)
    pids = _points_query(db, current, point_id)
    grams = grams_of(db)
    rows = db.query(Receipt).filter(Receipt.occurred_at >= since, Receipt.point_id.in_(pids)).order_by(Receipt.occurred_at.desc()).limit(limit).all()
    names = {p.id: p.display_name for p in db.query(Point).filter(Point.id.in_({r.point_id for r in rows})).all()} if rows else {}
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_({r.actor_id for r in rows})).all()} if rows else {}
    out = []
    for r in rows:
        units = sum(int(line.get("qty", 0)) for line in (r.lines or []))
        g = sum(int(line.get("qty", 0)) * grams.get(str(line.get("presentation_id")), 0) for line in (r.lines or []))
        out.append({
            "id": str(r.id), "occurred_at": iso(r.occurred_at), "shift_id": str(r.shift_id), "qr_code": r.qr_code,
            "point": {"id": str(r.point_id), "name": names.get(r.point_id, "—")}, "actor": {"id": str(r.actor_id), "name": users.get(r.actor_id, "—")},
            "lines": r.lines, "units": units, "kg": round(g / 1000, 3),
            "evidence": evidence_svc.serialize_for(db, "receipt", r.id),
        })
    return {"receipts": out, "days": days}
