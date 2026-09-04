"""Inventario: recepciones, conteos y estado por punto."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.models.catalog import Presentation
from app.models.org import Point
from app.schemas.operator import CountIn, ReceiptIn
from app.services import sync as cmd
from app.services.cases import get_rule_params
from app.services.inventory import balances_all

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
        items = [{"presentation_id": str(pr.id), "name": pr.name, "balance": pb.get(pr.id, 0), "theoretical": pb.get(pr.id, 0), "min_units": min_units} for pr in presentations]
        lowest = min((i["balance"] for i in items), default=0)
        risk = "critical" if lowest < min_units else ("low" if lowest < min_units * 2 else "ok")
        rows.append({"point": {"id": str(p.id), "name": p.name}, "stock_risk": risk, "items": items, "total_units": sum(i["balance"] for i in items)})
    return {"points": rows, "min_units": min_units}
