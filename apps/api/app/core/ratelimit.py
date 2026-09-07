"""Límite de peticiones por IP (ventana deslizante de 60 s, en memoria del proceso). Complementa el límite de intentos de
login. `RATE_LIMIT_PER_MINUTE=0` lo desactiva. Detrás de Caddy/nginx usa X-Forwarded-For."""
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.errors import error_body

EXEMPT = ("/v1/health",)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int | None = None):
        super().__init__(app)
        self.per_minute = settings.RATE_LIMIT_PER_MINUTE if per_minute is None else per_minute
        self.buckets: dict[str, deque] = {}

    async def dispatch(self, request: Request, call_next):
        if not self.per_minute or request.url.path.startswith(EXEMPT):
            return await call_next(request)
        xff = request.headers.get("x-forwarded-for")
        ip = (xff.split(",")[0].strip() if xff else None) or (request.client.host if request.client else "?")
        now = time.monotonic()
        q = self.buckets.setdefault(ip, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            retry = int(60 - (now - q[0])) + 1
            return JSONResponse(status_code=429, content=error_body("RATE_LIMITED", "Demasiadas peticiones. Intenta más tarde", {"retry_after_seconds": retry}), headers={"Retry-After": str(retry)})
        q.append(now)
        if len(self.buckets) > 10000:  # limpieza básica
            for k in [k for k, v in self.buckets.items() if not v or now - v[-1] > 60][:5000]:
                self.buckets.pop(k, None)
        return await call_next(request)
