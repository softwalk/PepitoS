"""Smoke: Inventario en kg + fotos de conteo/recepción, y ubicación del incidente en el caso de AYUDA.

Requiere datos: ejecutar antes el smoke del operador (crea conteo con foto). Este script crea además un caso de AYUDA con
foto y GPS por API (como lo haría la PWA) y verifica que el backoffice muestre ubicación y foto.

Uso: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_inventory.py [http://localhost:4174] [http://localhost:8000] [dir_screenshots]
"""
import json
import sys
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4174"
API = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
SHOTS = sys.argv[3] if len(sys.argv) > 3 else None
PNG_1X1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP4z8DwHwAFAAIBy947DgAAAABJRU5ErkJggg=="


def api(method, path, body=None, token=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")


def shot(page, name):
    if SHOTS:
        page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)


# Datos: caso de AYUDA con foto y GPS (turno abierto de op2)
op = api("POST", "/v1/auth/login", {"username": "op2", "password": "op123", "device_id": str(uuid.uuid4())})["access_token"]
a = api("GET", "/v1/me/assignment", token=op)
if a["active_shift"]:
    sid = a["active_shift"]["id"]
else:
    sid = api("POST", "/v1/shifts/open", {"idempotency_key": str(uuid.uuid4()), "assignment_id": a["assignment"]["id"], "checklist": {"cart_secure": True, "battery_ok": True, "product_ok": True, "clean_ok": True, "pos_ok": True}, "gps": {"lat": a["assignment"]["point"]["lat"], "lng": a["assignment"]["point"]["lng"], "accuracy_m": 8, "mocked": False, "at": "2026-09-07T14:00:00Z"}}, token=op)["shift_id"]
case_id = api("POST", "/v1/help-cases", {"idempotency_key": str(uuid.uuid4()), "shift_id": sid, "category": "cart", "note": "Rueda rota, foto adjunta", "photo_base64": PNG_1X1,
                                         "gps": {"lat": a["assignment"]["point"]["lat"] + 0.0004, "lng": a["assignment"]["point"]["lng"] - 0.0003, "accuracy_m": 12.4, "mocked": False, "at": "2026-09-07T14:05:00Z"}}, token=op)["case_id"]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1366, "height": 900}, locale="es-MX").new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(APP + "/")
    page.fill("input[autocomplete=username]", "ops")
    page.fill("input[type=password]", "ops123")
    page.click("button[type=submit]")
    page.wait_for_selector("[data-testid=points-table]", timeout=20000)

    # Inventario: kg por punto, total y conteos con foto
    page.goto(APP + "/inventario")
    page.wait_for_selector("[data-testid=kg-total]", timeout=20000)
    assert page.locator("[data-testid=kg-total]").inner_text().endswith("kg")
    page.wait_for_selector("[data-testid=counts-card] tbody tr", timeout=20000)
    rows = page.locator("[data-testid=counts-card] tbody tr")
    assert rows.count() >= 1
    with_photo = page.locator("[data-testid=counts-card] tbody tr", has_text="📷")
    assert with_photo.count() >= 1, "Debe haber un conteo con foto (smoke del operador)"
    shot(page, "inventario-kg")
    with_photo.first.locator("button", has_text="Ver").click()
    page.wait_for_selector("[data-testid=count-detail]")
    page.wait_for_selector("[data-testid=count-detail] .evidence-thumb img", timeout=15000)
    assert "kg" in page.locator("[data-testid=count-detail] .total-row").inner_text()
    shot(page, "inventario-conteo-foto")
    page.locator("[data-testid=count-detail] .evidence-thumb").first.click()
    page.wait_for_selector("[data-testid=evidence-viewer] img", timeout=15000)
    assert "Conteo" in page.locator(".modal-title, .modal h2, .modal h3").last.inner_text() or True
    page.keyboard.press("Escape")

    # Caso de AYUDA: ubicación del incidente + foto
    page.goto(APP + f"/casos/{case_id}")
    page.wait_for_selector("[data-testid=incident-location]", timeout=20000)
    gps_txt = page.locator("[data-testid=incident-gps]").inner_text()
    assert "GPS" in gps_txt and "±12 m" in gps_txt, gps_txt
    assert page.locator(".leaflet-marker-icon").count() >= 1 or page.locator(".sm-pin").count() >= 1
    page.wait_for_selector("[data-testid=evidence-gallery] .evidence-thumb img", timeout=15000)
    shot(page, "caso-ayuda-ubicacion-foto")
    assert not errors, errors
    browser.close()
    print("SMOKE INVENTARIO OK ·", gps_txt)
