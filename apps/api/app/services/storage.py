"""Object storage para evidencias (B4).

Backends (`STORAGE_BACKEND`):
- `s3`    : cualquier S3-compatible (AWS, MinIO, R2…) vía boto3. `get_url` devuelve una URL presignada.
- `local` : archivos en `STORAGE_LOCAL_DIR`; `get_url` apunta a `/v1/evidence/{id}/file` (la API los sirve).
- `none`  : descarta el contenido (comportamiento previo al B4); `get_url` devuelve None.

Interfaz: `put(key, data, content_type) -> str`, `get_url(key, expires=900) -> str | None`, `delete(key)`.
En `local` también `get_path(key)` para servir el archivo.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

log = logging.getLogger("pepito.storage")

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._/-]+$")


def _check_key(key: str) -> str:
    if not key or ".." in key or key.startswith("/") or not _SAFE_KEY.match(key):
        raise ValueError(f"storage key inválida: {key!r}")
    return key


class Storage:
    backend: str = "none"

    def put(self, key: str, data: bytes, content_type: str) -> str:  # pragma: no cover - interfaz
        raise NotImplementedError

    def get_url(self, key: str, expires: int = 900) -> str | None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # pragma: no cover - interfaz
        raise NotImplementedError


class NullStorage(Storage):
    backend = "none"

    def put(self, key: str, data: bytes, content_type: str) -> str:
        return _check_key(key)

    def get_url(self, key: str, expires: int = 900) -> str | None:
        return None

    def delete(self, key: str) -> None:
        return None

    def exists(self, key: str) -> bool:
        return False


class LocalStorage(Storage):
    """Guarda en disco. La URL pública la construye la API (`/v1/evidence/{id}/file`), por eso
    `get_url` recibe la key en formato `<evidence_id>/...` y devuelve la ruta relativa de la API."""

    backend = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def get_path(self, key: str) -> Path:
        path = (self.root / _check_key(key)).resolve()
        if self.root not in path.parents:
            raise ValueError("storage key fuera del directorio raíz")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self.get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return key

    def get_url(self, key: str, expires: int = 900) -> str | None:
        evidence_id = _check_key(key).split("/", 1)[0]
        return f"/v1/evidence/{evidence_id}/file"

    def delete(self, key: str) -> None:
        try:
            self.get_path(key).unlink(missing_ok=True)
        except (ValueError, OSError) as e:  # pragma: no cover - defensivo
            log.warning("No se pudo borrar %s: %s", key, e)

    def exists(self, key: str) -> bool:
        try:
            return self.get_path(key).is_file()
        except ValueError:
            return False


class S3Storage(Storage):
    backend = "s3"

    def __init__(self):
        import boto3
        from botocore.config import Config as BotoConfig

        kwargs = {"region_name": settings.STORAGE_REGION, "config": BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"})}
        if settings.STORAGE_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.STORAGE_ENDPOINT_URL
        if settings.STORAGE_ACCESS_KEY and settings.STORAGE_SECRET_KEY:
            kwargs["aws_access_key_id"] = settings.STORAGE_ACCESS_KEY
            kwargs["aws_secret_access_key"] = settings.STORAGE_SECRET_KEY
        self.client = boto3.client("s3", **kwargs)
        self.bucket = settings.STORAGE_BUCKET
        # Cliente aparte para presignar hacia fuera (p. ej. MinIO detrás de un dominio público)
        if settings.STORAGE_PUBLIC_URL:
            self.public_client = boto3.client("s3", **{**kwargs, "endpoint_url": settings.STORAGE_PUBLIC_URL})
        else:
            self.public_client = self.client

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(Bucket=self.bucket, Key=_check_key(key), Body=data, ContentType=content_type)
        return key

    def get_url(self, key: str, expires: int = 900) -> str | None:
        # Sin STORAGE_PUBLIC_URL el bucket no es alcanzable desde el navegador (MinIO interno del compose):
        # se devuelve None y la API sirve el archivo por /v1/evidence/{id}/file (get_bytes).
        if not settings.STORAGE_PUBLIC_URL:
            return None
        return self.public_client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": _check_key(key)}, ExpiresIn=expires)

    def get_bytes(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=_check_key(key))
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_check_key(key))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_check_key(key))
            return True
        except Exception:  # noqa: BLE001
            return False


@lru_cache
def get_storage() -> Storage:
    backend = (settings.STORAGE_BACKEND or "none").strip().lower()
    if backend == "s3":
        return S3Storage()
    if backend == "local":
        return LocalStorage(settings.STORAGE_LOCAL_DIR)
    if backend == "none":
        return NullStorage()
    raise RuntimeError(f"STORAGE_BACKEND inválido: {backend!r} (usa s3 | local | none)")


# Atajos con la firma de la interfaz pedida
def put(key: str, data: bytes, content_type: str) -> str:
    return get_storage().put(key, data, content_type)


def get_url(key: str, expires: int = 900) -> str | None:
    return get_storage().get_url(key, expires)


def delete(key: str) -> None:
    get_storage().delete(key)
