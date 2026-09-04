"""Idempotencia, sync/batch, cancelaciones e inventario."""
import uuid
from datetime import timedelta

from tests.conftest import new_key, open_payload, sale_payload


def test_idempotent_sale(fresh_operator, catalog, db_session):
    from sqlalchemy import func, select
    from app.models.sales import Sale

    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    key = new_key()
    body = sale_payload(shift_id, catalog, key=key)
    r1 = op.post("/v1/sales", json=body)
    assert r1.status_code == 201 and r1.json()["duplicate"] is False
    r2 = op.post("/v1/sales", json=body)
    assert r2.status_code == 200, r2.text
    assert r2.json()["duplicate"] is True
    assert r2.json()["sale_id"] == r1.json()["sale_id"]
    n = db_session.execute(select(func.count(Sale.id)).where(Sale.shift_id == uuid.UUID(shift_id))).scalar_one()
    assert n == 1
    # misma clave, payload distinto → 409
    body2 = dict(body, lines=[{"presentation_id": catalog["presentations"][1]["id"], "qty": 1}], payments=[{"method": "cash", "amount_cents": 3500}])
    r3 = op.post("/v1/sales", json=body2)
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # idempotencia también en cierre
    close = {"idempotency_key": new_key(), "cash_counted_cents": 2500}
    a = op.post(f"/v1/shifts/{shift_id}/close", json=close)
    b = op.post(f"/v1/shifts/{shift_id}/close", json=close)
    assert a.status_code == 200 and b.status_code == 200 and b.json()["duplicate"] is True
    assert b.json()["status"] == a.json()["status"]


def test_sync_batch_mixed_with_error(fresh_operator, catalog):
    op = fresh_operator()
    k_open, k_sale, k_bad, k_waste, k_help = new_key(), new_key(), new_key(), new_key(), new_key()
    pres = catalog["presentations"][0]
    # El shift_id no se conoce hasta abrir: enviamos apertura y luego un 2º batch con el resto.
    r = op.post("/v1/sync/batch", json={"device_id": op.device_id, "commands": [
        {"idempotency_key": k_open, "type": "shift_open", "created_at": None, "payload": {"assignment_id": op.assignment["id"], "checklist": {"cart_secure": True, "battery_ok": True, "product_ok": True, "clean_ok": True, "pos_ok": True}}},
    ]})
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert res[0]["status"] == "ok" and res[0]["result"]["shift_id"]
    shift_id = res[0]["result"]["shift_id"]
    commands = [
        {"idempotency_key": k_sale, "type": "sale", "payload": {"shift_id": shift_id, "price_version_id": catalog["price_version_id"], "lines": [{"presentation_id": pres["id"], "qty": 2}], "payments": [{"method": "cash", "amount_cents": 5000}], "offline_created": True}},
        {"idempotency_key": k_bad, "type": "sale", "payload": {"shift_id": shift_id, "price_version_id": str(uuid.uuid4()), "lines": [{"presentation_id": pres["id"], "qty": 1}], "payments": [{"method": "cash", "amount_cents": 2500}]}},
        {"idempotency_key": k_waste, "type": "waste", "payload": {"shift_id": shift_id, "presentation_id": pres["id"], "qty": 1, "reason_code": "quality"}},
        {"idempotency_key": k_help, "type": "help_case", "payload": {"shift_id": shift_id, "category": "other", "note": "se me apagó la batería del carrito"}},
        {"idempotency_key": new_key(), "type": "gps_ping", "payload": {"shift_id": shift_id, "lat": 19.4, "lng": -99.15, "accuracy_m": 10, "mocked": False, "battery_pct": 80}},
        {"idempotency_key": k_sale, "type": "sale", "payload": {"shift_id": shift_id, "price_version_id": catalog["price_version_id"], "lines": [{"presentation_id": pres["id"], "qty": 2}], "payments": [{"method": "cash", "amount_cents": 5000}], "offline_created": True}},
    ]
    r = op.post("/v1/sync/batch", json={"device_id": op.device_id, "commands": commands})
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert [x["status"] for x in res] == ["ok", "error", "ok", "ok", "ok", "duplicate"]
    assert res[1]["code"] == "PRICE_VERSION_INVALID"
    assert res[3]["result"]["category"] == "other"
    assert res[5]["result"]["sale_id"] == res[0]["result"]["sale_id"]
    exp = op.get(f"/v1/shifts/{shift_id}/expected").json()
    assert exp["sales_count"] == 1 and exp["cash_expected_cents"] == 5000 and exp["waste_units"] == 1
    # clasificador IA dejó sugerencia trazable en el caso
    case = op.get(f"/v1/cases/{res[3]['result']['case_id']}").json()
    assert case["ai"]["suggested_category"] == "battery"
    assert case["ai"]["confidence"] > 0.5


def test_cancel_window_and_permissions(fresh_operator, catalog, sup1, ops, db_session):
    from app.models.sales import Sale

    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    s1 = op.post("/v1/sales", json=sale_payload(shift_id, catalog)).json()
    s2 = op.post("/v1/sales", json=sale_payload(shift_id, catalog, method="qr")).json()
    # dentro de la ventana: el operador cancela la propia
    r = op.post(f"/v1/sales/{s1['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "customer_error"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert op.get(f"/v1/shifts/{shift_id}/expected").json()["cash_expected_cents"] == 0
    # doble cancelación con otra clave → CANCEL_NOT_ALLOWED
    r = op.post(f"/v1/sales/{s1['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "customer_error"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CANCEL_NOT_ALLOWED"
    # fuera de la ventana: envejecemos la venta 2
    sale = db_session.get(Sale, uuid.UUID(s2["sale_id"]))
    sale.created_at = sale.created_at - timedelta(minutes=10)
    db_session.commit()
    r = op.post(f"/v1/sales/{s2['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "customer_error"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CANCEL_NOT_ALLOWED"
    # el supervisor de la zona sí puede, con motivo
    r = sup1.post(f"/v1/sales/{s2['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "supervisor", "note": "Cliente devolvió producto"})
    assert r.status_code == 200, r.text
    # ledger: la venta sigue existiendo con status cancelled y registro de cancelación
    detail = ops.get(f"/v1/sales/{s2['sale_id']}").json()
    assert detail["status"] == "cancelled" and detail["cancellation"]["reason_code"] == "supervisor"
    log = ops.get("/v1/audit-log", params={"entity": "sale", "entity_id": s2["sale_id"]}).json()
    assert log and log[0]["action"] == "sale.cancel"
    # un operador ajeno no puede cancelar
    other = fresh_operator()
    r = other.post(f"/v1/sales/{s1['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "error"})
    assert r.status_code == 403


def test_inventory_rebuilt_from_movements(fresh_operator, catalog, ops, db_session):
    from sqlalchemy import select
    from app.models.inventory import InventoryMovement

    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    p0, p1 = catalog["presentations"][0], catalog["presentations"][1]
    r = op.post("/v1/inventory/receipts", json={"idempotency_key": new_key(), "shift_id": shift_id, "qr_code": "QR-1", "lines": [{"presentation_id": p0["id"], "qty": 20, "lot_code": "L-2026-001"}, {"presentation_id": p1["id"], "qty": 15}]})
    assert r.status_code == 201, r.text
    op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=3, pres_index=0))  # -3 p0
    s = op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=2, pres_index=1)).json()  # -2 p1
    op.post("/v1/waste", json={"idempotency_key": new_key(), "shift_id": shift_id, "presentation_id": p0["id"], "qty": 1, "reason_code": "spill"})  # -1 p0
    op.post(f"/v1/sales/{s['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "error"})  # +2 p1 (return)
    # conteo manual con diferencia de 1 (no supera units=3): ajuste sin caso
    r = op.post("/v1/inventory/counts", json={"idempotency_key": new_key(), "shift_id": shift_id, "counts": {p0["id"]: 15, p1["id"]: 15}})
    assert r.status_code == 200, r.text
    assert r.json()["differences"] == {p0["id"]: -1, p1["id"]: 0}
    exp = op.get(f"/v1/shifts/{shift_id}/expected").json()
    assert exp["product_expected"][p0["id"]] == 15 and exp["product_expected"][p1["id"]] == 15
    # reconstrucción manual desde movimientos == balance de la API
    rows = db_session.execute(select(InventoryMovement.presentation_id, InventoryMovement.qty, InventoryMovement.movement_type).where(InventoryMovement.shift_id == uuid.UUID(shift_id))).all()
    types = {t for _, _, t in rows}
    assert {"receipt", "sale", "waste", "return", "count_adjustment"} <= types
    assert sum(q for pid, q, _ in rows if str(pid) == p0["id"]) == 15
    # estado de inventario en backoffice y vista SQL
    status = ops.get("/v1/inventory/status").json()
    row = next(x for x in status["points"] if x["point"]["id"] == op.point["id"])
    assert next(i for i in row["items"] if i["presentation_id"] == p0["id"])["balance"] == 15
    from sqlalchemy import text
    v = db_session.execute(text("SELECT balance FROM inventory_balances WHERE point_id = :p AND presentation_id = :pr"), {"p": op.point["id"], "pr": p0["id"]}).scalar_one()
    assert v == 15


def test_lot_block(fresh_operator, catalog, ops, admin):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    p0 = catalog["presentations"][0]
    code = f"L-BLK-{uuid.uuid4().hex[:4]}"
    op.post("/v1/inventory/receipts", json={"idempotency_key": new_key(), "shift_id": shift_id, "lines": [{"presentation_id": p0["id"], "qty": 5, "lot_code": code}]})
    lot = next(l for l in ops.get("/v1/lots").json() if l["code"] == code)
    r = ops.post(f"/v1/lots/{lot['id']}/block", json={"reason": "Sospecha de contaminación"})
    assert r.status_code == 200, r.text
    assert r.json()["affected_points"][0]["point_id"] == op.point["id"]
    r = op.post("/v1/inventory/receipts", json={"idempotency_key": new_key(), "shift_id": shift_id, "lines": [{"presentation_id": p0["id"], "qty": 5, "lot_code": code}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LOT_BLOCKED"
    assert op.get(f"/v1/shifts/{shift_id}/expected").json()["product_expected"][p0["id"]] == 0


def test_idempotency_key_is_scoped_to_user(fresh_operator, catalog):
    """Otro usuario con la misma clave no recibe la respuesta ajena (409)."""
    a, b = fresh_operator(), fresh_operator()
    shift_a = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    body = sale_payload(shift_a, catalog, key=new_key())
    assert a.post("/v1/sales", json=body).status_code == 201
    r = b.post("/v1/sales", json=body)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
