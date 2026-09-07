"""Web Push sin dependencias extra: cifrado RFC 8291 (aes128gcm) + VAPID (RFC 8292) con `cryptography` y PyJWT.

Uso: `send(subscription, payload_dict)`. Sin `VAPID_PRIVATE_KEY` no envía (devuelve `skipped`). Generar claves:
    python -m app.services.webpush genkeys
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class Subscription:
    endpoint: str
    p256dh: str
    auth: str


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(sub: Subscription, plaintext: bytes, *, server_key: ec.EllipticCurvePrivateKey | None = None, salt: bytes | None = None) -> bytes:
    """Devuelve el cuerpo `aes128gcm` (header + registro único) para el push service."""
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64u_decode(sub.p256dh))
    auth_secret = b64u_decode(sub.auth)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    server_pub = server_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_pub_raw = ua_public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = server_key.exchange(ec.ECDH(), ua_public)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_pub_raw + server_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    record = plaintext + b"\x02"  # delimitador del último registro
    ciphertext = AESGCM(cek).encrypt(nonce, record, None)
    rs = (4096).to_bytes(4, "big")
    header = salt + rs + bytes([len(server_pub)]) + server_pub
    return header + ciphertext


def decrypt(body: bytes, ua_private: ec.EllipticCurvePrivateKey, auth_secret: bytes) -> bytes:
    """Sólo para pruebas: descifra lo que produce `encrypt` como lo haría el navegador."""
    salt, idlen = body[:16], body[20]
    server_pub_raw = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    server_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_pub_raw)
    ua_pub_raw = ua_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = ua_private.exchange(ec.ECDH(), server_pub)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_pub_raw + server_pub_raw, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    record = AESGCM(cek).decrypt(nonce, ciphertext, None)
    return record.rstrip(b"\x00")[:-1]


def vapid_private_key() -> ec.EllipticCurvePrivateKey | None:
    raw = settings.VAPID_PRIVATE_KEY
    if not raw:
        return None
    if raw.startswith("-----BEGIN"):
        return serialization.load_pem_private_key(raw.encode(), password=None)  # type: ignore[return-value]
    # Clave cruda de 32 bytes en base64url (formato habitual de las herramientas web-push)
    return ec.derive_private_key(int.from_bytes(b64u_decode(raw), "big"), ec.SECP256R1())


def vapid_public_key_b64u() -> str | None:
    if settings.VAPID_PUBLIC_KEY:
        return settings.VAPID_PUBLIC_KEY
    key = vapid_private_key()
    if key is None:
        return None
    return b64u_encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))


def vapid_headers(endpoint: str) -> dict[str, str]:
    key = vapid_private_key()
    if key is None:
        raise RuntimeError("VAPID_PRIVATE_KEY no configurada")
    u = urlparse(endpoint)
    aud = f"{u.scheme}://{u.netloc}"
    token = jwt.encode({"aud": aud, "exp": int(time.time()) + 12 * 3600, "sub": settings.VAPID_SUBJECT}, key, algorithm="ES256")
    return {"Authorization": f"vapid t={token}, k={vapid_public_key_b64u()}"}


def send(sub: Subscription, payload: dict, ttl: int = 3600, urgency: str = "high", timeout: float = 10.0) -> tuple[str, str | None]:
    """→ (status, error). status: sent | gone (suscripción caducada: borrar) | failed | skipped."""
    if vapid_private_key() is None:
        return "skipped", "VAPID no configurado"
    body = encrypt(sub, json.dumps(payload, ensure_ascii=False).encode())
    headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(ttl), "Urgency": urgency, **vapid_headers(sub.endpoint)}
    try:
        r = httpx.post(sub.endpoint, content=body, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:  # red
        return "failed", str(e)
    if r.status_code in (200, 201, 202):
        return "sent", None
    if r.status_code in (404, 410):
        return "gone", f"{r.status_code}"
    return "failed", f"{r.status_code} {r.text[:200]}"


def generate_keys() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = b64u_encode(key.private_numbers().private_value.to_bytes(32, "big"))
    pub = b64u_encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return priv, pub


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "genkeys":
    private, public = generate_keys()
    print(f"VAPID_PRIVATE_KEY={private}\nVAPID_PUBLIC_KEY={public}")
