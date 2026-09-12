"""Caja (fondo/salidas), devoluciones, SLA, notificaciones (bitácora + cifrado Web Push), muestreo de ruta, costos y
margen en expansión, CSV, caso manual, MFA TOTP, rate limit y forecast por perfil horario."""
import uuid

import pyotp

from tests.conftest import Api, new_key, open_payload, sale_payload


def _resolve(admin, *case_ids):
    """Cierra los casos creados por la prueba para no alterar el briefing (top 8) de otras pruebas."""
    for cid in case_ids:
        if cid:
            admin.patch(f"/v1/cases/{cid}", json={"status": "resolved", "resolution": "prueba"})


def test_cash_opening_and_movements_change_expected(fresh_operator, catalog, admin):
    a = fresh_operator()
    sid = a.post("/v1/shifts/open", json={**open_payload(a.assignment["id"]), "opening_cents": 20000}).json()["shift_id"]
    a.post("/v1/sales", json=sale_payload(sid, catalog, pres_index=2))  # $40 efectivo
    exp = a.get(f"/v1/shifts/{sid}/expected").json()
    assert exp["opening_cents"] == 20000 and exp["cash_sales_cents"] == 4000 and exp["cash_expected_cents"] == 24000
    r = a.post(f"/v1/shifts/{sid}/cash-movements", json={"idempotency_key": new_key(), "kind": "expense", "amount_cents": 3000, "reason": "Hielo"})
    assert r.status_code == 201 and r.json()["expected"]["cash_expected_cents"] == 21000
    # Retiro grande → caso de revisión ligado al movimiento
    assert a.post(f"/v1/shifts/{sid}/cash-movements", json={"idempotency_key": new_key(), "kind": "withdrawal", "amount_cents": 99999, "reason": "más de lo que hay"}).status_code == 409
    r = a.post(f"/v1/shifts/{sid}/cash-movements", json={"idempotency_key": new_key(), "kind": "withdrawal", "amount_cents": 20000, "reason": "Entrega parcial al supervisor"})
    assert r.status_code == 201 and r.json()["case_id"]
    _resolve(admin, r.json()["case_id"])
    rows = a.get(f"/v1/shifts/{sid}/cash-movements").json()["rows"]
    assert len(rows) == 2 and rows[1]["signed_cents"] == -20000
    # Cierre: la diferencia se calcula contra el esperado con fondo y salidas
    exp = a.get(f"/v1/shifts/{sid}/expected").json()
    assert exp["cash_expected_cents"] == 20000 + 4000 - 3000 - 20000
    r = a.post(f"/v1/shifts/{sid}/close", json={"idempotency_key": new_key(), "cash_counted_cents": exp["cash_expected_cents"], "product_counts": exp["product_expected"]})
    assert r.status_code == 200 and r.json()["difference_cents"] == 0
    # Otro operador no puede registrar movimientos en ese turno
    b = fresh_operator()
    assert b.post(f"/v1/shifts/{sid}/cash-movements", json={"idempotency_key": new_key(), "kind": "expense", "amount_cents": 100, "reason": "gasto"}).status_code == 403
    b.post("/v1/shifts/open", json=open_payload(b.assignment["id"]))  # evita un caso no_open en pruebas posteriores


def test_return_outside_cancel_window_creates_review_case(fresh_operator, catalog, admin, db_session):
    from datetime import timedelta

    from app.models.sales import Sale

    a = fresh_operator()
    sid = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    sale_id = a.post("/v1/sales", json=sale_payload(sid, catalog)).json()["sale_id"]
    s = db_session.get(Sale, uuid.UUID(sale_id))
    s.created_at = s.created_at - timedelta(minutes=30)
    db_session.commit()
    r = a.post(f"/v1/sales/{sale_id}/cancel", json={"idempotency_key": new_key(), "reason_code": "customer", "note": "tarde"})
    assert r.status_code == 403 and "devolución" in r.json()["error"]["message"]
    r = a.post(f"/v1/sales/{sale_id}/cancel", json={"idempotency_key": new_key(), "reason_code": "return", "note": "cliente regresó producto"})
    assert r.status_code in (200, 201), r.text
    cases = admin.get("/v1/cases", params={"status": "open"}).json()
    ret = [c for c in cases if c.get("rule_key") == "sale_return" and c["point"]["id"] == a.point["id"]]
    assert ret and ret[0]["severity"] == "review"
    assert a.get(f"/v1/shifts/{sid}/expected").json()["cash_expected_cents"] == 0
    _resolve(admin, ret[0]["id"])


def test_sla_escalation_and_notification_log(fresh_operator, admin, ops, db_session):
    from datetime import timedelta

    from app.models.cases import Case
    from app.services.notifications import notify_sla_breach
    from app.services.sla import check_sla

    a = fresh_operator()
    sid = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    r = a.post("/v1/help-cases", json={"idempotency_key": new_key(), "shift_id": sid, "category": "cart", "note": "rueda rota", "tags": ["rain"]})
    case_id = r.json()["case_id"]
    c = db_session.get(Case, uuid.UUID(case_id))
    assert c.payload["tags"] == ["rain"]
    detail = admin.get(f"/v1/cases/{case_id}").json()
    assert detail["sla"]["minutes"] in (15, 240) and detail["sla"]["taken"] is False and detail["sla"]["breached"] is False
    c.opened_at = c.opened_at - timedelta(hours=5)
    db_session.commit()
    for esc in check_sla(db_session):
        notify_sla_breach(db_session, esc)
    db_session.commit()
    db_session.expire_all()
    c = db_session.get(Case, uuid.UUID(case_id))
    assert c.payload.get("sla_breached_at") and c.severity == "urgent"
    detail = admin.get(f"/v1/cases/{case_id}").json()
    assert detail["sla"]["breached"] is True
    log = admin.get("/v1/notifications/log", params={"limit": 200}).json()
    assert any("SLA vencido" in x["title"] for x in log)
    assert any(x["title"].startswith(("🔴", "🟡")) for x in log)  # aviso al crear el caso (canal log: sin claves)
    cfg = ops.get("/v1/notifications/config").json()
    assert cfg["push_enabled"] is False and "prefs" in cfg
    assert ops.post("/v1/notifications/test").status_code == 200
    _resolve(admin, case_id)


def test_webpush_encrypt_roundtrip_and_subscription_api(ops):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from app.services import webpush

    ua = ec.generate_private_key(ec.SECP256R1())
    p256dh = webpush.b64u_encode(ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    auth = webpush.b64u_encode(b"0123456789abcdef")
    body = webpush.encrypt(webpush.Subscription("https://push.example/x", p256dh, auth), b'{"title":"hola"}')
    assert webpush.decrypt(body, ua, b"0123456789abcdef") == b'{"title":"hola"}'
    priv, pub = webpush.generate_keys()
    assert len(webpush.b64u_decode(priv)) == 32 and len(webpush.b64u_decode(pub)) == 65
    r = ops.post("/v1/notifications/subscriptions", json={"endpoint": "https://push.example/sub-1", "keys": {"p256dh": p256dh, "auth": auth}})
    assert r.status_code == 201
    assert ops.get("/v1/notifications/config").json()["subscriptions"] == 1
    assert ops.put("/v1/notifications/prefs", json={"whatsapp": False, "phone": "+5215512345678"}).json()["prefs"]["whatsapp"] is False
    ops.client.delete("/v1/notifications/subscriptions", params={"endpoint": "https://push.example/sub-1"}, headers=ops.headers)
    assert ops.get("/v1/notifications/config").json()["subscriptions"] == 0


def test_route_sampling_deterministic(sup1, admin, fresh_operator):
    f = fresh_operator()  # punto de Centro con asignación hoy y sin casos
    admin.put("/v1/admin/settings/route_sampling_normal_pct", json={"value": 100})
    r1 = sup1.get("/v1/supervisor/route").json()
    r2 = sup1.get("/v1/supervisor/route").json()
    sampled = [s for s in r1["stops"] if s.get("sampling")]
    assert r1["sampling_pct"] == 100 and sampled and [s["point"]["id"] for s in sampled] == [s["point"]["id"] for s in r2["stops"] if s.get("sampling")]
    admin.put("/v1/admin/settings/route_sampling_normal_pct", json={"value": 0})
    assert not [s for s in sup1.get("/v1/supervisor/route").json()["stops"] if s.get("sampling")]
    f.post("/v1/shifts/open", json=open_payload(f.assignment["id"]))


def test_point_costs_and_expansion_margin(fresh_operator, catalog, admin):
    a = fresh_operator()
    sid = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    for _ in range(2):
        a.post("/v1/sales", json=sale_payload(sid, catalog, pres_index=2))  # 2 × 100 g × $40 = $80, 200 g
    r = admin.post(f"/v1/admin/points/{a.point['id']}/costs", json={"valid_from": "2026-01-01", "rent_month_cents": 300000, "setup_cents": 1500000, "note": "renta local"})
    assert r.status_code == 201 and r.json()["monthly_cents"] == 300000
    assert len(admin.get(f"/v1/admin/points/{a.point['id']}/costs").json()) == 1
    body = admin.get("/v1/reports/bi/expansion", params={"period": "today"}).json()
    row = next(x for x in next(t for t in body["tables"] if t["key"] == "verdicts")["rows"] if x["point_id"] == a.point["id"])
    # materia prima 0.2 kg × $70 = $14; fijo 300000/30 = $100/día; margen = 80 − 14 − 100 = −$34 → sin payback
    assert row["raw_cost_cents"] == 1400 and row["fixed_cost_cents"] == 10000 and row["margin_cents"] == -3400
    assert row["payback_months"] is None
    assert any(k["key"] == "with_costs" and k["value"] >= 1 for k in body["kpis"])


def test_csv_export_and_manual_case(admin, sup1):
    r = admin.get("/v1/reports/bi/points/export.csv", params={"period": "month", "table": "ranking"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "Ranking completo" in r.text
    assert admin.get("/v1/reports/bi/points/export.csv", params={"table": "nope"}).status_code == 404
    log = admin.get("/v1/audit-log", params={"entity": "report", "limit": 3}).json()
    assert log[0]["action"] == "report.export"
    zones = admin.get("/v1/admin/zones").json()
    other = next(z for z in zones if z["name"] != "Centro")
    pt = admin.post("/v1/admin/points", json={"name": f"Pt fuera {uuid.uuid4().hex[:5]}", "address": "x", "lat": 19.5, "lng": -99.2, "zone_id": other["id"], "geofence_radius_m": 150}).json()
    assert sup1.post("/v1/cases", json={"title": "Revisar precios", "point_id": pt["id"]}).status_code == 403
    r = admin.post("/v1/cases", json={"title": "Evaluar reubicación", "point_id": pt["id"], "severity": "review", "action": "Visitar y medir afluencia", "action_due_date": "2026-12-31", "source_ref": "report:expansion"})
    assert r.status_code == 201 and r.json()["actions"][0]["description"] == "Visitar y medir afluencia"
    _resolve(admin, r.json()["id"])
    send = admin.post("/v1/reports/bi/executive/send", json={"to": [], "period": "yesterday"})
    assert send.status_code == 200 and send.json()["channel"] == "log" and send.json().get("path")


def test_mfa_totp_login_flow(client, admin):
    r = admin.post("/v1/auth/mfa/setup")
    assert r.status_code == 200 and r.json()["otpauth_uri"].startswith("otpauth://totp/")
    secret = r.json()["secret"]
    assert admin.post("/v1/auth/mfa/enable", json={"code": "000000"}).status_code == 401
    r = admin.post("/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200 and r.json()["enabled"] is True
    # Login ahora devuelve reto MFA; el mfa_token no sirve como access token
    r = client.post("/v1/auth/login", json={"username": "admin", "password": "admin123", "device_id": "dev-mfa-test"})
    assert r.status_code == 200 and r.json()["mfa_required"] is True
    tok = r.json()["mfa_token"]
    assert client.get("/v1/me/assignment", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert client.post("/v1/auth/mfa/verify", json={"mfa_token": tok, "code": "123456", "device_id": "dev-mfa-test"}).status_code == 401
    r = client.post("/v1/auth/mfa/verify", json={"mfa_token": tok, "code": pyotp.TOTP(secret).now(), "device_id": "dev-mfa-test"})
    assert r.status_code == 200 and r.json()["access_token"]
    api2 = Api.__new__(Api)
    api2.client, api2.token, api2.username, api2.device_id, api2.user = client, r.json()["access_token"], "admin", "dev-mfa-test", r.json()["user"]
    assert api2.get("/v1/auth/mfa").json()["enabled"] is True
    # Desactivar con código; la sesión original sigue funcionando
    assert api2.post("/v1/auth/mfa/disable", json={"code": pyotp.TOTP(secret).now()}).json()["enabled"] is False
    r = client.post("/v1/auth/login", json={"username": "admin", "password": "admin123", "device_id": "dev-mfa-test"})
    assert r.status_code == 200 and "access_token" in r.json()


def test_rate_limit_middleware():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.ratelimit import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_minute=3)

    @app.get("/v1/x")
    def x():
        return {"ok": True}

    c = TestClient(app)
    assert [c.get("/v1/x").status_code for _ in range(3)] == [200, 200, 200]
    r = c.get("/v1/x")
    assert r.status_code == 429 and r.headers["retry-after"] and r.json()["error"]["code"] == "RATE_LIMITED"


def test_hourly_profile_forecast(db_session):
    from app.core.timeutil import utcnow
    from app.services.control_tower import hourly_profiles, summary

    prof = hourly_profiles(db_session, utcnow())
    assert isinstance(prof, dict)
    s = summary(db_session, utcnow().date())
    assert s["totals"]["forecast_close_cents"] >= s["totals"]["sales_cents"]


def test_inventory_kg_and_count_receipt_photos(fresh_operator, catalog, admin):
    from tests.test_gate_6_20 import PNG_DATA_URL

    a = fresh_operator()
    sid = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    pres = sorted(catalog["presentations"], key=lambda p: p["sort"])
    # Recepción con foto: 4 × 50 g + 2 × 100 g = 0.4 kg
    r = a.post("/v1/inventory/receipts", json={"idempotency_key": new_key(), "shift_id": sid, "photo_base64": PNG_DATA_URL,
                                               "lines": [{"presentation_id": pres[0]["id"], "qty": 4}, {"presentation_id": pres[2]["id"], "qty": 2}]})
    assert r.status_code == 201 and len(r.json()["evidence_ids"]) == 1, r.text
    exp = a.get(f"/v1/shifts/{sid}/expected").json()
    assert exp["product_expected_kg"] >= 0.4
    # Conteo con foto: lo esperado → sin diferencia; kg contados = kg esperados
    r = a.post("/v1/inventory/counts", json={"idempotency_key": new_key(), "shift_id": sid, "counts": exp["product_expected"], "photo_base64": PNG_DATA_URL})
    assert r.status_code == 200 and len(r.json()["evidence_ids"]) == 1, r.text
    count_id = r.json()["count_id"]
    rows = admin.get("/v1/inventory/counts", params={"point_id": a.point["id"]}).json()["counts"]
    mine = [c for c in rows if c["id"] == count_id][0]
    assert mine["counted_kg"] == mine["expected_kg"] == exp["product_expected_kg"] and mine["diff_units"] == 0
    assert len(mine["evidence"]) == 1 and mine["evidence"][0]["kind"] == "inventory_count" and mine["evidence"][0]["url"]
    recs = admin.get("/v1/inventory/receipts", params={"point_id": a.point["id"]}).json()["receipts"]
    assert recs[0]["kg"] == 0.4 and recs[0]["units"] == 6 and recs[0]["evidence"][0]["kind"] == "inventory_receipt"
    # Estado por punto en kg y listado de evidencias por entidad
    st = admin.get("/v1/inventory/status").json()
    pt = [p for p in st["points"] if p["point"]["id"] == a.point["id"]][0]
    assert pt["total_kg"] == round(sum(i["balance"] * i["grams"] for i in pt["items"]) / 1000, 2) and st["total_kg"] >= pt["total_kg"]
    assert all(len(str(v).split(".")[-1]) <= 2 for v in (pt["total_kg"], st["total_kg"], mine["counted_kg"], recs[0]["kg"]))
    ev = admin.get("/v1/evidence", params={"entity": "inventory_count", "entity_id": count_id}).json()
    assert len(ev) == 1
    # El reporte de inventario expone existencias y conteos en kg
    rep = admin.get("/v1/reports/bi/inventory", params={"period": "today"}).json()
    assert rep["version"] == "1.2" and any(k["key"] == "stock_kg" for k in rep["kpis"])
    counts_tbl = [t for t in rep["tables"] if t["key"] == "counts"][0]
    assert any(c["key"] == "counted_kg" and c["format"] == "kg" for c in counts_tbl["columns"])
    assert [k for k in rep["kpis"] if k["key"] == "stock_kg"][0]["format"] == "kg"
    # 8025 g → 8.03 (mitad hacia arriba, 2 decimales) en la misma función que usa toda la API
    from app.services.inventory import kg2
    assert kg2(8025) == 8.03 and kg2(75) == 0.08 and kg2(2000) == 2.0


def test_cash_float_default_in_operator_config(fresh_operator, admin):
    """El fondo de caja estándar (Parámetros) llega a la app en config; el administrador puede cambiarlo."""
    a = fresh_operator()
    cfg = a.get("/v1/me/assignment").json()["config"]
    assert cfg["cash_float_default_cents"] == 50000
    r = admin.put("/v1/admin/settings/cash_float_default_cents", json={"value": 30000})
    assert r.status_code == 200, r.text
    try:
        assert a.get("/v1/me/assignment").json()["config"]["cash_float_default_cents"] == 30000
    finally:
        admin.put("/v1/admin/settings/cash_float_default_cents", json={"value": 50000})
