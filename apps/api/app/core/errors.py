"""Typed service errors + their HTTP mapping (docs/03, docs/12).

The one rule: ``services/`` raise :class:`ServiceError` (framework-free); this module
installs the FastAPI handlers that translate them — and Pydantic validation failures —
into the canonical envelope ``{"error": {"kind", "message", "details?}}``. Internal
exceptions never leak: they are logged with the request id and returned as a generic 500.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("tempo.errors")


class ErrorKind(StrEnum):
    """Domain error categories; each maps to one HTTP status."""

    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    VALIDATION = "validation"


STATUS_BY_KIND: dict[ErrorKind, int] = {
    ErrorKind.UNAUTHORIZED: 401,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.FORBIDDEN: 403,
    ErrorKind.CONFLICT: 409,
    ErrorKind.VALIDATION: 422,
}


class ServiceError(Exception):
    """A domain error raised inside ``services/``; carries a kind + safe message."""

    def __init__(self, kind: ErrorKind, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = details

    @property
    def status_code(self) -> int:
        return STATUS_BY_KIND[self.kind]


# Terse constructors for service code: ``raise errors.not_found("session")``.
def unauthorized(message: str, **details: Any) -> ServiceError:
    return ServiceError(ErrorKind.UNAUTHORIZED, message, details=details or None)


def not_found(message: str, **details: Any) -> ServiceError:
    return ServiceError(ErrorKind.NOT_FOUND, message, details=details or None)


def forbidden(message: str, **details: Any) -> ServiceError:
    return ServiceError(ErrorKind.FORBIDDEN, message, details=details or None)


def conflict(message: str, **details: Any) -> ServiceError:
    return ServiceError(ErrorKind.CONFLICT, message, details=details or None)


def validation(message: str, **details: Any) -> ServiceError:
    return ServiceError(ErrorKind.VALIDATION, message, details=details or None)


def _envelope(kind: str, message: str, details: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"kind": kind, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    """Register the exception → envelope handlers on ``app``."""

    @app.exception_handler(ServiceError)
    async def _service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.kind.value, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic/FastAPI input validation → the same envelope as domain validation.
        return JSONResponse(
            status_code=STATUS_BY_KIND[ErrorKind.VALIDATION],
            content=_envelope(
                ErrorKind.VALIDATION.value, "Request validation failed", exc.errors()
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Framework 404s/405s etc. — keep the envelope shape consistent.
        kind = ErrorKind.NOT_FOUND.value if exc.status_code == 404 else "http_error"
        detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(status_code=exc.status_code, content=_envelope(kind, detail))

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals. Log with the request id; return a generic 500.
        logger.error("unhandled exception: %s", exc, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope(
                "internal", "Internal server error", {"request_id": request_id_ctx.get()}
            ),
        )
