"""Comandos idempotentes compartidos por los endpoints REST y por /v1/sync/batch."""
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.ops import Shift
from app.models.sales import Sale
from app.schemas.operator import (
    CountIn,
    GpsBatchIn,
    HelpCaseIn,
    ReceiptIn,
    SaleCancelIn,
    SaleIn,
    ShiftCloseIn,
    ShiftOpenIn,
    ShiftTransferIn,
    WasteIn,
)
from app.services import cases as cases_svc
from app.services import inventory as inv_svc
from app.services import sales as sales_svc
from app.services import shifts as shifts_svc
from app.services.idempotency import IdemResult, run_idempotent
from app.services.sales import OPERATOR_CONFIG_DEFAULTS


def _open_shift_checked(db: Session, current, shift_id: uuid.UUID):
    shift = shifts_svc.get_shift_or_404(db, shift_id)
    shifts_svc.check_shift_access(shift, current, db)
    return shift


# ---- comandos (cada uno devuelve IdemResult) ----
def cmd_shift_open(db: Session, current, data: ShiftOpenIn) -> IdemResult:
    def fn():
        return shifts_svc.open_shift(db, current, data), 201

    return run_idempotent(db, data.idempotency_key, current.id, data.model_dump(mode="json"), fn)


def cmd_shift_close(db: Session, current, shift_id: uuid.UUID, data: ShiftCloseIn) -> IdemResult:
    payload = {"shift_id": str(shift_id), **data.model_dump(mode="json")}

    def fn():
        shift = _open_shift_checked(db, current, shift_id)
        return shifts_svc.close_shift(db, current, shift, data), 200

    return run_idempotent(db, data.idempotency_key, current.id, payload, fn)


def cmd_shift_transfer(db: Session, current, shift_id: uuid.UUID, data: ShiftTransferIn) -> IdemResult:
    payload = {"shift_id": str(shift_id), **data.model_dump(mode="json")}

    def fn():
        shift = _open_shift_checked(db, current, shift_id)
        return shifts_svc.transfer_shift(db, current, shift, data), 200

    return run_idempotent(db, data.idempotency_key, current.id, payload, fn)


def cmd_sale(db: Session, current, data: SaleIn) -> IdemResult:
    def fn():
        shift = _open_shift_checked(db, current, data.shift_id)
        sale = sales_svc.create_sale(db, shift, current.id, current.device_id, data)
        return {"sale_id": str(sale.id), "folio": sale.folio, "total_cents": sale.total_cents, "status": "recorded", "duplicate": False}, 201

    return run_idempotent(db, data.idempotency_key, current.id, data.model_dump(mode="json"), fn)


def cmd_sale_cancel(db: Session, current, sale_id: uuid.UUID, data: SaleCancelIn, ip: str | None = None) -> IdemResult:
    payload = {"sale_id": str(sale_id), **data.model_dump(mode="json")}

    def fn():
        sale = db.get(Sale, sale_id)
        if sale is None:
            raise ApiError("NOT_FOUND", "Venta no encontrada")
        if current.role == "supervisor":
            _open_shift_checked(db, current, sale.shift_id)
        sales_svc.cancel_sale(db, sale, current, data, OPERATOR_CONFIG_DEFAULTS["cancel_window_minutes"], ip=ip)
        return {"sale_id": str(sale.id), "status": "cancelled"}, 200

    return run_idempotent(db, data.idempotency_key, current.id, payload, fn)


def cmd_waste(db: Session, current, data: WasteIn) -> IdemResult:
    def fn():
        shift = _open_shift_checked(db, current, data.shift_id)
        w = inv_svc.create_waste(db, shift, current.id, data)
        return {"waste_id": str(w.id)}, 201

    return run_idempotent(db, data.idempotency_key, current.id, data.model_dump(mode="json"), fn)


def cmd_help_case(db: Session, current, data: HelpCaseIn) -> IdemResult:
    def fn():
        shift = None
        if data.shift_id is not None:
            shift = _open_shift_checked(db, current, data.shift_id)
        else:
            shift = db.query(Shift).filter_by(operator_id=current.id, status="open").first()
        case = cases_svc.create_help_case(db, current.user, data, shift)
        return {"case_id": str(case.id), "severity": case.severity, "category": case.category, "status": "open"}, 201

    return run_idempotent(db, data.idempotency_key, current.id, data.model_dump(mode="json", exclude={"photo_base64"}), fn)


def cmd_receipt(db: Session, current, data: ReceiptIn) -> IdemResult:
    def fn():
        shift = _open_shift_checked(db, current, data.shift_id)
        r = inv_svc.create_receipt(db, shift, current.id, data)
        return {"receipt_id": str(r.id)}, 201

    return run_idempotent(db, data.idempotency_key, current.id, data.model_dump(mode="json"), fn)


def cmd_count(db: Session, current, data: CountIn) -> IdemResult:
    def fn():
        shift = _open_shift_checked(db, current, data.shift_id)
        if shift.status != "open":
            raise ApiError("SHIFT_NOT_OPEN")
        ic, diffs, _ = inv_svc.apply_count(db, shift, current.id, data.counts, kind="manual", idempotency_key=data.idempotency_key, occurred_at=data.occurred_at)
        return {"count_id": str(ic.id), "differences": {str(k): v for k, v in diffs.items()}}, 200

    return run_idempotent(db, data.idempotency_key, current.id, data.model_dump(mode="json"), fn)


def cmd_gps(db: Session, current, data: GpsBatchIn) -> dict:
    accepted = shifts_svc.record_pings(db, current, data.pings)
    db.commit()
    return {"accepted": accepted}


# ---- despacho de /v1/sync/batch ----
def _parse(model, payload: dict, key: str):
    try:
        return model.model_validate({**payload, "idempotency_key": payload.get("idempotency_key", key)})
    except ValidationError as e:
        raise ApiError("VALIDATION", "Datos inválidos", details={"errors": [{"loc": [str(x) for x in err["loc"]], "msg": err["msg"]} for err in e.errors()]})


def execute_command(db: Session, current, cmd, ip: str | None = None) -> dict:
    """Ejecuta un comando de sync. Devuelve {idempotency_key, status, code?, message?, result?}."""
    key = cmd.idempotency_key
    payload = dict(cmd.payload or {})
    try:
        if cmd.type == "sale":
            res = cmd_sale(db, current, _parse(SaleIn, payload, key))
        elif cmd.type == "waste":
            res = cmd_waste(db, current, _parse(WasteIn, payload, key))
        elif cmd.type == "shift_open":
            res = cmd_shift_open(db, current, _parse(ShiftOpenIn, payload, key))
        elif cmd.type == "shift_close":
            shift_id = _required_uuid(payload, "shift_id")
            res = cmd_shift_close(db, current, shift_id, _parse(ShiftCloseIn, payload, key))
        elif cmd.type == "shift_transfer":
            shift_id = _required_uuid(payload, "shift_id")
            res = cmd_shift_transfer(db, current, shift_id, _parse(ShiftTransferIn, payload, key))
        elif cmd.type == "help_case":
            res = cmd_help_case(db, current, _parse(HelpCaseIn, payload, key))
        elif cmd.type == "inventory_receipt":
            res = cmd_receipt(db, current, _parse(ReceiptIn, payload, key))
        elif cmd.type == "inventory_count":
            res = cmd_count(db, current, _parse(CountIn, payload, key))
        elif cmd.type == "sale_cancel":
            sale_id = _required_uuid(payload, "sale_id")
            res = cmd_sale_cancel(db, current, sale_id, _parse(SaleCancelIn, payload, key), ip=ip)
        elif cmd.type == "gps_ping":
            pings = payload.get("pings") or [payload]
            try:
                data = GpsBatchIn.model_validate({"pings": pings})
            except ValidationError as e:
                raise ApiError("VALIDATION", "Datos inválidos", details={"errors": [{"loc": [str(x) for x in err["loc"]], "msg": err["msg"]} for err in e.errors()]})
            out = cmd_gps(db, current, data)
            return {"idempotency_key": key, "status": "ok", "result": out}
        else:
            raise ApiError("VALIDATION", f"Tipo de comando desconocido: {cmd.type}")
        return {"idempotency_key": key, "status": "duplicate" if res.duplicate else "ok", "result": res.body}
    except ApiError as e:
        db.rollback()
        return {"idempotency_key": key, "status": "error", "code": e.code, "message": e.message, "details": e.details}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"idempotency_key": key, "status": "error", "code": "CONFLICT", "message": f"Error interno al procesar el comando: {type(e).__name__}"}


def _required_uuid(payload: dict, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload[field]))
    except (KeyError, ValueError):
        raise ApiError("VALIDATION", f"Falta o es inválido el campo {field}")
