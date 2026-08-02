"""FastAPI application factory (docs/03-backend-fastapi.md).

``create_app()`` assembles the full surface: structured logging, a request-id middleware,
same-site CORS, the domain→HTTP error handlers, and every router. Phase 3 adds the auth/OAuth
routers (Google login, the OAuth 2.1 AS discovery/register/authorize/token endpoints) and the
OAuth-protected ``/mcp`` guard. Business logic stays in ``app/services``; routers are thin.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.api.deps import CLIENT_HEADER
from app.api.routers import (
    analytics,
    connections,
    corrections,
    exercises,
    health,
    me,
    prs,
    sessions,
    sets,
    skills,
)
from app.auth import routes as auth_routes
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger, new_request_id, request_id_ctx
from app.mcp.asgi import build_mcp_route, mcp_lifespan
from app.oauth import authorize as oauth_authorize
from app.oauth import metadata as oauth_metadata
from app.oauth import register as oauth_register
from app.oauth import token as oauth_token

__all__ = ["create_app", "app"]

# REST (all under /api); then the auth/OAuth surface (root paths). The OAuth-protected
# ``/mcp`` endpoint is added separately as an ASGI route (see below).
_ROUTERS = (
    health,
    me,
    exercises,
    sessions,
    sets,
    prs,
    skills,
    analytics,
    connections,
    corrections,
    auth_routes,
    oauth_metadata,
    oauth_register,
    oauth_authorize,
    oauth_token,
)

REQUEST_ID_HEADER = "X-Request-ID"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger("tempo.request")

    # Fail loud (not fatal) if a production-like deploy is still on insecure dev secrets.
    if settings.cookie_secure:
        insecure = settings.insecure_defaults_in_use()
        if insecure:
            get_logger("tempo.startup").warning(
                "insecure_defaults_in_use", extra={"settings": insecure}
            )

    # ``lifespan`` runs the MCP Streamable-HTTP session manager (its task group backs every
    # ``/mcp`` request); see app/mcp/asgi.py.
    application = FastAPI(title="Tempo API", version="0.5.0", lifespan=mcp_lifespan)

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

    # The OAuth-protected MCP endpoint. A Route (not a Mount) serves the exact ``/mcp`` path
    # with no trailing-slash redirect; the CORS + request-id middleware above still wrap it.
    application.router.routes.append(build_mcp_route())

    return application


app = create_app()
