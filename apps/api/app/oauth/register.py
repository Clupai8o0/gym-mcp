"""Dynamic Client Registration — ``POST /oauth/register`` (RFC 7591, docs/05 B2).

Thin adapter: validation, rate-limiting, and logging live in ``services.oauth.register_client``.
Unauthenticated by spec; claude.ai self-registers here as a public client.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.oauth.errors import oauth_error_json
from app.schemas.oauth import ClientRegistrationRequest, ClientRegistrationResponse
from app.services import oauth as oauth_service
from app.services.oauth import OAuthError

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.post("/register")
async def register_client(
    body: ClientRegistrationRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        client = await oauth_service.register_client(
            db,
            client_name=body.client_name,
            redirect_uris=body.redirect_uris,
            grant_types=body.grant_types,
            scope=body.scope,
        )
    except OAuthError as exc:
        return oauth_error_json(exc)

    response = ClientRegistrationResponse(
        client_id=client.client_id,
        client_id_issued_at=int(time.time()),
        client_name=client.client_name,
        redirect_uris=list(client.redirect_uris),
        grant_types=list(client.grant_types),
        response_types=["code"],
        token_endpoint_auth_method=client.token_endpoint_auth_method,
        scope=client.scope,
    )
    return JSONResponse(status_code=201, content=response.model_dump())
