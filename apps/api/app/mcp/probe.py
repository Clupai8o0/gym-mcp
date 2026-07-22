"""Temporary OAuth-protected ``/mcp`` endpoint (docs/05 B5) — replaced by Phase 5's mount.

Phase 3's job is to make ``/mcp`` *protectable*: an unauthenticated request must 401 with the
RFC 9728 ``WWW-Authenticate`` PRM pointer, and a valid audience-bound bearer with the read
scope must be accepted. This proves the resource-server guard end-to-end now; Phase 5 swaps
the handler for the real Streamable-HTTP MCP app while keeping these exact 401/403 semantics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.oauth import resource
from app.services import oauth as oauth_service

router = APIRouter(tags=["mcp"])

_READ_SCOPE = "workouts.read"


@router.api_route("/mcp", methods=["GET", "POST"])
async def mcp_probe(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    token = resource.extract_bearer_token(request)
    principal = await oauth_service.resolve_access_token(
        db, token=token, required_resource=get_settings().mcp_resource
    )
    if principal is None:
        return resource.unauthorized_response()
    if _READ_SCOPE not in principal.scopes:
        return resource.insufficient_scope_response(_READ_SCOPE)
    return JSONResponse(
        {
            "status": "ok",
            "user_id": str(principal.user_id),
            "client_id": principal.client_id,
            "scopes": sorted(principal.scopes),
        }
    )
