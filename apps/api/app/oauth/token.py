"""Token endpoint — ``POST /oauth/token`` (RFC 6749 §5, docs/05 B4).

Two grants, both delegated to ``services.oauth``: ``authorization_code`` (PKCE-verified,
single-use) and ``refresh_token`` (rotated, reuse → chain revocation). Form-encoded in;
JSON out with ``Cache-Control: no-store``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData

from app.api.deps import get_db
from app.oauth.errors import oauth_error_json
from app.schemas.oauth import TokenResponse
from app.services import oauth as oauth_service
from app.services.oauth import IssuedTokens, OAuthError

router = APIRouter(prefix="/oauth", tags=["oauth"])


def _field(form: FormData, key: str) -> str | None:
    value = form.get(key)
    return value if isinstance(value, str) else None


@router.post("/token")
async def token(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    form = await request.form()
    grant_type = _field(form, "grant_type")
    try:
        issued = await _dispatch(grant_type, form, db)
    except OAuthError as exc:
        return oauth_error_json(exc)

    body = TokenResponse(
        access_token=issued.access_token,
        token_type=issued.token_type,
        expires_in=issued.expires_in,
        refresh_token=issued.refresh_token,
        scope=issued.scope,
    )
    return JSONResponse(content=body.model_dump(), headers={"Cache-Control": "no-store"})


async def _dispatch(grant_type: str | None, form: FormData, db: AsyncSession) -> IssuedTokens:
    if grant_type == "authorization_code":
        return await oauth_service.exchange_authorization_code(
            db,
            code=_field(form, "code"),
            client_id=_field(form, "client_id"),
            redirect_uri=_field(form, "redirect_uri"),
            code_verifier=_field(form, "code_verifier"),
            resource=_field(form, "resource"),
        )
    if grant_type == "refresh_token":
        return await oauth_service.refresh_access_token(
            db,
            refresh_token=_field(form, "refresh_token"),
            client_id=_field(form, "client_id"),
            resource=_field(form, "resource"),
        )
    raise OAuthError("unsupported_grant_type", f"unsupported grant_type: {grant_type!r}")
