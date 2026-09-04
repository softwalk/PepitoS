"""Asignación del operador, catálogo y precios vigentes."""
import hashlib

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.timeutil import iso, local_today
from app.models.catalog import Flavor, Presentation
from app.models.ops import Checklist, Shift
from app.models.org import User, Assignment
from app.services import settings as settings_svc
from app.services.ranking import serialize_ranking
from app.services.sales import current_price_version, price_map

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


def require_open_photo(assignment_id, sampling_pct: int) -> bool:
    """Muestreo determinístico: hash del assignment_id → [0,100). Estable durante el día para esa asignación."""
    pct = max(0, min(100, int(sampling_pct)))
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    bucket = int(hashlib.sha256(str(assignment_id).encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < pct


def operator_config(db: Session, assignment=None) -> dict:
    """Parámetros del operador leídos de `settings` (B6). El umbral de caja respeta rules.params > settings."""
    threshold, severe = settings_svc.cash_thresholds(db)
    sampling = settings_svc.get_int(db, "photo_sampling_pct")
    return {
        "cash_difference_threshold_cents": threshold,
        "cash_difference_severe_cents": severe,
        "cancel_window_minutes": settings_svc.get_int(db, "cancel_window_minutes"),
        "gps_interval_seconds": settings_svc.get_int(db, "gps_interval_seconds"),
        "photo_sampling_pct": sampling,
        "require_open_photo": require_open_photo(assignment.id, sampling) if assignment is not None else False,
        "evidence_max_bytes": settings.EVIDENCE_MAX_BYTES,
        "open_max_distance_m": settings_svc.get_int(db, "open_max_distance_m"),
    }


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
            "point": {"id": str(p.id), "name": p.display_name, "score": p.score, "address": p.address, "lat": p.lat, "lng": p.lng, "geofence_radius_m": p.geofence_radius_m, "geo_verified": bool(p.geo_verified)},
            "cart": {"id": str(a.cart.id), "code": a.cart.code},
        }
    total_ops = db.query(User).filter(User.role == "operator", User.is_active.is_(True)).count()
    return {
        "assignment": assignment,
        "ranking": serialize_ranking(current.user, total_ops),
        "active_shift": {"id": str(active.id), "opened_at": iso(active.opened_at), "status": active.status, "ready": active.ready, "exceptions": active.open_exceptions} if active else None,
        "catalog": build_catalog(db),
        "config": operator_config(db, a),
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
