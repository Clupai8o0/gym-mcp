"""Web session + OIDC-login-transaction cookies (docs/05 Part A).

Both are **stateless** signed cookies (Decision: no ``web_sessions`` table — docs/02 left the
choice to Phase 3). The session cookie is HMAC-signed (``core.security``), ``httpOnly`` +
``Secure`` + ``SameSite=Lax`` + parent-``Domain`` so it reaches both ``tempo.clupai.com`` and
``api.tempo.clupai.com``. The short-lived ``oidc_tx`` cookie carries the login flow's
``state`` / ``nonce`` / PKCE verifier / return-to across the round trip to Google, so callback
validation needs no server-side state.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from fastapi import Request, Response

from app.core import security
from app.core.config import get_settings

SESSION_COOKIE = "tempo_session"
OIDC_TX_COOKIE = "tempo_oidc_tx"
_SESSION_TYP = "session"
_OIDC_TX_TYP = "oidc_tx"
# Login should complete quickly; bound how long a planted state/nonce stays valid.
_OIDC_TX_TTL_SECONDS = 600


@dataclass(frozen=True)
class SessionInfo:
    user_id: uuid.UUID
    age_seconds: int


# ── web session cookie ────────────────────────────────────────────────────────────────
def issue_session_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    return security.sign_payload(
        {"sub": str(user_id)}, key=settings.session_signing_key, typ=_SESSION_TYP
    )


def read_session(request: Request) -> SessionInfo | None:
    """Return the signed-in principal from the session cookie, or ``None`` if absent/invalid."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    settings = get_settings()
    payload = security.verify_payload(
        raw,
        key=settings.session_signing_key,
        typ=_SESSION_TYP,
        max_age_seconds=settings.session_ttl_seconds,
    )
    if payload is None:
        return None
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        return None
    age = max(0, int(time.time()) - int(payload.get("iat", 0)))
    return SessionInfo(user_id=user_id, age_seconds=age)


def read_session_user_id(request: Request) -> uuid.UUID | None:
    info = read_session(request)
    return info.user_id if info else None


def should_renew(info: SessionInfo) -> bool:
    """Sliding renewal: re-issue once a session is past half its lifetime."""
    return info.age_seconds > get_settings().session_ttl_seconds // 2


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.session_cookie_domain or None,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        domain=settings.session_cookie_domain or None,
        path="/",
    )


# ── OIDC login-transaction cookie (state / nonce / PKCE verifier / return-to) ─────────
def issue_oidc_tx(*, state: str, nonce: str, code_verifier: str, return_to: str) -> str:
    settings = get_settings()
    return security.sign_payload(
        {"state": state, "nonce": nonce, "cv": code_verifier, "rt": return_to},
        key=settings.session_signing_key,
        typ=_OIDC_TX_TYP,
    )


def read_oidc_tx(request: Request) -> dict[str, str] | None:
    raw = request.cookies.get(OIDC_TX_COOKIE)
    if not raw:
        return None
    payload = security.verify_payload(
        raw,
        key=get_settings().session_signing_key,
        typ=_OIDC_TX_TYP,
        max_age_seconds=_OIDC_TX_TTL_SECONDS,
    )
    if payload is None:
        return None
    return {k: str(payload.get(k, "")) for k in ("state", "nonce", "cv", "rt")}


def set_oidc_tx_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    # Host-only (no Domain): only this API host reads it, on the Google callback.
    response.set_cookie(
        OIDC_TX_COOKIE,
        token,
        max_age=_OIDC_TX_TTL_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_oidc_tx_cookie(response: Response) -> None:
    response.delete_cookie(OIDC_TX_COOKIE, path="/")
