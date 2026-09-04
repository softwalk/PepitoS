"""Ventas y cancelaciones."""
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.core.errors import ApiError
from app.core.timeutil import iso
from app.models.sales import Sale
from app.schemas.operator import SaleCancelIn, SaleIn
from app.services import shifts as shifts_svc
from app.services import sync as cmd

router = APIRouter(prefix="/v1/sales", tags=["ventas"])


@router.post("", status_code=201)
def create_sale(data: SaleIn, current: CurrentUser = Depends(require("sale.create")), db: Session = Depends(get_db)):
    res = cmd.cmd_sale(db, current, data)
    return JSONResponse(status_code=res.status_code, content=res.body)


@router.get("/{sale_id}")
def get_sale(sale_id: uuid.UUID, current: CurrentUser = Depends(require("sale.create", "cases.read", "reports.read")), db: Session = Depends(get_db)):
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise ApiError("NOT_FOUND", "Venta no encontrada")
    shift = shifts_svc.get_shift_or_404(db, sale.shift_id)
    shifts_svc.check_shift_access(shift, current, db)
    return {
        "id": str(sale.id), "folio": sale.folio, "shift_id": str(sale.shift_id), "status": sale.status, "total_cents": sale.total_cents,
        "occurred_at": iso(sale.occurred_at), "price_version_id": str(sale.price_version_id), "offline_created": sale.offline_created,
        "lines": [{"presentation_id": str(l.presentation_id), "flavor_id": str(l.flavor_id) if l.flavor_id else None, "qty": l.qty, "unit_price_cents": l.unit_price_cents, "line_total_cents": l.line_total_cents} for l in sale.lines],
        "payments": [{"method": p.method, "amount_cents": p.amount_cents} for p in sale.payments],
        "cancellation": {"reason_code": sale.cancellation.reason_code, "note": sale.cancellation.note, "cancelled_at": iso(sale.cancellation.cancelled_at), "actor_id": str(sale.cancellation.actor_id)} if sale.cancellation else None,
    }


@router.post("/{sale_id}/cancel")
def cancel_sale(sale_id: uuid.UUID, data: SaleCancelIn, request: Request, current: CurrentUser = Depends(require("sale.cancel_own", "sale.cancel")), db: Session = Depends(get_db)):
    res = cmd.cmd_sale_cancel(db, current, sale_id, data, ip=client_ip(request))
    return JSONResponse(status_code=res.status_code, content=res.body)
