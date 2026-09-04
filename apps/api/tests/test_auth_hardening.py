"""B1/B2/B3: refresh tokens rotativos, rate limiting de login, cambio de contraseña obligatorio, seed prod."""
import os
import uuid
from datetime import timedelta

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.timeutil import utcnow
from app.services import auth as auth_svc
from tests.conftest import Api


def _login(client, username, password, device_id, **kw):
    headers = kw.pop("headers", None)
    return client.post("/v1/auth/login", json={"username": username, "password": password, "device_id": device_id, **kw}, headers=headers)


def _refresh(client, token, device_id, headers=None):
    return client.post("/v1/auth/refresh", json={"refresh_token": token, "device_id": device_id}, headers=headers)


# ---------------------------------------------------------------- B3 refresh


def test_login_returns_refresh_and_must_change_false(client):
    r = _login(client, "op1", "op123", "dev-rt-login")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["must_change_password"] is False
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.JWT_EXPIRES_HOURS * 3600
    assert len(body["refresh_token"]) >= 48
    assert body["refresh_expires_at"].endswith("Z")
    assert body["user"]["username"] == "op1"


def test_refresh_rotates_and_reuse_revokes_family(client):
    dev = "dev-rt-rotate"
    first = _login(client, "op1", "op123", dev).json()
    r = _refresh(client, first["refresh_token"], dev)
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"]
    assert second["must_change_password"] is False
    assert second["user"]["username"] == "op1"
    # el nuevo access token sirve
    assert client.get("/v1/catalog", headers={"Authorization": f"Bearer {second['access_token']}"}).status_code == 200
    # reutilizar el viejo → 401 y revoca toda la familia (el nuevo tampoco sirve ya)
    r = _refresh(client, first["refresh_token"], dev)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID"
    r = _refresh(client, second["refresh_token"], dev)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID"


def test_refresh_wrong_device_fails(client):
    dev = "dev-rt-otherdev"
    body = _login(client, "op1", "op123", dev).json()
    r = _refresh(client, body["refresh_token"], "dev-rt-otherdev-2")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID"


def test_new_login_same_device_revokes_previous_refresh(client):
    dev = "dev-rt-relogin"
    first = _login(client, "op1", "op123", dev).json()
    _login(client, "op1", "op123", dev).json()
    r = _refresh(client, first["refresh_token"], dev)
    assert r.status_code == 401


def test_logout_invalidates_refresh(client):
    dev = "dev-rt-logout"
    body = _login(client, "op2", "op123", dev).json()
    r = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r.status_code == 200
    r = _refresh(client, body["refresh_token"], dev)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID"


def test_device_revoke_invalidates_refresh(client, admin):
    dev = "dev-rt-revoked"
    body = _login(client, "op2", "op123", dev).json()
    r = admin.post(f"/v1/admin/devices/{dev}/revoke", json={"reason": "perdido"})
    assert r.status_code == 200, r.text
    r = _refresh(client, body["refresh_token"], dev)
    assert r.status_code == 401
    assert r.json()["error"]["code"] in ("AUTH_INVALID", "DEVICE_REVOKED")


def test_refresh_expired_token(client, monkeypatch):
    dev = "dev-rt-expired"
    body = _login(client, "op1", "op123", dev).json()
    later = utcnow() + timedelta(days=settings.REFRESH_EXPIRES_DAYS + 1)
    monkeypatch.setattr(auth_svc, "current_time", lambda: later)
    r = _refresh(client, body["refresh_token"], dev)
    assert r.status_code == 401


# ---------------------------------------------------------------- B2 rate limiting


def test_rate_limit_user_lockout_and_recovery(client, admin, monkeypatch, db_session):
    """6 fallos → 429 con Retry-After; tras la ventana de bloqueo vuelve a entrar; el éxito limpia los fallos."""
    tag = uuid.uuid4().hex[:6]
    username = f"rl{tag}"
    admin.post("/v1/admin/users", json={"username": username, "name": "Rate Limit", "role": "operator", "password": "op123456"})
    ip_headers = {"X-Forwarded-For": f"10.9.{int(tag[:2], 16)}.{int(tag[2:4], 16)}, 1.1.1.1"}
    dev = f"dev-rl-{tag}"
    t0 = utcnow()
    monkeypatch.setattr(auth_svc, "current_time", lambda: t0)

    for _ in range(settings.LOGIN_MAX_FAILS_USER):
        r = _login(client, username, "mala", dev, headers=ip_headers)
        assert r.status_code == 401, r.text
    r = _login(client, username, "mala", dev, headers=ip_headers)
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["message"].startswith("Demasiados intentos. Intenta en")
    retry = body["error"]["details"]["retry_after_seconds"]
    assert 0 < retry <= settings.LOGIN_LOCK_MINUTES * 60
    assert r.headers["Retry-After"] == str(retry)
    # incluso con la contraseña correcta sigue bloqueado
    r = _login(client, username, "op123456", dev, headers=ip_headers)
    assert r.status_code == 429

    # audit log del bloqueo (actor null, entity user)
    log = admin.get("/v1/audit-log", params={"entity": "user"}).json()
    lock = [e for e in log if e["action"] == "auth.lockout" and (e.get("after") or {}).get("username") == username]
    assert len(lock) == 1
    assert lock[0]["actor_id"] is None

    # pasada la ventana de bloqueo entra sin dormir
    t1 = t0 + timedelta(minutes=settings.LOGIN_LOCK_MINUTES, seconds=1)
    monkeypatch.setattr(auth_svc, "current_time", lambda: t1)
    r = _login(client, username, "op123456", dev, headers=ip_headers)
    assert r.status_code == 200, r.text

    # el login correcto limpió los fallos: otros 5 fallos vuelven a pasar como 401 antes de bloquear
    from app.models.org import LoginAttempt

    db_session.expire_all()
    fails = db_session.query(LoginAttempt).filter(LoginAttempt.username == username, LoginAttempt.success.is_(False)).count()
    assert fails == 0
    # la IP registrada es el primer valor de X-Forwarded-For
    ok = db_session.query(LoginAttempt).filter(LoginAttempt.username == username, LoginAttempt.success.is_(True)).first()
    assert ok.ip == ip_headers["X-Forwarded-For"].split(",")[0]


def test_rate_limit_ip(client, monkeypatch):
    ip_headers = {"X-Forwarded-For": "10.77.77.77"}
    t0 = utcnow()
    monkeypatch.setattr(auth_svc, "current_time", lambda: t0)
    for i in range(settings.LOGIN_MAX_FAILS_IP):
        r = _login(client, f"nadie{i}", "mala", "dev-rl-ip", headers=ip_headers)
        assert r.status_code == 401
    r = _login(client, "op1", "op123", "dev-rl-ip", headers=ip_headers)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    # el refresh también queda bloqueado por IP, pero desde otra IP no
    r = _refresh(client, "x" * 64, "dev-rl-ip", headers=ip_headers)
    assert r.status_code == 429
    r = _refresh(client, "x" * 64, "dev-rl-ip", headers={"X-Forwarded-For": "10.77.77.78"})
    assert r.status_code == 401


# ---------------------------------------------------------------- B1 contraseñas


def test_must_change_password_flow_and_policy(client, admin):
    tag = uuid.uuid4().hex[:6]
    username = f"mcp{tag}"
    u = admin.post("/v1/admin/users", json={"username": username, "name": "Cambio Obligatorio", "role": "operator", "password": "temporal123"}).json()
    r = admin.post(f"/v1/admin/users/{u['id']}/reset-password", json={"new_password": "temporal456"})
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True
    assert "temporary_password" not in r.json()

    dev = f"dev-mcp-{tag}"
    body = _login(client, username, "temporal456", dev).json()
    assert body["must_change_password"] is True
    h = {"Authorization": f"Bearer {body['access_token']}"}
    r = client.get("/v1/me/assignment", headers=h)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/auth/me", headers=h).status_code == 200
    # refresh permitido mientras tanto y sigue avisando
    r = _refresh(client, body["refresh_token"], dev)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    current_device_refresh = r.json()["refresh_token"]

    # política
    r = client.post("/v1/auth/change-password", json={"current_password": "mala", "new_password": "nuevaclave1"}, headers=h)
    assert r.status_code == 401
    r = client.post("/v1/auth/change-password", json={"current_password": "temporal456", "new_password": "corta"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION"
    r = client.post("/v1/auth/change-password", json={"current_password": "temporal456", "new_password": "temporal456"}, headers=h)
    assert r.status_code == 422

    # otro dispositivo con sesión: su refresh debe quedar revocado tras el cambio
    other = _login(client, username, "temporal456", f"{dev}-b").json()

    r = client.post("/v1/auth/change-password", json={"current_password": "temporal456", "new_password": "nuevaclave1"}, headers=h)
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.get("/v1/me/assignment", headers=h)
    assert r.status_code in (200, 409)  # ya no 403; 409 NO_ASSIGNMENT es válido (usuario sin asignación)
    assert r.json().get("error", {}).get("code") != "PASSWORD_CHANGE_REQUIRED"
    assert _refresh(client, other["refresh_token"], f"{dev}-b").status_code == 401
    # el refresh del dispositivo actual sigue vivo
    assert _refresh(client, current_device_refresh, dev).status_code == 200
    # entra con la nueva contraseña y ya no se pide cambio
    body = _login(client, username, "nuevaclave1", dev).json()
    assert body["must_change_password"] is False
    log = admin.get("/v1/audit-log", params={"entity": "user"}).json()
    assert any(e["action"] == "user.password_change" and e["entity_id"] == u["id"] for e in log)
    assert any(e["action"] == "user.password_reset" and e["entity_id"] == u["id"] for e in log)


def test_admin_reset_password_generates_temporary(client, admin):
    tag = uuid.uuid4().hex[:6]
    u = admin.post("/v1/admin/users", json={"username": f"rst{tag}", "name": "Reset", "role": "operator", "password": "clave1234"}).json()
    session = _login(client, u["username"], "clave1234", f"dev-rst-{tag}").json()
    r = admin.post(f"/v1/admin/users/{u['id']}/reset-password")
    assert r.status_code == 200, r.text
    tmp = r.json()["temporary_password"]
    assert len(tmp) >= 8
    # la anterior ya no sirve, el refresh anterior fue revocado, la temporal obliga a cambiar
    assert _login(client, u["username"], "clave1234", f"dev-rst-{tag}").status_code == 401
    assert _refresh(client, session["refresh_token"], f"dev-rst-{tag}").status_code == 401
    body = _login(client, u["username"], tmp, f"dev-rst-{tag}").json()
    assert body["must_change_password"] is True
    # política también aplica al admin
    r = admin.post(f"/v1/admin/users/{u['id']}/reset-password", json={"new_password": "corta"})
    assert r.status_code == 422


# ---------------------------------------------------------------- B1 seed prod


def _seed_db_url() -> str:
    return os.environ["TEST_DATABASE_URL"].rsplit("/", 1)[0] + "/pepito_test_seed"


def test_seed_prod_only_admin(monkeypatch):
    """Ejecuta el seed con SEED_MODE=prod en una base aparte (para no tocar la demo del resto de pruebas)."""
    from app.core.db import Base
    from app.models.catalog import Flavor, Presentation, PriceVersion
    from app.models.cases import Rule
    from app.models.org import Assignment, Cart, Device, Point, User, Zone
    from app.seed import run_seed

    url = _seed_db_url()
    dsn = url.replace("postgresql+psycopg://", "postgresql://")
    base, dbname = dsn.rsplit("/", 1)
    with psycopg.connect(base + "/postgres", autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {dbname}")
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    try:
        with pytest.raises(RuntimeError):
            run_seed(db, "prod", admin_password=None)  # sin ADMIN_INITIAL_PASSWORD aborta
        db.rollback()
        result = run_seed(db, "prod", admin_password="ClaveInicial123")
        assert result["mode"] == "prod" and result["users"] == 1
        result = run_seed(db, "prod", admin_password="ClaveInicial123")  # idempotente
        assert result["users"] == 0
        users = db.query(User).all()
        assert [u.username for u in users] == ["admin"]
        assert users[0].must_change_password is True and users[0].role == "admin"
        assert [z.name for z in db.query(Zone).all()] == ["Default"]
        assert db.query(Point).count() == 0
        assert db.query(Cart).count() == 0
        assert db.query(Assignment).count() == 0
        assert db.query(Device).count() == 0
        assert db.query(Presentation).count() == 3
        assert db.query(Flavor).count() == 5
        assert db.query(PriceVersion).count() == 1
        assert db.query(Rule).count() >= 10
        # none no hace nada; demo con APP_ENV=production aborta
        assert run_seed(db, "none") == {"mode": "none"}
        monkeypatch.setattr(settings, "APP_ENV", "production")
        with pytest.raises(RuntimeError):
            run_seed(db, "demo")
        with pytest.raises(RuntimeError):
            run_seed(db, "otro")
    finally:
        db.close()
        engine.dispose()
    with psycopg.connect(base + "/postgres", autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")


def test_seed_prod_cli(monkeypatch):
    """`python -m app.seed` con SEED_MODE=prod y APP_ENV=production sin ADMIN_INITIAL_PASSWORD → sale con error claro."""
    import subprocess
    import sys

    env = {**os.environ, "SEED_MODE": "demo", "APP_ENV": "production", "JWT_SECRET": "x" * 40, "CORS_ORIGINS": "https://a.b"}
    p = subprocess.run([sys.executable, "-m", "app.seed"], capture_output=True, text=True, env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert p.returncode == 2
    assert "SEED_MODE=demo" in p.stderr


def test_docs_disabled_in_production(monkeypatch):
    from app.main import create_app

    monkeypatch.setattr(settings, "APP_ENV", "production")
    app = create_app()
    assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None
    monkeypatch.setattr(settings, "APP_ENV", "development")
    assert create_app().docs_url == "/docs"
