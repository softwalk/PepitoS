"""Fixtures: base de datos de pruebas aislada (pepito_test) migrada con Alembic y sembrada con datos demo."""
import os
import tempfile
import uuid

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://pepito:pepito@localhost:5433/pepito_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_SCHEDULER"] = "false"
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("STORAGE_LOCAL_DIR", os.path.join(tempfile.gettempdir(), f"pepito-evidence-test-{os.getpid()}"))
os.environ.setdefault("JWT_SECRET", "secreto-de-pruebas-suficientemente-largo-32b")

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _recreate_database(url: str) -> None:
    # url: postgresql+psycopg://user:pass@host:port/dbname
    dsn = url.replace("postgresql+psycopg://", "postgresql://")
    base, dbname = dsn.rsplit("/", 1)
    with psycopg.connect(base + "/postgres", autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {dbname}")


@pytest.fixture(scope="session", autouse=True)
def database():
    _recreate_database(os.environ["DATABASE_URL"])
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
    command.upgrade(cfg, "head")
    from app.core.db import SessionLocal
    from app.seed import seed

    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def db_session():
    from app.core.db import SessionLocal

    db = SessionLocal()
    yield db
    db.close()


class Api:
    """Cliente autenticado de conveniencia."""

    def __init__(self, client: TestClient, username: str, password: str, device_id: str | None = None):
        self.client = client
        self.username = username
        self.device_id = device_id or f"dev-{username}-{uuid.uuid4().hex[:8]}"
        r = client.post("/v1/auth/login", json={"username": username, "password": password, "device_id": self.device_id, "device_name": "pytest"})
        assert r.status_code == 200, r.text
        self.token = r.json()["access_token"]
        self.user = r.json()["user"]

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json, headers=self.headers, **kw)

    def patch(self, url, json=None, **kw):
        return self.client.patch(url, json=json, headers=self.headers, **kw)

    def put(self, url, json=None, **kw):
        return self.client.put(url, json=json, headers=self.headers, **kw)


@pytest.fixture(scope="session")
def admin(client):
    return Api(client, "admin", "admin123")


@pytest.fixture(scope="session")
def ops(client):
    return Api(client, "ops", "ops123")


@pytest.fixture(scope="session")
def sup1(client):
    return Api(client, "sup1", "sup123")


@pytest.fixture(scope="session")
def op1(client):
    return Api(client, "op1", "op123")


@pytest.fixture(scope="session")
def op2(client):
    return Api(client, "op2", "op123")


@pytest.fixture(scope="session")
def op3(client):
    return Api(client, "op3", "op123")


@pytest.fixture(scope="session")
def catalog(op1):
    return op1.get("/v1/catalog").json()


_counter = {"n": 0}


@pytest.fixture
def fresh_operator(client, admin):
    """Crea un operador nuevo con punto, carrito y asignación de hoy (aislado del resto de pruebas)."""

    def _make(zone_id=None, lat=19.40, lng=-99.15, planned_start=None):
        from app.core.timeutil import local_today

        _counter["n"] += 1
        n = _counter["n"]
        tag = f"{uuid.uuid4().hex[:6]}"
        zones = admin.get("/v1/admin/zones").json()
        # Zona "Centro" (la de sup1); el catálogo de puntos autorizados crea una zona por alcaldía.
        zone_id = zone_id or next((z["id"] for z in zones if z["name"] == "Centro"), zones[0]["id"])
        point = admin.post("/v1/admin/points", json={"name": f"Punto Test {tag}", "address": "test", "lat": lat, "lng": lng, "zone_id": zone_id, "geofence_radius_m": 150}).json()
        cart = admin.post("/v1/admin/carts", json={"code": f"T-{tag}"}).json()
        user = admin.post("/v1/admin/users", json={"username": f"optest{tag}", "name": f"Operador Test {n}", "role": "operator", "password": "op123", "zone_id": zone_id}).json()
        body = {"operator_id": user["id"], "point_id": point["id"], "cart_id": cart["id"], "shift_date": local_today().isoformat()}
        if planned_start:
            body["planned_start"] = planned_start
        assignment = admin.post("/v1/admin/assignments", json=body).json()
        api = Api(client, user["username"], "op123")
        api.point = point
        api.cart = cart
        api.assignment = assignment
        return api

    return _make


def new_key() -> str:
    return str(uuid.uuid4())


def open_payload(assignment_id, **overrides):
    body = {
        "idempotency_key": new_key(),
        "assignment_id": assignment_id,
        "checklist": {"cart_secure": True, "battery_ok": True, "product_ok": True, "clean_ok": True, "pos_ok": True},
        "gps": None,
    }
    body.update(overrides)
    return body


def sale_payload(shift_id, catalog, qty=1, method="cash", pres_index=0, key=None):
    pres = catalog["presentations"][pres_index]
    return {
        "idempotency_key": key or new_key(),
        "shift_id": shift_id,
        "price_version_id": catalog["price_version_id"],
        "lines": [{"presentation_id": pres["id"], "qty": qty}],
        "payments": [{"method": method, "amount_cents": pres["price_cents"] * qty}],
        "offline_created": False,
    }
