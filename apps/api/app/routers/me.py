"""Asignación del operador, catálogo y precios vigentes."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.timeutil import iso, local_today
from app.models.catalog import Flavor, Presentation
from app.models.ops import Checklist, Shift
from app.models.org import Assignment
from app.services.cases import get_rule_params
from app.services.sales import OPERATOR_CONFIG_DEFAULTS, current_price_version, price_map

router = APIRouter(prefix="/v1", tags=["operador"])

WASTE_REASONS = [
    {"code": "spill", "label": "Se cayó / derramó"},
    {"code": "quality", "label": "Mala calidad"},
    {"code": "expired", "label": "Caducado"},
    {"code": "sample", "label": "Muestra / degustación"},
    {"code": "other", "label": "Otro"},
]
HELP_CATEGORIES = [
    {"code": "cart", "label": "Carrito", "icon": "cart"},
    {"code": "battery", "label": "Batería", "icon": "battery"},
    {"code": "product", "label": "Producto", "icon": "package"},
    {"code": "payment", "label": "Cobro", "icon": "credit-card"},
    {"code": "security", "label": "Seguridad", "icon": "shield"},
    {"code": "other", "label": "Otro", "icon": "help-circle"},
]


def build_catalog(db: Session) -> dict:
    version = current_price_version(db)
    prices = price_map(db, version.id) if version else {}
    presentations = db.query(Presentation).filter(Presentation.is_active.is_(True)).order_by(Presentation.sort).all()
    flavors = db.query(Flavor).filter(Flavor.is_active.is_(True)).order_by(Flavor.sort).all()
    checks = db.query(Checklist).order_by(Checklist.sort).all()
    return {
        "presentations": [{"id": str(p.id), "name": p.name, "grams": p.grams, "price_cents": prices.get(p.id), "sort": p.sort} for p in presentations],
        "flavors": [{"id": str(f.id), "name": f.name, "sort": f.sort} for f in flavors],
        "price_version_id": str(version.id) if version else None,
        "waste_reasons": WASTE_REASONS,
        "help_categories": HELP_CATEGORIES,
        "checklist_open": [{"key": c.key, "label": c.label, "critical": c.critical} for c in checks if c.kind == "open"],
        "checklist_close": [{"key": c.key, "label": c.label, "critical": c.critical} for c in checks if c.kind == "close"],
    }


def operator_config(db: Session) -> dict:
    cfg = dict(OPERATOR_CONFIG_DEFAULTS)
    cfg["cash_difference_threshold_cents"] = int(get_rule_params(db, "cash_difference").get("threshold_cents", cfg["cash_difference_threshold_cents"]))
    return cfg


@router.get("/me/assignment")
def my_assignment(current: CurrentUser = Depends(require("me.read")), db: Session = Depends(get_db)):
    today = local_today()
    a = db.query(Assignment).filter(Assignment.operator_id == current.id, Assignment.shift_date == today).first()
    active = db.query(Shift).filter(Shift.operator_id == current.id, Shift.status == "open").first()
    assignment = None
    if a is not None:
        p = a.point
        assignment = {
            "id": str(a.id),
            "shift_date": a.shift_date.isoformat(),
            "planned_start": iso(a.planned_start),
            "planned_end": iso(a.planned_end),
            "status": a.status,
            "point": {"id": str(p.id), "name": p.name, "address": p.address, "lat": p.lat, "lng": p.lng, "geofence_radius_m": p.geofence_radius_m},
            "cart": {"id": str(a.cart.id), "code": a.cart.code},
        }
    return {
        "assignment": assignment,
        "active_shift": {"id": str(active.id), "opened_at": iso(active.opened_at), "status": active.status, "ready": active.ready, "exceptions": active.open_exceptions} if active else None,
        "catalog": build_catalog(db),
        "config": operator_config(db),
    }


@router.get("/catalog")
def catalog(_: CurrentUser = Depends(require("catalog.read")), db: Session = Depends(get_db)):
    return build_catalog(db)


@router.get("/prices/current")
def prices_current(_: CurrentUser = Depends(require("catalog.read")), db: Session = Depends(get_db)):
    version = current_price_version(db)
    if version is None:
        return {"price_version_id": None, "valid_from": None, "prices": {}}
    return {"price_version_id": str(version.id), "valid_from": iso(version.valid_from), "name": version.name, "prices": {str(k): v for k, v in price_map(db, version.id).items()}}
