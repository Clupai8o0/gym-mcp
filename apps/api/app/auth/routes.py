"""Web-login endpoints: Google OIDC sign-in + logout (docs/05 Part A).

Thin adapter — the OIDC protocol lives in :mod:`app.auth.google`, the cookie mechanics in
:mod:`app.auth.session`, and the identity write in :mod:`app.services.auth`. ``state`` (CSRF)
and ``nonce`` are validated on the callback; ``return_to`` is constrained to our own origins
so login can't be turned into an open redirector.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import google, session
from app.core import security
from app.core.config import get_settings
from app.core.logging import get_logger
from app.pages import error_page
from app.services import auth as auth_service

router = APIRouter(prefix="/oauth", tags=["auth"])
logger = get_logger("tempo.auth")


def _safe_return_to(return_to: str | None) -> str:
    """Constrain the post-login destination to our own web/api origins (open-redirect guard)."""
    settings = get_settings()
    if return_to:
        for base in (settings.web_origin, settings.public_base_url):
            if return_to == base or return_to.startswith(base + "/"):
                return return_to
    return settings.web_origin


@router.get("/login/google")
async def login_google(
    return_to: str | None = Query(default=None),
) -> Response:
    """Start Google sign-in: plant state/nonce/PKCE in a signed tx cookie, redirect to Google."""
    settings = get_settings()
    if not settings.google_client_id:
        return error_page("Login unavailable", "Google sign-in is not configured.", status=503)

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = security.compute_s256_challenge(code_verifier)

    url = google.build_authorization_url(state=state, nonce=nonce, code_challenge=code_challenge)
    response = RedirectResponse(url, status_code=302)
    tx = session.issue_oidc_tx(
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        return_to=_safe_return_to(return_to),
    )
    session.set_oidc_tx_cookie(response, tx)
    return response


@router.get("/callback/google")
async def callback_google(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> Response:
    """Validate the Google callback, verify the ID token, upsert the user, set the session."""
    tx = session.read_oidc_tx(request)
    if tx is None:
        return error_page(
            "Sign-in expired", "Your sign-in session expired — please try again.", status=400
        )
    # CSRF: the returned state must match the one we planted (constant-time).
    if not state or not hmac.compare_digest(state, tx["state"]):
        return error_page("Sign-in failed", "Invalid state parameter.", status=400)
    if error:  # user denied consent at Google, or Google returned an error
        response = RedirectResponse(_safe_return_to(tx["rt"]), status_code=302)
        session.clear_oidc_tx_cookie(response)
        return response
    if not code:
        return error_page("Sign-in failed", "Missing authorization code.", status=400)

    try:
        id_token = await google.exchange_code(code=code, code_verifier=tx["cv"])
        identity = await google.verify_id_token(id_token, nonce=tx["nonce"])
    except google.GoogleAuthError as exc:
        logger.warning("google_login_failed", extra={"reason": str(exc)})
        return error_page("Sign-in failed", "We couldn't verify your Google sign-in.", status=400)

    user = await auth_service.upsert_google_user(
        db,
        google_sub=identity.sub,
        email=identity.email,
        name=identity.name,
        avatar_url=identity.picture,
    )
    response = RedirectResponse(_safe_return_to(tx["rt"]), status_code=302)
    session.set_session_cookie(response, session.issue_session_token(user.id))
    session.clear_oidc_tx_cookie(response)
    logger.info("google_login_success", extra={"user_id": str(user.id)})
    return response


@router.post("/logout")
async def logout() -> Response:
    """Clear the session cookie (idempotent)."""
    response = Response(status_code=204)
    session.clear_session_cookie(response)
    return response
