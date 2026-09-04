"""Continuar un turno terminado (sólo administrador): cerrado → reabierto → el operador sigue vendiendo → cierra de nuevo."""
from tests.conftest import new_key, open_payload, sale_payload

CHECKLIST = {"off_ok": True, "clean_ok": True, "secured_ok": True, "stored_ok": True, "charging_ok": True}


def _open_and_close(op, catalog):
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 201, r.text
    shift_id = r.json()["shift_id"]
    r = op.post("/v1/sales", json=sale_payload(shift_id, catalog, method="cash", pres_index=0))
    assert r.status_code == 201, r.text
    exp = op.get(f"/v1/shifts/{shift_id}/expected").json()
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": exp["cash_expected_cents"], "product_counts": exp["product_expected"], "checklist": CHECKLIST})
    assert r.status_code == 200, r.text
    return shift_id


def test_admin_reopens_closed_shift_and_operator_continues(fresh_operator, catalog, admin, ops):
    op = fresh_operator()
    shift_id = _open_and_close(op, catalog)

    # Turno cerrado: la asignación quedó "done" y no se puede vender ni volver a abrir
    assert op.get("/v1/me/assignment").json()["assignment"]["status"] == "done"
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 409

    # Ops/supervisor no tienen el permiso
    r = ops.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "prueba sin permiso"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

    # Motivo obligatorio
    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "x"})
    assert r.status_code == 422

    # Admin reabre
    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "El operador cerró por error a media jornada"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == shift_id and body["status"] == "open" and body["closed_at"] is None and body["close_status"] is None

    # No se puede reabrir dos veces
    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "segunda vez no aplica"})
    assert r.status_code == 409

    # El operador ve el mismo turno activo y puede seguir vendiendo
    me = op.get("/v1/me/assignment").json()
    assert me["active_shift"]["id"] == shift_id and me["assignment"]["status"] == "started"
    r = op.post("/v1/sales", json=sale_payload(shift_id, catalog, method="cash", pres_index=2))
    assert r.status_code == 201, r.text

    # El esperado acumula TODAS las ventas del turno (antes y después de reabrir)
    exp = op.get(f"/v1/shifts/{shift_id}/expected").json()
    assert exp["sales_count"] == 2 and exp["cash_expected_cents"] == 2500 + 4500

    # Segundo cierre conciliado
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": exp["cash_expected_cents"], "product_counts": exp["product_expected"], "checklist": CHECKLIST})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "reconciled"
    assert op.get("/v1/me/assignment").json()["assignment"]["status"] == "done"

    # Trazabilidad: audit_log con motivo
    logs = admin.get("/v1/audit-log?entity=shift&action=shift.reopen").json()
    rows = logs["rows"] if isinstance(logs, dict) and "rows" in logs else logs
    assert any(x["entity_id"] == shift_id and x["reason"].startswith("El operador cerró") for x in rows)


def test_reopen_blocked_if_operator_has_another_open_shift(fresh_operator, catalog, admin):
    op = fresh_operator()
    first = _open_and_close(op, catalog)
    # El admin devuelve la asignación a "planned" y el operador abre un segundo turno del día
    admin.patch(f"/v1/admin/assignments/{op.assignment['id']}", json={"status": "planned"})
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 201, r.text
    r = admin.post(f"/v1/shifts/{first}/reopen", json={"reason": "ya hay otro turno abierto"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SHIFT_ALREADY_OPEN"


def test_reopen_supersedes_cash_case_and_approval(fresh_operator, catalog, admin):
    """Cierre con diferencia grave → caso urgente + aprobación pendiente. Al reabrir quedan superados; el 2.º cierre concilia limpio."""
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    for _ in range(3):
        op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=3, pres_index=2))  # 13500 c/u
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 0, "product_counts": {}})
    case_id = r.json()["case_id"]
    assert case_id and r.json()["difference_cents"] == -40500
    assert any(a["entity_id"] == shift_id for a in admin.get("/v1/approvals", params={"status": "pending"}).json())

    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "El operador no había contado el efectivo del cajón"})
    assert r.status_code == 200, r.text
    case = admin.get(f"/v1/cases/{case_id}").json()
    assert case["status"] == "closed" and "reabierto" in (case["resolution"] or "")
    assert not any(a["entity_id"] == shift_id for a in admin.get("/v1/approvals", params={"status": "pending"}).json())
    assert any(a["entity_id"] == shift_id for a in admin.get("/v1/approvals", params={"status": "cancelled"}).json())

    exp = op.get(f"/v1/shifts/{shift_id}/expected").json()
    assert exp["cash_expected_cents"] == 40500
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 40500, "product_counts": exp["product_expected"], "checklist": CHECKLIST})
    assert r.status_code == 200 and r.json()["status"] == "reconciled" and r.json()["case_id"] is None
    # El audit conserva el cierre anterior completo
    log = admin.get("/v1/audit-log", params={"entity": "shift", "entity_id": shift_id}).json()
    entry = next(e for e in log if e["action"] == "shift.reopen")
    assert entry["before"]["difference_cents"] == -40500 and "product_diff" in entry["before"] and entry["after"]["superseded_cases"] == [case_id]


def test_reopen_rejects_old_shift_and_transferred(fresh_operator, catalog, admin, db_session):
    from datetime import timedelta

    from app.models.ops import Shift

    op = fresh_operator()
    shift_id = _open_and_close(op, catalog)
    # Turno de ayer (mismo estado closed): no se puede continuar
    sh = db_session.get(Shift, __import__("uuid").UUID(shift_id))
    sh.opened_at = sh.opened_at - timedelta(days=1)
    sh.closed_at = sh.closed_at - timedelta(days=1)
    db_session.commit()
    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "turno de ayer"})
    assert r.status_code == 409 and "hoy" in r.json()["error"]["message"]
    # Cerrado hoy pero fuera de la ventana de horas
    sh.opened_at = sh.opened_at + timedelta(days=1)
    sh.closed_at = sh.closed_at + timedelta(days=1)
    db_session.commit()
    admin.put("/v1/admin/settings/shift_reopen_window_hours", json={"value": 1})
    sh.closed_at = sh.closed_at - timedelta(hours=2)
    db_session.commit()
    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "fuera de ventana"})
    assert r.status_code == 409 and "shift_reopen_window_hours" in r.json()["error"]["message"]
    admin.put("/v1/admin/settings/shift_reopen_window_hours", json={"value": 24})
    sh.closed_at = sh.closed_at + timedelta(hours=2)
    db_session.commit()
    # Transferido: tampoco
    sh.status = "transferred"
    db_session.commit()
    r = admin.post(f"/v1/shifts/{shift_id}/reopen", json={"reason": "transferido no aplica"})
    assert r.status_code == 409 and "transferido" in r.json()["error"]["message"]
