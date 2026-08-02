"""Google OIDC protocol adapter (docs/05 Part A) — no DB, no web framework.

Delegating end-user identity to Google keeps the hand-rolled surface to the OAuth *protocol*
only (Decision D5). This module builds the Google auth URL, exchanges the code, and — the
security-critical part — **fully verifies** the returned ID token: RS256 signature against
Google's JWKS, plus ``iss`` / ``aud`` / ``exp`` (with small clock-skew leeway) and the
single-use ``nonce`` we planted. Only a verified token yields a :class:`GoogleIdentity`.
"""

from __future__ import annotations

import hmac
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from app.core.config import get_settings

if TYPE_CHECKING:
    from authlib.jose import JsonWebToken

# Google's OIDC endpoints are stable and documented; hardcoded to avoid a discovery round
# trip. JWKS is fetched per verification (low login volume) so key rotation is always honored.
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
_VALID_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
_CLOCK_SKEW_LEEWAY_SECONDS = 30
_HTTP_TIMEOUT_SECONDS = 10.0


def _http() -> Any:
    """``httpx`` — imported on use, not on import.

    Nothing on the REST path talks HTTP outbound, but this module is reached from
    ``app.main`` through the auth router, so a module-scope ``import httpx`` put ~21 ms of
    cold start in front of *every* request to pay for the two calls below (docs/13 S1).
    """
    import httpx

    return httpx


@lru_cache(maxsize=1)
def _jwt() -> JsonWebToken:
    """RS256-only JWT decoder. Deferred for the same reason: ``authlib.jose`` costs ~32 ms
    to import and is only ever needed inside the Google callback."""
    with warnings.catch_warnings():
        # authlib.jose is supported until 2.0; docs/05 mandates authlib here. Quiet its
        # migrate-to-joserfc notice at the single import site rather than globally.
        warnings.simplefilter("ignore")
        from authlib.jose import JsonWebToken

    return JsonWebToken(["RS256"])  # reject any other alg in the token header


class GoogleAuthError(Exception):
    """Google login could not be completed or the ID token failed verification."""


@dataclass(frozen=True)
class GoogleIdentity:
    """A verified Google end-user identity."""

    sub: str
    email: str
    name: str | None
    picture: str | None


def build_authorization_url(*, state: str, nonce: str, code_challenge: str) -> str:
    """Google's consent URL (scope ``openid email profile``, ``state``, ``nonce``, PKCE)."""
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri_resolved,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(*, code: str, code_verifier: str) -> str:
    """Exchange the authorization code at Google's token endpoint; return the ID token."""
    settings = get_settings()
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri_resolved,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    async with _http().AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(_TOKEN_ENDPOINT, data=data)
    if response.status_code != 200:
        raise GoogleAuthError(f"Google token exchange failed ({response.status_code})")
    id_token = response.json().get("id_token")
    if not id_token:
        raise GoogleAuthError("Google token response contained no id_token")
    return str(id_token)


async def verify_id_token(id_token: str, *, nonce: str) -> GoogleIdentity:
    """Verify signature + claims + nonce; return the identity or raise :class:`GoogleAuthError`."""
    settings = get_settings()
    jwks = await _fetch_jwks()
    try:
        claims = _jwt().decode(
            id_token,
            jwks,
            claims_options={
                "iss": {"essential": True, "values": list(_VALID_ISSUERS)},
                "aud": {"essential": True, "value": settings.google_client_id},
                "exp": {"essential": True},
            },
        )
        claims.validate(leeway=_CLOCK_SKEW_LEEWAY_SECONDS)
    except Exception as exc:  # authlib raises a family of JoseError subclasses
        raise GoogleAuthError(f"ID token verification failed: {exc}") from exc

    if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise GoogleAuthError("OIDC nonce mismatch")
    email = claims.get("email")
    if not email:
        raise GoogleAuthError("Google identity is missing an email")
    if claims.get("email_verified") is False:
        raise GoogleAuthError("Google email address is not verified")

    return GoogleIdentity(
        sub=str(claims["sub"]),
        email=str(email),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


async def _fetch_jwks() -> dict[str, object]:
    async with _http().AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(_JWKS_URI)
    if response.status_code != 200:
        raise GoogleAuthError(f"could not fetch Google JWKS ({response.status_code})")
    return dict(response.json())
