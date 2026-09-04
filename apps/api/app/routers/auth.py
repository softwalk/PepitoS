"""Autenticación (§3): login con rate limiting, refresh tokens rotativos, logout, cambio de contraseña."""
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.errors import ApiError
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutil import iso
from app.models.org import Device, RevokedToken, User
from app.schemas.backoffice import ChangePasswordIn, LoginIn, RefreshIn
from app.services import audit
from app.services import auth as auth_svc

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def ser_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "role": user.role,
        "zone_id": str(user.zone_id) if user.zone_id else None,
        "username": user.username,
    }


def _session_payload(user: User, device_id: str, refresh_token: str, refresh_row) -> dict:
    token, expires_in, _ = create_access_token(str(user.id), user.role, device_id, str(user.zone_id) if user.zone_id else None)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "refresh_expires_at": iso(refresh_row.expires_at),
        "user": ser_user(user),
        "must_change_password": bool(user.must_change_password),
    }


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    now = auth_svc.current_time()
    ip = auth_svc.request_ip(request)
    auth_svc.purge_old_attempts(db, now)
    auth_svc.check_login_allowed(db, data.username, ip, now)

    user = db.query(User).filter(User.username == data.username).first()
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        auth_svc.record_failure(db, data.username, ip, now, user=user)
        db.commit()
        raise ApiError("AUTH_INVALID", "Usuario o contraseña incorrectos")

    device = db.query(Device).filter(Device.device_id == data.device_id).first()
    if device is None:
        device = Device(device_id=data.device_id, user_id=user.id, name=data.device_name, platform=data.platform)
        db.add(device)
    elif device.revoked:
        raise ApiError("DEVICE_REVOKED")
    else:
        device.user_id = user.id
        device.name = data.device_name or device.name
        device.platform = data.platform or device.platform
    device.last_login_at = now
    device.last_seen_at = now

    auth_svc.record_success(db, data.username, ip, now)
    refresh_raw, refresh_row = auth_svc.issue_refresh_token(db, user, data.device_id, now)  # revoca los anteriores del device
    body = _session_payload(user, data.device_id, refresh_raw, refresh_row)
    db.commit()
    return body


@router.post("/refresh")
def refresh(data: RefreshIn, request: Request, db: Session = Depends(get_db)):
    """Rota el refresh token. No cuenta para el límite por usuario, pero sí registra fallos por IP."""
    now = auth_svc.current_time()
    ip = auth_svc.request_ip(request)
    auth_svc.check_ip_allowed(db, ip, now)
    try:
        refresh_raw, refresh_row, user = auth_svc.rotate_refresh_token(db, data.refresh_token, data.device_id, now)
    except ApiError:
        auth_svc.record_failure(db, None, ip, now)
        db.commit()
        raise
    body = _session_payload(user, data.device_id, refresh_raw, refresh_row)
    db.commit()
    return body


@router.post("/logout")
def logout(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    now = auth_svc.current_time()
    if current.jti and db.get(RevokedToken, current.jti) is None:
        db.add(RevokedToken(jti=current.jti, user_id=current.id, revoked_at=now, expires_at=current.exp.astimezone(timezone.utc) if current.exp else None))
        audit.log(db, actor_id=current.id, action="auth.logout", entity="token", entity_id=None, after={"jti": current.jti}, ip=auth_svc.request_ip(request), device_id=current.device_id)
    if current.device_id:
        auth_svc.revoke_device_tokens(db, current.device_id, now)
    db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(data: ChangePasswordIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    now = auth_svc.current_time()
    user = current.user
    if not verify_password(data.current_password, user.password_hash):
        raise ApiError("AUTH_INVALID", "La contraseña actual es incorrecta")
    auth_svc.validate_new_password(data.new_password, current_hash=user.password_hash)
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    user.password_changed_at = now
    revoked = auth_svc.revoke_user_tokens(db, user.id, except_device_id=current.device_id, now=now)
    audit.log(
        db,
        actor_id=user.id,
        action="user.password_change",
        entity="user",
        entity_id=user.id,
        after={"must_change_password": False, "revoked_refresh_tokens": revoked},
        ip=auth_svc.request_ip(request),
        device_id=current.device_id,
    )
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)):
    u = current.user
    return {**ser_user(u), "device_id": current.device_id, "must_change_password": bool(u.must_change_password)}
