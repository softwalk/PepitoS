"""Dependencias FastAPI: usuario actual (JWT + dispositivo + jti) y RBAC `require(perm)`."""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import decode_token
from app.models.org import Device, RevokedToken, User

bearer = HTTPBearer(auto_error=False)

# Permisos por rol (§2). Los roles superiores heredan los del anterior.
OPERATOR_PERMS = {
    "me.read", "catalog.read", "shift.open", "shift.close", "sale.create", "sale.cancel_own",
    "waste.create", "help.create", "inventory.receipt", "inventory.count", "gps.ping", "sync.batch",
}
SUPERVISOR_PERMS = OPERATOR_PERMS | {
    "cases.read", "cases.update", "audits.create", "cash_count.surprise", "sale.cancel", "shift.transfer",
    "supervisor.read", "points.read",
}
OPS_PERMS = SUPERVISOR_PERMS | {
    "control_tower.read", "rules.read", "rules.update", "inventory.read", "inventory.manage",
    "maintenance.read", "maintenance.manage", "people.read", "reports.read", "assets.read", "lots.block",
    "approvals.read", "audit_log.read",
}
FINANCE_PERMS = {
    "me.read", "catalog.read", "reconciliation.read", "approvals.read", "approvals.decide", "reports.read",
    "cases.read", "audit_log.read", "control_tower.read", "points.read",
}

# Módulo de Reportes (docs/REPORTES.md): un permiso por área. El alcance (zona / propio) lo aplica la consulta en
# `services/reporting.py`, no el frontend. `reports.self` = el operador sólo ve su propio desempeño.
REPORT_PERMS_BY_ROLE: dict[str, set[str]] = {
    "operator": {"reports.self"},
    "supervisor": {
        "reports.sales", "reports.cash", "reports.points", "reports.people", "reports.inventory", "reports.quality",
        "reports.maintenance", "reports.compliance",
    },
    "ops": {
        "reports.executive", "reports.sales", "reports.cash", "reports.points", "reports.people", "reports.inventory",
        "reports.quality", "reports.maintenance", "reports.compliance", "reports.expansion",
    },
    "finance": {
        "reports.executive", "reports.sales", "reports.cash", "reports.points", "reports.people", "reports.inventory",
        "reports.compliance", "reports.expansion",
    },
}
OPERATOR_PERMS |= REPORT_PERMS_BY_ROLE["operator"]
SUPERVISOR_PERMS |= REPORT_PERMS_BY_ROLE["supervisor"] | REPORT_PERMS_BY_ROLE["operator"]
OPS_PERMS |= REPORT_PERMS_BY_ROLE["ops"] | SUPERVISOR_PERMS
FINANCE_PERMS |= REPORT_PERMS_BY_ROLE["finance"]
ROLE_PERMS: dict[str, set[str]] = {
    "operator": OPERATOR_PERMS,
    "supervisor": SUPERVISOR_PERMS,
    "ops": OPS_PERMS,
    "finance": FINANCE_PERMS,
    "admin": {"*"},
}


@dataclass
class CurrentUser:
    user: User
    device_id: str | None
    jti: str | None
    exp: datetime | None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def zone_id(self) -> uuid.UUID | None:
        return self.user.zone_id

    def has(self, perm: str) -> bool:
        perms = ROLE_PERMS.get(self.role, set())
        return "*" in perms or perm in perms

    @property
    def is_network_wide(self) -> bool:
        return self.role in ("ops", "finance", "admin")


PASSWORD_CHANGE_EXEMPT_PREFIXES = ("/v1/auth/", "/v1/health")


def _password_change_exempt(path: str) -> bool:
    return path.startswith(PASSWORD_CHANGE_EXEMPT_PREFIXES)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise ApiError("AUTH_INVALID", "Falta el token de autorización")
    try:
        claims = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise ApiError("AUTH_INVALID", "El token expiró")
    except jwt.PyJWTError:
        raise ApiError("AUTH_INVALID", "Token inválido")

    jti = claims.get("jti")
    if jti and db.get(RevokedToken, jti):
        raise ApiError("AUTH_INVALID", "La sesión fue cerrada")

    try:
        user = db.get(User, uuid.UUID(claims["sub"]))
    except (KeyError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise ApiError("AUTH_INVALID", "Usuario inválido o inactivo")
    if user.must_change_password and not _password_change_exempt(request.url.path):
        raise ApiError("PASSWORD_CHANGE_REQUIRED", details={"change_password_url": "/v1/auth/change-password"})

    device_id = claims.get("device_id")
    if device_id:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if device is not None and device.revoked:
            raise ApiError("DEVICE_REVOKED")
        if device is not None:
            device.last_seen_at = datetime.now(timezone.utc)
            db.commit()

    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc) if claims.get("exp") else None
    cu = CurrentUser(user=user, device_id=device_id, jti=jti, exp=exp)
    request.state.current_user = cu
    return cu


def require(*perms: str):
    """Dependencia que exige al menos uno de los permisos indicados."""

    def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(current.has(p) for p in perms):
            raise ApiError("FORBIDDEN", details={"required": list(perms), "role": current.role})
        return current

    return _dep


def client_ip(request: Request | None) -> str | None:
    """IP del cliente: primer valor de X-Forwarded-For si existe, si no request.client.host."""
    if request is None:
        return None
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.split(",")[0].strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None
