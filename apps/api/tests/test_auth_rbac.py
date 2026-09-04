"""Login, asignación, RBAC, revocación de dispositivo y logout."""
from tests.conftest import Api


def test_login_and_assignment(client, op1):
    assert op1.user["role"] == "operator"
    r = op1.get("/v1/me/assignment")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assignment"] is not None
    assert body["assignment"]["point"]["name"] == "Metro Insurgentes"
    assert body["assignment"]["cart"]["code"] == "C-001"
    assert body["catalog"]["price_version_id"]
    assert len(body["catalog"]["presentations"]) == 3
    assert body["catalog"]["presentations"][0]["price_cents"] == 2500
    assert body["config"]["cancel_window_minutes"] == 5


def test_login_invalid(client):
    r = client.post("/v1/auth/login", json={"username": "op1", "password": "mala", "device_id": "dev-x-1"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID"


def test_error_format_validation(client, op1):
    r = op1.post("/v1/sales", json={"idempotency_key": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION"
    assert "errors" in body["error"]["details"]


def test_rbac_operator_cannot_see_control_tower(op1, sup1, ops):
    r = op1.get("/v1/control-tower/summary")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    r = op1.get("/v1/rules")
    assert r.status_code == 403
    r = sup1.get("/v1/supervisor/exceptions")
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) >= {"urgent", "review", "normal"}
    r = sup1.get("/v1/control-tower/summary")
    assert r.status_code == 403
    r = ops.get("/v1/control-tower/summary")
    assert r.status_code == 200


def test_device_revoke(client, admin):
    api = Api(client, "op2", "op123", device_id="dev-revocable-1")
    assert api.get("/v1/catalog").status_code == 200
    r = admin.post("/v1/admin/devices/dev-revocable-1/revoke", json={"reason": "Dispositivo perdido"})
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] is True
    r = api.get("/v1/catalog")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "DEVICE_REVOKED"
    # login con dispositivo revocado también falla
    r = client.post("/v1/auth/login", json={"username": "op2", "password": "op123", "device_id": "dev-revocable-1"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "DEVICE_REVOKED"
    log = admin.get("/v1/audit-log", params={"entity": "device"}).json()
    assert any(e["action"] == "device.revoke" for e in log)


def test_logout_revokes_token(client):
    api = Api(client, "op3", "op123")
    assert api.get("/v1/catalog").status_code == 200
    assert api.post("/v1/auth/logout").status_code == 200
    r = api.get("/v1/catalog")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID"
