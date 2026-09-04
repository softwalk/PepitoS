"""Smoke de foto por muestreo: admin fuerza `photo_sampling_pct=100` → op1 abre el puesto con foto del puesto
(PNG generado, cargado en el input con set_input_files) → `GET /v1/evidence?entity=shift&entity_id=…` la lista →
cierra también con foto → 2 evidencias. Además prueba: apertura sin red con foto (viaja en la cola) y "Continuar sin foto".
Al final restaura `photo_sampling_pct=10`.

Uso:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_photo.py [http://localhost:4173] [http://localhost:8000]
Requiere que op1 tenga la asignación de hoy en `planned` (scripts/reset-demo-op1.sql).
"""
import json
import struct
import sys
import time
import urllib.request
import zlib

from playwright.sync_api import sync_playwright

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
API = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"


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


def make_png(width=1600, height=1200, color=(232, 89, 12)):
    """PNG RGB sin dependencias (más grande que 1280 px para forzar la reducción en el cliente)."""
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


DB_URL = "postgresql://pepito:pepito@localhost:5433/pepito"


def reset_assignment():
    """Vuelve a dejar `planned` la asignación de hoy de op1 (sólo demo). False si no hay psql."""
    import os
    import shutil
    import subprocess

    if not shutil.which("psql"):
        return False
    sql = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reset-demo-op1.sql")
    return subprocess.run(["psql", DB_URL, "-q", "-f", sql], capture_output=True).returncode == 0


def answer_all_yes(page):
    yes = page.locator("button:has-text('Sí')")
    for i in range(yes.count()):
        yes.nth(i).click()


adm = api("POST", "/v1/auth/login", {"username": "admin", "password": "admin123", "device_id": "smoke-photo-admin"})[1]["access_token"]
st, before = api("GET", "/v1/admin/settings/photo_sampling_pct", token=adm)
assert st == 200, before
original = before["value"]
st, r = api("PUT", "/v1/admin/settings/photo_sampling_pct", {"value": 100}, token=adm)
assert st == 200 and r["value"] == 100, r
# 422 si el valor es inválido (rango 0..100)
st, bad = api("PUT", "/v1/admin/settings/photo_sampling_pct", {"value": 150}, token=adm)
assert st == 422 and bad["error"]["code"] == "VALIDATION", bad

png = make_png()
try:
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
        device_id = page.evaluate("localStorage.getItem('pepito.device_id')")
        token = api("POST", "/v1/auth/login", {"username": "op1", "password": "op123", "device_id": device_id})[1]["access_token"]
        st, a = api("GET", "/v1/me/assignment", token=token)
        assert a["config"]["require_open_photo"] is True, a["config"]
        assert a["config"]["evidence_max_bytes"] == 3 * 1024 * 1024, a["config"]
        assert a["active_shift"] is None, "Debe empezar sin turno abierto (scripts/reset-demo-op1.sql)"
        # La config quedó cacheada en IndexedDB
        cfg = page.evaluate("""() => new Promise((res) => { const r = indexedDB.open('pepito-operator'); r.onsuccess = () => { const db = r.result; const tx = db.transaction('catalog'); const g = tx.objectStore('catalog').get('current'); g.onsuccess = () => res(g.result && g.result.config); }; })""")
        assert cfg and cfg["require_open_photo"] is True and cfg["gps_interval_seconds"] == a["config"]["gps_interval_seconds"], cfg

        # --- ABRIR sin red, con foto: la foto viaja dentro del comando shift_open de la cola ---
        ctx.set_offline(True)
        page.click("text=ABRIR PUESTO")
        page.wait_for_selector("text=Abrir puesto")
        answer_all_yes(page)
        page.click("button:has-text('SIGUIENTE: FOTO')")
        page.wait_for_selector("text=Toma una foto del puesto listo")
        page.set_input_files("[data-testid=photo-input]", {"name": "puesto.png", "mimeType": "image/png", "buffer": png})
        page.wait_for_selector("[data-testid=photo-preview]", timeout=15000)
        # Reducida en el cliente: ≤1280 px y JPEG
        dims = page.evaluate("() => { const i = document.querySelector('[data-testid=photo-preview]'); return [i.naturalWidth, i.naturalHeight, i.src.slice(0, 22)]; }")
        assert dims[0] == 1280 and dims[1] == 960 and dims[2] == "data:image/jpeg;base64", dims
        page.click("[data-testid=photo-continue]")
        page.wait_for_selector("text=LISTO PARA VENDER", timeout=30000)
        assert page.locator("text=Se enviará cuando haya señal").count() == 1
        # vuelve la red → sincroniza el shift_open con la foto
        ctx.set_offline(False)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        shift_id = None
        for _ in range(60):
            st, a = api("GET", "/v1/me/assignment", token=token)
            if a["active_shift"]:
                shift_id = a["active_shift"]["id"]
                break
            time.sleep(0.5)
        assert shift_id, "El turno abierto sin red (con foto) debe llegar a la API"
        st, ev = api("GET", f"/v1/evidence?entity=shift&entity_id={shift_id}", token=token)
        assert st == 200 and len(ev) == 1, ev
        e0 = ev[0]
        assert e0["kind"] == "shift_open" and e0["entity"] == "shift" and e0["entity_id"] == shift_id and e0["content_type"] == "image/jpeg", e0
        assert 0 < e0["size_bytes"] <= 3 * 1024 * 1024 and len(e0["sha256"]) == 64 and e0["url"], e0
        # El archivo se sirve con Bearer
        req = urllib.request.Request(API + e0["url"] if e0["url"].startswith("/") else e0["url"])
        req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req) as r:
            data = r.read()
        assert data[:3] == b"\xff\xd8\xff" and len(data) == e0["size_bytes"], (len(data), e0["size_bytes"])
        print("Evidencia de apertura:", e0["id"], e0["size_bytes"], "bytes", e0["url"])

        # --- CERRAR con foto (mismo flag) ---
        page.click("button:has-text('VENDER')")
        page.wait_for_selector("text=Ventas del turno")
        page.goto(APP + "/#/cerrar")
        page.wait_for_function("document.querySelector('.big-money') && document.querySelector('.big-money').textContent.trim() !== '…'")
        page.click(".numpad button[aria-label='0']")
        page.click("button:has-text('CONTINUAR')")
        page.wait_for_selector("text=¿Cuánto producto queda?")
        page.click("button:has-text('CONTINUAR')")
        page.wait_for_selector("text=Antes de irte")
        assert page.locator(".steps span").count() == 4, "Con foto el cierre tiene 4 pasos"
        answer_all_yes(page)
        page.click("button:has-text('SIGUIENTE: FOTO')")
        page.wait_for_selector("text=Toma una foto del puesto listo")
        page.set_input_files("[data-testid=photo-input]", {"name": "cierre.png", "mimeType": "image/png", "buffer": png})
        page.wait_for_selector("[data-testid=photo-preview]", timeout=15000)
        page.click("[data-testid=photo-continue]")
        page.wait_for_selector("text=Cierre conciliado", timeout=20000)
        page.click("button:has-text('Terminar')")
        page.wait_for_selector("text=ABRIR PUESTO")
        st, ev = api("GET", f"/v1/evidence?entity=shift&entity_id={shift_id}", token=token)
        assert len(ev) == 2 and sorted(e["kind"] for e in ev) == ["shift_close", "shift_open"], ev
        assert api("GET", "/v1/me/assignment", token=token)[1]["active_shift"] is None

        # --- "Continuar sin foto" no bloquea la apertura (requiere psql para reponer la asignación; si no hay, se omite) ---
        if reset_assignment():
            page.reload()
            page.wait_for_selector("button:has-text('ABRIR PUESTO'):not([disabled])", timeout=20000)
            page.click("text=ABRIR PUESTO")
            page.wait_for_selector("text=Abrir puesto")
            answer_all_yes(page)
            page.click("button:has-text('SIGUIENTE: FOTO')")
            page.wait_for_selector("[data-testid=photo-continue]:has-text('Continuar sin foto')")
            page.click("[data-testid=photo-continue]")
            page.wait_for_selector("text=LISTO PARA VENDER", timeout=30000)
            st, a = api("GET", "/v1/me/assignment", token=token)
            shift2 = a["active_shift"]["id"]
            st, ev2 = api("GET", f"/v1/evidence?entity=shift&entity_id={shift2}", token=token)
            assert ev2 == [], ev2
            # cerrar sin foto para dejar limpio
            page.click("button:has-text('VENDER')")
            page.goto(APP + "/#/cerrar")
            page.wait_for_function("document.querySelector('.big-money') && document.querySelector('.big-money').textContent.trim() !== '…'")
            page.click(".numpad button[aria-label='0']")
            page.click("button:has-text('CONTINUAR')")
            page.click("button:has-text('CONTINUAR')")
            answer_all_yes(page)
            page.click("button:has-text('SIGUIENTE: FOTO')")
            page.click("[data-testid=photo-continue]")
            page.wait_for_selector("text=Cierre conciliado", timeout=20000)
            page.click("button:has-text('Terminar')")
            page.wait_for_selector("text=ABRIR PUESTO")
            print("Apertura/cierre sin foto OK:", shift2)
        else:
            print("psql no disponible: se omite la prueba 'Continuar sin foto'")
        assert not errors, errors
        browser.close()
        print("SMOKE PHOTO OK · shift", shift_id, "· evidencias:", [(e["kind"], e["size_bytes"]) for e in ev])
finally:
    st, r = api("PUT", "/v1/admin/settings/photo_sampling_pct", {"value": original if isinstance(original, int) else 10}, token=adm)
    assert st == 200 and r["value"] == (original if isinstance(original, int) else 10), r
    print("photo_sampling_pct restaurado a", r["value"])
