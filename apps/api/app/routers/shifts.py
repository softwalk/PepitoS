"""Turnos: abrir, esperado, cerrar, transferir."""
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.schemas.operator import CashMovementIn, ShiftCloseIn, ShiftOpenIn, ShiftReopenIn, ShiftTransferIn
from app.services import shifts as shifts_svc
from app.services import sync as cmd

router = APIRouter(prefix="/v1/shifts", tags=["turnos"])


def _resp(res):
    return JSONResponse(status_code=res.status_code, content=res.body)


@router.post("/open", status_code=201)
def open_shift(data: ShiftOpenIn, current: CurrentUser = Depends(require("shift.open")), db: Session = Depends(get_db)):
    return _resp(cmd.cmd_shift_open(db, current, data))


@router.get("/{shift_id}")
def get_shift(shift_id: uuid.UUID, current: CurrentUser = Depends(require("shift.open", "cases.read")), db: Session = Depends(get_db)):
    shift = shifts_svc.get_shift_or_404(db, shift_id)
    shifts_svc.check_shift_access(shift, current, db)
    return shifts_svc.serialize_shift(shift)


@router.get("/{shift_id}/expected")
def expected(shift_id: uuid.UUID, current: CurrentUser = Depends(require("shift.close", "cases.read")), db: Session = Depends(get_db)):
    shift = shifts_svc.get_shift_or_404(db, shift_id)
    shifts_svc.check_shift_access(shift, current, db)
    return shifts_svc.expected(db, shift)


@router.post("/{shift_id}/close")
def close_shift(shift_id: uuid.UUID, data: ShiftCloseIn, current: CurrentUser = Depends(require("shift.close")), db: Session = Depends(get_db)):
    return _resp(cmd.cmd_shift_close(db, current, shift_id, data))


@router.post("/{shift_id}/transfer")
def transfer_shift(shift_id: uuid.UUID, data: ShiftTransferIn, current: CurrentUser = Depends(require("shift.transfer")), db: Session = Depends(get_db)):
    return _resp(cmd.cmd_shift_transfer(db, current, shift_id, data))


@router.post("/{shift_id}/reopen")
def reopen_shift(shift_id: uuid.UUID, data: ShiftReopenIn, request: Request, current: CurrentUser = Depends(require("shift.reopen")), db: Session = Depends(get_db)):
    """Continuar un turno terminado (sólo administrador). Devuelve el turno ya abierto."""
    shift = shifts_svc.get_shift_or_404(db, shift_id)
    out = shifts_svc.reopen_shift(db, current, shift, data.reason, ip=client_ip(request))
    db.commit()
    return out


@router.post("/{shift_id}/cash-movements", status_code=201)
def create_cash_movement(shift_id: uuid.UUID, data: CashMovementIn, request: Request, current: CurrentUser = Depends(require("shift.close", "cash_count.surprise")), db: Session = Depends(get_db)):
    """Fondo inicial, retiro, gasto o devolución en efectivo del turno (operador en su turno; supervisor en su zona)."""
    from app.core.deps import client_ip
    from app.services import cash_movements as cm

    shift = shifts_svc.get_shift_or_404(db, shift_id)
    shifts_svc.check_shift_access(shift, current, db)
    m = cm.create_movement(db, shift, current, data, ip=client_ip(request))
    db.commit()
    return {**cm.serialize(m), "expected": shifts_svc.expected(db, shift)}


@router.get("/{shift_id}/cash-movements")
def list_cash_movements(shift_id: uuid.UUID, current: CurrentUser = Depends(require("shift.close", "cases.read")), db: Session = Depends(get_db)):
    from app.services import cash_movements as cm

    shift = shifts_svc.get_shift_or_404(db, shift_id)
    shifts_svc.check_shift_access(shift, current, db)
    return {"shift_id": str(shift.id), "rows": cm.list_for_shift(db, shift.id)}
