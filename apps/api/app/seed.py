"""Datos demo (CONTRATOS.md §10). Idempotente: se puede ejecutar varias veces.

    python -m app.seed
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

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


def seed(db: Session, today=None) -> dict:
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
        version = PriceVersion(name="v1", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), created_by=users["admin"].id)
        version.items = [PriceItem(presentation_id=p.id, amount_cents=amt) for p, (_, _, amt, _) in zip(presentations, PRESENTATIONS)]
        db.add(version)
        db.flush()

    for key, name, severity in RULES:
        r = db.get(Rule, key)
        if r is None:
            db.add(Rule(key=key, name=name, enabled=True, params=DEFAULT_RULE_PARAMS[key], severity=severity, updated_at=utcnow()))

    if db.query(Checklist).count() == 0:
        for i, (key, label, critical) in enumerate(CHECKLIST_OPEN):
            db.add(Checklist(kind="open", key=key, label=label, critical=critical, sort=i))
        for i, (key, label, critical) in enumerate(CHECKLIST_CLOSE):
            db.add(Checklist(kind="close", key=key, label=label, critical=critical, sort=i))

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


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = seed(db)
        log.info("Seed listo: %s", result)
        print(f"Seed listo: {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
