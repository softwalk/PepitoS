"""Smoke de refresh: login → sin red: venta → el access token local se invalida (simula expiración) → reinicio
de la app → vuelve la red → la app refresca el token con el refresh token y la venta se sincroniza sin pedir login.

Uso:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_refresh.py [APP] [API]
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
API = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

READ_SESSION = """
() => new Promise((resolve, reject) => {
  const req = indexedDB.open('pepito-operator');
  req.onerror = () => reject(req.error);
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction('session', 'readonly');
    const get = tx.objectStore('session').get('current');
    get.onsuccess = () => { db.close(); resolve(get.result || null); };
    get.onerror = () => reject(get.error);
  };
})
"""

TAMPER_SESSION = """
() => new Promise((resolve, reject) => {
  const req = indexedDB.open('pepito-operator');
  req.onerror = () => reject(req.error);
  req.onsuccess = () => {
    const db = req.result;
    const tx = db.transaction('session', 'readwrite');
    const store = tx.objectStore('session');
    const get = store.get('current');
    get.onsuccess = () => {
      const s = get.result;
      s.access_token = 'invalid.' + s.access_token.slice(0, 20);
      store.put(s);
    };
    tx.oncomplete = () => { db.close(); resolve(true); };
    tx.onerror = () => reject(tx.error);
  };
})
"""


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
    page.fill("input[autocomplete=username]", "op1")
    page.fill("input[type=password]", "op123")
    page.click("text=ENTRAR")
    page.wait_for_selector("text=ABRIR PUESTO", timeout=15000)
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)

    session0 = page.evaluate(READ_SESSION)
    assert session0 and session0.get("refresh_token"), "La sesión local debe guardar refresh_token"
    assert session0.get("refresh_expires_at"), "La sesión local debe guardar refresh_expires_at"
    device_id = session0["device_id"]

    # Token propio para consultar la API (otro device_id: no invalida el refresh token de la app).
    st, login = api("POST", "/v1/auth/login", {"username": "op1", "password": "op123", "device_id": device_id + "-smoke"})
    assert st == 200, login
    token = login["access_token"]
    st, a = api("GET", "/v1/me/assignment", token=token)
    if not a["active_shift"]:
        page.click("text=ABRIR PUESTO")
        page.wait_for_selector("text=Abrir puesto")
        yes = page.locator("button:has-text('Sí')")
        for i in range(yes.count()):
            yes.nth(i).click()
        page.click("button:has-text('LISTO'), button:has-text('SIGUIENTE: FOTO')")
        skip_photo_if_asked(page)
        page.wait_for_selector("text=LISTO PARA VENDER", timeout=20000)
        st, a = api("GET", "/v1/me/assignment", token=token)
    assert a["active_shift"], "Debe haber turno abierto"
    shift_id = a["active_shift"]["id"]
    st, exp0 = api("GET", f"/v1/shifts/{shift_id}/expected", token=token)
    base_count = exp0["sales_count"]

    # --- sin red: una venta queda en cola ---
    ctx.set_offline(True)
    page.goto(APP + "/#/vender")
    page.wait_for_selector("text=Ventas del turno")
    page.click("button.sale-btn >> nth=0")  # 50 g
    page.wait_for_selector("text=Venta registrada")
    page.wait_for_selector("text=Pendiente de enviar", timeout=10000)

    # El access token "expira" mientras no hay red: lo sustituimos por uno inválido en IndexedDB.
    page.evaluate(TAMPER_SESSION)
    tampered = page.evaluate(READ_SESSION)
    assert tampered["access_token"].startswith("invalid."), tampered

    # Reinicio de la app sin red: carga la sesión inválida de IndexedDB.
    page.reload()
    page.wait_for_selector("text=Ventas del turno", timeout=20000)
    assert page.locator("text=ENTRAR").count() == 0, "No debe pedir login"

    # --- vuelve la red: 401 → refresh → reintento del batch ---
    ctx.set_offline(False)
    for _ in range(60):
        st, exp1 = api("GET", f"/v1/shifts/{shift_id}/expected", token=token)
        if exp1["sales_count"] == base_count + 1:
            break
        time.sleep(0.5)
    else:
        raise AssertionError(f"La venta no se sincronizó tras el refresh: {exp1}")
    page.wait_for_function("!document.body.innerText.includes('Pendiente de enviar')", timeout=15000)
    assert page.locator("text=ENTRAR").count() == 0, "No debe pedir login tras refrescar"

    session1 = page.evaluate(READ_SESSION)
    assert not session1["access_token"].startswith("invalid."), "El access token debe haberse reemplazado"
    assert session1["refresh_token"] != session0["refresh_token"], "El refresh token debe haber rotado"
    assert session1["device_id"] == device_id
    # El refresh token anterior ya no sirve (rotación).
    st, old = api("POST", "/v1/auth/refresh", {"refresh_token": session0["refresh_token"], "device_id": device_id})
    assert st == 401 and old["error"]["code"] == "AUTH_INVALID", old
    print("Venta sincronizada tras refresh; tokens rotados. Ventas en API:", exp1["sales_count"])

    # Dejar el turno cerrado para que el smoke normal pueda repetirse.
    page.goto(APP + "/#/cerrar")
    page.wait_for_selector("text=Debes tener")
    page.wait_for_function("document.querySelector('.big-money') && document.querySelector('.big-money').textContent.trim() !== '…'")
    st, exp2 = api("GET", f"/v1/shifts/{shift_id}/expected", token=token)
    for ch in str(exp2["cash_expected_cents"] // 100):
        page.click(f".numpad button[aria-label='{ch}']")
    page.click("button:has-text('CONTINUAR')")
    page.wait_for_selector("text=¿Cuánto producto queda?")
    page.click("button:has-text('CONTINUAR')")
    page.wait_for_selector("text=Antes de irte")
    yes = page.locator("button:has-text('Sí')")
    for i in range(yes.count()):
        yes.nth(i).click()
    page.click("button:has-text('CERRAR PUESTO'), button:has-text('SIGUIENTE: FOTO')")
    skip_photo_if_asked(page)
    page.wait_for_selector("text=Cierre conciliado", timeout=20000)
    page.click("button:has-text('Terminar')")
    page.wait_for_selector("text=ABRIR PUESTO")

    assert not errors, errors
    browser.close()
    print("SMOKE REFRESH OK")
