"""Gate 6-20: evidencias en storage (B4), settings editables (B6), ventana de precio offline (B8)."""
import base64
import uuid
from datetime import timedelta

from tests.conftest import Api, new_key, open_payload, sale_payload

# PNG 1x1 válido (firma real: el servidor valida por magic bytes)
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG_1X1).decode()
PNG_DATA_URL = "data:image/png;base64," + PNG_B64
JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()


def _open(op):
    r = op.post("/v1/shifts/open", json=open_payload(op.assignment["id"]))
    assert r.status_code == 201, r.text
    return r.json()["shift_id"]


def _set(admin, key, value):
    r = admin.put(f"/v1/admin/settings/{key}", json={"value": value})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- B4 evidencias
def test_help_case_photo_is_stored_and_visible_with_permissions(fresh_operator, ops, sup1, client):
    op = fresh_operator()
    shift_id = _open(op)
    r = op.post("/v1/help-cases", json={"idempotency_key": new_key(), "shift_id": shift_id, "category": "cart", "note": "rueda rota", "photo_base64": PNG_DATA_URL})
    assert r.status_code == 201, r.text
    case_id = r.json()["case_id"]

    case = op.get(f"/v1/cases/{case_id}").json()
    assert len(case["evidence"]) == 1
    ev = case["evidence"][0]
    assert ev["kind"] == "help_case" and ev["content_type"] == "image/png" and ev["size_bytes"] == len(PNG_1X1)
    assert ev["url"] == f"/v1/evidence/{ev['id']}/file"
    assert case["payload"]["evidence_ids"] == [ev["id"]]

    # listado por entidad
    lst = op.get("/v1/evidence", params={"entity": "case", "entity_id": case_id}).json()
    assert [e["id"] for e in lst] == [ev["id"]]
    assert set(lst[0]) >= {"id", "kind", "content_type", "size_bytes", "taken_at", "url"}
    # archivo servido por la API (backend local) con los mismos permisos
    f = op.get(ev["url"])
    assert f.status_code == 200 and f.headers["content-type"].startswith("image/png") and f.content == PNG_1X1
    # otro operador no la ve ni la puede bajar
    other = fresh_operator()
    assert other.get("/v1/evidence", params={"entity": "case", "entity_id": case_id}).json() == []
    assert other.get(ev["url"]).status_code == 403
    # supervisor de la zona y ops sí
    assert sup1.get(ev["url"]).status_code == 200
    assert ops.get(f"/v1/evidence/{ev['id']}").json()["sha256"] == ev["sha256"]
    # sin token → 401
    assert client.get(ev["url"]).status_code == 401


def test_photo_too_large_or_invalid_is_422(fresh_operator):
    op = fresh_operator()
    shift_id = _open(op)
    big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024 + 10)).decode()
    r = op.post("/v1/help-cases", json={"idempotency_key": new_key(), "shift_id": shift_id, "category": "cart", "photo_base64": big})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION", r.text
    assert "3 MB" in r.json()["error"]["message"]
    # no es imagen
    txt = base64.b64encode(b"hola mundo esto no es una imagen").decode()
    r = op.post("/v1/help-cases", json={"idempotency_key": new_key(), "shift_id": shift_id, "category": "cart", "photo_base64": txt})
    assert r.status_code == 422 and "JPEG" in r.json()["error"]["message"]
    # base64 inválido
    r = op.post("/v1/help-cases", json={"idempotency_key": new_key(), "shift_id": shift_id, "category": "cart", "photo_base64": "!!!no-base64!!!"})
    assert r.status_code == 422
    # el comando fallido no consumió la clave: no hay caso creado
    assert op.get("/v1/cases").status_code in (200, 403)


def test_sync_batch_help_case_with_photo(fresh_operator, ops):
    op = fresh_operator()
    shift_id = _open(op)
    key = new_key()
    cmd = {"idempotency_key": key, "type": "help_case", "payload": {"shift_id": shift_id, "category": "product", "note": "producto húmedo", "photo_base64": JPEG_B64}}
    r = op.post("/v1/sync/batch", json={"device_id": op.device_id, "commands": [cmd]})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["status"] == "ok", res
    case_id = res["result"]["case_id"]
    lst = ops.get("/v1/evidence", params={"entity": "case", "entity_id": case_id}).json()
    assert len(lst) == 1 and lst[0]["content_type"] == "image/jpeg"
    # reintento del mismo comando: duplicado, no crea segunda evidencia
    r = op.post("/v1/sync/batch", json={"device_id": op.device_id, "commands": [cmd]})
    assert r.json()["results"][0]["status"] == "duplicate"
    assert len(ops.get("/v1/evidence", params={"entity": "case", "entity_id": case_id}).json()) == 1


def test_shift_open_close_and_audit_photos(fresh_operator, sup1, ops):
    op = fresh_operator()
    body = open_payload(op.assignment["id"], photos=[{"key": "front", "base64": PNG_DATA_URL}, {"key": "side", "base64": JPEG_B64}])
    r = op.post("/v1/shifts/open", json=body)
    assert r.status_code == 201, r.text
    shift_id = r.json()["shift_id"]
    assert len(r.json()["evidence_ids"]) == 2
    # auditoría con fotos (str y {key, base64})
    r = sup1.post("/v1/audits", json={"point_id": op.point["id"], "checklist": {"clean_ok": True}, "photos": [PNG_B64, {"key": "cash", "base64": JPEG_B64}]})
    assert r.status_code == 201, r.text
    audit_id = r.json()["audit_id"]
    assert len(r.json()["evidence"]) == 2
    a = ops.get(f"/v1/audits/{audit_id}").json()
    assert len(a["evidence"]) == 2 and a["photos"][1]["key"] == "cash" and a["photos"][1]["evidence_id"] == a["evidence"][1]["id"]
    # cierre con fotos
    r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 0, "photos": [{"key": "cash", "base64": PNG_B64}]})
    assert r.status_code == 200, r.text
    assert len(r.json()["evidence_ids"]) == 1
    evs = ops.get("/v1/evidence", params={"entity": "shift", "entity_id": shift_id}).json()
    assert sorted(e["kind"] for e in evs) == ["shift_close", "shift_open", "shift_open"]


def test_retention_purges_expired_evidence(fresh_operator, ops, db_session):
    import os

    from app.core.timeutil import utcnow
    from app.models.system import Evidence
    from app.services.evidence import purge_expired_evidence
    from app.services.storage import get_storage

    op = fresh_operator()
    shift_id = _open(op)
    case_id = op.post("/v1/help-cases", json={"idempotency_key": new_key(), "shift_id": shift_id, "category": "cart", "photo_base64": PNG_B64}).json()["case_id"]
    ev_id = ops.get("/v1/evidence", params={"entity": "case", "entity_id": case_id}).json()[0]["id"]
    ev = db_session.get(Evidence, uuid.UUID(ev_id))
    assert ev.retention_until is not None and ev.retention_until > utcnow() + timedelta(days=170)
    path = get_storage().get_path(ev.storage_key)
    assert os.path.isfile(path)
    # aún no vence: no se purga
    assert purge_expired_evidence(db_session, utcnow()) == 0
    db_session.commit()
    # vencida
    n = purge_expired_evidence(db_session, ev.retention_until + timedelta(seconds=1))
    db_session.commit()
    assert n >= 1
    db_session.refresh(ev)
    assert ev.deleted_at is not None and not os.path.exists(path)
    assert ops.get("/v1/evidence", params={"entity": "case", "entity_id": case_id}).json() == []
    assert ops.get(f"/v1/evidence/{ev_id}/file").status_code == 404
    assert ops.get(f"/v1/cases/{case_id}").json()["evidence"] == []
    # el job de mantenimiento también corre la purga de GPS
    from app.services.rules_engine import run_maintenance

    out = run_maintenance(db_session)
    assert set(out) == {"evidence_purged", "gps_purged"}


def test_require_open_photo_is_stable_and_follows_sampling(fresh_operator, admin):
    from app.routers.me import require_open_photo

    op = fresh_operator()
    cfg1 = op.get("/v1/me/assignment").json()["config"]
    cfg2 = op.get("/v1/me/assignment").json()["config"]
    assert cfg1["require_open_photo"] == cfg2["require_open_photo"]
    assert cfg1["require_open_photo"] == require_open_photo(op.assignment["id"], cfg1["photo_sampling_pct"])
    assert cfg1["photo_sampling_pct"] == 10 and cfg1["gps_interval_seconds"] == 120 and cfg1["cancel_window_minutes"] == 5
    assert cfg1["cash_difference_threshold_cents"] == 2000 and cfg1["cash_difference_severe_cents"] == 10000
    try:
        _set(admin, "photo_sampling_pct", 100)
        assert op.get("/v1/me/assignment").json()["config"]["require_open_photo"] is True
        _set(admin, "photo_sampling_pct", 0)
        assert op.get("/v1/me/assignment").json()["config"]["require_open_photo"] is False
    finally:
        _set(admin, "photo_sampling_pct", 10)
    # determinístico por asignación: ~10% de 1000 ids
    hits = sum(require_open_photo(uuid.uuid4(), 10) for _ in range(1000))
    assert 50 < hits < 170


# ---------------------------------------------------------------- B6 settings
def test_settings_list_put_validation_and_audit(admin, ops, sup1):
    lst = admin.get("/v1/admin/settings").json()
    keys = {s["key"] for s in lst}
    assert keys >= {"cash_difference_threshold_cents", "cash_difference_severe_cents", "cancel_window_minutes", "gps_interval_seconds", "photo_sampling_pct", "evidence_retention_days", "gps_retention_days", "daily_sales_target_default_cents", "inventory_count_tolerance_units"}
    item = next(s for s in lst if s["key"] == "gps_interval_seconds")
    assert set(item) >= {"key", "value", "type", "description", "updated_at"} and item["type"] == "int"
    # tipo inválido → 422
    r = admin.put("/v1/admin/settings/gps_interval_seconds", json={"value": "rápido"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION"
    r = admin.put("/v1/admin/settings/gps_interval_seconds", json={"value": True})
    assert r.status_code == 422
    r = admin.put("/v1/admin/settings/photo_sampling_pct", json={"value": 150})
    assert r.status_code == 422
    assert admin.put("/v1/admin/settings/no_existe", json={"value": 1}).status_code == 404
    # ops no puede escribir (sólo admin); sí leer
    assert ops.put("/v1/admin/settings/gps_interval_seconds", json={"value": 60}).status_code == 403
    assert ops.get("/v1/admin/settings").status_code == 200
    assert sup1.get("/v1/admin/settings").status_code == 403
    out = _set(admin, "gps_interval_seconds", 60)
    assert out["value"] == 60 and out["updated_at"]
    try:
        log = admin.get("/v1/audit-log", params={"entity": "setting"}).json()
        e = next(x for x in log if x["action"] == "settings.update" and x["after"]["key"] == "gps_interval_seconds")
        assert e["before"]["value"] == 120 and e["after"]["value"] == 60
    finally:
        _set(admin, "gps_interval_seconds", 120)


def test_cash_threshold_setting_changes_next_close(fresh_operator, catalog, admin):
    op = fresh_operator()
    try:
        _set(admin, "cash_difference_threshold_cents", 6000)
        assert op.get("/v1/me/assignment").json()["config"]["cash_difference_threshold_cents"] == 6000
        shift_id = _open(op)
        op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=2, pres_index=2))  # 9000 cash
        r = op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 4000})  # -5000 < 6000
        assert r.status_code == 200 and r.json()["case_id"] is None and r.json()["status"] == "reconciled", r.text
    finally:
        _set(admin, "cash_difference_threshold_cents", 2000)
    # con el umbral por defecto, el mismo faltante sí abre caso
    op2 = fresh_operator()
    shift_id = _open(op2)
    op2.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=2, pres_index=2))
    r = op2.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 4000})
    assert r.json()["case_id"] and r.json()["status"] == "difference"


def test_cash_difference_rule_uses_settings_unless_overridden(fresh_operator, catalog, admin, ops):
    def cases(point_id):
        return [c for c in ops.get("/v1/cases", params={"point_id": point_id, "status": "open,in_progress"}).json() if c["rule_key"] == "cash_difference"]

    op = fresh_operator()
    try:
        _set(admin, "cash_difference_threshold_cents", 6000)
        shift_id = _open(op)
        op.post("/v1/sales", json=sale_payload(shift_id, catalog, qty=2, pres_index=2))
        assert op.post(f"/v1/shifts/{shift_id}/close", json={"idempotency_key": new_key(), "cash_counted_cents": 4000}).json()["case_id"] is None
        ops.post("/v1/rules/run")
        assert cases(op.point["id"]) == []  # la regla lee settings (6000)
        # override explícito en rules.params tiene precedencia
        r = ops.put("/v1/rules/cash_difference", json={"params": {"threshold_cents": 1000}})
        assert r.status_code == 200 and r.json()["params"]["threshold_cents"] == 1000
        ops.post("/v1/rules/run")
        assert len(cases(op.point["id"])) == 1
        # quitar el override (null) → vuelve a settings
        r = ops.put("/v1/rules/cash_difference", json={"params": {"threshold_cents": None}})
        assert "threshold_cents" not in r.json()["params"]
    finally:
        ops.put("/v1/rules/cash_difference", json={"params": {"threshold_cents": None, "severe_cents": None}})
        _set(admin, "cash_difference_threshold_cents", 2000)


def test_cancel_window_from_settings(fresh_operator, catalog, admin):
    op = fresh_operator()
    shift_id = _open(op)
    sale_id = op.post("/v1/sales", json=sale_payload(shift_id, catalog)).json()["sale_id"]
    try:
        _set(admin, "cancel_window_minutes", 0)
        assert op.get("/v1/me/assignment").json()["config"]["cancel_window_minutes"] == 0
        r = op.post(f"/v1/sales/{sale_id}/cancel", json={"idempotency_key": new_key(), "reason_code": "error"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "CANCEL_NOT_ALLOWED"
        assert r.json()["error"]["details"]["cancel_window_minutes"] == 0
    finally:
        _set(admin, "cancel_window_minutes", 5)
    r = op.post(f"/v1/sales/{sale_id}/cancel", json={"idempotency_key": new_key(), "reason_code": "error"})
    assert r.status_code == 200, r.text


def test_inventory_tolerance_from_settings(fresh_operator, catalog, admin):
    op = fresh_operator()
    shift_id = _open(op)
    pres = catalog["presentations"][0]["id"]
    try:
        _set(admin, "inventory_count_tolerance_units", 10)
        r = op.post("/v1/inventory/counts", json={"idempotency_key": new_key(), "shift_id": shift_id, "counts": {pres: 5}})  # teórico 0 → dif 5 ≤ 10
        assert r.status_code == 200, r.text
        cases = [c for c in admin.get("/v1/cases", params={"point_id": op.point["id"], "status": "open"}).json() if c["rule_key"] == "inventory_inconsistent"]
        assert cases == []
    finally:
        _set(admin, "inventory_count_tolerance_units", 3)


def test_purge_old_gps(fresh_operator, db_session):
    from app.core.timeutil import utcnow
    from app.models.ops import GpsPing
    from app.services.rules_engine import purge_old_gps

    op = fresh_operator()
    shift_id = _open(op)
    old = GpsPing(shift_id=uuid.UUID(shift_id), user_id=uuid.UUID(op.user["id"]), at=utcnow() - timedelta(days=100), lat=19.4, lng=-99.1)
    recent = GpsPing(shift_id=uuid.UUID(shift_id), user_id=uuid.UUID(op.user["id"]), at=utcnow() - timedelta(days=1), lat=19.4, lng=-99.1)
    db_session.add_all([old, recent])
    db_session.commit()
    old_id, recent_id = old.id, recent.id
    n = purge_old_gps(db_session, utcnow())
    db_session.commit()
    db_session.expunge_all()
    assert n >= 1
    assert db_session.get(GpsPing, old_id) is None and db_session.get(GpsPing, recent_id) is not None


# ---------------------------------------------------------------- B8 ventana de precio
def test_offline_sale_with_recently_deactivated_price_version(fresh_operator, catalog, admin, ops, db_session):
    from app.core.timeutil import utcnow
    from app.models.catalog import PriceVersion

    prices = {p["id"]: p["price_cents"] + 500 for p in catalog["presentations"]}
    v2 = admin.post("/v1/admin/price-versions", json={"name": f"v2-{uuid.uuid4().hex[:6]}", "valid_from": (utcnow() - timedelta(days=2)).isoformat(), "prices": prices}).json()
    assert v2["is_active"] and v2["deactivated_at"] is None
    op = fresh_operator()
    shift_id = _open(op)
    try:
        # desactivar → deactivated_at
        r = admin.patch(f"/v1/admin/price-versions/{v2['id']}", json={"is_active": False})
        assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["deactivated_at"], r.text
        assert r.json()["sales_count"] == 0
        # simular desactivación hace 1 h
        pv = db_session.get(PriceVersion, uuid.UUID(v2["id"]))
        pv.deactivated_at = utcnow() - timedelta(hours=1)
        db_session.commit()
        pres = catalog["presentations"][0]
        body = {
            "idempotency_key": new_key(), "shift_id": shift_id, "price_version_id": v2["id"], "offline_created": True,
            "occurred_at": (utcnow() - timedelta(minutes=30)).isoformat(),
            "lines": [{"presentation_id": pres["id"], "qty": 1}], "payments": [{"method": "cash", "amount_cents": prices[pres["id"]]}],
        }
        r = op.post("/v1/sales", json=body)
        assert r.status_code == 201, r.text
        sale = ops.get(f"/v1/sales/{r.json()['sale_id']}").json()
        assert sale["price_version_stale"] is True and sale["total_cents"] == prices[pres["id"]]
        # desactivada hace 4 días → rechazo claro
        pv.deactivated_at = utcnow() - timedelta(days=4)
        db_session.commit()
        body["idempotency_key"] = new_key()
        r = op.post("/v1/sales", json=body)
        assert r.status_code == 422 and r.json()["error"]["code"] == "PRICE_VERSION_INVALID", r.text
        assert "desactivada" in r.json()["error"]["message"] and r.json()["error"]["details"]["grace_hours"] == 72
        # versión inexistente
        body["idempotency_key"] = new_key()
        body["price_version_id"] = str(uuid.uuid4())
        assert op.post("/v1/sales", json=body).json()["error"]["message"] == "La versión de precio no existe"
        # reports/daily muestra stale_price_sales
        row = next(x for x in ops.get("/v1/reports/daily").json()["rows"] if x["shift_id"] == shift_id)
        assert row["stale_price_sales"] == 1
        assert ops.get("/v1/reports/daily").json()["totals"]["stale_price_sales"] >= 1
        # listado admin incluye deactivated_at y sales_count
        item = next(v for v in admin.get("/v1/admin/price-versions").json() if v["id"] == v2["id"])
        assert item["deactivated_at"] and item["sales_count"] == 1
        # venta normal con la versión vigente no queda marcada
        r = op.post("/v1/sales", json=sale_payload(shift_id, catalog))
        assert ops.get(f"/v1/sales/{r.json()['sale_id']}").json()["price_version_stale"] is False
    finally:
        pv = db_session.get(PriceVersion, uuid.UUID(v2["id"]))
        pv.is_active = False
        db_session.commit()
