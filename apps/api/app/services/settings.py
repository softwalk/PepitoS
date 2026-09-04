"""Parámetros operativos editables (B6): tabla `settings(key, value jsonb)`.

Precedencia para parámetros que también existen en `rules.params`:
    rules.params (si la clave está definida explícitamente) > settings > default de código.
"""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import iso, utcnow
from app.models.system import Setting
from app.services import audit

# key -> (type, default, description). Los tipos: int | bool | str | float.
SETTINGS_SCHEMA: dict[str, dict[str, Any]] = {
    "cash_difference_threshold_cents": {"type": "int", "default": 2000, "min": 0, "description": "Diferencia de caja (centavos) a partir de la cual se abre un caso de revisión"},
    "cash_difference_severe_cents": {"type": "int", "default": 10000, "min": 0, "description": "Diferencia de caja (centavos) considerada grave: caso urgente + aprobación de Finanzas"},
    "cancel_window_minutes": {"type": "int", "default": 5, "min": 0, "description": "Minutos en que el operador puede cancelar su propia venta"},
    "gps_interval_seconds": {"type": "int", "default": 120, "min": 10, "description": "Intervalo de envío de GPS desde la PWA (segundos)"},
    "photo_sampling_pct": {"type": "int", "default": 10, "min": 0, "max": 100, "description": "Porcentaje de aperturas a las que se les exige foto (muestreo determinístico por asignación)"},
    "evidence_retention_days": {"type": "int", "default": 180, "min": 1, "description": "Días que se conservan las evidencias (fotos) antes de purgarlas del storage"},
    "gps_retention_days": {"type": "int", "default": 90, "min": 1, "description": "Días que se conservan los gps_pings"},
    "daily_sales_target_default_cents": {"type": "int", "default": 234000, "min": 0, "description": "Meta diaria de ventas por punto (centavos) cuando el punto no tiene una propia"},
    "shift_reopen_window_hours": {"type": "int", "default": 12, "min": 1, "max": 48, "description": "Horas tras el cierre en que un administrador aún puede continuar (reabrir) un turno terminado; además debe ser del día en curso"},
    "inventory_count_tolerance_units": {"type": "int", "default": 3, "min": 0, "description": "Diferencia (unidades) entre conteo y teórico a partir de la cual se abre caso de inventario"},
}

_TYPES = {"int": int, "bool": bool, "str": str, "float": (int, float)}


def _validate(key: str, value: Any) -> Any:
    spec = SETTINGS_SCHEMA.get(key)
    if spec is None:
        raise ApiError("NOT_FOUND", "Parámetro no encontrado", details={"key": key, "known": sorted(SETTINGS_SCHEMA)})
    t = spec["type"]
    py = _TYPES[t]
    if isinstance(value, bool) and t != "bool":
        raise ApiError("VALIDATION", f"{key} debe ser {t}", details={"key": key, "type": t, "value": value})
    if not isinstance(value, py):
        raise ApiError("VALIDATION", f"{key} debe ser {t}", details={"key": key, "type": t, "value": value})
    if t in ("int", "float"):
        if "min" in spec and value < spec["min"]:
            raise ApiError("VALIDATION", f"{key} debe ser ≥ {spec['min']}", details={"key": key, "min": spec["min"], "value": value})
        if "max" in spec and value > spec["max"]:
            raise ApiError("VALIDATION", f"{key} debe ser ≤ {spec['max']}", details={"key": key, "max": spec["max"], "value": value})
    return value


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    if row is not None and row.value is not None:
        return row.value
    if default is not None:
        return default
    spec = SETTINGS_SCHEMA.get(key)
    return spec["default"] if spec else None


def get_int(db: Session, key: str, default: int | None = None) -> int:
    return int(get_setting(db, key, default))


def get_all(db: Session) -> dict[str, Any]:
    values = {k: spec["default"] for k, spec in SETTINGS_SCHEMA.items()}
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def list_settings(db: Session) -> list[dict]:
    rows = {r.key: r for r in db.query(Setting).all()}
    out = []
    for key, spec in SETTINGS_SCHEMA.items():
        row = rows.get(key)
        out.append({
            "key": key,
            "value": row.value if row is not None else spec["default"],
            "type": spec["type"],
            "default": spec["default"],
            "description": spec["description"],
            "updated_at": iso(row.updated_at) if row is not None else None,
            "updated_by": str(row.updated_by) if row is not None and row.updated_by else None,
        })
    return out


def set_setting(db: Session, key: str, value: Any, actor: uuid.UUID | None, ip: str | None = None) -> dict:
    value = _validate(key, value)
    row = db.get(Setting, key)
    before = row.value if row is not None else None
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    row.updated_at = utcnow()
    row.updated_by = actor
    audit.log(db, actor_id=actor, action="settings.update", entity="setting", entity_id=None, before={"key": key, "value": before}, after={"key": key, "value": value}, reason=f"setting:{key}", ip=ip)
    db.flush()
    spec = SETTINGS_SCHEMA[key]
    return {"key": key, "value": row.value, "type": spec["type"], "default": spec["default"], "description": spec["description"], "updated_at": iso(row.updated_at), "updated_by": str(actor) if actor else None}


def ensure_defaults(db: Session) -> int:
    """Inserta las claves faltantes con su default (seed demo/prod). Idempotente."""
    n = 0
    existing = {r.key for r in db.query(Setting).all()}
    for key, spec in SETTINGS_SCHEMA.items():
        if key not in existing:
            db.add(Setting(key=key, value=spec["default"], updated_at=utcnow()))
            n += 1
    db.flush()
    return n


def cash_thresholds(db: Session) -> tuple[int, int]:
    """(threshold_cents, severe_cents) con precedencia rules.params > settings > default."""
    from app.models.cases import Rule

    rule = db.get(Rule, "cash_difference")
    params = (rule.params or {}) if rule is not None else {}
    threshold = int(params["threshold_cents"]) if "threshold_cents" in params else get_int(db, "cash_difference_threshold_cents")
    severe = int(params["severe_cents"]) if "severe_cents" in params else get_int(db, "cash_difference_severe_cents")
    return threshold, severe


def inventory_tolerance(db: Session) -> int:
    """Unidades de tolerancia en conteos: rules.inventory_inconsistent.params.units > settings > default."""
    from app.models.cases import Rule

    rule = db.get(Rule, "inventory_inconsistent")
    params = (rule.params or {}) if rule is not None else {}
    if "units" in params:
        return int(params["units"])
    return get_int(db, "inventory_count_tolerance_units")
