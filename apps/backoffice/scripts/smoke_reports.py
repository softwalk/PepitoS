"""Smoke E2E del módulo de Reportes contra `vite preview` y la API real.

Flujo: login admin → /reportes (centro con 8 categorías) → cada uno de los 10 reportes (KPIs, hallazgos, gráficas SVG,
tablas) con periodo «month» → filtros en URL (cambiar periodo y punto) → vista de impresión (sin nav, logo, KPIs)
→ logout → login sup1 (sin Ejecutivo/Expansión, filtro de zona bloqueado, alcance «tu zona») → móvil 390 px.
Uso:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_reports.py [http://localhost:4174] [dir_screenshots]
"""
import os
import sys

from playwright.sync_api import expect, sync_playwright

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4174"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/tmp/smoke-reports"
os.makedirs(SHOTS, exist_ok=True)
KEYS = ["executive", "sales", "cash", "points", "people", "inventory", "quality", "maintenance", "compliance", "expansion"]


def shot(page, name, full=False):
    page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)


def login(page, user, pwd):
    page.goto(APP + "/login")
    page.fill("input[autocomplete=username]", user)
    page.fill("input[type=password]", pwd)
    page.click("button:has-text('Entrar')")
    page.wait_for_url(lambda u: "/login" not in u)


def logout(page):
    page.click("aside >> text=Cerrar sesión")
    page.wait_for_url(lambda u: "/login" in u)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page, "admin", "admin123")
        page.click("aside >> text=Reportes")
        page.wait_for_url("**/reportes")
        expect(page.locator("[data-testid^=report-tile-]")).to_have_count(10)
        assert page.locator("[data-testid^=report-category-]").count() == 8, "8 categorías para admin"
        shot(page, "01-centro", full=True)

        for key in KEYS:
            page.goto(APP + f"/reportes/{key}?period=month")
            page.wait_for_selector("[data-testid=report-kpis] .kpi")
            page.wait_for_selector("[data-testid=report-insights]")
            assert page.locator("[data-testid=report-kpis] .kpi").count() >= 3, key
            assert page.locator(".report-chart").count() >= 1, key
            # recharts renderiza SVG (o heatmap div) — al menos un bloque de gráfica con contenido
            page.wait_for_timeout(300)
            assert page.locator(".report-chart svg, .report-chart .heatmap, .report-chart .empty").count() >= 1, key
            assert page.locator("[data-testid^=table-]").count() >= 1, key
            assert page.locator("[data-testid=export-pdf]").get_attribute("href").startswith(f"/reportes/{key}/imprimir"), key
            shot(page, f"02-{key}", full=True)

        # Filtros en la URL: periodo y punto
        page.goto(APP + "/reportes/sales?period=month")
        page.wait_for_selector("[data-testid=report-kpis] .kpi")
        page.click(".seg button:has-text('Últimos 7 días')")
        page.wait_for_url("**/reportes/sales?period=last7")
        opts = page.locator("[data-testid=filter-point_id] option")
        assert opts.count() > 2
        first_point = opts.nth(1).get_attribute("value")
        page.select_option("[data-testid=filter-point_id]", first_point)
        page.wait_for_url(lambda u: f"point_id={first_point}" in u and "period=last7" in u)
        page.wait_for_selector("[data-testid=report-kpis] .kpi")
        assert "Limpiar filtros" in page.inner_text(".report-filters")
        shot(page, "03-filtros-url")
        page.click("button:has-text('Limpiar filtros')")
        page.wait_for_url(lambda u: "point_id=" not in u)

        # Vista de impresión (noprint evita el diálogo del navegador headless)
        page.goto(APP + f"/reportes/executive/imprimir?period=month&point_id={first_point}&noprint=1")
        page.wait_for_selector("[data-testid=report-print]")
        assert page.locator("aside").count() == 0, "sin navegación en impresión"
        assert page.locator(".print-logo").count() == 1
        assert "Filtros:" in page.inner_text(".print-meta") and "Punto:" in page.inner_text(".print-meta")
        assert page.locator("[data-testid=report-kpis] .kpi").count() >= 3
        page.wait_for_timeout(500)
        shot(page, "04-imprimir", full=True)
        page.emulate_media(media="print")
        page.pdf(path=f"{SHOTS}/04-imprimir.pdf", format="Letter", print_background=True)
        page.emulate_media(media="screen")

        # Supervisor: alcance zona, sin ejecutivo/expansión; 403 por URL directa
        page.goto(APP + "/reportes")
        logout(page)
        login(page, "sup1", "sup123")
        page.goto(APP + "/reportes")
        page.wait_for_selector("[data-testid^=report-tile-]")
        tiles = [t.get_attribute("data-testid").replace("report-tile-", "") for t in page.locator("[data-testid^=report-tile-]").all()]
        assert set(tiles) == set(KEYS) - {"executive", "expansion"}, tiles
        shot(page, "05-centro-supervisor", full=True)
        page.goto(APP + "/reportes/sales?period=month")
        page.wait_for_selector("[data-testid=report-kpis] .kpi")
        assert page.locator("[data-testid=filter-zone_id]").is_disabled(), "zona bloqueada para supervisor"
        assert "Alcance: tu zona" in page.inner_text(".report-meta")
        shot(page, "06-supervisor-ventas", full=True)
        page.goto(APP + "/reportes/executive?period=month")
        page.wait_for_selector(".empty")
        assert "permiso" in page.inner_text(".empty").lower()
        shot(page, "07-supervisor-403")

        # Móvil
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(APP + "/reportes/points?period=month")
        page.wait_for_selector("[data-testid=report-kpis] .kpi")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "sin scroll horizontal en móvil"
        shot(page, "08-movil", full=True)

        assert not errors, errors
        browser.close()
        print(f"OK smoke reportes → {SHOTS}")


if __name__ == "__main__":
    run()
