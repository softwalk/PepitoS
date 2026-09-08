"""Smoke end-to-end contra el backend real: login op1 → abrir → 2 ventas → cerrar; verifica en la API.

Uso:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke.py [http://localhost:4173] [http://localhost:8000]
"""
import json
import sys
import time
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

# PNG 1×1 (el sello se dibuja sobre él; el servidor valida tipo y tamaño)
PNG_1X1 = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000201cb3e3b0e0000000049454e44ae426082")

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
API = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
SHOTS = sys.argv[3] if len(sys.argv) > 3 else None


def api(method, path, body=None, token=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def shot(page, name):
    if SHOTS:
        page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)



def skip_photo_if_asked(page):
    """Si hoy toca foto de muestreo (config.require_open_photo), continúa sin foto: la apertura/cierre nunca se bloquea."""
    try:
        page.wait_for_selector("[data-testid=photo-continue]", timeout=1500)
        page.click("[data-testid=photo-continue]")
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, geolocation={"latitude": 19.4235, "longitude": -99.163}, permissions=["geolocation"], locale="es-MX")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(APP + "/")
    page.wait_for_selector("text=ENTRAR", timeout=20000)
    shot(page, "01-login")
    page.fill("input[autocomplete=username]", "op1")
    page.fill("input[type=password]", "op123")
    page.click("text=ENTRAR")
    page.wait_for_selector("text=Bienvenido", timeout=15000)
    assert page.locator("text=Metro Insurgentes").count() >= 1, "Debe mostrar el punto"
    assert page.locator("text=C-001").count() >= 1, "Debe mostrar el carrito"
    shot(page, "02-bienvenida")
    page.wait_for_selector("text=ABRIR PUESTO", timeout=15000)
    shot(page, "03-home")
    device_id = page.evaluate("localStorage.getItem('pepito.device_id')")
    assert device_id and uuid.UUID(device_id), "device_id UUID persistido"

    # VENDER y CERRAR deshabilitados antes de abrir
    assert page.locator("button:has-text('VENDER')").is_disabled()
    assert page.locator("button:has-text('CERRAR PUESTO')").is_disabled()

    # token para consultar la API (mismo device_id → mismo Device)
    st, login = api("POST", "/v1/auth/login", {"username": "op1", "password": "op123", "device_id": device_id})
    token = login["access_token"]
    st, before = api("GET", "/v1/me/assignment", token=token)
    if before["active_shift"]:
        print("Ya había turno abierto en el servidor; la app lo adopta.")
    else:
        # ABRIR
        page.click("text=ABRIR PUESTO")
        page.wait_for_selector("text=Abrir puesto")
        yes = page.locator("button:has-text('Sí')")
        for i in range(yes.count()):
            yes.nth(i).click()
        shot(page, "04-abrir-checklist")
        page.click("button:has-text('SIGUIENTE: FONDO DE CAJA')")
        page.wait_for_selector("[data-testid=opening-cash]")
        # El fondo estándar ($500, Parámetros) viene propuesto; el vendedor lo corrige a $200 → aviso "distinto al estándar"
        assert page.locator("[data-testid=opening-cash] .amount-display").inner_text().replace(",", "").startswith("$500"), "Debe proponer el fondo estándar"
        for _ in range(3):
            page.click("[data-testid=opening-cash] .numpad button[aria-label='Borrar']")
        for ch in "200":  # fondo $200
            page.click(f"[data-testid=opening-cash] .numpad button[aria-label='{ch}']")
        page.wait_for_selector("[data-testid=float-diff]")
        shot(page, "04b-fondo-caja")
        page.click("button:has-text('LISTO'), button:has-text('SIGUIENTE: FOTO')")
        skip_photo_if_asked(page)
        page.wait_for_selector("text=LISTO PARA VENDER", timeout=20000)
        shot(page, "05-listo")
        page.click("button:has-text('VENDER')")

    st, a = api("GET", "/v1/me/assignment", token=token)
    assert a["active_shift"], "El turno debe existir en la API"
    shift_id = a["active_shift"]["id"]
    st, exp0 = api("GET", f"/v1/shifts/{shift_id}/expected", token=token)
    base_count = exp0["sales_count"]
    base_cash = exp0["cash_expected_cents"]
    if not before["active_shift"]:
        assert exp0["opening_cents"] == 20000, exp0

    # VENDER: 2 ventas en efectivo (1 toque cada una)
    if "vender" not in page.url:
        page.goto(APP + "/#/vender")
    page.wait_for_selector("text=Ventas del turno")
    page.click("button.sale-btn >> nth=0")  # 50 g
    page.wait_for_selector("text=Venta registrada")
    shot(page, "06-venta-toast")
    time.sleep(1.8)
    page.click("button.sale-btn >> nth=2")  # 100 g
    page.wait_for_selector("text=Venta registrada")
    # esperar sincronización
    for _ in range(30):
        if page.locator("text=Guardado").count() and not page.locator("text=Pendiente de enviar").count():
            break
        time.sleep(0.5)
    shot(page, "07-vender")
    st, exp1 = api("GET", f"/v1/shifts/{shift_id}/expected", token=token)
    assert exp1["sales_count"] == base_count + 2, f"Deben existir 2 ventas nuevas en la API: {exp1}"
    assert exp1["cash_expected_cents"] == base_cash + 2500 + 4500, f"Efectivo esperado incorrecto: {exp1}"
    print("Ventas confirmadas en API:", exp1["sales_count"], "efectivo", exp1["cash_expected_cents"])

    # DEVOLUCIÓN / CAJA: gasto de $30 (hielo) y devolución de la última venta (100 g) → caso de revisión
    page.click("[data-testid=go-returns]")
    page.wait_for_selector("text=¿Qué venta devolvió el cliente?")
    page.click("[data-testid=return-sale] >> nth=0")
    page.click("[data-testid=return-confirm]")
    page.wait_for_selector("text=Devolución registrada", timeout=15000)
    shot(page, "07b-devolucion")
    page.click("button:has-text('Seguir vendiendo')")
    page.click("[data-testid=go-returns]")
    page.click("[role=tab]:has-text('Caja')")
    page.click(".chip:has-text('Hielo')")
    for ch in "30":
        page.click(f".numpad button[aria-label='{ch}']")
    page.click("[data-testid=cash-confirm]")
    page.wait_for_selector("text=Gasto registrado", timeout=15000)
    shot(page, "07c-gasto")
    page.click("button:has-text('Seguir vendiendo')")
    for _ in range(30):
        if page.locator("text=Guardado").count() and not page.locator("text=Pendiente de enviar").count():
            break
        time.sleep(0.5)
    st, exp1 = api("GET", f"/v1/shifts/{shift_id}/expected", token=token)
    assert exp1["sales_count"] == base_count + 1 and exp1["cash_out_cents"] == 3000, f"Devolución/gasto no reflejados: {exp1}"
    assert exp1["cash_expected_cents"] == base_cash + 2500 - 3000, f"Esperado tras devolución y gasto: {exp1}"
    st, cases = api("GET", "/v1/cases?status=open", token=api("POST", "/v1/auth/login", {"username": "sup1", "password": "sup123", "device_id": device_id + "-sup"})[1]["access_token"])
    assert any(c.get("rule_key") == "sale_return" for c in cases), "Debe existir el caso de devolución"
    print("Devolución y gasto confirmados; esperado", exp1["cash_expected_cents"])

    # RECIBIR / CONTAR producto
    page.goto(APP + "/#/recibir")
    page.wait_for_selector("text=Recibir producto")
    page.click("[data-testid=qty-50] button[aria-label='Más 50 g']")
    page.click("[data-testid=qty-50] button[aria-label='Más 50 g']")
    page.click("[data-testid=receive-confirm]")
    page.wait_for_selector("text=Producto recibido")
    shot(page, "07d-recibir")
    page.goto(APP + "/#/contar")
    page.wait_for_selector("text=Contar producto")
    page.wait_for_timeout(800)
    # Total en kilogramos visible (piezas × gramos) y foto del producto con sello de fecha/hora
    kg_text = page.locator("[data-testid=count-kg-value]").inner_text()
    assert kg_text.endswith("kg"), kg_text
    page.set_input_files("[data-testid=count-photo-input]", {"name": "producto.png", "mimeType": "image/png", "buffer": PNG_1X1})
    page.wait_for_selector("[data-testid=count-photo-stamp]", timeout=10000)
    stamp = page.locator("[data-testid=count-photo-stamp]").inner_text()
    assert "Conteo ·" in stamp and "Metro Insurgentes" in stamp, stamp
    shot(page, "07e-contar-foto")
    page.click("[data-testid=count-confirm]")
    page.wait_for_selector("text=Conteo registrado")
    for _ in range(30):
        if page.locator("text=Guardado").count() and not page.locator("text=Pendiente de enviar").count():
            break
        time.sleep(0.5)
    st, counts = api("GET", "/v1/inventory/counts?days=1", token=api("POST", "/v1/auth/login", {"username": "admin", "password": "admin123", "device_id": device_id + "-adm"})[1]["access_token"])
    mine = [c for c in counts["counts"] if c["shift_id"] == shift_id]
    assert mine and mine[0]["evidence"] and mine[0]["evidence"][0]["kind"] == "inventory_count", mine
    assert abs(float(kg_text.replace(",", "").split()[0]) - mine[0]["counted_kg"]) < 0.01, (mine[0]["counted_kg"], kg_text)
    print("Conteo con foto sellada:", mine[0]["counted_kg"], "kg;", stamp.replace(chr(10), " | "))

    # CERRAR: paso 1
    page.goto(APP + "/#/cerrar")
    page.wait_for_selector("text=Debes tener")
    page.wait_for_function("document.querySelector('.big-money') && document.querySelector('.big-money').textContent.trim() !== '…'")
    shown = page.locator(".big-money").inner_text()
    print("Debes tener:", shown)
    pesos = exp1["cash_expected_cents"] // 100
    for ch in str(pesos):
        page.click(f".numpad button[aria-label='{ch}']")
    shot(page, "08-cerrar-caja")
    page.click("button:has-text('CONTINUAR')")
    page.wait_for_selector("text=¿Cuánto producto queda?")
    shot(page, "09-cerrar-producto")
    page.click("button:has-text('CONTINUAR')")
    page.wait_for_selector("text=Antes de irte")
    yes = page.locator("button:has-text('Sí')")
    for i in range(yes.count()):
        yes.nth(i).click()
    shot(page, "10-cerrar-checklist")
    page.click("button:has-text('CERRAR PUESTO'), button:has-text('SIGUIENTE: FOTO')")
    skip_photo_if_asked(page)
    page.wait_for_selector("text=Cierre conciliado", timeout=20000)
    shot(page, "11-cierre-ok")
    page.click("button:has-text('Terminar')")
    page.wait_for_selector("text=ABRIR PUESTO")
    shot(page, "12-home-final")

    st, closed = api("GET", f"/v1/shifts/{shift_id}", token=token)
    print("Turno en API:", closed["status"], "close_status:", closed.get("close_status"), "diff:", closed.get("difference_cents"))
    assert closed["status"] == "closed", closed
    assert closed.get("close_status") == "reconciled", closed
    st, a2 = api("GET", "/v1/me/assignment", token=token)
    assert a2["active_shift"] is None
    assert page.locator("button:has-text('ABRIR PUESTO')").is_disabled(), "Asignación terminada → ABRIR deshabilitado"

    # PWA: manifest + service worker registrado
    sw = page.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r)")
    manifest = page.evaluate("fetch('/manifest.webmanifest').then(r => r.json())")
    print("SW registrado:", sw, "| manifest:", manifest["name"])
    assert manifest["lang"] == "es-MX"
    assert not errors, errors
    browser.close()
    print("SMOKE OK")
