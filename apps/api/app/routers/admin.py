"""CRUD administrativo: usuarios, puntos, carritos, asignaciones, presentaciones, precios, dispositivos, zonas."""
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session, object_session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.core.errors import ApiError
from app.core.security import hash_password
from app.core.timeutil import iso, local_dt, local_today, utcnow
from app.models.catalog import Presentation, PriceItem, PriceVersion
from app.models.ops import Shift
from app.models.org import Assignment, Cart, Device, Point, User, Zone
from app.schemas.backoffice import (
    AssignmentIn,
    AssignmentPatch,
    CartIn,
    CartPatch,
    PointIn,
    PointPatch,
    PointVerifyIn,
    PresentationIn,
    PresentationPatch,
    PriceVersionIn,
    PriceVersionPatch,
    ResetPasswordIn,
    SettingPut,
    RevokeIn,
    UserIn,
    UserPatch,
    ZoneIn,
)
from sqlalchemy import func, select

from app.models.sales import Sale
from app.services import audit
from app.services import auth as auth_svc
from app.services import settings as settings_svc

router = APIRouter(prefix="/v1/admin", tags=["admin"])
ADMIN = require("admin.users")  # sólo admin (comodín "*")


def _u(x):
    return str(x) if x is not None else None


def ser_zone(z: Zone) -> dict:
    return {"id": _u(z.id), "name": z.name, "is_active": z.is_active}


def ser_user(u: User) -> dict:
    return {"id": _u(u.id), "username": u.username, "name": u.name, "role": u.role, "zone_id": _u(u.zone_id), "phone": u.phone, "is_active": u.is_active, "must_change_password": u.must_change_password}


def ser_point(p: Point) -> dict:
    return {
        "id": _u(p.id), "name": p.name, "address": p.address, "lat": p.lat, "lng": p.lng, "geofence_radius_m": p.geofence_radius_m, "zone_id": _u(p.zone_id),
        "open_time": p.open_time, "close_time": p.close_time, "daily_target_cents": p.daily_target_cents, "daily_target_tx": p.daily_target_tx, "is_active": p.is_active,
        "geo_verified": bool(p.geo_verified), "meta": p.meta or {},
    }


def ser_cart(c: Cart) -> dict:
    return {"id": _u(c.id), "code": c.code, "description": c.description, "is_active": c.is_active}


def ser_assignment(a: Assignment, last_shift: "Shift | None" = None) -> dict:
    out = {
        "id": _u(a.id), "operator_id": _u(a.operator_id), "point_id": _u(a.point_id), "cart_id": _u(a.cart_id), "shift_date": a.shift_date.isoformat(),
        "planned_start": iso(a.planned_start), "planned_end": iso(a.planned_end), "status": a.status,
    }
    if last_shift is not None:
        out["shift_id"], out["shift_status"] = _u(last_shift.id), last_shift.status
    return out


def last_shifts_by_assignment(db: Session, assignment_ids: list[uuid.UUID]) -> dict[uuid.UUID, "Shift"]:
    """Último turno por asignación en UNA consulta (DISTINCT ON), para "Continuar turno" en el backoffice."""
    if not assignment_ids:
        return {}
    rows = (
        db.query(Shift)
        .filter(Shift.assignment_id.in_(assignment_ids))
        .distinct(Shift.assignment_id)
        .order_by(Shift.assignment_id, Shift.opened_at.desc())
        .all()
    )
    return {r.assignment_id: r for r in rows}


def ser_presentation(p: Presentation) -> dict:
    return {"id": _u(p.id), "name": p.name, "grams": p.grams, "sort": p.sort, "is_active": p.is_active, "product_id": _u(p.product_id)}


def ser_price_version(v: PriceVersion, sales_count: int | None = None) -> dict:
    out = {"id": _u(v.id), "name": v.name, "valid_from": iso(v.valid_from), "valid_to": iso(v.valid_to), "is_active": v.is_active, "deactivated_at": iso(v.deactivated_at), "prices": {str(i.presentation_id): i.amount_cents for i in v.items}}
    if sales_count is not None:
        out["sales_count"] = sales_count
    return out


def ser_device(d: Device) -> dict:
    return {"id": _u(d.id), "device_id": d.device_id, "user_id": _u(d.user_id), "name": d.name, "platform": d.platform, "revoked": d.revoked, "revoked_at": iso(d.revoked_at), "revoked_reason": d.revoked_reason, "last_login_at": iso(d.last_login_at), "last_seen_at": iso(d.last_seen_at)}


def _get(db: Session, model, id_: uuid.UUID, label: str):
    obj = db.get(model, id_)
    if obj is None:
        raise ApiError("NOT_FOUND", f"{label} no encontrado")
    return obj


def _apply_patch(obj, data: dict) -> dict:
    before = {}
    for k, v in data.items():
        before[k] = getattr(obj, k, None)
        setattr(obj, k, v)
    return before


def crud(name: str, model, ser: Callable[[Any], dict], create_schema, patch_schema, label: str, order_by, before_create=None, before_patch=None):
    @router.get(f"/{name}", name=f"list_{name}")
    def _list(
        current: CurrentUser = Depends(require("admin.users", "people.read", "points.read")),
        db: Session = Depends(get_db),
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = Query(500, ge=1, le=5000),
    ):
        q = db.query(model)
        if model is Assignment:
            # Por defecto: últimos 30 días + próximos 7 (la pantalla de admin no necesita el histórico completo).
            today = local_today()
            q = q.filter(Assignment.shift_date >= (date_from or today - timedelta(days=30)), Assignment.shift_date <= (date_to or today + timedelta(days=7)))
        rows = q.order_by(order_by).limit(limit).all()
        if model is Assignment:
            last = last_shifts_by_assignment(db, [a.id for a in rows])
            return [ser_assignment(a, last.get(a.id)) for a in rows]
        return [ser(o) for o in rows]

    @router.post(f"/{name}", status_code=201, name=f"create_{name}")
    def _create(data: create_schema, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):  # type: ignore[valid-type]
        values = data.model_dump()
        if before_create:
            values = before_create(db, values)
        obj = model(**values)
        db.add(obj)
        db.flush()
        audit.log(db, actor_id=current.id, action=f"{name}.create", entity=name, entity_id=obj.id, after=ser(obj), ip=client_ip(request))
        db.commit()
        return ser(obj)

    @router.get(f"/{name}/{{item_id}}", name=f"get_{name}")
    def _get_one(item_id: uuid.UUID, current: CurrentUser = Depends(require("admin.users", "people.read", "points.read")), db: Session = Depends(get_db)):
        return ser(_get(db, model, item_id, label))

    @router.patch(f"/{name}/{{item_id}}", name=f"patch_{name}")
    def _patch(item_id: uuid.UUID, data: patch_schema, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):  # type: ignore[valid-type]
        obj = _get(db, model, item_id, label)
        values = data.model_dump(exclude_unset=True)
        if before_patch:
            values = before_patch(db, obj, values)
        before = _apply_patch(obj, values)
        audit.log(db, actor_id=current.id, action=f"{name}.update", entity=name, entity_id=obj.id, before=before, after=values, ip=client_ip(request))
        db.commit()
        return ser(obj)

    @router.delete(f"/{name}/{{item_id}}", name=f"delete_{name}")
    def _delete(item_id: uuid.UUID, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
        obj = _get(db, model, item_id, label)
        if hasattr(obj, "is_active"):
            obj.is_active = False  # baja lógica: nunca se borran registros referenciados por el ledger
            action = f"{name}.deactivate"
        else:
            db.delete(obj)
            action = f"{name}.delete"
        audit.log(db, actor_id=current.id, action=action, entity=name, entity_id=item_id, ip=client_ip(request))
        db.commit()
        return {"ok": True}


def _user_create(db, values):
    pwd = values.pop("password", None)
    if not pwd:
        raise ApiError("VALIDATION", "La contraseña es obligatoria")
    if db.query(User).filter(User.username == values["username"]).first():
        raise ApiError("CONFLICT", "El usuario ya existe")
    values["password_hash"] = hash_password(pwd)
    return values


def _user_patch(db, obj, values):
    pwd = values.pop("password", None)
    if pwd:
        values["password_hash"] = hash_password(pwd)
    return values


def _assignment_create(db, values):
    point = _get(db, Point, values["point_id"], "Punto")
    if not point.is_active:
        raise ApiError("VALIDATION", f"El punto «{point.name}» no está activo: sólo se asignan puntos autorizados activos")
    _get(db, User, values["operator_id"], "Operador")
    _get(db, Cart, values["cart_id"], "Carrito")
    if db.query(Assignment).filter(Assignment.operator_id == values["operator_id"], Assignment.shift_date == values["shift_date"]).first():
        raise ApiError("CONFLICT", "El operador ya tiene asignación ese día")
    if values.get("planned_start") is None:
        values["planned_start"] = local_dt(values["shift_date"], point.open_time or "08:00")
    if values.get("planned_end") is None:
        values["planned_end"] = local_dt(values["shift_date"], point.close_time or "18:00")
    return values


def _point_create(db, values):
    if values.get("daily_target_cents") is None:
        values["daily_target_cents"] = settings_svc.get_int(db, "daily_sales_target_default_cents")
    return values


def _presentation_create(db, values):
    return values


crud("zones", Zone, ser_zone, ZoneIn, ZoneIn, "Zona", Zone.name)
crud("users", User, ser_user, UserIn, UserPatch, "Usuario", User.username, _user_create, _user_patch)
crud("points", Point, ser_point, PointIn, PointPatch, "Punto", Point.name, _point_create)
crud("carts", Cart, ser_cart, CartIn, CartPatch, "Carrito", Cart.code)
crud("assignments", Assignment, ser_assignment, AssignmentIn, AssignmentPatch, "Asignación", Assignment.shift_date.desc(), _assignment_create)
crud("presentations", Presentation, ser_presentation, PresentationIn, PresentationPatch, "Presentación", Presentation.sort)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: uuid.UUID, request: Request, data: ResetPasswordIn | None = None, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    """Restablece la contraseña (temporal generada si no se envía `new_password`) y obliga a cambiarla al entrar.
    Revoca todos los refresh tokens del usuario. `temporary_password` sólo se devuelve cuando fue generada."""
    u = _get(db, User, user_id, "Usuario")
    generated = data is None or not data.new_password
    new_password = auth_svc.generate_temporary_password() if generated else data.new_password
    auth_svc.validate_new_password(new_password)
    u.password_hash = hash_password(new_password)
    u.must_change_password = True
    revoked = auth_svc.revoke_user_tokens(db, u.id)
    audit.log(db, actor_id=current.id, action="user.password_reset", entity="user", entity_id=u.id, after={"must_change_password": True, "generated": generated, "revoked_refresh_tokens": revoked}, ip=client_ip(request))
    db.commit()
    body = {"ok": True, "user_id": _u(u.id), "must_change_password": True}
    if generated:
        body["temporary_password"] = new_password
    return body


@router.post("/points/import-authorized")
def import_authorized(request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    """Re-importa el catálogo de puntos autorizados (idempotente; no pisa coordenadas verificadas)."""
    from app.services.points_import import import_authorized_points

    out = import_authorized_points(db, actor_id=current.id)
    db.commit()
    return out


@router.post("/points/{point_id}/verify-location")
def verify_point_location(point_id: uuid.UUID, data: PointVerifyIn, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    """Marca las coordenadas del punto como verificadas en campo. Si vienen lat/lng (p. ej. el GPS de una apertura), se adoptan."""
    p = _get(db, Point, point_id, "Punto")
    before = {"lat": p.lat, "lng": p.lng, "geo_verified": p.geo_verified}
    if data.lat is not None and data.lng is not None:
        p.lat, p.lng = data.lat, data.lng
    p.geo_verified = data.verified
    p.meta = {**(p.meta or {}), "geo_source": data.source or ("verificado por administrador" if data.verified else "por validar")}
    audit.log(db, actor_id=current.id, action="points.verify_location", entity="points", entity_id=p.id, before=before, after={"lat": p.lat, "lng": p.lng, "geo_verified": p.geo_verified}, reason=data.source, ip=client_ip(request))
    db.commit()
    return ser_point(p)


@router.get("/price-versions")
def list_price_versions(_: CurrentUser = Depends(require("admin.users", "reports.read")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Sale.price_version_id, func.count(Sale.id)).group_by(Sale.price_version_id)).all())
    return [ser_price_version(v, int(counts.get(v.id, 0))) for v in db.query(PriceVersion).order_by(PriceVersion.valid_from.desc()).all()]


@router.patch("/price-versions/{version_id}")
def patch_price_version(version_id: uuid.UUID, data: PriceVersionPatch, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    """Activa/desactiva una versión (los precios no se editan). Al desactivar se fija `deactivated_at`; las ventas
    offline con esa versión se aceptan `PRICE_OFFLINE_GRACE_HOURS` más y quedan marcadas `price_version_stale` (B8)."""
    v = _get(db, PriceVersion, version_id, "Versión de precio")
    values = data.model_dump(exclude_unset=True)
    before = ser_price_version(v)
    if "is_active" in values and values["is_active"] is not None and values["is_active"] != v.is_active:
        v.is_active = values["is_active"]
        v.deactivated_at = None if v.is_active else utcnow()
    if values.get("name"):
        v.name = values["name"]
    if "valid_to" in values:
        v.valid_to = values["valid_to"]
    audit.log(db, actor_id=current.id, action="price_version.update", entity="price_version", entity_id=v.id, before=before, after=ser_price_version(v), reason="Cambio de estado de versión de precio", ip=client_ip(request))
    db.commit()
    sales_count = int(db.execute(select(func.count(Sale.id)).where(Sale.price_version_id == v.id)).scalar_one())
    return ser_price_version(v, sales_count)


# ---- Parámetros operativos (B6) ----
@router.get("/settings")
def list_settings(_: CurrentUser = Depends(require("admin.users", "rules.read", "reports.read")), db: Session = Depends(get_db)):
    return settings_svc.list_settings(db)


@router.get("/settings/{key}")
def get_setting(key: str, _: CurrentUser = Depends(require("admin.users", "rules.read", "reports.read")), db: Session = Depends(get_db)):
    for item in settings_svc.list_settings(db):
        if item["key"] == key:
            return item
    raise ApiError("NOT_FOUND", "Parámetro no encontrado", details={"key": key})


@router.put("/settings/{key}")
def put_setting(key: str, data: SettingPut, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    out = settings_svc.set_setting(db, key, data.value, current.id, ip=client_ip(request))
    db.commit()
    return out


@router.post("/price-versions", status_code=201)
def create_price_version(data: PriceVersionIn, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    """Crea una nueva versión de precio (los precios nunca se editan in-place)."""
    if db.query(PriceVersion).filter(PriceVersion.name == data.name).first():
        raise ApiError("CONFLICT", "Ya existe una versión con ese nombre")
    for pid in data.prices:
        _get(db, Presentation, pid, "Presentación")
    valid_from = data.valid_from or utcnow()
    v = PriceVersion(name=data.name, valid_from=valid_from, created_by=current.id)
    v.items = [PriceItem(presentation_id=pid, amount_cents=amt) for pid, amt in data.prices.items()]
    prev = db.query(PriceVersion).filter(PriceVersion.is_active.is_(True), PriceVersion.valid_from < valid_from).order_by(PriceVersion.valid_from.desc()).first()
    db.add(v)
    db.flush()
    audit.log(db, actor_id=current.id, action="price_version.create", entity="price_version", entity_id=v.id, before=ser_price_version(prev) if prev else None, after=ser_price_version(v), reason="Cambio de precios", ip=client_ip(request))
    db.commit()
    return ser_price_version(v)


@router.get("/devices")
def list_devices(_: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    return [ser_device(d) for d in db.query(Device).order_by(Device.created_at.desc()).all()]


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, data: RevokeIn | None = None, request: Request = None, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    """Revoca un dispositivo por id interno (UUID) o por `device_id` del cliente."""
    d = None
    try:
        d = db.get(Device, uuid.UUID(device_id))
    except ValueError:
        pass
    if d is None:
        d = db.query(Device).filter(Device.device_id == device_id).first()
    if d is None:
        raise ApiError("NOT_FOUND", "Dispositivo no encontrado")
    d.revoked = True
    d.revoked_at = utcnow()
    d.revoked_reason = data.reason if data else None
    revoked_tokens = auth_svc.revoke_device_tokens(db, d.device_id)
    audit.log(db, actor_id=current.id, action="device.revoke", entity="device", entity_id=d.id, before={"revoked": False}, after={"revoked": True, "revoked_refresh_tokens": revoked_tokens}, reason=d.revoked_reason, ip=client_ip(request) if request else None)
    db.commit()
    return ser_device(d)


@router.post("/devices/{device_id}/unrevoke")
def unrevoke_device(device_id: str, request: Request, current: CurrentUser = Depends(ADMIN), db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if d is None:
        raise ApiError("NOT_FOUND", "Dispositivo no encontrado")
    d.revoked = False
    d.revoked_at = None
    audit.log(db, actor_id=current.id, action="device.unrevoke", entity="device", entity_id=d.id, before={"revoked": True}, after={"revoked": False}, ip=client_ip(request))
    db.commit()
    return ser_device(d)
