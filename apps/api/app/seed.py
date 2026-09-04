"""Seed de datos. Idempotente: se puede ejecutar varias veces.

    SEED_MODE=demo python -m app.seed   # (default) usuarios demo §10, puntos, carritos, asignaciones, inventario
    SEED_MODE=prod python -m app.seed   # zona "Default", usuario admin (ADMIN_INITIAL_PASSWORD, must_change_password)
                                        # y catálogo (presentaciones, sabores, precios, reglas, checklists); sin puntos
    SEED_MODE=none python -m app.seed   # no hace nada

Con APP_ENV=production y SEED_MODE=demo aborta.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.timeutil import local_dt, local_today, utcnow
from app.models.cases import Rule
from app.models.catalog import DailyTarget, Flavor, Presentation, PriceItem, PriceVersion, Product
from app.models.inventory import InventoryMovement, Lot, Warehouse
from app.models.ops import Checklist
from app.models.org import Assignment, Asset, Cart, Point, User, Zone
from app.services.cases import DEFAULT_RULE_PARAMS
from app.services.inventory import add_movement
from app.services.settings import ensure_defaults as ensure_settings

log = logging.getLogger("pepito.seed")

USERS = [
    ("admin", "Administrador", "admin", "admin123", None),
    ("ops", "Operaciones", "ops", "ops123", None),
    ("finanzas", "Finanzas", "finance", "fin123", None),
    ("sup1", "Supervisor Centro", "supervisor", "sup123", "Centro"),
    ("op1", "Operador Uno", "operator", "op123", "Centro"),
    ("op2", "Operador Dos", "operator", "op123", "Centro"),
    ("op3", "Operador Tres", "operator", "op123", "Centro"),
]
POINTS = [
    ("Metro Insurgentes", "Glorieta de Insurgentes, Roma Norte, CDMX", 19.4235, -99.1630),
    ("Parque México", "Av. México s/n, Hipódromo, CDMX", 19.4120, -99.1700),
    ("Alameda Central", "Av. Juárez s/n, Centro Histórico, CDMX", 19.4355, -99.1435),
]
PRESENTATIONS = [("Pepitas 50 g", 50, 2500, 1), ("Pepitas 75 g", 75, 3500, 2), ("Pepitas 100 g", 100, 4500, 3)]
FLAVORS = ["Natural", "Limón", "Chile", "Enchilado", "Salado"]
RULES = [
    ("no_open", "Punto sin abrir", "urgent"),
    ("out_of_geofence", "Fuera de geocerca", "urgent"),
    ("low_sales_trajectory", "Ventas bajo trayectoria", "review"),
    ("high_waste", "Merma alta", "review"),
    ("cash_difference", "Diferencia de caja", "review"),
    ("inventory_inconsistent", "Inventario inconsistente", "review"),
    ("low_battery", "Batería baja", "review"),
    ("anomalous_cancellations", "Cancelaciones anómalas", "review"),
    ("sync_stale", "Sin sincronizar", "review"),
    ("maintenance_overdue", "Mantenimiento vencido", "review"),
    ("stock_critical", "Stock crítico", "review"),
]
CHECKLIST_OPEN = [("cart_secure", "Carrito asegurado", True), ("battery_ok", "Batería cargada", True), ("product_ok", "Producto suficiente y en buen estado", True), ("clean_ok", "Carrito limpio", False), ("pos_ok", "Terminal POS funciona", True)]
CHECKLIST_CLOSE = [("off_ok", "Equipo apagado", False), ("clean_ok", "Carrito limpio", False), ("secured_ok", "Carrito asegurado", True), ("stored_ok", "Producto guardado", False), ("charging_ok", "Batería cargando", False)]
ASSET_TYPES = [("battery", 30), ("charger", 90), ("pos", 180)]
INITIAL_STOCK_UNITS = 40
SEED_MODES = ("demo", "prod", "none")


def _seed_catalog(db: Session, created_by) -> list:
    """Producto, presentaciones, sabores, versión de precio v1, reglas y checklists (común a demo y prod)."""
    product = db.query(Product).filter(Product.name == "Pepitas").first()
    if product is None:
        product = Product(name="Pepitas", description="Semillas de calabaza tostadas")
        db.add(product)
        db.flush()
    presentations = []
    for name, grams, _, sort in PRESENTATIONS:
        p = db.query(Presentation).filter(Presentation.name == name).first()
        if p is None:
            p = Presentation(name=name, grams=grams, sort=sort, product_id=product.id)
            db.add(p)
        presentations.append(p)
    for i, name in enumerate(FLAVORS, start=1):
        if db.query(Flavor).filter(Flavor.name == name).first() is None:
            db.add(Flavor(name=name, sort=i))
    db.flush()

    version = db.query(PriceVersion).filter(PriceVersion.name == "v1").first()
    if version is None:
        version = PriceVersion(name="v1", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), created_by=created_by)
        version.items = [PriceItem(presentation_id=p.id, amount_cents=amt) for p, (_, _, amt, _) in zip(presentations, PRESENTATIONS)]
        db.add(version)
        db.flush()

    for key, name, severity in RULES:
        r = db.get(Rule, key)
        if r is None:
            db.add(Rule(key=key, name=name, enabled=True, params=DEFAULT_RULE_PARAMS[key], severity=severity, updated_at=utcnow()))

    ensure_settings(db)  # parámetros operativos (B6), mismas claves en demo y prod

    # Puntos autorizados (catálogo de 100 ubicaciones CDMX): mismas altas en demo y prod; idempotente.
    from app.services.points_import import import_authorized_points

    import_authorized_points(db, actor_id=created_by)

    if db.query(Checklist).count() == 0:
        for i, (key, label, critical) in enumerate(CHECKLIST_OPEN):
            db.add(Checklist(kind="open", key=key, label=label, critical=critical, sort=i))
        for i, (key, label, critical) in enumerate(CHECKLIST_CLOSE):
            db.add(Checklist(kind="close", key=key, label=label, critical=critical, sort=i))
    db.flush()
    return presentations


def seed_prod(db: Session, admin_password: str | None = None) -> dict:
    """Seed de producción: zona "Default", usuario `admin` con contraseña inicial obligatoria y
    `must_change_password=true`, catálogo/reglas/checklists. SIN puntos, carritos, operadores ni asignaciones."""
    admin_password = admin_password or settings.ADMIN_INITIAL_PASSWORD
    created = {"users": 0, "zones": 0}
    zone = db.query(Zone).filter(Zone.name == "Default").first()
    if zone is None:
        zone = Zone(name="Default")
        db.add(zone)
        db.flush()
        created["zones"] += 1
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        if not admin_password:
            raise RuntimeError("SEED_MODE=prod requiere ADMIN_INITIAL_PASSWORD para crear el usuario admin")
        if len(admin_password) < settings.PASSWORD_MIN_LENGTH:
            raise RuntimeError(f"ADMIN_INITIAL_PASSWORD debe tener al menos {settings.PASSWORD_MIN_LENGTH} caracteres")
        admin = User(username="admin", name="Administrador", role="admin", password_hash=hash_password(admin_password), must_change_password=True)
        db.add(admin)
        db.flush()
        created["users"] += 1
    _seed_catalog(db, admin.id)
    db.commit()
    return created


def seed(db: Session, today=None) -> dict:
    """Seed demo (§10)."""
    today = today or local_today()
    created = {"users": 0, "points": 0, "assignments": 0, "movements": 0}

    zone = db.query(Zone).filter(Zone.name == "Centro").first()
    if zone is None:
        zone = Zone(name="Centro")
        db.add(zone)
        db.flush()

    users = {}
    for username, name, role, password, zone_name in USERS:
        u = db.query(User).filter(User.username == username).first()
        if u is None:
            u = User(username=username, name=name, role=role, password_hash=hash_password(password), zone_id=zone.id if zone_name else None)
            db.add(u)
            created["users"] += 1
        users[username] = u
    db.flush()

    points = []
    for name, address, lat, lng in POINTS:
        p = db.query(Point).filter(Point.name == name).first()
        if p is None:
            p = Point(name=name, address=address, lat=lat, lng=lng, geofence_radius_m=150, zone_id=zone.id, open_time="08:00", close_time="18:00", daily_target_cents=234000, daily_target_tx=60)
            db.add(p)
            created["points"] += 1
        points.append(p)
    db.flush()

    carts = []
    for i in range(1, 4):
        code = f"C-{i:03d}"
        c = db.query(Cart).filter(Cart.code == code).first()
        if c is None:
            c = Cart(code=code, description=f"Carrito {i}")
            db.add(c)
        carts.append(c)
    db.flush()

    presentations = _seed_catalog(db, users["admin"].id)

    for cart in carts:
        for asset_type, interval in ASSET_TYPES:
            code = f"{cart.code}-{asset_type.upper()}"
            if db.query(Asset).filter(Asset.code == code).first() is None:
                db.add(Asset(code=code, asset_type=asset_type, cart_id=cart.id, status="active", maintenance_interval_days=interval, last_maintenance_at=utcnow() - timedelta(days=5), next_maintenance_at=utcnow() + timedelta(days=interval - 5)))

    warehouse = db.query(Warehouse).filter(Warehouse.name == "Almacén Central").first()
    if warehouse is None:
        warehouse = Warehouse(name="Almacén Central", address="Col. Doctores, CDMX")
        db.add(warehouse)
        db.flush()
    lot = db.query(Lot).filter(Lot.code == "L-2026-001").first()
    if lot is None:
        lot = Lot(code="L-2026-001", warehouse_id=warehouse.id, produced_at=utcnow() - timedelta(days=10), expires_at=utcnow() + timedelta(days=80))
        db.add(lot)
        db.flush()

    # Asignaciones de hoy op1..op3 (08:00–18:00 local) y metas diarias
    for i, username in enumerate(["op1", "op2", "op3"]):
        op = users[username]
        if db.query(Assignment).filter(Assignment.operator_id == op.id, Assignment.shift_date == today).first() is None:
            db.add(Assignment(operator_id=op.id, point_id=points[i].id, cart_id=carts[i].id, shift_date=today, planned_start=local_dt(today, "08:00"), planned_end=local_dt(today, "18:00")))
            created["assignments"] += 1
    for p in points:
        if db.query(DailyTarget).filter(DailyTarget.point_id == p.id, DailyTarget.target_date == today).first() is None:
            db.add(DailyTarget(point_id=p.id, target_date=today, target_cents=234000, target_tx=60))
    db.flush()

    # Inventario inicial por punto (recepción desde almacén) si el punto no tiene movimientos
    for p in points:
        if db.query(InventoryMovement).filter(InventoryMovement.point_id == p.id).count() == 0:
            for pres in presentations:
                add_movement(db, point_id=p.id, presentation_id=pres.id, qty=INITIAL_STOCK_UNITS, movement_type="receipt", actor_id=users["ops"].id, lot_id=lot.id, ref_entity="seed", note="Inventario inicial demo", emit_event=False)
                created["movements"] += 1
    db.commit()
    return created


def run_seed(db: Session, mode: str, admin_password: str | None = None) -> dict:
    mode = (mode or "demo").strip().lower()
    if mode not in SEED_MODES:
        raise RuntimeError(f"SEED_MODE inválido: {mode!r} (usa demo | prod | none)")
    if mode == "none":
        return {"mode": "none"}
    if mode == "demo" and settings.is_production:
        raise RuntimeError("SEED_MODE=demo está prohibido con APP_ENV=production: usa SEED_MODE=prod (o none)")
    if mode == "prod":
        return {"mode": "prod", **seed_prod(db, admin_password)}
    return {"mode": "demo", **seed(db)}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # Compatibilidad: SEED=true (Dockerfile antiguo) equivale a SEED_MODE=demo cuando SEED_MODE no viene en el entorno.
    mode = os.environ.get("SEED_MODE") or ("demo" if os.environ.get("SEED", "").lower() == "true" else settings.SEED_MODE)
    db = SessionLocal()
    try:
        try:
            result = run_seed(db, mode)
        except RuntimeError as e:
            log.error("Seed abortado: %s", e)
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)
        log.info("Seed listo: %s", result)
        print(f"Seed listo: {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
