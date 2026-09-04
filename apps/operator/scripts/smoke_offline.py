"""Smoke offline: login → sin red: abrir + 2 ventas + deshacer 1 + merma → reinicio de la app → vuelve la red → todo sincroniza.

Uso:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_offline.py [APP] [API]
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
API = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"


def api(method, path, body=None, token=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, geolocation={"latitude": 19.4235, "longitude": -99.163}, permissions=["geolocation"])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(APP + "/")
    page.wait_for_selector("text=ENTRAR")
    page.fill("input[autocomplete=username]", "op1")
    page.fill("input[type=password]", "op123")
    page.click("text=ENTRAR")
    page.wait_for_selector("text=ABRIR PUESTO", timeout=15000)
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    device_id = page.evaluate("localStorage.getItem('pepito.device_id')")
    token = api("POST", "/v1/auth/login", {"username": "op1", "password": "op123", "device_id": device_id})["access_token"]
    assert api("GET", "/v1/me/assignment", token=token)["active_shift"] is None, "Debe empezar sin turno abierto"

    # --- sin red ---
    ctx.set_offline(True)
    page.click("text=ABRIR PUESTO")
    page.wait_for_selector("text=Abrir puesto")
    yes = page.locator("button:has-text('Sí')")
    for i in range(yes.count()):
        yes.nth(i).click()
    page.click("button:has-text('LISTO')")
    page.wait_for_selector("text=LISTO PARA VENDER", timeout=30000)
    assert page.locator("text=Se enviará cuando haya señal").count() == 1
    page.click("button:has-text('VENDER')")
    page.wait_for_selector("text=Ventas del turno")
    page.click("button.sale-btn >> nth=1")  # 75 g
    page.wait_for_selector("text=Venta registrada")
    time.sleep(1.7)
    page.click("button.sale-btn >> nth=1")  # 75 g
    page.wait_for_selector("text=Venta registrada")
    page.click("button:has-text('Deshacer')")  # aún en cola → se elimina
    page.wait_for_function("document.querySelector('.counter .n').textContent.trim() === '1'")
    # merma: 1 unidad de 50 g por derrame
    page.click("button:has-text('MERMA')")
    page.click("button.sale-btn >> nth=0")
    page.click("button:has-text('1')")
    page.click("button:has-text('derramó')")
    page.wait_for_selector("text=Merma registrada")
    pend = page.locator(".pill:has-text('Pendiente de enviar')").inner_text()
    print("Estado sin red:", pend)
    assert "Pendiente de enviar" in pend
    assert api("GET", "/v1/me/assignment", token=token)["active_shift"] is None, "Nada debe haber llegado al servidor aún"

    # --- reinicio de la app (sigue sin red): debe restaurar turno y cola ---
    page.goto(APP + "/#/")
    page.reload()
    page.wait_for_selector("button:has-text('VENDER')", timeout=20000)
    assert page.locator(".counter").count() == 0  # estamos en Home, no en Vender
    assert not page.locator("button:has-text('VENDER')").is_disabled(), "Turno restaurado tras reinicio"
    page.wait_for_selector(".pill:has-text('Pendiente de enviar')")
    print("Reinicio offline OK:", page.locator(".pill:has-text('Pendiente de enviar')").inner_text())

    # --- vuelve la red ---
    ctx.set_offline(False)
    page.evaluate("window.dispatchEvent(new Event('online'))")
    for _ in range(60):
        if page.locator(".pill:has-text('Guardado')").count() == 1:
            break
        time.sleep(0.5)
    assert page.locator(".pill:has-text('Guardado')").count() == 1, "Debe quedar todo enviado"
    a = api("GET", "/v1/me/assignment", token=token)
    assert a["active_shift"], "El turno abierto offline debe existir en la API"
    exp = api("GET", f"/v1/shifts/{a['active_shift']['id']}/expected", token=token)
    print("API tras sincronizar:", exp)
    assert exp["sales_count"] == 1 and exp["cash_expected_cents"] == 3500, exp
    assert exp["waste_units"] == 1, exp

    # cerrar con red para dejar limpio
    page.goto(APP + "/#/cerrar")
    page.wait_for_function("document.querySelector('.big-money') && document.querySelector('.big-money').textContent.trim() === '$35'")
    for ch in "35":
        page.click(f".numpad button[aria-label='{ch}']")
    page.click("button:has-text('CONTINUAR')")
    page.click("button:has-text('CONTINUAR')")
    yes = page.locator("button:has-text('Sí')")
    for i in range(yes.count()):
        yes.nth(i).click()
    page.click("button:has-text('CERRAR PUESTO')")
    page.wait_for_selector("text=Cierre conciliado", timeout=20000)
    page.click("button:has-text('Terminar')")
    page.wait_for_selector("text=ABRIR PUESTO")
    assert api("GET", "/v1/me/assignment", token=token)["active_shift"] is None
    assert not errors, errors
    browser.close()
    print("SMOKE OFFLINE OK")
