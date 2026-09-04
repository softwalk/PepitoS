"""Motor de reglas §6."""
import uuid
from datetime import timedelta

from tests.conftest import new_key, open_payload, sale_payload


def _run(ops):
    r = ops.post("/v1/rules/run")
    assert r.status_code == 200, r.text
    return r.json()


def _cases_for(api, point_id, rule_key):
    return [c for c in api.get("/v1/cases", params={"point_id": point_id, "status": "open,in_progress"}).json() if c["rule_key"] == rule_key]


def test_no_open_creates_urgent_case(fresh_operator, ops):
    from app.core.timeutil import utcnow

    start = (utcnow() - timedelta(hours=2)).isoformat()
    op = fresh_operator(planned_start=start)  # asignación con hora planeada hace 2 h y sin abrir
    result = _run(ops)
    assert result["cases_created"] >= 1
    cases = _cases_for(ops, op.point["id"], "no_open")
    assert len(cases) == 1
    assert cases[0]["severity"] == "urgent" and cases[0]["source"] == "rule"
    assert cases[0]["priority_score"] >= 100
    # dedupe: segunda corrida no duplica
    _run(ops)
    assert len(_cases_for(ops, op.point["id"], "no_open")) == 1
    # control tower marca el punto como "late" y el briefing lo incluye
    summ = ops.get("/v1/control-tower/summary").json()
    ps = next(p for p in summ["points"] if p["point"]["id"] == op.point["id"])
    assert ps["status"] == "late"
    brief = ops.get("/v1/control-tower/briefing").json()
    assert any(d["case_id"] == cases[0]["id"] for d in brief["decisions"])
    assert "urgentes" in brief["headline"]


def test_cash_difference_rule(fresh_operator, catalog, ops, admin):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=2, pres_index=2))  # 9000 cash
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 5000})
    case_id = r.json()["case_id"]
    assert case_id
    # el motor no duplica el caso creado en el cierre (mismo dedupe_key)
    _run(ops)
    cases = _cases_for(ops, op.point["id"], "cash_difference")
    assert len(cases) == 1 and cases[0]["id"] == case_id
    # si el supervisor lo resuelve, ya no cuenta como abierto y el motor lo puede reabrir sólo si persiste la condición
    admin.patch(f"/v1/cases/{case_id}", json={"status": "closed"})
    _run(ops)
    assert len(_cases_for(ops, op.point["id"], "cash_difference")) == 1  # se reabre (condición persiste hoy)


def test_low_battery_rule(fresh_operator, ops):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    r = op.post("/v1/gps/pings", json={"pings": [{"shift_id": shift_id, "lat": op.point["lat"], "lng": op.point["lng"], "accuracy_m": 5, "mocked": False, "battery_pct": 20}]})
    assert r.json()["accepted"] == 1
    _run(ops)
    cases = _cases_for(ops, op.point["id"], "low_battery")
    assert len(cases) == 1 and cases[0]["severity"] == "review"
    # crítica → urgente (el caso anterior sigue abierto: dedupe mantiene 1 caso)
    ops.patch(f"/v1/cases/{cases[0]['id']}", json={"status": "resolved"})
    op.post("/v1/gps/pings", json={"pings": [{"shift_id": shift_id, "lat": op.point["lat"], "lng": op.point["lng"], "mocked": False, "battery_pct": 5}]})
    _run(ops)
    cases = _cases_for(ops, op.point["id"], "low_battery")
    assert len(cases) == 1 and cases[0]["severity"] == "urgent"
    ps = next(p for p in ops.get("/v1/control-tower/summary").json()["points"] if p["point"]["id"] == op.point["id"])
    assert ps["battery_pct"] == 5 and ps["status"] == "open"


def test_out_of_geofence_and_sync_stale(fresh_operator, ops, db_session):
    import uuid
    from app.core.timeutil import utcnow
    from app.models.ops import GpsPing, Shift

    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    now = utcnow()
    for minutes_ago in (15, 10, 5, 1):
        db_session.add(GpsPing(shift_id=uuid.UUID(shift_id), at=now - timedelta(minutes=minutes_ago), lat=op.point["lat"] + 0.01, lng=op.point["lng"], mocked=False, in_geofence=False))
    db_session.commit()
    _run(ops)
    assert len(_cases_for(ops, op.point["id"], "out_of_geofence")) == 1
    # sync_stale: sin actividad hace 45 min
    shift = db_session.get(Shift, uuid.UUID(shift_id))
    shift.last_seen_at = now - timedelta(minutes=45)
    shift.opened_at = now - timedelta(minutes=60)
    db_session.query(GpsPing).filter(GpsPing.shift_id == shift.id).delete()
    db_session.commit()
    from app.models.system import Event
    db_session.query(Event).filter(Event.shift_id == shift.id).update({Event.occurred_at: now - timedelta(minutes=50)})
    db_session.commit()
    _run(ops)
    cases = _cases_for(ops, op.point["id"], "sync_stale")
    assert len(cases) == 1
    ps = next(p for p in ops.get("/v1/control-tower/summary").json()["points"] if p["point"]["id"] == op.point["id"])
    assert ps["status"] == "offline"


def test_high_waste_and_stock_and_cancellations(fresh_operator, catalog, ops, sup1):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    p0 = catalog["presentations"][0]
    op.post("/v1/inventory/receipts", json={"idempotency_key": new_key(), "shift_id": shift_id, "lines": [{"presentation_id": p0["id"], "qty": 12}]})
    sales = [op.post("/v1/sales", json=sale_payload(shift_id, catalog)).json() for _ in range(4)]
    op.post("/v1/waste", json={"idempotency_key": new_key(), "shift_id": shift_id, "presentation_id": p0["id"], "qty": 2, "reason_code": "quality"})
    for s in sales:
        op.post(f"/v1/sales/{s['sale_id']}/cancel", json={"idempotency_key": new_key(), "reason_code": "error"})
    _run(ops)
    assert _cases_for(ops, op.point["id"], "high_waste")  # 2/(0+2) > 4%
    assert _cases_for(ops, op.point["id"], "stock_critical")  # otras presentaciones en 0 < 10
    assert _cases_for(ops, op.point["id"], "anomalous_cancellations")  # 4 > 3
    # ruta del supervisor incluye el punto
    route = sup1.get("/v1/supervisor/route").json()
    assert any(s["point"]["id"] == op.point["id"] for s in route["stops"])
    assert [s["order"] for s in route["stops"]] == list(range(1, len(route["stops"]) + 1))


def test_rules_config_and_audit(ops, admin):
    r = ops.get("/v1/rules")
    assert r.status_code == 200 and len(r.json()) == 11
    r = ops.put("/v1/rules/high_waste", json={"params": {"pct": 6}})
    assert r.status_code == 200 and r.json()["params"]["pct"] == 6
    log = admin.get("/v1/audit-log", params={"entity": "rule"}).json()
    assert log and log[0]["action"] == "rule.update"
    ops.put("/v1/rules/high_waste", json={"params": {"pct": 4}})


def test_maintenance_overdue_and_tickets(ops, db_session):
    from datetime import timedelta
    from app.core.timeutil import utcnow
    from app.models.org import Asset

    asset = db_session.query(Asset).filter(Asset.code == "C-001-BATTERY").first()
    asset.next_maintenance_at = utcnow() - timedelta(days=3)
    db_session.commit()
    _run(ops)
    cases = [c for c in ops.get("/v1/cases", params={"status": "open"}).json() if c["rule_key"] == "maintenance_overdue"]
    assert any(c["payload"]["asset_code"] == "C-001-BATTERY" for c in cases)
    t = ops.post("/v1/maintenance/tickets", json={"asset_id": str(asset.id), "title": "Preventivo batería", "kind": "preventive"}).json()
    r = ops.patch(f"/v1/maintenance/tickets/{t['id']}", json={"status": "resolved", "resolution": "Cambio de celdas"})
    assert r.status_code == 200
    db_session.refresh(asset)
    assert asset.next_maintenance_at > utcnow()


def test_audit_with_corrective_actions(fresh_operator, catalog, sup1, ops):
    op = fresh_operator()
    shift_id = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).json()["shift_id"]
    op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=2, pres_index=2))  # 9000 cash
    r = sup1.post("/v1/audits", json={"point_id": op.point["id"], "checklist": {"clean": True, "uniform": False}, "cash_counted_cents": 9000, "notes": "Falta uniforme", "corrective_actions": [{"description": "Entregar uniforme", "owner_id": sup1.user["id"], "due_date": "2026-09-10"}]})
    assert r.status_code == 201, r.text
    assert len(r.json()["case_ids"]) == 1
    case = sup1.get(f"/v1/cases/{r.json()['case_ids'][0]}").json()
    assert case["source"] == "supervisor" and len(case["actions"]) == 1
    a = case["actions"][0]
    r = sup1.patch(f"/v1/actions/{a['id']}", json={"status": "done"})
    assert r.status_code == 200 and r.json()["status"] == "done"


def test_no_open_auto_resolves_when_point_opens(fresh_operator, admin, db_session):
    from datetime import timedelta
    from app.core.timeutil import utcnow
    from app.services.rules_engine import run_rules
    from app.models.cases import Case
    from tests.conftest import open_payload

    start = (utcnow() - timedelta(hours=2)).isoformat()
    op = fresh_operator(planned_start=start)
    run_rules(db_session)
    db_session.expire_all()
    case = db_session.query(Case).filter(Case.rule_key == "no_open", Case.point_id == uuid.UUID(op.point["id"])).first()
    assert case is not None and case.status == "open"
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 201, r.text
    out = run_rules(db_session)
    assert out["cases_resolved"] >= 1
    db_session.expire_all()
    db_session.refresh(case)
    assert case.status == "resolved"
