# -*- coding: utf-8 -*-
"""Genera los manuales HTML por rol de PEPITO OS (autocontenidos, imprimibles)."""
import base64, html, os, re, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
def _data_uri(rel):
    with open(os.path.join(_HERE, rel), "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()
LOGO = _data_uri("logo.png")
MARK = _data_uri("mark.png")

CSS = """
:root{--brand:#e8590c;--brand-dark:#c04607;--navy:#14213d;--ink:#16202c;--muted:#5b6b7d;--line:#dfe4ec;--bg:#f6f7f9;--panel:#fff;
--green:#1a7f46;--green-bg:#dff5e7;--amber:#8a5a00;--amber-fill:#e0951a;--amber-bg:#fff1d6;--red:#b3261e;--red-bg:#fde8e6;--blue:#1a56b3;--blue-bg:#e2ecfb}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;font-size:15px;line-height:1.55;color:var(--ink);background:var(--bg)}
a{color:var(--blue)}
.wrap{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:100vh}
nav.toc{background:var(--navy);color:#c9d3e6;padding:22px 18px;position:sticky;top:0;height:100vh;overflow:auto}
nav.toc .brand{display:flex;gap:10px;align-items:center;margin-bottom:18px}
nav.toc .mark{width:40px;height:40px;border-radius:10px;background:#f8f2e5;object-fit:cover}
nav.toc .logo{display:block;width:100%;max-width:200px;margin:0 auto 14px;border-radius:14px}
.hero{display:flex;gap:22px;align-items:center;margin-bottom:6px}.hero img{width:150px;height:auto;border-radius:16px;flex:none}
nav.toc .t{font-weight:800;letter-spacing:.06em;color:#fff;font-size:13px}nav.toc .s{font-size:12px;color:#7f8fb0}
nav.toc a{display:block;color:#c9d3e6;text-decoration:none;padding:6px 10px;border-radius:7px;font-size:13.5px}
nav.toc a:hover{background:rgba(255,255,255,.07);color:#fff}nav.toc a.l2{padding-left:22px;font-size:12.5px;color:#9fb0cc}
nav.toc .g{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#7f8fb0;margin:14px 10px 4px;font-weight:700}
main{padding:36px 48px 80px;max-width:1080px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.01em}h2{font-size:22px;margin:44px 0 12px;padding-top:12px;border-top:3px solid var(--brand)}
h3{font-size:17px;margin:26px 0 8px}h4{font-size:15px;margin:18px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
p{margin:0 0 10px}.lead{font-size:17px;color:#3b4757}
.rolebar{display:inline-flex;gap:8px;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:6px 14px 6px 8px;margin:10px 0 22px;font-size:13px}
.rolebar b{background:var(--brand);color:#fff;border-radius:999px;padding:2px 10px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(22,32,44,.05)}
.card h5{margin:0 0 6px;font-size:14px}.card p{font-size:13.5px;margin:0;color:#3b4757}.card .n{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--brand);color:#fff;font-weight:800;font-size:13px;margin-right:8px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0 16px;background:var(--panel)}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);background:#f8fafc}tr:last-child td{border-bottom:0}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}
.b-green{background:var(--green-bg);color:var(--green)}.b-amber{background:var(--amber-bg);color:var(--amber)}.b-red{background:var(--red-bg);color:var(--red)}.b-blue{background:var(--blue-bg);color:var(--blue)}.b-gray{background:#eaeef3;color:#5b6b7d}
kbd,.ui{display:inline-block;background:#fff;border:1px solid #c7cfdb;border-bottom-width:2px;border-radius:6px;padding:0 7px;font:inherit;font-size:12.5px;font-weight:700;white-space:nowrap}
.ui.p{background:var(--brand);color:#fff;border-color:var(--brand-dark)}.ui.g{background:var(--green);color:#fff;border-color:#125a32}.ui.a{background:var(--amber-fill);color:#1a1000;border-color:#a86a00}.ui.b{background:var(--blue);color:#fff;border-color:#143f85}.ui.r{background:var(--red);color:#fff;border-color:#86170f}
.muted{color:#5b6b7d;font-size:12px}
tr.off td{opacity:.7}
.callout{border-left:5px solid var(--blue);background:var(--blue-bg);padding:10px 14px;border-radius:8px;margin:12px 0;font-size:14px}
.callout.warn{border-color:var(--amber-fill);background:var(--amber-bg)}.callout.ok{border-color:var(--green);background:var(--green-bg)}.callout.bad{border-color:var(--red);background:var(--red-bg)}
.steps{counter-reset:s;list-style:none;padding:0;margin:14px 0}.steps li{position:relative;padding:10px 12px 10px 52px;margin:0 0 8px;background:var(--panel);border:1px solid var(--line);border-radius:10px}
.steps li::before{counter-increment:s;content:counter(s);position:absolute;left:12px;top:10px;width:28px;height:28px;border-radius:50%;background:var(--navy);color:#fff;font-weight:800;display:grid;place-items:center;font-size:13px}
.steps li b:first-child{display:block;margin-bottom:2px}.steps .ex{margin-top:6px;font-size:13px;color:#3b4757;background:#f8fafc;border-radius:6px;padding:6px 10px;border:1px dashed var(--line)}
.ex::before{content:'Ejemplo · ';font-weight:700;color:var(--brand-dark)}
figure{margin:16px 0;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;overflow-x:auto}
figcaption{font-size:12.5px;color:var(--muted);margin-top:6px}
svg text{font-family:inherit}
.print{font-size:12px;color:var(--muted);margin-top:40px;border-top:1px solid var(--line);padding-top:10px}
@media (max-width:860px){.wrap{grid-template-columns:1fr}nav.toc{position:static;height:auto}main{padding:20px}}
@media print{.wrap{display:block}nav.toc{display:none}.hero img{width:110px}main{max-width:none;padding:0}h2{break-before:page}figure{break-inside:avoid}.steps li{break-inside:avoid}}
"""

# ---------- SVG helpers ----------
def flow(nodes, w=980, h=150, color="#14213d"):
    """Diagrama de flujo horizontal. nodes = [(texto, sub, color?)]"""
    n = len(nodes); gap = 26; bw = (w - gap * (n - 1) - 20) / n; out = []
    for i, nd in enumerate(nodes):
        t, s = nd[0], nd[1]; c = nd[2] if len(nd) > 2 else color
        x = 10 + i * (bw + gap)
        out.append(f'<rect x="{x}" y="30" width="{bw}" height="74" rx="12" fill="{c}"/>')
        out.append(f'<text x="{x+bw/2}" y="62" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">{html.escape(t)}</text>')
        out.append(f'<text x="{x+bw/2}" y="84" text-anchor="middle" fill="#fff" font-size="11.5" opacity=".9">{html.escape(s)}</text>')
        if i < n - 1:
            out.append(f'<path d="M{x+bw+3} 67 L{x+bw+gap-6} 67" stroke="#8a97a5" stroke-width="2.5" marker-end="url(#ar)"/>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" role="img"><defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#8a97a5"/></marker></defs>{"".join(out)}</svg>'

def semaforo(title, rows, w=980):
    """Barra de umbrales: rows=[(label, [(texto, color)] )]"""
    out = [f'<text x="0" y="16" font-size="13" font-weight="700" fill="#16202c">{html.escape(title)}</text>']
    y = 30
    for label, segs in rows:
        out.append(f'<text x="0" y="{y+22}" font-size="12.5" fill="#3b4757">{html.escape(label)}</text>')
        x = 250; sw = (w - 250) / len(segs)
        for t, c in segs:
            out.append(f'<rect x="{x}" y="{y+4}" width="{sw-4}" height="28" rx="6" fill="{c}"/>')
            out.append(f'<text x="{x+(sw-4)/2}" y="{y+23}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">{html.escape(t)}</text>')
            x += sw
        y += 40
    return f'<svg viewBox="0 0 {w} {y+6}" width="100%" role="img">{"".join(out)}</svg>'

def states(nodes, edges, w=980, h=260):
    """Diagrama de estados: nodes={id:(x,y,label,color)}, edges=[(a,b,label)]. Las flechas terminan en el borde del nodo;
    los pares bidireccionales se separan para que no se encimen."""
    import math
    out = []
    pairs = {(a, b) for a, b, _ in edges}
    for a, b, lab in edges:
        ax, ay = nodes[a][0], nodes[a][1]; bx, by = nodes[b][0], nodes[b][1]
        dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy) or 1; ux, uy = dx / L, dy / L
        # radio efectivo de la cápsula (62 x 20) en la dirección de la flecha
        r = 1 / math.sqrt((ux / 66) ** 2 + (uy / 24) ** 2)
        off = 9 if (b, a) in pairs else 0
        px, py = -uy * off, ux * off
        x1, y1 = ax + ux * r + px, ay + uy * r + py; x2, y2 = bx - ux * (r + 4) + px, by - uy * (r + 4) + py
        out.append(f'<path d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}" stroke="#8a97a5" stroke-width="2" marker-end="url(#ar2)"/>')
        # etiqueta desplazada perpendicularmente a la línea (arriba en horizontales) para no tacharla
        nx, ny = -uy, ux
        if off:  # bidireccional: etiqueta hacia el lado exterior de su propia línea
            nx, ny = px / off, py / off
        elif ny > 0:
            nx, ny = -nx, -ny
        mx, my = (x1 + x2) / 2 + px + nx * (14 + (len(lab) * 3.2 if abs(nx) > 0.5 else 0)), (y1 + y2) / 2 + py + ny * 14
        tw = len(lab) * 6.4 + 10
        out.append(f'<rect x="{mx-tw/2:.1f}" y="{my-9}" width="{tw:.1f}" height="17" rx="4" fill="#fff" stroke="#e3e8ef"/><text x="{mx:.1f}" y="{my+4}" text-anchor="middle" font-size="11" fill="#3b4757">{html.escape(lab)}</text>')
    for _, (x, y, lab, c) in nodes.items():
        hw = max(62, len(lab) * 4.2 + 16)
        out.append(f'<rect x="{x-hw:.1f}" y="{y-20}" width="{2*hw:.1f}" height="40" rx="20" fill="{c}"/><text x="{x}" y="{y+5}" text-anchor="middle" fill="#fff" font-size="12.5" font-weight="700">{html.escape(lab)}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" role="img"><defs><marker id="ar2" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#8a97a5"/></marker></defs>{"".join(out)}</svg>'

def bars(title, items, unit="", w=980):
    """Barras horizontales: items=[(label, value, max, color)]"""
    out = [f'<text x="0" y="16" font-size="13" font-weight="700">{html.escape(title)}</text>']; y = 30
    for label, v, mx, c in items:
        bw = (w - 330) * (v / mx)
        out.append(f'<text x="0" y="{y+18}" font-size="12.5" fill="#3b4757">{html.escape(label)}</text><rect x="230" y="{y+2}" width="{w-330}" height="22" rx="5" fill="#eaeef3"/><rect x="230" y="{y+2}" width="{bw}" height="22" rx="5" fill="{c}"/><text x="{w-90}" y="{y+18}" font-size="12.5" font-weight="700">{html.escape(str(v)+unit)}</text>')
        y += 32
    return f'<svg viewBox="0 0 {w} {y+4}" width="100%" role="img">{"".join(out)}</svg>'

def fig(svg, cap):
    return f'<figure>{svg}<figcaption>{cap}</figcaption></figure>'

def page(role_key, role_name, subtitle, sections, app_label):
    toc = []
    body = []
    for sec in sections:
        sid = sec["id"]; toc.append(f'<a href="#{sid}">{sec["title"]}</a>')
        for h3 in re.findall(r'<h3 id="([^"]+)">([^<]+)</h3>', sec["html"]):
            toc.append(f'<a class="l2" href="#{h3[0]}">{h3[1]}</a>')
        body.append(f'<section id="{sid}"><h2>{sec["title"]}</h2>{sec["html"]}</section>')
    return f"""<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PEPITO OS · Manual · {html.escape(role_name)}</title><style>{CSS}</style></head><body><div class="wrap">
<nav class="toc"><img class="logo" src="{LOGO}" alt="PEPITO · Pepitas recién doradas al comal"><div class="brand"><img class="mark" src="{MARK}" alt=""><div><div class="t">PEPITO OS</div><div class="s">Manual · {html.escape(role_name)}</div></div></div>
<div class="g">Contenido</div>{"".join(toc)}
<div class="g">Otros manuales</div><a href="manual-operador.html">Operador</a><a href="manual-supervisor.html">Supervisor</a><a href="manual-operaciones.html">Operaciones</a><a href="manual-finanzas.html">Finanzas</a><a href="manual-administrador.html">Administrador</a></nav>
<main><div class="hero"><img src="{LOGO}" alt="PEPITO"><div><h1>Manual del {html.escape(role_name)}</h1><p class="lead">{subtitle}</p></div></div>
<div class="rolebar"><b>{html.escape(role_key)}</b> {app_label}</div>
{"".join(body)}
<p class="print">PEPITO OS v1 · rama feat/ux-redesign · Generado el 4 de septiembre de 2026. Los textos entre comillas son literales de la aplicación.</p>
</main></div></body></html>"""

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    import content
    for key, spec in content.MANUALS.items():
        out = page(*spec)
        with open(f"manual-{key}.html", "w", encoding="utf-8") as f:
            f.write(out)
        print(key, len(out))
