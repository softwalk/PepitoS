"""Servicios de autenticación: rate limiting de login (B2), refresh tokens rotativos (B3) y política de contraseñas (B1).

Todas las funciones aceptan `now` para poder probarlas sin dormir; `current_time()` es el reloj por defecto
(los tests lo pueden monkeypatchear).
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.models.org import Device, LoginAttempt, RefreshToken, User
from app.services import audit


def current_time() -> datetime:
    return utcnow()


# ---------------------------------------------------------------- IP


def request_ip(request: Request | None) -> str | None:
    """Primer valor de X-Forwarded-For si existe; si no, request.client.host."""
    if request is None:
        return None
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


# ---------------------------------------------------------------- rate limiting


def _retry_after_seconds(locked_until: datetime, now: datetime) -> int:
    return max(1, int((locked_until - now).total_seconds() + 0.999))


def _rate_limited(retry_after: int) -> ApiError:
    minutes = max(1, (retry_after + 59) // 60)
    return ApiError(
        "RATE_LIMITED",
        f"Demasiados intentos. Intenta en {minutes} minutos",
        details={"retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def _fails_in_window(db: Session, column, value: str, now: datetime) -> tuple[int, datetime | None]:
    """(número de fallos en la ventana, instante del último fallo)."""
    since = now - timedelta(minutes=settings.LOGIN_WINDOW_MINUTES)
    row = db.execute(
        select(func.count(LoginAttempt.id), func.max(LoginAttempt.at)).where(
            column == value, LoginAttempt.success.is_(False), LoginAttempt.at > since, LoginAttempt.at <= now
        )
    ).one()
    return int(row[0]), row[1]


def _check(db: Session, column, value: str | None, max_fails: int, now: datetime) -> None:
    if not value:
        return
    count, last = _fails_in_window(db, column, value, now)
    if count >= max_fails and last is not None:
        locked_until = last + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
        if locked_until > now:
            raise _rate_limited(_retry_after_seconds(locked_until, now))


def check_login_allowed(db: Session, username: str | None, ip: str | None, now: datetime | None = None) -> None:
    """Lanza 429 RATE_LIMITED si el usuario o la IP están bloqueados."""
    now = now or current_time()
    _check(db, LoginAttempt.ip, ip, settings.LOGIN_MAX_FAILS_IP, now)
    _check(db, LoginAttempt.username, username, settings.LOGIN_MAX_FAILS_USER, now)


def check_ip_allowed(db: Session, ip: str | None, now: datetime | None = None) -> None:
    """Sólo el límite por IP (usado por /refresh)."""
    now = now or current_time()
    _check(db, LoginAttempt.ip, ip, settings.LOGIN_MAX_FAILS_IP, now)


def record_failure(db: Session, username: str | None, ip: str | None, now: datetime | None = None, user: User | None = None) -> None:
    """Registra un fallo; si con él el usuario alcanza el máximo, deja audit `auth.lockout` (una vez por bloqueo)."""
    now = now or current_time()
    db.add(LoginAttempt(username=username, ip=ip, at=now, success=False))
    db.flush()
    if username:
        count, _ = _fails_in_window(db, LoginAttempt.username, username, now)
        if count == settings.LOGIN_MAX_FAILS_USER:
            audit.log(
                db,
                actor_id=None,
                action="auth.lockout",
                entity="user",
                entity_id=user.id if user is not None else None,
                after={"username": username, "fails": count, "lock_minutes": settings.LOGIN_LOCK_MINUTES},
                ip=ip,
            )


def record_success(db: Session, username: str, ip: str | None, now: datetime | None = None) -> None:
    """Login correcto: limpia los fallos previos del usuario y registra el éxito."""
    now = now or current_time()
    db.execute(delete(LoginAttempt).where(LoginAttempt.username == username, LoginAttempt.success.is_(False)))
    db.add(LoginAttempt(username=username, ip=ip, at=now, success=True))


def purge_old_attempts(db: Session, now: datetime | None = None) -> int:
    now = now or current_time()
    cutoff = now - timedelta(days=settings.LOGIN_ATTEMPTS_RETENTION_DAYS)
    return db.execute(delete(LoginAttempt).where(LoginAttempt.at < cutoff)).rowcount


# ---------------------------------------------------------------- refresh tokens


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _active_tokens(db: Session, *, user_id: uuid.UUID | None = None, device_id: str | None = None):
    q = db.query(RefreshToken).filter(RefreshToken.revoked_at.is_(None))
    if user_id is not None:
        q = q.filter(RefreshToken.user_id == user_id)
    if device_id is not None:
        q = q.filter(RefreshToken.device_id == device_id)
    return q


def revoke_device_tokens(db: Session, device_id: str, now: datetime | None = None) -> int:
    """Revoca toda la familia de refresh tokens de un dispositivo."""
    now = now or current_time()
    n = 0
    for t in _active_tokens(db, device_id=device_id).all():
        t.revoked_at = now
        n += 1
    return n


def revoke_user_tokens(db: Session, user_id: uuid.UUID, except_device_id: str | None = None, now: datetime | None = None) -> int:
    now = now or current_time()
    n = 0
    for t in _active_tokens(db, user_id=user_id).all():
        if except_device_id is not None and t.device_id == except_device_id:
            continue
        t.revoked_at = now
        n += 1
    return n


def issue_refresh_token(db: Session, user: User, device_id: str, now: datetime | None = None, *, revoke_previous: bool = True) -> tuple[str, RefreshToken]:
    """Crea un refresh token opaco (48 bytes urlsafe) ligado al dispositivo. Devuelve (token en claro, fila)."""
    now = now or current_time()
    if revoke_previous:
        revoke_device_tokens(db, device_id, now)
    raw = secrets.token_urlsafe(48)
    row = RefreshToken(
        user_id=user.id,
        device_id=device_id,
        token_hash=_hash(raw),
        expires_at=now + timedelta(days=settings.REFRESH_EXPIRES_DAYS),
        created_at=now,
    )
    db.add(row)
    db.flush()
    return raw, row


def rotate_refresh_token(db: Session, raw_token: str, device_id: str, now: datetime | None = None) -> tuple[str, RefreshToken, User]:
    """Rotación: el token anterior queda revocado con `replaced_by`. Reutilizar uno ya rotado/revocado revoca toda la
    familia del dispositivo (detección de robo). Devuelve (nuevo token, fila nueva, usuario)."""
    now = now or current_time()
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash(raw_token)).first()
    if row is None:
        raise ApiError("AUTH_INVALID", "Refresh token inválido")
    if row.device_id != device_id:
        # Token presentado desde otro dispositivo: sospechoso → se revoca la familia original.
        revoke_device_tokens(db, row.device_id, now)
        raise ApiError("AUTH_INVALID", "Refresh token inválido")
    if row.revoked_at is not None:
        revoke_device_tokens(db, row.device_id, now)
        raise ApiError("AUTH_INVALID", "Refresh token reutilizado; la sesión del dispositivo fue revocada")
    if row.expires_at <= now:
        row.revoked_at = now
        raise ApiError("AUTH_INVALID", "Refresh token expirado")

    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is not None and device.revoked:
        revoke_device_tokens(db, device_id, now)
        raise ApiError("DEVICE_REVOKED")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        revoke_device_tokens(db, device_id, now)
        raise ApiError("AUTH_INVALID", "Usuario inválido o inactivo")

    raw, new_row = issue_refresh_token(db, user, device_id, now, revoke_previous=False)
    row.revoked_at = now
    row.replaced_by = new_row.id
    if device is not None:
        device.last_seen_at = now
    return raw, new_row, user


# ---------------------------------------------------------------- contraseñas


def validate_new_password(new_password: str, *, current_hash: str | None = None) -> None:
    from app.core.security import verify_password

    if len(new_password) < settings.PASSWORD_MIN_LENGTH:
        raise ApiError("VALIDATION", f"La contraseña debe tener al menos {settings.PASSWORD_MIN_LENGTH} caracteres", details={"min_length": settings.PASSWORD_MIN_LENGTH})
    if current_hash and verify_password(new_password, current_hash):
        raise ApiError("VALIDATION", "La nueva contraseña debe ser distinta de la actual")


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(9)  # 12 caracteres urlsafe
