"""MFA con TOTP (RFC 6238) para administradores y finanzas. Secreto en `users.totp_secret`; `mfa_enabled` sólo tras
verificar un código. El reto de login es un JWT de 5 minutos con `purpose=mfa` que no sirve como access token."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.security import ALGORITHM
from app.core.timeutil import iso, utcnow
from app.models.org import User
from app.services import audit
from app.services.settings import get_setting

MFA_ROLES = ("admin", "finance")
ISSUER = "PEPITO OS"


def status(db: Session, user: User) -> dict:
    return {
        "enabled": bool(user.mfa_enabled), "enabled_at": iso(user.mfa_enabled_at), "pending_setup": bool(user.totp_secret and not user.mfa_enabled),
        "required": user.role in MFA_ROLES, "enforced": bool(get_setting(db, "mfa_enforce")) and user.role in MFA_ROLES,
    }


def setup(db: Session, user: User) -> dict:
    if user.mfa_enabled:
        raise ApiError("CONFLICT", "MFA ya está activo; desactívalo con un código antes de regenerar el secreto")
    user.totp_secret = pyotp.random_base32()
    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.username, issuer_name=ISSUER)
    return {"secret": user.totp_secret, "otpauth_uri": uri, "issuer": ISSUER, "account": user.username}


def _verify(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def enable(db: Session, user: User, code: str, *, ip: str | None = None, device_id: str | None = None) -> None:
    if not user.totp_secret:
        raise ApiError("CONFLICT", "Primero genera el secreto con /auth/mfa/setup")
    if not _verify(user.totp_secret, code):
        raise ApiError("MFA_INVALID")
    user.mfa_enabled = True
    user.mfa_enabled_at = utcnow()
    audit.log(db, actor_id=user.id, action="auth.mfa_enable", entity="user", entity_id=user.id, after={"mfa_enabled": True}, ip=ip, device_id=device_id)


def disable(db: Session, user: User, code: str, *, ip: str | None = None, device_id: str | None = None) -> None:
    if not user.mfa_enabled:
        return
    if not _verify(user.totp_secret, code):
        raise ApiError("MFA_INVALID")
    user.mfa_enabled = False
    user.totp_secret = None
    user.mfa_enabled_at = None
    audit.log(db, actor_id=user.id, action="auth.mfa_disable", entity="user", entity_id=user.id, after={"mfa_enabled": False}, ip=ip, device_id=device_id)


def admin_reset(db: Session, actor_id: uuid.UUID, user: User, *, ip: str | None = None) -> None:
    """Un administrador quita el MFA de otro usuario (teléfono perdido). Queda en audit_log."""
    user.mfa_enabled = False
    user.totp_secret = None
    user.mfa_enabled_at = None
    audit.log(db, actor_id=actor_id, action="auth.mfa_reset", entity="user", entity_id=user.id, after={"mfa_enabled": False}, reason="Reset por administrador", ip=ip)


def issue_challenge(user: User, device_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "device_id": device_id, "purpose": "mfa", "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=5)).timestamp())}, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_challenge(db: Session, token: str, device_id: str, code: str) -> User | None:
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if claims.get("purpose") != "mfa" or claims.get("device_id") != device_id:
        return None
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active or not user.mfa_enabled or not _verify(user.totp_secret, code):
        return None
    return user
