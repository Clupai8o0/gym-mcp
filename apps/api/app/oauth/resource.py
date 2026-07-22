"""Resource-server helpers: bearer extraction + spec 401/403 responses (docs/05 B5).

RFC 9728 requires the protected resource's ``401`` to carry a ``WWW-Authenticate: Bearer``
header pointing at the Protected Resource Metadata URL, so an MCP client can discover the AS.
These helpers are shared by the Phase-3 ``/mcp`` guard and reused by REST's bearer branch;
Phase 5's real MCP mount keeps the same 401 semantics.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

_PRM_PATH = "/.well-known/oauth-protected-resource"


def extract_bearer_token(request: Request) -> str | None:
    """Return the token from an ``Authorization: Bearer <token>`` header, or ``None``."""
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


def _www_authenticate(*, error: str | None = None, description: str | None = None) -> str:
    prm_url = f"{get_settings().public_base_url}{_PRM_PATH}"
    parts = [f'Bearer resource_metadata="{prm_url}"']
    if error:
        parts.append(f'error="{error}"')
    if description:
        parts.append(f'error_description="{description}"')
    return ", ".join(parts)


def unauthorized_response(description: str = "authentication required") -> JSONResponse:
    """401 with the PRM pointer (RFC 9728) — for missing/invalid/expired bearer tokens."""
    return JSONResponse(
        status_code=401,
        content={"error": "invalid_token", "error_description": description},
        headers={
            "WWW-Authenticate": _www_authenticate(error="invalid_token", description=description)
        },
    )


def insufficient_scope_response(required_scope: str) -> JSONResponse:
    """403 with the PRM pointer (RFC 6750) — token valid but missing a required scope."""
    description = f"required scope: {required_scope}"
    return JSONResponse(
        status_code=403,
        content={"error": "insufficient_scope", "error_description": description},
        headers={
            "WWW-Authenticate": _www_authenticate(
                error="insufficient_scope", description=description
            )
        },
    )
