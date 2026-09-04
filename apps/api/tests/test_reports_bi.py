"""Módulo de Reportes (BI): catálogo por rol, RBAC en la API, alcance por zona/operador, periodos, hallazgos y auditoría."""
import pytest

from tests.conftest import Api, open_payload, sale_payload

ALL = ["executive", "sales", "cash", "points", "people", "inventory", "quality", "maintenance", "compliance", "expansion"]


@pytest.fixture(scope="module")
def finance(client):
    return Api(client, "finanzas", "fin123")


def _keys(api):
    cat = api.get("/v1/reports/bi").json()
    return {r["key"] for c in cat["categories"] for r in c["reports"]}


def test_catalog_per_role(admin, ops, finance, sup1, op1):
    assert _keys(admin) == set(ALL)
    assert _keys(ops) == set(ALL)
    assert _keys(finance) == set(ALL) - {"quality", "maintenance"}
    assert _keys(sup1) == set(ALL) - {"executive", "expansion"}
    assert _keys(op1) == {"sales", "people"}


def test_rbac_enforced_in_api_and_audited(finance, sup1, op1, admin):
    # Finanzas no ve calidad; supervisor no ve ejecutivo; operador no ve caja → 403 + audit_log
    for api, key in ((finance, "quality"), (sup1, "executive"), (op1, "cash")):
        r = api.get(f"/v1/reports/bi/{key}")
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "FORBIDDEN"
    log = admin.get("/v1/audit-log", params={"entity": "report", "limit": 50}).json()
    denied = [x for x in log if x["action"] == "report.view" and x["after"]["result"] == "denied"]
    assert {x["after"]["report"] for x in denied} >= {"quality", "executive", "cash"}
    assert admin.get("/v1/reports/bi/no-existe").status_code == 404


def test_every_report_renders_for_admin_all_presets(admin):
    for key in ALL:
        for preset in ("today", "yesterday", "last7", "week", "month", "prev_month", "year"):
            r = admin.get(f"/v1/reports/bi/{key}", params={"period": preset})
            assert r.status_code == 200, (key, preset, r.text)
            body = r.json()
            assert body["key"] == key and body["period"]["preset"] == preset and body["compare"]["from"] <= body["period"]["from"]
            assert isinstance(body["kpis"], list) and isinstance(body["charts"], list) and isinstance(body["tables"], list)
            for ins in body["insights"]:
                assert ins["kind"] in ("fact", "trend", "alert", "hypothesis", "recommendation")
    # export queda auditado como report.export
    assert admin.get("/v1/reports/bi/executive", params={"period": "today", "export": "true"}).status_code == 200
    log = admin.get("/v1/audit-log", params={"entity": "report", "limit": 5}).json()
    assert any(x["action"] == "report.export" and x["after"]["report"] == "executive" for x in log)


def test_custom_range_validation(admin):
    assert admin.get("/v1/reports/bi/sales", params={"period": "custom", "from": "2026-01-01", "to": "2025-12-31"}).status_code == 422
    assert admin.get("/v1/reports/bi/sales", params={"period": "custom", "from": "2024-01-01", "to": "2026-01-01"}).status_code == 422
    assert admin.get("/v1/reports/bi/sales", params={"period": "raro"}).status_code == 422
    r = admin.get("/v1/reports/bi/sales", params={"from": "2026-09-01", "to": "2026-09-03"})
    assert r.status_code == 200 and r.json()["period"]["preset"] == "custom" and r.json()["period"]["days"] == 3


def test_supervisor_scoped_to_zone_even_if_url_says_otherwise(fresh_operator, catalog, admin, sup1):
    zones = admin.get("/v1/admin/zones").json()
    centro = next(z for z in zones if z["name"] == "Centro")
    other = next(z for z in zones if z["name"] != "Centro")
    a = fresh_operator(zone_id=centro["id"])
    b = fresh_operator(zone_id=other["id"])
    sa = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    sb = b.post("/v1/shifts/open", json=open_payload(b.assignment["id"])).json()["shift_id"]
    assert a.post("/v1/sales", json=sale_payload(sa, catalog, pres_index=2)).status_code == 201
    assert b.post("/v1/sales", json=sale_payload(sb, catalog, pres_index=2)).status_code == 201
    r = sup1.get("/v1/reports/bi/sales", params={"period": "today", "zone_id": other["id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"]["zone_id"] == centro["id"] and body["scope"]["zone_locked"] is True
    points = {row["point_id"] for row in next(t for t in body["tables"] if t["key"] == "points")["rows"]}
    assert a.point["id"] in points and b.point["id"] not in points
    ops_rows = {row["operator_id"] for row in next(t for t in body["tables"] if t["key"] == "operators")["rows"]}
    assert a.user["id"] in ops_rows and b.user["id"] not in ops_rows
    # point_id de otra zona → sin filas, nunca datos ajenos
    r = sup1.get("/v1/reports/bi/points", params={"period": "today", "point_id": b.point["id"]})
    assert r.status_code == 200 and next(t for t in r.json()["tables"] if t["key"] == "ranking")["rows"] == []
    # admin sí ve ambas
    body = admin.get("/v1/reports/bi/sales", params={"period": "today"}).json()
    points = {row["point_id"] for row in next(t for t in body["tables"] if t["key"] == "points")["rows"]}
    assert {a.point["id"], b.point["id"]} <= points


def test_operator_only_sees_own_rows(fresh_operator, catalog):
    a = fresh_operator()
    b = fresh_operator()
    sa = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    sb = b.post("/v1/shifts/open", json=open_payload(b.assignment["id"])).json()["shift_id"]
    a.post("/v1/sales", json=sale_payload(sa, catalog))
    b.post("/v1/sales", json=sale_payload(sb, catalog))
    body = a.get("/v1/reports/bi/people", params={"period": "today", "operator_id": b.user["id"]}).json()
    rows = next(t for t in body["tables"] if t["key"] == "operators")["rows"]
    assert [r["operator_id"] for r in rows] == [a.user["id"]]
    assert body["scope"]["operator_locked"] is True


def test_partial_sections_by_role(ops, finance, admin):
    cash_ops = ops.get("/v1/reports/bi/cash", params={"period": "month"}).json()
    assert "approvals" in cash_ops["hidden"] and not any(t["key"] == "approvals" for t in cash_ops["tables"])
    cash_fin = finance.get("/v1/reports/bi/cash", params={"period": "month"}).json()
    assert any(t["key"] == "approvals" for t in cash_fin["tables"])
    people_fin = finance.get("/v1/reports/bi/people", params={"period": "month"}).json()
    assert "attendance" in people_fin["hidden"] and all("late" not in r for r in people_fin["tables"][0]["rows"])
    inv_fin = finance.get("/v1/reports/bi/inventory", params={"period": "month"}).json()
    assert "stock" in inv_fin["hidden"] and not any(t["key"] in ("stock", "lots") for t in inv_fin["tables"])
    inv_admin = admin.get("/v1/reports/bi/inventory", params={"period": "month"}).json()
    assert any(t["key"] == "stock" for t in inv_admin["tables"])


def test_executive_numbers_and_insights_from_data(fresh_operator, catalog, admin):
    a = fresh_operator()
    sa = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    for _ in range(4):
        a.post("/v1/sales", json=sale_payload(sa, catalog, pres_index=2))  # 4 × $45
    body = admin.get("/v1/reports/bi/executive", params={"period": "today", "point_id": a.point["id"]}).json()
    k = {x["key"]: x for x in body["kpis"]}
    assert k["sales"]["value"] == 18000 and k["tx"]["value"] == 4 and k["ticket"]["value"] == 4500 and k["ticket"]["tone"] == "ok"
    assert k["target_pct"]["value"] == round(18000 * 100 / 234000, 1)
    assert any(i["kind"] == "fact" and "Avance vs meta" in i["text"] for i in body["insights"])
    trend = next(c for c in body["charts"] if c["key"] == "trend")
    assert len(trend["data"]) == 24 and sum(r["sales_cents"] for r in trend["data"]) == 18000
    # Comparativo: ayer no hubo ventas en ese punto → delta None, tendencia plana
    assert k["sales"]["prev"] == 0 and k["sales"]["delta_pct"] is None


def test_options_scoped(admin, sup1):
    a = admin.get("/v1/reports/bi/options").json()
    s = sup1.get("/v1/reports/bi/options").json()
    assert len(a["zones"]) > 1 and len(s["zones"]) == 1 and s["zones"][0]["id"] == sup1.user["zone_id"]
    assert all(p["zone_id"] == sup1.user["zone_id"] for p in s["points"]) and len(s["points"]) < len(a["points"])
    assert a["presentations"] and a["methods"]
