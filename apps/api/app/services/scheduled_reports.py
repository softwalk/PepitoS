"""Reportes programados: resumen ejecutivo diario (ayer) por correo a las 7:05 hora local, y envío bajo demanda.

Render en servidor (HTML autocontenido con KPIs, hallazgos y tablas; las gráficas viven en el backoffice). Si
WeasyPrint está instalado se adjunta PDF; si no, va el HTML. Sin SMTP configurado el archivo se guarda en
`REPORTS_OUT_DIR` y queda en la bitácora (`notification_log`, canal email/log). Cada envío se audita como
`report.export` con actor nulo (sistema) o el usuario que lo pidió.
"""
from __future__ import annotations

import html
import logging
import os
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.ops import NotificationLog
from app.models.org import User
from app.services import audit
from app.services.reporting import REPORTS, build_report

log = logging.getLogger("pepito.reports")

KIND_TONE = {"ok": "#1a7f46", "warn": "#b06f00", "bad": "#b3261e", "neutral": "#5b6b7d"}
INSIGHT = {"fact": ("Hecho", "#1a56b3"), "trend": ("Tendencia", "#5b6b7d"), "alert": ("Alerta", "#b3261e"), "hypothesis": ("Hipótesis", "#b06f00"), "recommendation": ("Recomendación", "#1a7f46")}


def _fmt(v, fmt: str) -> str:
    if v is None or v == "":
        return "—"
    if fmt == "money":
        return f"${v / 100:,.2f}" if abs(v) < 100000 else f"${v / 100:,.0f}"
    if fmt == "pct":
        return f"{v:.1f}%" if isinstance(v, float) and not float(v).is_integer() else f"{int(v)}%"
    if fmt == "delta":
        return f"{'+' if v > 0 else ''}{v:.0f} %"
    if fmt in ("int", "float"):
        return f"{v:,}" if isinstance(v, int) else f"{v:,.1f}"
    return html.escape(str(v))


def render_html(payload: dict, generated_by: str | None = None) -> str:
    e = html.escape
    kpis = "".join(
        f'<td style="padding:10px;border:1px solid #dfe4ec;border-left:4px solid {KIND_TONE.get(k["tone"], "#c7cfdb")};vertical-align:top;min-width:120px">'
        f'<div style="font-size:11px;color:#5b6b7d;text-transform:uppercase">{e(k["label"])}</div>'
        f'<div style="font-size:20px;font-weight:700">{_fmt(k["value"], k["format"])}{(" " + e(k["unit"])) if k.get("unit") else ""}</div>'
        f'<div style="font-size:11px;color:#5b6b7d">{("Δ " + _fmt(k["delta_pct"], "delta")) if k.get("delta_pct") is not None else ("Sin base comparable" if k.get("compare") == "no_comparable" else "")}{(" · " + e(k["hint"])) if k.get("hint") else ""}</div></td>'
        for k in payload["kpis"]
    )
    ins = "".join(
        f'<li style="margin:4px 0"><b style="color:{INSIGHT[i["kind"]][1]}">{INSIGHT[i["kind"]][0]}:</b> {e(i["text"])}</li>' for i in payload["insights"]
    ) or "<li>Sin hallazgos.</li>"
    tables = []
    for t in payload["tables"]:
        cols = [c for c in t["columns"] if c["format"] != "link"]
        head = "".join(f'<th style="text-align:{"right" if c["format"] in ("money", "int", "pct", "float", "delta") else "left"};padding:6px 8px;border-bottom:1px solid #c7cfdb;font-size:11px;text-transform:uppercase;color:#5b6b7d">{e(c["label"])}</th>' for c in cols)
        rows = "".join(
            "<tr>" + "".join(f'<td style="text-align:{"right" if c["format"] in ("money", "int", "pct", "float", "delta") else "left"};padding:5px 8px;border-bottom:1px solid #eef1f5;font-size:12.5px">{_fmt(r.get(c["key"]), c["format"])}</td>' for c in cols) + "</tr>"
            for r in t["rows"][:60]
        ) or '<tr><td style="padding:8px;color:#5b6b7d">Sin registros en el periodo</td></tr>'
        tables.append(f'<h3 style="margin:18px 0 6px;font-size:14px">{e(t["title"])}</h3><table style="border-collapse:collapse;width:100%">{head and "<thead><tr>" + head + "</tr></thead>"}<tbody>{rows}</tbody></table>')
    cov = payload.get("coverage") or {}
    cov_note = f'<p style="background:#fff1d6;color:#8a5a00;padding:8px 12px;border-left:4px solid #e0951a">Cifras preliminares: {cov.get("open_shifts", 0)} turno(s) abiertos al corte.</p>' if cov.get("status") == "pending" else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{e(payload["title"])} · {e(payload["period"]["label"])}</title>
<style>@page {{ size: Letter {payload["orientation"]}; margin: 14mm 12mm }} body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color:#16202c; margin:0; padding:16px }} table {{ page-break-inside: auto }} tr {{ page-break-inside: avoid }} h3 {{ page-break-after: avoid }}</style></head>
<body><div style="border-bottom:2px solid #14213d;padding-bottom:8px;margin-bottom:12px">
<div style="font-size:22px;font-weight:800;color:#14213d">PEPITO OS · {e(payload["title"])}</div>
<div style="font-size:12px;color:#5b6b7d">{e(payload["category"])} · {e(payload["description"])}</div>
<div style="font-size:12px;margin-top:6px"><b>Periodo:</b> {e(payload["period"]["preset_label"])} — {e(payload["period"]["label"])} · <b>Comparado con:</b> {e(payload["compare"]["label"])} · <b>Corte de datos:</b> {e(payload["data_as_of"])} · <b>Generado:</b> {e(payload["generated_at"])}{(" por " + e(generated_by)) if generated_by else " por el sistema"} · v{e(payload["version"])}</div></div>
{cov_note}
<table style="border-collapse:separate;border-spacing:6px;width:100%"><tr>{kpis}</tr></table>
<h3 style="margin:14px 0 6px;font-size:14px">Hallazgos y alertas</h3><ul style="padding-left:18px;margin:0">{ins}</ul>
{"".join(tables)}
<p style="margin-top:18px;font-size:10px;color:#777">Las gráficas interactivas están en el backoffice (Reportes). Uso interno{" — CONFIDENCIAL" if payload["key"] in ("cash", "executive", "people", "expansion") else ""}.</p>
</body></html>"""


def to_pdf(html_text: str) -> bytes | None:
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:  # noqa: BLE001 — opcional
        return None
    try:
        return HTML(string=html_text).write_pdf()
    except Exception:  # noqa: BLE001
        log.exception("WeasyPrint falló; se envía HTML")
        return None


def deliver(db: Session, *, subject: str, html_text: str, to: list[str], actor_id: uuid.UUID | None, report_key: str, filters: dict) -> dict:
    pdf = to_pdf(html_text)
    fname = f"{report_key}-{utcnow().strftime('%Y%m%d-%H%M')}"
    result: dict = {"to": to, "pdf": pdf is not None}
    if settings.SMTP_HOST and to:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, settings.SMTP_FROM, ", ".join(to)
        msg.set_content("Tu cliente de correo no muestra HTML. Abre el adjunto.")
        msg.add_alternative(html_text, subtype="html")
        if pdf:
            msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=fname + ".pdf")
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
                s.starttls()
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
                s.send_message(msg)
            status, err, channel = "sent", None, "email"
        except Exception as e:  # noqa: BLE001
            status, err, channel = "failed", str(e)[:300], "email"
    else:
        os.makedirs(settings.REPORTS_OUT_DIR, exist_ok=True)
        path = os.path.join(settings.REPORTS_OUT_DIR, fname + (".pdf" if pdf else ".html"))
        with open(path, "wb") as f:
            f.write(pdf or html_text.encode())
        status, err, channel = "skipped", f"SMTP no configurado; guardado en {path}", "log"
        result["path"] = path
    db.add(NotificationLog(channel=channel, user_id=actor_id, dedupe_key=f"report:{report_key}", title=subject, body=", ".join(to) or "sin destinatarios", payload={"report": report_key, "filters": filters}, status=status, error=err, sent_at=utcnow()))
    audit.log(db, actor_id=actor_id, action="report.export", entity="report", after={"report": report_key, "filters": filters, "result": "allowed", "channel": channel, "status": status, "to": to, "scheduled": actor_id is None})
    result.update({"status": status, "error": err, "channel": channel})
    return result


def send_report(db: Session, *, key: str, current, period: str | None, date_from: str | None, date_to: str | None, filters: dict, to: list[str]) -> dict:
    payload = build_report(db, key, current, period=period, date_from=date_from, date_to=date_to, filters=filters)
    html_text = render_html(payload, generated_by=current.user.name)
    subject = f"PEPITO · {payload['title']} · {payload['period']['label']}"
    return deliver(db, subject=subject, html_text=html_text, to=to, actor_id=current.id, report_key=key, filters={**{k: str(v) for k, v in filters.items() if v}, "period": period or "today"})


class _SystemUser:
    """Actor de sistema para el job programado: alcance de red completa."""

    def __init__(self, user: User):
        self.user = user
        self.id = user.id
        self.role = "admin"
        self.zone_id = None

    def has(self, perm: str) -> bool:
        return True


def run_daily_reports(db: Session, now: datetime | None = None) -> dict | None:
    to = [x.strip() for x in (settings.REPORTS_EMAIL_TO or "").split(",") if x.strip()]
    admin = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).order_by(User.created_at).first()
    if admin is None:
        return None
    actor = _SystemUser(admin)
    out = {}
    for key in ("executive", "cash"):
        payload = build_report(db, key, actor, period="yesterday", date_from=None, date_to=None, filters={})
        html_text = render_html(payload)
        out[key] = deliver(db, subject=f"PEPITO · {REPORTS[key]['title']} · {payload['period']['label']}", html_text=html_text, to=to, actor_id=None, report_key=key, filters={"period": "yesterday"})
    db.commit()
    return out


def run_daily_reports_job() -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        log.info("reportes diarios: %s", run_daily_reports(db))
    except Exception:  # noqa: BLE001
        log.exception("Fallo en reportes programados")
        db.rollback()
    finally:
        db.close()
