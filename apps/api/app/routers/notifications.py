"""Suscripciones Web Push, preferencias y bitácora de notificaciones."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require
from app.core.timeutil import iso, utcnow
from app.models.ops import NotificationLog, PushSubscription
from app.models.org import User
from app.services import notifications as notif
from app.services import webpush

router = APIRouter(prefix="/v1/notifications", tags=["notificaciones"])


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: dict[str, str]
    user_agent: str | None = None


class PrefsIn(BaseModel):
    push: bool | None = None
    whatsapp: bool | None = None
    phone: str | None = Field(default=None, max_length=40)


@router.get("/config")
def config(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    subs = db.execute(select(PushSubscription).where(PushSubscription.user_id == current.id, PushSubscription.disabled_at.is_(None))).scalars().all()
    from app.core.config import settings

    return {
        "vapid_public_key": webpush.vapid_public_key_b64u(), "push_enabled": webpush.vapid_private_key() is not None,
        "whatsapp_enabled": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_WHATSAPP_FROM), "subscriptions": len(subs),
        "prefs": {"push": True, "whatsapp": True, **(current.user.notify_prefs or {})}, "phone": current.user.phone,
    }


@router.post("/subscriptions", status_code=201)
def subscribe(data: SubscriptionIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if "p256dh" not in data.keys or "auth" not in data.keys:
        from app.core.errors import ApiError

        raise ApiError("VALIDATION", "La suscripción debe incluir keys.p256dh y keys.auth")
    row = db.execute(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)).scalar_one_or_none()
    if row is None:
        row = PushSubscription(user_id=current.id, endpoint=data.endpoint, p256dh=data.keys["p256dh"], auth=data.keys["auth"], user_agent=(data.user_agent or "")[:200], created_at=utcnow())
        db.add(row)
    else:
        row.user_id, row.p256dh, row.auth, row.disabled_at, row.last_error = current.id, data.keys["p256dh"], data.keys["auth"], None, None
    db.commit()
    return {"id": str(row.id)}


@router.delete("/subscriptions")
def unsubscribe(endpoint: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint, PushSubscription.user_id == current.id)).scalar_one_or_none()
    if row is not None:
        row.disabled_at = utcnow()
        db.commit()
    return {"ok": True}


@router.put("/prefs")
def prefs(data: PrefsIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(User, current.id)
    p = dict(u.notify_prefs or {})
    if data.push is not None:
        p["push"] = data.push
    if data.whatsapp is not None:
        p["whatsapp"] = data.whatsapp
    u.notify_prefs = p
    if data.phone is not None:
        u.phone = data.phone or None
    db.commit()
    return {"prefs": p, "phone": u.phone}


@router.post("/test")
def test_notification(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    out = notif.notify_users(db, [current.user], title="Prueba de notificación", body="Si ves esto, las alertas urgentes te llegarán aquí.", url="/excepciones", dedupe_key=None, severity="urgent")
    db.commit()
    return out


@router.get("/log")
def log_list(limit: int = 50, current: CurrentUser = Depends(require("cases.read")), db: Session = Depends(get_db)):
    q = select(NotificationLog).order_by(NotificationLog.sent_at.desc()).limit(min(limit, 500))
    if not current.is_network_wide:
        q = q.where(NotificationLog.user_id == current.id)
    rows = db.execute(q).scalars().all()
    return [{"id": str(r.id), "channel": r.channel, "user_id": str(r.user_id) if r.user_id else None, "title": r.title, "body": r.body, "status": r.status, "error": r.error, "sent_at": iso(r.sent_at), "url": (r.payload or {}).get("url")} for r in rows]
