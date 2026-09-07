"""Notificaciones al supervisor/ops: Web Push (VAPID) + WhatsApp (Twilio) de respaldo, con dedupe y bitácora.

Política (docs/NOTIFICACIONES.md):
- Caso URGENTE → supervisores de la zona del punto + Operaciones. Caso REVISAR → supervisores de la zona.
- SLA vencido → Operaciones y administradores.
- Dedupe: misma clave (regla+punto) no se repite en `notify_dedupe_minutes`; las de prioridad normal no se envían.
- Sin claves configuradas se registra en `notification_log` con canal `log` (así el piloto ve qué habría avisado).
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.cases import Case
from app.models.ops import NotificationLog, PushSubscription
from app.models.org import Point, User
from app.services import webpush
from app.services.settings import get_int

log = logging.getLogger("pepito.notify")


def _recipients_for_case(db: Session, case: Case) -> list[User]:
    zone_id = None
    if case.point_id:
        p = db.get(Point, case.point_id)
        zone_id = p.zone_id if p else None
    q = select(User).where(User.is_active.is_(True))
    users = list(db.execute(q).scalars().all())
    out = [u for u in users if u.role == "supervisor" and (zone_id is None or u.zone_id == zone_id)]
    if case.severity == "urgent":
        out += [u for u in users if u.role in ("ops", "admin")]
    return out


def _recently_sent(db: Session, dedupe_key: str) -> bool:
    minutes = get_int(db, "notify_dedupe_minutes")
    since = utcnow() - timedelta(minutes=minutes)
    row = db.execute(select(NotificationLog.id).where(NotificationLog.dedupe_key == dedupe_key, NotificationLog.sent_at >= since, NotificationLog.status != "failed").limit(1)).first()
    return row is not None


def _log(db: Session, *, channel: str, user_id: uuid.UUID | None, dedupe_key: str | None, title: str, body: str, payload: dict, status: str, error: str | None = None) -> None:
    db.add(NotificationLog(channel=channel, user_id=user_id, dedupe_key=dedupe_key, title=title, body=body, payload=payload, status=status, error=error, sent_at=utcnow()))


def _send_push(db: Session, user: User, title: str, body: str, payload: dict, dedupe_key: str | None) -> int:
    subs = db.execute(select(PushSubscription).where(PushSubscription.user_id == user.id, PushSubscription.disabled_at.is_(None))).scalars().all()
    n = 0
    for s in subs:
        status, err = webpush.send(webpush.Subscription(s.endpoint, s.p256dh, s.auth), {"title": title, "body": body, **payload})
        if status == "gone":
            s.disabled_at = utcnow()
            s.last_error = err
        elif status == "failed":
            s.last_error = err
        _log(db, channel="push", user_id=user.id, dedupe_key=dedupe_key, title=title, body=body, payload=payload, status="sent" if status == "sent" else "failed" if status in ("failed", "gone") else "skipped", error=err)
        n += 1 if status == "sent" else 0
    return n


def _send_whatsapp(db: Session, user: User, title: str, body: str, payload: dict, dedupe_key: str | None) -> bool:
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM and user.phone):
        return False
    if not (user.notify_prefs or {}).get("whatsapp", True):
        return False
    to = user.phone if user.phone.startswith("whatsapp:") else f"whatsapp:{user.phone}"
    text = f"PEPITO · {title}\n{body}" + (f"\n{payload['url']}" if payload.get("url") else "")
    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
            data={"From": settings.TWILIO_WHATSAPP_FROM, "To": to, "Body": text},
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), timeout=10,
        )
        ok = r.status_code in (200, 201)
        _log(db, channel="whatsapp", user_id=user.id, dedupe_key=dedupe_key, title=title, body=body, payload=payload, status="sent" if ok else "failed", error=None if ok else r.text[:200])
        return ok
    except httpx.HTTPError as e:
        _log(db, channel="whatsapp", user_id=user.id, dedupe_key=dedupe_key, title=title, body=body, payload=payload, status="failed", error=str(e))
        return False


def notify_users(db: Session, users: list[User], *, title: str, body: str, url: str | None = None, dedupe_key: str | None = None, severity: str = "review", extra: dict | None = None) -> dict:
    """Envía a cada usuario por push; si el caso es urgente y no hubo push entregado, intenta WhatsApp. Devuelve conteos."""
    if dedupe_key and _recently_sent(db, dedupe_key):
        return {"skipped": "dedupe"}
    payload = {"url": url, "severity": severity, **(extra or {})}
    out = {"push": 0, "whatsapp": 0, "log": 0}
    seen: set[uuid.UUID] = set()
    for u in users:
        if u.id in seen:
            continue
        seen.add(u.id)
        if not (u.notify_prefs or {}).get("push", True) and not (u.notify_prefs or {}).get("whatsapp", True):
            continue
        sent = _send_push(db, u, title, body, payload, dedupe_key) if (u.notify_prefs or {}).get("push", True) else 0
        out["push"] += sent
        if severity == "urgent" and not sent and _send_whatsapp(db, u, title, body, payload, dedupe_key):
            out["whatsapp"] += 1
        if not sent and not (severity == "urgent" and out["whatsapp"]):
            _log(db, channel="log", user_id=u.id, dedupe_key=dedupe_key, title=title, body=body, payload=payload, status="skipped", error="sin canal configurado o sin suscripción")
            out["log"] += 1
    if not users:
        _log(db, channel="log", user_id=None, dedupe_key=dedupe_key, title=title, body=body, payload=payload, status="skipped", error="sin destinatarios")
    db.flush()
    return out


def notify_case(db: Session, case: Case) -> dict | None:
    """Aviso al crear un caso urgente/revisar (los normales no notifican)."""
    if case.severity not in ("urgent", "review"):
        return None
    users = _recipients_for_case(db, case)
    point = db.get(Point, case.point_id) if case.point_id else None
    body = (point.display_name + " · " if point else "") + (case.description or "")[:180]
    try:
        return notify_users(db, users, title=("🔴 URGENTE: " if case.severity == "urgent" else "🟡 Revisar: ") + case.title, body=body, url=f"/casos/{case.id}",
                            dedupe_key=case.dedupe_key or f"case:{case.id}", severity=case.severity, extra={"case_id": str(case.id)})
    except Exception:  # noqa: BLE001 — una notificación nunca debe tumbar la regla
        log.exception("Fallo notificando caso %s", case.id)
        return None


def notify_sla_breach(db: Session, case: Case) -> dict | None:
    users = [u for u in db.execute(select(User).where(User.is_active.is_(True), User.role.in_(("ops", "admin")))).scalars().all()]
    minutes = (case.payload or {}).get("sla_original_severity")
    try:
        return notify_users(db, users, title=f"⏰ SLA vencido: {case.title}", body=f"Caso sin tomar (severidad original: {minutes}). Escalado a Operaciones.", url=f"/casos/{case.id}",
                            dedupe_key=f"sla:{case.id}", severity="urgent", extra={"case_id": str(case.id)})
    except Exception:  # noqa: BLE001
        log.exception("Fallo notificando SLA %s", case.id)
        return None
