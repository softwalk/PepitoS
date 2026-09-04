"""Turnos: abrir, esperado, cerrar, transferir. Asistencia y caja asociadas."""
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.timeutil import iso, local_today, utcnow
from app.models.cases import Alert, Approval, Case, Rule
from app.models.catalog import Presentation
from app.models.ops import CashSession, ChecklistResult, GpsPing, Shift
from app.models.org import Assignment, Attendance, Point, User
from app.services import audit, events
from app.services import evidence as evidence_svc
from app.services.cases import open_case_if_new
from app.services import settings as settings_svc
from app.services.settings import cash_thresholds, get_setting
from app.services.cash import sales_summary
from app.services.geo import haversine_m, in_geofence
from app.services.inventory import add_movement, apply_count, balances_for_point, shift_units

# out_of_geofence cuenta como crítica: el operador ve el aviso ("abierto con pendientes") y el supervisor recibe caso urgente.
CRITICAL_OPEN_KEYS = {"cart_secure", "battery_ok", "product_ok", "pos_ok", "out_of_geofence"}
OPEN_EXCEPTION_MESSAGES = {
    "cart_secure": "Carrito no asegurado: revisa candado y resguardo",
    "battery_ok": "Batería insuficiente: conecta el cargador o pide reemplazo",
    "product_ok": "Producto insuficiente o en mal estado: pide reposición",
    "clean_ok": "Carrito sucio: limpia antes de vender",
    "pos_ok": "Terminal POS no funciona: cobra sólo en efectivo y pide ayuda",
    "out_of_geofence": "Estás fuera del punto asignado",
    "gps_mocked": "La ubicación parece simulada",
}


def get_shift_or_404(db: Session, shift_id: uuid.UUID) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise ApiError("NOT_FOUND", "Turno no encontrado")
    return shift


def check_shift_access(shift: Shift, current, db: Session) -> None:
    """Operador: sólo turnos propios. Supervisor: su zona. ops/finance/admin: todo."""
    if current.role == "operator" and shift.operator_id != current.id:
        raise ApiError("FORBIDDEN", "Este turno no es tuyo")
    if current.role == "supervisor":
        point = db.get(Point, shift.point_id)
        if point is None or point.zone_id != current.zone_id:
            raise ApiError("FORBIDDEN", "El punto no pertenece a tu zona")


def _open_shift_for(
    db: Session,
    *,
    operator: User,
    assignment: Assignment | None,
    point_id: uuid.UUID,
    cart_id: uuid.UUID,
    opened_at: datetime,
    device_id: str | None,
    exceptions: list[dict],
    ready: bool,
    gps: dict | None,
    transferred_from: uuid.UUID | None = None,
) -> Shift:
    if db.query(Shift).filter(Shift.operator_id == operator.id, Shift.status == "open").first():
        raise ApiError("SHIFT_ALREADY_OPEN")
    if db.query(Shift).filter(Shift.cart_id == cart_id, Shift.status == "open").first():
        raise ApiError("CART_IN_USE")
    shift = Shift(
        assignment_id=assignment.id if assignment else None, operator_id=operator.id, point_id=point_id, cart_id=cart_id,
        device_id=device_id, status="open", opened_at=opened_at, open_exceptions=exceptions, ready=ready,
        last_seen_at=utcnow(), open_gps=gps, transferred_from_shift_id=transferred_from,
    )
    db.add(shift)
    try:
        db.flush()
    except IntegrityError as e:  # índice único parcial
        db.rollback()
        msg = str(e.orig)
        if "uq_shifts_operator_open" in msg:
            raise ApiError("SHIFT_ALREADY_OPEN")
        raise ApiError("CART_IN_USE")
    db.add(CashSession(shift_id=shift.id, point_id=point_id, opened_at=opened_at, opening_cents=0, status="open"))
    late = 0
    if assignment is not None:
        late = max(0, int((opened_at - assignment.planned_start).total_seconds() // 60))
        assignment.status = "started"
    db.add(
        Attendance(
            user_id=operator.id, assignment_id=assignment.id if assignment else None, shift_id=shift.id,
            work_date=opened_at.astimezone(settings.tz).date(),
            check_in_at=opened_at, late_minutes=late, status="late" if late > 15 else "present",
        )
    )
    return shift


def open_shift(db: Session, current, data) -> dict:
    assignment = db.get(Assignment, data.assignment_id)
    if assignment is None or assignment.operator_id != current.id:
        raise ApiError("NO_ASSIGNMENT", "La asignación no existe o no es tuya")
    if assignment.status == "done":
        raise ApiError("CONFLICT", "La asignación ya fue completada")
    if db.query(Shift).filter(Shift.assignment_id == assignment.id, Shift.status == "open").first():
        raise ApiError("SHIFT_ALREADY_OPEN")
    point = db.get(Point, assignment.point_id)
    opened_at = data.opened_at or utcnow()

    checklist = data.checklist.model_dump()
    exceptions: list[dict] = []
    for key, ok in checklist.items():
        if not ok:
            exceptions.append({"code": key, "message": OPEN_EXCEPTION_MESSAGES.get(key, key)})
    gps = data.gps.model_dump(mode="json") if data.gps else None
    distance_m: float | None = None
    limit_m: int | None = None
    if data.gps is not None:
        # Regla de apertura: a no más de `open_max_distance_m` (50 m) del punto asignado. Si las coordenadas del punto
        # aún no están verificadas en campo, la tolerancia es su geocerca (150 m) para no generar falsos avisos.
        distance_m = haversine_m(data.gps.lat, data.gps.lng, point.lat, point.lng)
        limit_m = settings_svc.get_int(db, "open_max_distance_m") if point.geo_verified else point.geofence_radius_m
        if distance_m > limit_m:
            exceptions.append({
                "code": "out_of_geofence",
                "message": f"Estás a {distance_m:.0f} m del punto asignado (máximo {limit_m} m)",
                "distance_m": round(distance_m), "limit_m": limit_m,
            })
        if data.gps.mocked:
            exceptions.append({"code": "gps_mocked", "message": OPEN_EXCEPTION_MESSAGES["gps_mocked"]})
    critical = [e for e in exceptions if e["code"] in CRITICAL_OPEN_KEYS]
    ready = len(critical) == 0

    shift = _open_shift_for(
        db, operator=current.user, assignment=assignment, point_id=assignment.point_id, cart_id=assignment.cart_id,
        opened_at=opened_at, device_id=current.device_id, exceptions=exceptions, ready=ready, gps=gps,
    )
    for key, ok in checklist.items():
        db.add(ChecklistResult(shift_id=shift.id, kind="open", key=key, value=ok, at=opened_at))
    if data.gps is not None:
        db.add(
            GpsPing(
                shift_id=shift.id, user_id=current.id, device_id=current.device_id, at=data.gps.at or opened_at,
                lat=data.gps.lat, lng=data.gps.lng, accuracy_m=data.gps.accuracy_m, mocked=data.gps.mocked,
                in_geofence=in_geofence(data.gps.lat, data.gps.lng, point.lat, point.lng, point.geofence_radius_m),
            )
        )
    photos = evidence_svc.store_photos(
        db, data.photos, kind="shift_open", entity="shift", entity_id=shift.id, uploaded_by=current.id,
        point_id=shift.point_id, shift_id=shift.id, taken_at=opened_at,
    )
    for e in critical:
        severity = "urgent" if e["code"] in ("cart_secure", "out_of_geofence") else "review"
        open_case_if_new(
            db, rule_key=f"open_{e['code']}", point_id=shift.point_id, shift_id=shift.id,
            severity=severity, title=f"Apertura con excepción: {e['message']}",
            description=e["message"] + (f" · Operador {current.user.name}" if e["code"] == "out_of_geofence" else ""),
            impact_score=25 if e["code"] == "out_of_geofence" else 15, source="operator", actor_id=current.id, category="opening",
            payload={k: v for k, v in e.items() if k not in ("code", "message")},
        )

    events.emit(
        db, "ShiftOpened", actor_id=current.id, point_id=shift.point_id, shift_id=shift.id, entity="shift", entity_id=shift.id,
        payload={"assignment_id": assignment.id, "cart_id": assignment.cart_id, "exceptions": exceptions, "ready": ready, "photos": len(data.photos or []), "evidence_ids": [ev.id for ev in photos]},
        occurred_at=opened_at,
    )
    return {
        "shift_id": str(shift.id),
        "status": "open" if not exceptions else "open_with_exception",
        "exceptions": exceptions,
        "ready": ready,
        "evidence_ids": [str(ev.id) for ev in photos],
    }


def expected(db: Session, shift: Shift) -> dict:
    s = sales_summary(db, shift.id)
    balances = balances_for_point(db, shift.point_id)
    return {
        "sales_count": s["sales_count"],
        "sales_total_cents": s["sales_total_cents"],
        "cash_expected_cents": s["cash_expected_cents"],
        "digital_total_cents": s["digital_total_cents"],
        "product_expected": {str(k): v for k, v in balances.items()},
        "waste_units": shift_units(db, shift.id, "waste"),
        "cancelled_count": s["cancelled_count"],
    }


def _settle_cash(db: Session, shift: Shift, actor_id: uuid.UUID, counted: int, closed_at: datetime) -> tuple[int, int, uuid.UUID | None]:
    s = sales_summary(db, shift.id)
    exp = s["cash_expected_cents"]
    diff = counted - exp
    threshold, severe = cash_thresholds(db)  # rules.params > settings > default
    case_id = None
    if abs(diff) > threshold:
        severity = "urgent" if abs(diff) > severe else "review"
        events.emit(
            db, "CashDifferenceDetected", actor_id=actor_id, point_id=shift.point_id, shift_id=shift.id, entity="shift",
            entity_id=shift.id, payload={"expected_cents": exp, "counted_cents": counted, "difference_cents": diff, "severity": severity},
            occurred_at=closed_at,
        )
        case = open_case_if_new(
            db, rule_key="cash_difference", point_id=shift.point_id, shift_id=shift.id, severity=severity,
            title=f"Diferencia de caja de ${abs(diff) / 100:,.2f}",
            description=f"Esperado ${exp / 100:,.2f}, contado ${counted / 100:,.2f} ({'faltante' if diff < 0 else 'sobrante'})",
            impact_score=min(abs(diff) / 100, 50), source="rule", actor_id=actor_id,
            payload={"expected_cents": exp, "counted_cents": counted, "difference_cents": diff}, dedupe_date=closed_at,
        )
        case_id = case.id if case else None
        if abs(diff) > severe:
            ap = Approval(
                approval_type="cash_difference", entity="shift", entity_id=shift.id,
                title=f"Diferencia de caja grave en turno {str(shift.id)[:8]}", amount_cents=diff, requested_by=actor_id,
                payload={"case_id": str(case_id) if case_id else None},
            )
            db.add(ap)
            db.flush()
            events.emit(db, "ApprovalRequested", actor_id=actor_id, point_id=shift.point_id, shift_id=shift.id, entity="approval", entity_id=ap.id, payload={"amount_cents": diff, "type": "cash_difference"})
    cs = db.query(CashSession).filter(CashSession.shift_id == shift.id).first()
    if cs is not None:
        cs.closed_at = closed_at
        cs.cash_sales_cents = exp
        cs.digital_sales_cents = s["digital_total_cents"]
        cs.expected_cents = exp
        cs.counted_cents = counted
        cs.difference_cents = diff
        cs.status = "reconciled" if abs(diff) <= threshold else "difference"
    return exp, diff, case_id


def _finish_shift(db: Session, shift: Shift, closed_at: datetime, status: str, exp: int, counted: int, diff: int, product_diff: dict, gps: dict | None) -> None:
    threshold, _ = cash_thresholds(db)
    shift.status = status
    shift.closed_at = closed_at
    shift.cash_expected_cents = exp
    shift.cash_counted_cents = counted
    shift.difference_cents = diff
    shift.close_status = "reconciled" if abs(diff) <= threshold else "difference"
    shift.product_diff = {str(k): v for k, v in product_diff.items()}
    shift.close_gps = gps
    shift.last_seen_at = utcnow()
    att = db.query(Attendance).filter(Attendance.shift_id == shift.id).first()
    if att is not None:
        att.check_out_at = closed_at
    if shift.assignment_id:
        a = db.get(Assignment, shift.assignment_id)
        if a is not None:
            a.status = "done"


def close_shift(db: Session, current, shift: Shift, data) -> dict:
    if shift.status != "open":
        raise ApiError("SHIFT_NOT_OPEN")
    closed_at = data.closed_at or utcnow()
    exp, diff, cash_case_id = _settle_cash(db, shift, current.id, data.cash_counted_cents, closed_at)
    product_diff: dict = {}
    inv_case_id = None
    if data.product_counts:
        _, product_diff, inv_case_id = apply_count(db, shift, current.id, data.product_counts, kind="close", occurred_at=closed_at)
    for key, ok in data.checklist.model_dump().items():
        db.add(ChecklistResult(shift_id=shift.id, kind="close", key=key, value=ok, at=closed_at))
    gps = data.gps.model_dump(mode="json") if data.gps else None
    photos = evidence_svc.store_photos(
        db, getattr(data, "photos", None), kind="shift_close", entity="shift", entity_id=shift.id, uploaded_by=current.id,
        point_id=shift.point_id, shift_id=shift.id, taken_at=closed_at,
    )
    _finish_shift(db, shift, closed_at, "closed", exp, data.cash_counted_cents, diff, product_diff, gps)
    events.emit(
        db, "ShiftClosed", actor_id=current.id, point_id=shift.point_id, shift_id=shift.id, entity="shift", entity_id=shift.id,
        payload={"cash_expected_cents": exp, "cash_counted_cents": data.cash_counted_cents, "difference_cents": diff, "close_status": shift.close_status, "product_diff": product_diff, "evidence_ids": [ev.id for ev in photos]},
        occurred_at=closed_at,
    )
    case_id = cash_case_id or inv_case_id
    # El cierre consolida las ventas del turno: refrescar el ranking de vendedores.
    from app.services.ranking import recompute_rankings

    recompute_rankings(db, closed_at)
    return {
        "shift_id": str(shift.id),
        "status": shift.close_status,
        "cash_expected_cents": exp,
        "cash_counted_cents": data.cash_counted_cents,
        "difference_cents": diff,
        "product_diff": {str(k): v for k, v in product_diff.items()},
        "case_id": str(case_id) if case_id else None,
        "evidence_ids": [str(ev.id) for ev in photos],
    }


def transfer_shift(db: Session, current, shift: Shift, data) -> dict:
    """Cierra el turno actual con caja/inventario intermedio y abre uno nuevo para `to_operator_id`."""
    if shift.status != "open":
        raise ApiError("SHIFT_NOT_OPEN")
    to_op = db.get(User, data.to_operator_id)
    if to_op is None or to_op.role != "operator" or not to_op.is_active:
        raise ApiError("NOT_FOUND", "Operador destino no encontrado")
    if to_op.id == shift.operator_id:
        raise ApiError("VALIDATION", "El operador destino es el mismo")
    if db.query(Shift).filter(Shift.operator_id == to_op.id, Shift.status == "open").first():
        raise ApiError("SHIFT_ALREADY_OPEN", "El operador destino ya tiene un turno abierto")
    at = data.occurred_at or utcnow()
    exp, diff, _ = _settle_cash(db, shift, current.id, data.cash_counted_cents, at)
    product_diff: dict = {}
    if data.product_counts:
        _, product_diff, _ = apply_count(db, shift, current.id, data.product_counts, kind="transfer", occurred_at=at)
    gps = data.gps.model_dump(mode="json") if data.gps else None
    # Inventario intermedio: transfer_out del turno saliente y transfer_in del entrante (mismo punto).
    balances = balances_for_point(db, shift.point_id)
    _finish_shift(db, shift, at, "transferred", exp, data.cash_counted_cents, diff, product_diff, gps)
    db.flush()
    # Asignación del nuevo operador para hoy (si existe) para conservar trazabilidad
    assignment = (
        db.query(Assignment).filter(Assignment.operator_id == to_op.id, Assignment.shift_date == local_today(at)).first()
    )
    new_shift = _open_shift_for(
        db, operator=to_op, assignment=assignment, point_id=shift.point_id, cart_id=shift.cart_id, opened_at=at,
        device_id=None, exceptions=[], ready=True, gps=gps, transferred_from=shift.id,
    )
    shift.transferred_to_shift_id = new_shift.id
    for pres_id, qty in balances.items():
        if qty:
            add_movement(db, point_id=shift.point_id, presentation_id=pres_id, qty=-qty, movement_type="transfer_out", shift_id=shift.id, actor_id=current.id, ref_entity="shift", ref_id=new_shift.id, occurred_at=at, note="Transferencia de turno")
            add_movement(db, point_id=shift.point_id, presentation_id=pres_id, qty=qty, movement_type="transfer_in", shift_id=new_shift.id, actor_id=current.id, ref_entity="shift", ref_id=shift.id, occurred_at=at, note="Transferencia de turno")
    events.emit(
        db, "ShiftTransferred", actor_id=current.id, point_id=shift.point_id, shift_id=shift.id, entity="shift", entity_id=shift.id,
        payload={"closed_shift_id": shift.id, "new_shift_id": new_shift.id, "to_operator_id": to_op.id, "cash_counted_cents": data.cash_counted_cents, "difference_cents": diff},
        occurred_at=at,
    )
    events.emit(db, "ShiftOpened", actor_id=current.id, point_id=shift.point_id, shift_id=new_shift.id, entity="shift", entity_id=new_shift.id, payload={"transferred_from": shift.id, "operator_id": to_op.id}, occurred_at=at)
    audit.log(db, actor_id=current.id, action="shift.transfer", entity="shift", entity_id=shift.id, before={"operator_id": str(shift.operator_id)}, after={"new_shift_id": str(new_shift.id), "to_operator_id": str(to_op.id)}, reason="Transferencia de turno")
    return {"closed_shift_id": str(shift.id), "new_shift_id": str(new_shift.id), "difference_cents": diff}


def reopen_shift(db: Session, current, shift: Shift, reason: str, ip: str | None = None) -> dict:
    """Sólo administrador: vuelve a abrir un turno cerrado HOY para que el operador continúe vendiendo y lo cierre de nuevo.

    - Conserva ventas, movimientos y el cierre anterior (queda íntegro en audit_log y en el evento ShiftReopened).
    - Los casos de caja/inventario y la aprobación de diferencia grave generados por ese cierre se cierran/cancelan
      como "superados": el siguiente cierre volverá a evaluar contra TODAS las ventas del turno.
    - Sólo turnos abiertos en el día local actual: reabrir uno viejo dejaría al operador sin poder abrir el de hoy y
      fuera del Control Tower (que filtra por día).
    """
    if shift.status != "closed":
        raise ApiError("CONFLICT", "Sólo se puede continuar un turno cerrado (no transferido ni abierto)")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ApiError("VALIDATION", "Indica un motivo (mínimo 5 caracteres)")
    at = utcnow()
    if local_today(shift.opened_at) != local_today(at):
        raise ApiError("CONFLICT", "Sólo se puede continuar un turno abierto hoy")
    window_h = settings_svc.get_int(db, "shift_reopen_window_hours")
    if shift.closed_at is not None and at - shift.closed_at > timedelta(hours=window_h):
        elapsed = at - shift.closed_at
        mins = int(elapsed.total_seconds() // 60)
        closed_local = shift.closed_at.astimezone(settings.tz).strftime("%d-%b %H:%M")
        now_local = at.astimezone(settings.tz).strftime("%d-%b %H:%M")
        raise ApiError(
            "CONFLICT",
            f"El turno se cerró el {closed_local} (hace {mins // 60} h {mins % 60} min; servidor: {now_local}) y la ventana es de {window_h} h "
            "(parámetro shift_reopen_window_hours en Administración → Parámetros). Si la hora no cuadra, revisa el reloj del servidor o del teléfono.",
        )
    if db.query(Shift).filter(Shift.operator_id == shift.operator_id, Shift.status == "open").first():
        raise ApiError("SHIFT_ALREADY_OPEN", "El operador ya tiene otro turno abierto")
    if db.query(Shift).filter(Shift.cart_id == shift.cart_id, Shift.status == "open").first():
        raise ApiError("SHIFT_ALREADY_OPEN", "El carrito ya tiene otro turno abierto")

    before = {
        "closed_at": iso(shift.closed_at), "close_status": shift.close_status, "cash_expected_cents": shift.cash_expected_cents,
        "cash_counted_cents": shift.cash_counted_cents, "difference_cents": shift.difference_cents,
        "product_diff": shift.product_diff, "close_gps": shift.close_gps,
    }
    shift.status = "open"
    shift.closed_at = None
    shift.close_status = None
    shift.cash_expected_cents = None
    shift.cash_counted_cents = None
    shift.difference_cents = None
    shift.product_diff = {}
    shift.close_gps = None
    shift.last_seen_at = at
    cs = db.query(CashSession).filter(CashSession.shift_id == shift.id).first()
    if cs is not None:
        cs.status = "open"
        cs.closed_at = None
        cs.cash_sales_cents = 0
        cs.digital_sales_cents = 0
        cs.expected_cents = None
        cs.counted_cents = None
        cs.difference_cents = None
    att = db.query(Attendance).filter(Attendance.shift_id == shift.id).first()
    if att is not None:
        att.check_out_at = None
    if shift.assignment_id:
        a = db.get(Assignment, shift.assignment_id)
        if a is not None:
            a.status = "started"

    # Casos y aprobaciones del cierre anterior: quedan superados (el nuevo cierre los volverá a evaluar).
    note = f"Superado: turno reabierto por administrador ({reason})"
    superseded_cases: list[str] = []
    for case in db.query(Case).filter(Case.shift_id == shift.id, Case.rule_key.in_(["cash_difference", "inventory_inconsistent"]), Case.status.in_(["open", "in_progress"])).all():
        case.status = "closed"
        case.resolved_at = at
        case.resolution = note
        for alert in db.query(Alert).filter(Alert.case_id == case.id, Alert.status == "open").all():
            alert.status = "resolved"
            alert.resolved_at = at
        audit.log(db, actor_id=current.id, action="case.update", entity="case", entity_id=case.id, before={"status": "open"}, after={"status": "closed"}, reason=note, ip=ip)
        superseded_cases.append(str(case.id))
    superseded_approvals: list[str] = []
    for ap in db.query(Approval).filter(Approval.entity == "shift", Approval.entity_id == shift.id, Approval.status == "pending").all():
        ap.status = "cancelled"
        ap.decided_by = current.id
        ap.decided_at = at
        ap.decision_note = note
        audit.log(db, actor_id=current.id, action="approval.cancel", entity="approval", entity_id=ap.id, before={"status": "pending"}, after={"status": "cancelled"}, reason=note, ip=ip)
        superseded_approvals.append(str(ap.id))

    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        # Carrera con otra apertura/reapertura simultánea: índices únicos parciales uq_shifts_operator_open / uq_shifts_cart_open.
        if "uq_shifts_" in str(e.orig):
            raise ApiError("SHIFT_ALREADY_OPEN", "El operador o el carrito ya tienen otro turno abierto") from e
        raise
    events.emit(
        db, "ShiftReopened", actor_id=current.id, point_id=shift.point_id, shift_id=shift.id, entity="shift", entity_id=shift.id,
        payload={"reason": reason, "previous_close": before, "superseded_cases": superseded_cases, "superseded_approvals": superseded_approvals}, occurred_at=at,
    )
    audit.log(
        db, actor_id=current.id, action="shift.reopen", entity="shift", entity_id=shift.id, before=before,
        after={"status": "open", "superseded_cases": superseded_cases, "superseded_approvals": superseded_approvals}, reason=reason, ip=ip,
    )
    db.flush()
    return serialize_shift(shift)


def record_pings(db: Session, current, pings) -> int:
    accepted = 0
    for p in pings:
        shift = db.get(Shift, p.shift_id)
        if shift is None or shift.status != "open":
            continue
        if current.role == "operator" and shift.operator_id != current.id:
            continue
        point = db.get(Point, shift.point_id)
        inside = in_geofence(p.lat, p.lng, point.lat, point.lng, point.geofence_radius_m) if point else None
        db.add(
            GpsPing(
                shift_id=shift.id, user_id=current.id, device_id=current.device_id, at=p.at or utcnow(), lat=p.lat, lng=p.lng,
                accuracy_m=p.accuracy_m, mocked=p.mocked, battery_pct=p.battery_pct, in_geofence=inside,
            )
        )
        shift.last_seen_at = utcnow()
        accepted += 1
    return accepted


def serialize_shift(shift: Shift) -> dict:
    return {
        "id": str(shift.id),
        "status": shift.status,
        "opened_at": iso(shift.opened_at),
        "closed_at": iso(shift.closed_at),
        "point_id": str(shift.point_id),
        "cart_id": str(shift.cart_id),
        "operator_id": str(shift.operator_id),
        "ready": shift.ready,
        "exceptions": shift.open_exceptions,
        "close_status": shift.close_status,
    }


def presentation_ids(db: Session) -> list[uuid.UUID]:
    return [p.id for p in db.query(Presentation).filter(Presentation.is_active.is_(True))]
