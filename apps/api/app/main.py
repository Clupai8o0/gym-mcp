"""FastAPI application factory.

Phase 0 boots a minimal app with a liveness probe only. Routers, the MCP mount,
the OAuth AS, middleware (CORS), and the DB-ping health check are added in later
phases — all as thin adapters over ``app/services`` (see docs/03-backend-fastapi.md).
"""

from __future__ import annotations

from fastapi import FastAPI

__all__ = ["create_app", "app"]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(title="Tempo API", version="0.1.0")

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness probe. A real DB ping is added in Phase 2 (see docs/03)."""
        return {"status": "ok"}

    return application


app = create_app()
