"""Authorization endpoint + consent — ``/oauth/authorize`` (RFC 6749 §4.1, docs/05 B3).

Flow: validate the request → require a web session (else bounce through Google login and
return here) → show a consent screen → on approval, mint a single-use code and redirect back
to the client with ``code`` + ``state``.

The consent screen embeds an HMAC-signed ``approval`` token binding the (re-validated)
request to the logged-in user, with a short TTL. That token is the consent POST's CSRF
defense — an attacker cannot forge a valid signature for the victim — reinforced by the
``SameSite=Lax`` session cookie. Consent is shown every time (satisfying "at least once per
client") and recorded via a structured log rather than a table (Decision, docs/01).
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import session as auth_session
from app.core import security
from app.core.config import get_settings
from app.core.logging import get_logger
from app.oauth.errors import redirect_with_error
from app.pages import consent_page, error_page
from app.services import oauth as oauth_service
from app.services.oauth import AuthorizationRequest, OAuthError

router = APIRouter(prefix="/oauth", tags=["oauth"])
logger = get_logger("tempo.oauth")

_CONSENT_TYP = "authz_consent"
_CONSENT_TTL_SECONDS = 600


@router.get("/authorize")
async def authorize(
    request: Request,
    response_type: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    redirect_uri: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    state: str | None = Query(default=None),
    code_challenge: str | None = Query(default=None),
    code_challenge_method: str | None = Query(default=None),
    resource: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        auth_request = await oauth_service.build_authorization_request(
            db,
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            resource=resource,
            state=state,
        )
    except OAuthError as exc:
        # Redirectable errors imply redirect_uri was validated → safe to bounce back.
        if exc.redirectable and redirect_uri:
            return redirect_with_error(redirect_uri, exc, state)
        return error_page("Authorization error", exc.description, status=400)

    # Require an authenticated web session; otherwise log in and return to this exact URL.
    user_id = auth_session.read_session_user_id(request)
    if user_id is None:
        login_url = (
            f"{get_settings().public_base_url}/oauth/login/google"
            f"?{urlencode({'return_to': str(request.url)})}"
        )
        return RedirectResponse(login_url, status_code=302)

    return consent_page(
        client_name=auth_request.client.client_name,
        scope=auth_request.scope,
        approval=_sign_consent(auth_request, user_id),
    )


@router.post("/authorize/consent")
async def authorize_consent(
    request: Request,
    approval: str = Form(...),
    decision: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    payload = _read_consent(approval)
    if payload is None:
        return error_page(
            "Authorization error", "This authorization request has expired.", status=400
        )

    # The approval must belong to the *currently* logged-in user (defence in depth).
    session_user = auth_session.read_session_user_id(request)
    if session_user is None or str(session_user) != payload.get("uid"):
        return error_page("Authorization error", "Please sign in and try again.", status=401)

    redirect_uri = str(payload["redirect_uri"])
    state = payload.get("state") or None

    if decision != "approve":
        return redirect_with_error(
            redirect_uri,
            OAuthError("access_denied", "The user denied the authorization request."),
            state,
        )

    try:
        auth_request = await oauth_service.build_authorization_request(
            db,
            client_id=str(payload["client_id"]),
            redirect_uri=redirect_uri,
            response_type="code",
            scope=str(payload["scope"]),
            code_challenge=str(payload["code_challenge"]),
            code_challenge_method="S256",
            resource=str(payload["resource"]),
            state=state,
        )
        code = await oauth_service.create_authorization_code(
            db, request=auth_request, user_id=session_user
        )
    except OAuthError as exc:
        if exc.redirectable:
            return redirect_with_error(redirect_uri, exc, state)
        return error_page("Authorization error", exc.description, status=400)

    logger.info(
        "oauth_consent_granted",
        extra={
            "client_id": str(payload["client_id"]),
            "user_id": str(session_user),
            "scope": str(payload["scope"]),
        },
    )
    params = {"code": code}
    if state:
        params["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(params)}", status_code=302)


def _sign_consent(request: AuthorizationRequest, user_id: uuid.UUID) -> str:
    return security.sign_payload(
        {
            "uid": str(user_id),
            "client_id": request.client.client_id,
            "redirect_uri": request.redirect_uri,
            "scope": request.scope,
            "state": request.state or "",
            "code_challenge": request.code_challenge,
            "resource": request.resource,
        },
        key=get_settings().session_signing_key,
        typ=_CONSENT_TYP,
    )


def _read_consent(token: str) -> dict[str, Any] | None:
    return security.verify_payload(
        token,
        key=get_settings().session_signing_key,
        typ=_CONSENT_TYP,
        max_age_seconds=_CONSENT_TTL_SECONDS,
    )
