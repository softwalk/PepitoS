"""Apertura a ≤ open_max_distance_m (50 m) del punto asignado; catálogo de puntos autorizados."""
from tests.conftest import open_payload


def _gps(lat, lng):
    return {"lat": lat, "lng": lng, "accuracy_m": 5, "mocked": False}


def test_open_far_from_verified_point_warns_and_opens_case(fresh_operator, admin, ops):
    op = fresh_operator(lat=19.4000, lng=-99.1500)  # punto creado por admin → geo_verified=True
    # ~120 m al norte (0.00108° lat ≈ 120 m)
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"], gps=_gps(19.40108, -99.1500)))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ready"] is False
    exc = next(e for e in body["exceptions"] if e["code"] == "out_of_geofence")
    assert "máximo 50 m" in exc["message"] and 110 <= exc["distance_m"] <= 130
    # Caso urgente para el supervisor + alerta en Control Tower
    cases = ops.get("/v1/cases", params={"status": "open", "point_id": op.point["id"]}).json()
    c = next(x for x in cases if x["rule_key"] == "open_out_of_geofence")
    assert c["severity"] == "urgent" and "Apertura con excepción" in c["title"]
    summ = ops.get("/v1/control-tower/summary").json()
    assert any(a["case_id"] == c["id"] for a in summ["alerts_recent"])
    # Limpieza: resolver el caso urgente para no desplazar decisiones de otras pruebas en el briefing (top 8)
    assert ops.patch(f"/v1/cases/{c['id']}", json={"status": "resolved", "resolution": "prueba"}).status_code == 200


def test_open_within_50m_is_clean(fresh_operator):
    op = fresh_operator(lat=19.4000, lng=-99.1500)
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"], gps=_gps(19.40030, -99.1500)))  # ~33 m
    assert r.status_code == 201 and r.json()["ready"] is True
    assert not any(e["code"] == "out_of_geofence" for e in r.json()["exceptions"])


def test_unverified_point_uses_geofence_tolerance(fresh_operator, admin):
    op = fresh_operator(lat=19.4000, lng=-99.1500)
    admin.post(f"/v1/admin/points/{op.point['id']}/verify-location", json={"verified": False, "source": "por validar"})
    # 120 m: supera 50 m pero no la geocerca de 150 m → sin aviso
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"], gps=_gps(19.40108, -99.1500)))
    assert r.status_code == 201 and r.json()["ready"] is True


def test_verify_location_adopts_gps_and_is_audited(fresh_operator, admin):
    op = fresh_operator(lat=19.4000, lng=-99.1500)
    assert op.post("/v1/shifts/open", json=open_payload(op.assignment["id"], gps=_gps(19.4000, -99.1500))).status_code == 201  # evita caso no_open
    r = admin.post(f"/v1/admin/points/{op.point['id']}/verify-location", json={"verified": True, "lat": 19.40011, "lng": -99.15009, "source": "GPS de apertura"})
    assert r.status_code == 200 and r.json()["geo_verified"] is True and abs(r.json()["lat"] - 19.40011) < 1e-6
    log = admin.get("/v1/audit-log", params={"entity": "points", "entity_id": op.point["id"]}).json()
    assert any(e["action"] == "points.verify_location" for e in log)


def test_authorized_catalog_imported(admin):
    pts = admin.get("/v1/admin/points").json()
    cat = [p for p in pts if p.get("meta", {}).get("ranking")]
    assert len(cat) == 100
    top = next(p for p in cat if p["meta"]["ranking"] == 1)
    assert top["geo_verified"] is False and "Central de Abasto" in top["name"] and top["meta"]["alcaldia"] == "Iztapalapa"
    # Reimportar es idempotente
    r = admin.post("/v1/admin/points/import-authorized")
    assert r.status_code == 200 and r.json()["created"] == 0 and r.json()["updated"] == 100
    assert len([p for p in admin.get("/v1/admin/points").json() if p.get("meta", {}).get("ranking")]) == 100


def test_assignment_requires_active_point(fresh_operator, admin):
    op = fresh_operator()
    assert op.post("/v1/shifts/open", json=open_payload(op.assignment["id"])).status_code == 201  # evita caso no_open
    admin.patch(f"/v1/admin/points/{op.point['id']}", json={"is_active": False})
    r = admin.post("/v1/admin/assignments", json={"operator_id": op.user["id"], "point_id": op.point["id"], "cart_id": op.cart["id"], "shift_date": "2030-01-01"})
    assert r.status_code == 422 and "no está activo" in r.json()["error"]["message"]
