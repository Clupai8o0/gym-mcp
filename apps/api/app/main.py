"""FastAPI application factory (docs/03-backend-fastapi.md).

``create_app()`` assembles the REST surface: structured logging, a request-id middleware,
same-site CORS, the domain→HTTP error handlers, and every router — each a thin adapter over
``app/services``. The MCP mount and the OAuth AS arrive in later phases; auth is stubbed here
(``api/deps.current_user`` resolves to a fixed dev user) so features work before real login.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.api.routers import (
    analytics,
    exercises,
    health,
    me,
    prs,
    sessions,
    sets,
    skills,
)
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger, new_request_id, request_id_ctx

__all__ = ["create_app", "app"]

_ROUTERS = (health, me, exercises, sessions, sets, prs, skills, analytics)

# Header carried by browser calls (CORS-exposed); also used as the CSRF signal in Phase 3.
CLIENT_HEADER = "X-Tempo-Client"
REQUEST_ID_HEADER = "X-Request-ID"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger("tempo.request")

    application = FastAPI(title="Tempo API", version="0.2.0")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", CLIENT_HEADER, REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )
        return response

    install_error_handlers(application)

    for module in _ROUTERS:
        application.include_router(module.router)

    return application


app = create_app()
