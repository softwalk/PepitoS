"""Nombre de punto «Nombre - Score» en todo el sistema y ranking de vendedores (día/mes/año) guardado en users."""
from tests.conftest import new_key, open_payload, sale_payload


def test_point_display_name_concatenates_score(admin, ops, op1):
    pts = admin.get("/v1/admin/points").json()
    top = next(p for p in pts if p.get("meta", {}).get("ranking") == 1)
    assert top["score"] == 97 and top["display_name"] == f"{top['name']} - 97"
    manual = next(p for p in pts if not p.get("meta", {}).get("ranking"))
    assert manual["score"] is None and manual["display_name"] == manual["name"]
    # Control Tower y asignación del operador usan el nombre concatenado (los puntos demo no tienen score → sin sufijo)
    ct = ops.get("/v1/control-tower/summary").json()
    assert all(" - " not in p["point"]["name"] or p["point"]["score"] is not None for p in ct["points"])
    # Un punto del catálogo asignado se muestra con score
    me = op1.get("/v1/me/assignment").json()
    assert "score" in me["assignment"]["point"]


def test_sales_ranking_day_month_year(fresh_operator, catalog, admin, ops):
    a = fresh_operator()
    b = fresh_operator()
    sa = a.post("/v1/shifts/open", json=open_payload(a.assignment["id"])).json()["shift_id"]
    sb = b.post("/v1/shifts/open", json=open_payload(b.assignment["id"])).json()["shift_id"]
    for _ in range(3):
        assert a.post("/v1/sales", json=sale_payload(sa, catalog, pres_index=2)).status_code == 201  # 3 × 4500
    assert b.post("/v1/sales", json=sale_payload(sb, catalog, pres_index=0)).status_code == 201  # 2500
    r = ops.post("/v1/rules/run")
    assert r.status_code == 200 and "ranking" in r.json()
    lb = ops.get("/v1/people/ranking", params={"period": "day"}).json()["rows"]
    ra = next(x for x in lb if x["operator"]["id"] == a.user["id"])
    rb = next(x for x in lb if x["operator"]["id"] == b.user["id"])
    assert ra["total_cents"] == 13500 and rb["total_cents"] == 2500 and ra["rank"] < rb["rank"]
    assert ra["rank"] == 1  # nadie vende más hoy en la base de pruebas limpia
    # Guardado en el usuario (admin) y visible para el operador en /me/assignment
    ua = next(u for u in admin.get("/v1/admin/users").json() if u["id"] == a.user["id"])
    assert ua["ranking"]["day"] == 1 and ua["ranking"]["day_cents"] == 13500
    assert ua["ranking"]["month"] == 1 and ua["ranking"]["year"] == 1
    me = a.get("/v1/me/assignment").json()["ranking"]
    assert me["day"]["rank"] == 1 and me["month"]["total_cents"] >= 13500 and me["of"] >= 2
    # El cierre también recalcula: b vende más y cierra → pasa a #1
    for _ in range(5):
        b.post("/v1/sales", json=sale_payload(sb, catalog, pres_index=2))
    exp = b.get(f"/v1/shifts/{sb}/expected").json()
    r = b.post(f"/v1/shifts/{sb}/close", json={"idempotency_key": new_key(), "cash_counted_cents": exp["cash_expected_cents"], "product_counts": exp["product_expected"]})
    assert r.status_code == 200
    assert b.get("/v1/me/assignment").json()["ranking"]["day"]["rank"] == 1
    assert ops.get("/v1/people/ranking", params={"period": "bad"}).status_code == 422
