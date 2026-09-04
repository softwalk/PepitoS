"""Autenticación (§3)."""
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, get_current_user
from app.core.errors import ApiError
from app.core.security import create_access_token, verify_password
from app.core.timeutil import utcnow
from app.models.org import Device, RevokedToken, User
from app.schemas.backoffice import LoginIn
from app.services import audit

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
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
    device.last_login_at = utcnow()
    device.last_seen_at = utcnow()
    token, expires_in, _ = create_access_token(str(user.id), user.role, data.device_id, str(user.zone_id) if user.zone_id else None)
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": {"id": str(user.id), "name": user.name, "role": user.role, "zone_id": str(user.zone_id) if user.zone_id else None, "username": user.username},
    }


@router.post("/logout")
def logout(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.jti and db.get(RevokedToken, current.jti) is None:
        db.add(RevokedToken(jti=current.jti, user_id=current.id, revoked_at=utcnow(), expires_at=current.exp.astimezone(timezone.utc) if current.exp else None))
        audit.log(db, actor_id=current.id, action="auth.logout", entity="token", entity_id=None, after={"jti": current.jti}, ip=client_ip(request), device_id=current.device_id)
        db.commit()
    return {"ok": True}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)):
    u = current.user
    return {"id": str(u.id), "name": u.name, "username": u.username, "role": u.role, "zone_id": str(u.zone_id) if u.zone_id else None, "device_id": current.device_id}
