"""Errores con el formato del contrato §4:
{"error": {"code": "STRING_ESTABLE", "message": "texto corto en español", "details": {...}}}
"""
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

DEFAULT_MESSAGES = {
    "AUTH_INVALID": "Credenciales inválidas",
    "DEVICE_REVOKED": "Dispositivo revocado",
    "FORBIDDEN": "No tienes permiso para esta acción",
    "NOT_FOUND": "Recurso no encontrado",
    "VALIDATION": "Datos inválidos",
    "NO_ASSIGNMENT": "No tienes asignación para hoy",
    "SHIFT_ALREADY_OPEN": "Ya tienes un turno abierto",
    "CART_IN_USE": "El carrito ya tiene un turno abierto",
    "SHIFT_NOT_OPEN": "El turno no está abierto",
    "IDEMPOTENCY_CONFLICT": "La clave de idempotencia ya se usó con otro contenido",
    "PRICE_VERSION_INVALID": "Versión de precio inválida",
    "CANCEL_NOT_ALLOWED": "No se puede cancelar esta venta",
    "LOT_BLOCKED": "El lote está bloqueado",
    "CONFLICT": "Conflicto con el estado actual",
    "PASSWORD_CHANGE_REQUIRED": "Debes cambiar tu contraseña antes de continuar",
    "RATE_LIMITED": "Demasiados intentos. Intenta más tarde",
}

DEFAULT_STATUS = {
    "AUTH_INVALID": 401,
    "DEVICE_REVOKED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION": 422,
    "NO_ASSIGNMENT": 409,
    "SHIFT_ALREADY_OPEN": 409,
    "CART_IN_USE": 409,
    "SHIFT_NOT_OPEN": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "PRICE_VERSION_INVALID": 422,
    "CANCEL_NOT_ALLOWED": 403,
    "LOT_BLOCKED": 409,
    "CONFLICT": 409,
    "PASSWORD_CHANGE_REQUIRED": 403,
    "RATE_LIMITED": 429,
}


class ApiError(HTTPException):
    """Excepción de dominio con código estable."""

    def __init__(self, code: str, message: str | None = None, status_code: int | None = None, details: Any = None, headers: dict[str, str] | None = None):
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, code)
        self.details = details or {}
        super().__init__(status_code=status_code or DEFAULT_STATUS.get(code, 400), detail=self.message, headers=headers)

    def to_body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def error_body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_body(), headers=exc.headers or None)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException):
        code = {401: "AUTH_INVALID", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION"}.get(
            exc.status_code, "ERROR"
        )
        message = exc.detail if isinstance(exc.detail, str) else DEFAULT_MESSAGES.get(code, "Error")
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        details = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=error_body("VALIDATION", "Datos inválidos", {"errors": details}))
