"""Smoke end-to-end del backoffice contra `vite preview` y la API real.

Flujo: login ops → /ct (KPIs + puntos) → /excepciones (casos) → logout → login sup1 → /supervisor (bloques)
→ /supervisor/auditoria/<punto> envía auditoría con una no conformidad y una acción correctiva → aparece el caso con la acción
→ sesión: access token inválido en localStorage → la app refresca sola (tokens rotados) → admin restablece la contraseña de un
usuario temporal (modal con contraseña temporal) → ese usuario entra, es forzado a /cambiar-contrasena y, tras cambiarla, llega a su home.

Uso:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke.py [http://localhost:4174] [http://localhost:8000] [dir_screenshots]
"""
import json
import sys
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4174"
API = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
SHOTS = sys.argv[3] if len(sys.argv) > 3 else None


def api(method, path, body=None, token=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def shot(page, name, full=True):
    if SHOTS:
        page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)


def login(page, user, pwd):
    page.goto(APP + "/login")
    page.wait_for_selector("input[autocomplete=username]", timeout=20000)
    page.fill("input[autocomplete=username]", user)
    page.fill("input[type=password]", pwd)
    page.click("button:has-text('Entrar')")


def logout(page):
    page.click("aside >> text=Cerrar sesión")
    page.wait_for_selector("input[autocomplete=username]", timeout=10000)


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="es-MX")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 1) ops → Control Tower
    login(page, "ops", "ops123")
    page.wait_for_selector("[data-testid=points-table]", timeout=20000)
    assert page.locator("h1", has_text="Control Tower").count() == 1
    assert page.locator("[data-testid=points-table] tbody tr").count() >= 3, "Debe listar los 3 puntos"
    assert page.locator("[data-testid='kpi-Ventas hoy']").count() == 1
    assert page.locator("[data-testid='kpi-Ticket promedio']").count() == 1
    assert page.locator(".leaflet-marker-icon").count() >= 3, "Mapa con marcadores"
    page.wait_for_timeout(1500)  # tiles
    shot(page, "ct")

    # 2) Excepciones
    page.click("aside >> text=Excepciones")
    page.wait_for_selector("[data-testid=cases-table]", timeout=15000)
    n_cases = page.locator("[data-testid=cases-table] tbody tr").count()
    assert n_cases >= 1, "Debe listar casos"
    shot(page, "excepciones")

    # 3) Ventas
    page.click("aside >> text=Ventas")
    page.wait_for_selector("text=Ventas · reporte diario", timeout=15000)
    page.wait_for_selector("tfoot", timeout=15000)
    page.wait_for_timeout(800)
    shot(page, "ventas")
    logout(page)

    # 4) sup1 → Supervisor (viewport móvil)
    page.set_viewport_size({"width": 414, "height": 896})
    login(page, "sup1", "sup123")
    page.wait_for_selector("[data-testid=block-urgent]", timeout=20000)
    assert page.locator("[data-testid=block-review]").count() == 1
    assert page.locator("[data-testid=block-normal]").count() == 1
    assert page.locator(".bottom-nav").is_visible(), "Navegación inferior visible en móvil"
    assert page.locator("[data-testid=sev-card]").count() >= 1, "Debe haber tarjetas de casos"
    shot(page, "supervisor")

    # 5) Auditoría en el primer punto
    tok = api("POST", "/v1/auth/login", {"username": "sup1", "password": "sup123", "device_id": "smoke-sup1"})[1]["access_token"]
    points = api("GET", "/v1/admin/points", token=tok)[1]
    point = points[0]
    before = {c["id"] for c in api("GET", "/v1/cases?status=open,in_progress", token=tok)[1]}
    page.goto(APP + f"/supervisor/auditoria/{point['id']}")
    page.wait_for_selector("[data-testid=check-clean_ok]", timeout=15000)
    for key in ["clean_ok", "uniform_ok", "product_ok", "display_ok", "cart_secure", "pos_ok"]:
        page.click(f"[data-testid=check-{key}] button:has-text('Sí')")
    page.click("[data-testid=check-prices_visible] button:has-text('No')")  # no conformidad
    page.fill("textarea", "Smoke: precios no visibles, se indicó al operador colocar el letrero.")
    page.fill("input[placeholder='Qué debe corregirse']", "Colocar letrero de precios")
    page.click("button:has-text('+ Agregar')")
    assert page.locator("text=Colocar letrero de precios").count() >= 1
    page.click("button:has-text('Enviar auditoría')")
    page.wait_for_url("**/casos/**", timeout=20000)
    page.wait_for_selector("text=Acciones correctivas", timeout=15000)
    assert page.locator("text=No conformidades en auditoría").count() >= 1, "Debe abrir caso por no conformidad"
    assert page.locator("td", has_text="Colocar letrero de precios").count() >= 1, "La acción correctiva debe aparecer en el caso"
    after = {c["id"] for c in api("GET", "/v1/cases?status=open,in_progress", token=tok)[1]}
    new_ids = after - before
    assert new_ids, "La API debe reportar el caso nuevo"
    case = api("GET", f"/v1/cases/{list(new_ids)[0]}", token=tok)[1]
    assert any(a["description"] == "Colocar letrero de precios" for a in case["actions"]), "Acción correctiva persistida"
    shot(page, "caso-auditoria", full=False)

    # 6) Refresh: el access token guardado se invalida → la siguiente navegación refresca y rota tokens sin login
    page.set_viewport_size({"width": 1366, "height": 900})
    sess0 = page.evaluate("JSON.parse(localStorage.getItem('pepito.backoffice.session'))")
    assert sess0.get("refreshToken"), "La sesión debe guardar refreshToken"
    page.evaluate("() => { const s = JSON.parse(localStorage.getItem('pepito.backoffice.session')); s.token = 'invalid.' + s.token.slice(0, 20); localStorage.setItem('pepito.backoffice.session', JSON.stringify(s)); }")
    page.goto(APP + "/excepciones")
    page.wait_for_selector("[data-testid=cases-table]", timeout=15000)
    assert page.locator("input[autocomplete=username]").count() == 0, "No debe pedir login: refresca solo"
    sess1 = page.evaluate("JSON.parse(localStorage.getItem('pepito.backoffice.session'))")
    assert not sess1["token"].startswith("invalid."), "Access token reemplazado"
    assert sess1["refreshToken"] != sess0["refreshToken"], "Refresh token rotado"
    st, old = api("POST", "/v1/auth/refresh", {"refresh_token": sess0["refreshToken"], "device_id": page.evaluate("localStorage.getItem('pepito.device_id')")})
    assert st == 401 and old["error"]["code"] == "AUTH_INVALID", old
    logout(page)

    # 7) admin: restablecer contraseña de un usuario temporal → contraseña temporal en modal → login forzado a cambiarla
    adm = api("POST", "/v1/auth/login", {"username": "admin", "password": "admin123", "device_id": "smoke-admin"})[1]["access_token"]
    uname = f"smoke_pw_{uuid.uuid4().hex[:6]}"
    st, tmp_user = api("POST", "/v1/admin/users", {"username": uname, "name": "Smoke Reset", "role": "ops", "password": "inicial-123"}, token=adm)
    assert st in (200, 201), tmp_user
    try:
        login(page, "admin", "admin123")
        page.wait_for_selector("[data-testid=points-table]", timeout=20000)
        page.click("aside >> text=Administración")
        page.wait_for_selector(f"[data-testid=reset-password-{uname}]", timeout=15000)
        page.click(f"[data-testid=reset-password-{uname}]")
        page.click("[data-testid=reset-password-confirm]")
        page.wait_for_selector("[data-testid=temporary-password]", timeout=15000)
        temp_pw = page.locator("[data-testid=temporary-password]").inner_text().strip()
        assert len(temp_pw) >= 8, temp_pw
        page.click("button:has-text('Listo')")
        page.wait_for_selector("text=Debe cambiar contraseña", timeout=15000)
        shot(page, "admin-reset-password")
        st, users = api("GET", "/v1/admin/users", token=adm)
        assert next(u for u in users if u["username"] == uname)["must_change_password"] is True
        logout(page)

        login(page, uname, temp_pw)
        page.wait_for_url("**/cambiar-contrasena", timeout=15000)
        page.wait_for_selector("[data-testid=change-password-form]", timeout=15000)
        page.goto(APP + "/ct")  # Guard redirige de vuelta mientras must_change_password
        page.wait_for_url("**/cambiar-contrasena", timeout=15000)
        form = page.locator("[data-testid=change-password-form]")
        form.locator("input[autocomplete=current-password]").fill(temp_pw)
        form.locator("input[autocomplete=new-password]").nth(0).fill("nueva-clave-456")
        form.locator("input[autocomplete=new-password]").nth(1).fill("nueva-clave-456")
        shot(page, "cambiar-contrasena")
        page.click("button:has-text('Guardar contraseña')")
        page.wait_for_selector("[data-testid=points-table]", timeout=20000)
        assert "/ct" in page.url, page.url
        st, users = api("GET", "/v1/admin/users", token=adm)
        assert next(u for u in users if u["username"] == uname)["must_change_password"] is False
        st, relog = api("POST", "/v1/auth/login", {"username": uname, "password": "nueva-clave-456", "device_id": "smoke-tmp"})
        assert st == 200 and relog["must_change_password"] is False, relog
        # Cambio voluntario accesible desde el menú de usuario
        page.click("aside >> text=Cambiar contraseña")
        page.wait_for_selector("[data-testid=change-password-form]", timeout=15000)
        logout(page)
    finally:
        api("DELETE", f"/v1/admin/users/{tmp_user['id']}", token=adm)

    assert not errors, f"Errores JS en página: {errors}"
    print("SMOKE OK · casos listados:", n_cases, "· caso de auditoría:", case["id"], "·", case["title"], "· refresh + reset-password OK")
    browser.close()
