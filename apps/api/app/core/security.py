"""Hash de contraseñas (bcrypt) y JWT HS256."""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, role: str, device_id: str, zone_id: str | None = None) -> tuple[str, int, str]:
    """Devuelve (token, expires_in_seconds, jti)."""
    now = datetime.now(timezone.utc)
    expires = timedelta(hours=settings.JWT_EXPIRES_HOURS)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "role": role,
        "device_id": device_id,
        "zone_id": zone_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)
    return token, int(expires.total_seconds()), jti


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
