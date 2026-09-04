"""Flujo completo del operador: abrir → vender → merma → esperado → cerrar."""
import uuid

from tests.conftest import new_key, open_payload, sale_payload


def test_full_flow_reconciled(fresh_operator, catalog, ops):
    op = fresh_operator()
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"], gps={"lat": op.point["lat"], "lng": op.point["lng"], "accuracy_m": 5, "mocked": False}))
    assert r.status_code == 201, r.text
    shift_id = r.json()["shift_id"]
    assert r.json()["status"] == "open"
    assert r.json()["ready"] is True

    me = op.get("/v1/me/assignment").json()
    assert me["active_shift"]["id"] == shift_id

    # 3 ventas: 2 cash, 1 qr
    totals = {"cash": 0, "qr": 0}
    for method, idx in (("cash", 0), ("cash", 2), ("qr", 1)):
        r = op.post("/v1/sales", json=sale_payload(shift_id, catalog, method=method, pres_index=idx))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "recorded" and body["duplicate"] is False and body["folio"].startswith("F-")
        totals[method] += body["total_cents"]
    assert totals["cash"] == 2500 + 4500 and totals["qr"] == 3500

    # merma
    r = op.post("/v1/waste", json={"idempotency_key": new_key(), "shift_id": shift_id, "presentation_id": catalog["presentations"][0]["id"], "qty": 2, "reason_code": "spill"})
    assert r.status_code == 201, r.text

    # esperado
    r = op.get(f"/v1/shifts/{shift_id}/expected")
    assert r.status_code == 200
    exp = r.json()
    assert exp["sales_count"] == 3
    assert exp["sales_total_cents"] == 10500
    assert exp["cash_expected_cents"] == 7000
    assert exp["digital_total_cents"] == 3500
    assert exp["waste_units"] == 2
    # Inventario: el punto nuevo empezó en 0 → -1 venta -2 merma = -3 en la presentación 0
    assert exp["product_expected"][catalog["presentations"][0]["id"]] == -3

    # cierre conciliado con conteo igual al teórico
    counts = {k: v for k, v in exp["product_expected"].items()}
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 7000, "product_counts": counts, "checklist": {"off_ok": True, "clean_ok": True, "secured_ok": True, "stored_ok": True, "charging_ok": True}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reconciled"
    assert body["difference_cents"] == 0
    assert body["case_id"] is None
    assert all(v == 0 for v in body["product_diff"].values())

    # ya cerrado: nueva venta → SHIFT_NOT_OPEN
    r = op.post("/v1/sales", json=sale_payload(shift_id, catalog))
    assert r.status_code == 409 and r.json()["error"]["code"] == "SHIFT_NOT_OPEN"

    # reporte diario refleja el turno
    rows = ops.get("/v1/reports/daily").json()["rows"]
    row = next(x for x in rows if x["shift_id"] == shift_id)
    assert row["sales_cents"] == 10500 and row["tx"] == 3 and row["status"] == "reconciled" and row["waste_units"] == 2


def test_close_with_difference_creates_case(fresh_operator, catalog, sup1, ops):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    for _ in range(2):
        assert op.post("/v1/sales", json=sale_payload(shift_id, catalog, method="cash", pres_index=2)).status_code == 201
    # esperado 9000, contado 4000 → diferencia -5000 (> umbral 2000, < grave 10000) → review
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 4000, "product_counts": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "difference"
    assert body["cash_expected_cents"] == 9000 and body["difference_cents"] == -5000
    assert body["case_id"]
    case = sup1.get(f"/v1/cases/{body['case_id']}").json()
    assert case["rule_key"] == "cash_difference" and case["severity"] == "review" and case["status"] == "open"
    assert case["priority_score"] >= 50
    # evento CashDifferenceDetected y alerta en control tower
    summ = ops.get("/v1/control-tower/summary").json()
    assert any(a["case_id"] == body["case_id"] for a in summ["alerts_recent"])
    # el supervisor lo ve en excepciones y puede resolverlo
    exc = sup1.get("/v1/supervisor/exceptions").json()
    assert any(c["id"] == body["case_id"] for c in exc["review"])
    r = sup1.patch(f"/v1/cases/{body['case_id']}", json={"status": "resolved", "resolution": "Se encontró el efectivo en el cajón"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    log = ops.get("/v1/audit-log", params={"entity": "case", "entity_id": body["case_id"]}).json()
    assert any(e["action"] == "case.update" for e in log)


def test_severe_difference_is_urgent_and_requests_approval(fresh_operator, catalog, admin):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    for _ in range(3):
        op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=3, pres_index=2))  # 13500 c/u
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 0})
    assert r.json()["difference_cents"] == -40500
    case = admin.get(f"/v1/cases/{r.json()['case_id']}").json()
    assert case["severity"] == "urgent"
    approvals = admin.get("/v1/approvals", params={"status": "pending"}).json()
    assert any(a["entity_id"] == shift_id for a in approvals)


def test_open_with_exception(fresh_operator):
    op = fresh_operator()
    body = open_payload(op.assignment["id"])
    body["checklist"]["battery_ok"] = False
    r = op.post("/v1/shifts/open", json=body)
    assert r.status_code == 201
    assert r.json()["status"] == "open_with_exception"
    assert r.json()["ready"] is False
    assert r.json()["exceptions"][0]["code"] == "battery_ok"


def test_cart_in_use_and_shift_already_open(fresh_operator, admin, client):
    from tests.conftest import Api
    from app.core.timeutil import local_today

    op = fresh_operator()
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 201
    # el mismo operador no puede abrir de nuevo (nueva clave)
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "SHIFT_ALREADY_OPEN"
    # otro operador con asignación al MISMO carrito → CART_IN_USE
    tag = uuid.uuid4().hex[:6]
    other = admin.post("/v1/admin/users", json={"username": f"opcart{tag}", "name": "Otro", "role": "operator", "password": "op123"}).json()
    a2 = admin.post("/v1/admin/assignments", json={"operator_id": other["id"], "point_id": op.point["id"], "cart_id": op.cart["id"], "shift_date": local_today().isoformat()}).json()
    api2 = Api(client, other["username"], "op123")
    r = api2.post("/v1/shifts/open", json=open_payload(a2["id"]))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CART_IN_USE"
    # asignación ajena → NO_ASSIGNMENT
    r = api2.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_ASSIGNMENT"


def test_transfer_shift(fresh_operator, catalog, admin, sup1, client):
    from tests.conftest import Api

    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    op.post("/v1/inventory/receipts", json={"idempotency_key": new_key(), "shift_id": shift_id, "lines": [{"presentation_id": catalog["presentations"][0]["id"], "qty": 10, "lot_code": "L-2026-001"}]})
    op.post("/v1/sales", json=sale_payload(shift_id, catalog, method="cash"))
    tag = uuid.uuid4().hex[:6]
    other = admin.post("/v1/admin/users", json={"username": f"optr{tag}", "name": "Relevo", "role": "operator", "password": "op123", "zone_id": op.user["zone_id"]}).json()
    r = sup1.post(f"/v1/shifts/{shift_id}/transfer", json={"idempotency_key": new_key(), "to_operator_id": other["id"], "cash_counted_cents": 2500, "product_counts": {catalog["presentations"][0]["id"]: 9}})
    assert r.status_code == 200, r.text
    new_shift = r.json()["new_shift_id"]
    assert r.json()["closed_shift_id"] == shift_id
    old = sup1.get(f"/v1/shifts/{shift_id}").json()
    assert old["status"] == "transferred"
    api2 = Api(client, other["username"], "op123")
    me = api2.get("/v1/me/assignment").json()
    assert me["active_shift"]["id"] == new_shift
    # el inventario del punto se conserva (9 unidades)
    exp = api2.get(f"/v1/shifts/{new_shift}/expected").json()
    assert exp["product_expected"][catalog["presentations"][0]["id"]] == 9
    assert exp["cash_expected_cents"] == 0
