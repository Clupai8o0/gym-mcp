"""OAuth 2.1 Authorization-Server logic (docs/05 — SECURITY-CRITICAL).

Framework-free domain layer for the AS: DCR, authorization-code issuance/exchange, refresh
rotation with reuse-triggered chain revocation, and the resource-server token resolver. The
``app/oauth`` routers are thin adapters that translate :class:`OAuthError` into spec error
responses and orchestrate the interactive consent flow.

Invariants enforced here (each a docs/05 checklist item):

* Authorization codes: single-use (atomic guarded consume), hashed at rest, ≤60s TTL, bound
  to client + redirect_uri + PKCE challenge + resource.
* PKCE **S256 mandatory** (``core.security.verify_pkce_s256``); ``plain`` never accepted.
* ``redirect_uri`` **exact-match** against the registered set (no prefix/substring).
* Access & refresh tokens: opaque 256-bit, stored only as HMAC-SHA256 hashes, audience-bound
  to ``resource``.
* Refresh **rotation** on every use; reuse of a revoked token revokes the whole chain **and**
  the client's live access tokens (token-theft response).
* DCR redirect_uris https-validated against an allowlist; endpoint rate-limited; every
  registration logged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlsplit

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import (
    OAuthAccessToken,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthRefreshToken,
)

logger = get_logger("tempo.oauth")

# Scopes advertised in the AS/PRM metadata (docs/05 B1). Dot form is the wire contract.
SUPPORTED_SCOPES = frozenset({"workouts.read", "workouts.write"})
DEFAULT_SCOPE = "workouts.read workouts.write"
_SUPPORTED_GRANT_TYPES = frozenset({"authorization_code", "refresh_token"})


class OAuthError(Exception):
    """An OAuth protocol error (RFC 6749 §5.2 / §4.1.2.1).

    ``redirectable`` distinguishes errors that may be returned to the client by redirecting
    to a *validated* ``redirect_uri`` (e.g. bad scope) from those that must **not** (unknown
    client / unvalidated redirect_uri) — the latter are rendered as an error page to avoid
    becoming an open redirector.
    """

    def __init__(
        self,
        error: str,
        description: str,
        *,
        status: int = 400,
        redirectable: bool = True,
    ) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status
        self.redirectable = redirectable


@dataclass(frozen=True)
class IssuedTokens:
    """Freshly minted plaintext tokens — returned to the client exactly once."""

    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    token_type: str = "Bearer"


@dataclass(frozen=True)
class TokenPrincipal:
    """The identity/authorization carried by a valid access token."""

    user_id: uuid.UUID
    client_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class AuthorizationRequest:
    """A validated ``GET /oauth/authorize`` request, ready for consent + code issuance."""

    client: OAuthClient
    redirect_uri: str
    scope: str
    state: str | None
    code_challenge: str
    resource: str


# ── scope / resource helpers ─────────────────────────────────────────────────────────
def parse_scope(raw: str | None) -> frozenset[str]:
    return frozenset(part for part in (raw or "").split() if part)


def format_scope(scopes: frozenset[str]) -> str:
    return " ".join(sorted(scopes))


def _validated_scope(requested: str | None) -> str:
    if not requested:
        return DEFAULT_SCOPE
    scopes = parse_scope(requested)
    unknown = scopes - SUPPORTED_SCOPES
    if unknown:
        raise OAuthError("invalid_scope", f"unsupported scope(s): {' '.join(sorted(unknown))}")
    return format_scope(scopes)


def _validated_resource(resource: str | None) -> str:
    """Bind to our single MCP resource (RFC 8707); reject a mismatched explicit value."""
    expected = get_settings().mcp_resource
    if resource and resource != expected:
        raise OAuthError("invalid_target", f"resource must be {expected}")
    return expected


# ── Dynamic Client Registration (RFC 7591) ───────────────────────────────────────────
def _validate_redirect_uris(redirect_uris: list[str]) -> None:
    if not redirect_uris:
        raise OAuthError("invalid_redirect_uri", "at least one redirect_uri is required")
    allowed_hosts = get_settings().allowed_redirect_hosts_list
    for uri in redirect_uris:
        parts = urlsplit(uri)
        if parts.scheme != "https":
            raise OAuthError("invalid_redirect_uri", f"redirect_uri must be https: {uri}")
        host = (parts.hostname or "").lower()
        if host not in allowed_hosts:
            raise OAuthError("invalid_redirect_uri", f"redirect_uri host not allowed: {uri}")
        if parts.fragment:
            raise OAuthError("invalid_redirect_uri", "redirect_uri must not contain a fragment")


async def _enforce_registration_rate_limit(db: AsyncSession) -> None:
    """Coarse, stateless DCR backstop: cap new registrations per rolling minute.

    ``/oauth/register`` is unauthenticated by spec; a global per-minute cap (counted from the
    table itself, so it holds across serverless instances) blunts registration floods. A
    per-personal-app abuse guard — not a substitute for an edge WAF at scale (noted in docs).
    """
    settings = get_settings()
    window_start = datetime.now(UTC) - timedelta(minutes=1)
    recent = (
        await db.execute(
            select(func.count())
            .select_from(OAuthClient)
            .where(OAuthClient.created_at >= window_start)
        )
    ).scalar_one()
    if recent >= settings.oauth_registration_rate_limit_per_minute:
        raise OAuthError(
            "temporarily_unavailable",
            "registration rate limit exceeded; retry shortly",
            status=429,
        )


async def register_client(
    db: AsyncSession,
    *,
    client_name: str | None,
    redirect_uris: list[str],
    grant_types: list[str] | None = None,
    scope: str | None = None,
) -> OAuthClient:
    """Register a **public** client (no secret). Validates + rate-limits + logs (docs/05 B2)."""
    _validate_redirect_uris(redirect_uris)
    await _enforce_registration_rate_limit(db)

    grants = grant_types or ["authorization_code", "refresh_token"]
    unsupported = set(grants) - _SUPPORTED_GRANT_TYPES
    if unsupported:
        raise OAuthError(
            "invalid_client_metadata",
            f"unsupported grant_types: {' '.join(sorted(unsupported))}",
        )
    scope_str = _validated_scope(scope)

    client = OAuthClient(
        client_id=f"tempo-{security.generate_opaque_token()}",
        client_secret_hash=None,  # public client — no secret to store
        client_name=client_name,
        redirect_uris=list(redirect_uris),
        grant_types=grants,
        token_endpoint_auth_method="none",
        scope=scope_str,
        is_dynamic=True,
    )
    db.add(client)
    await db.flush()
    logger.info(
        "oauth_client_registered",
        extra={
            "client_id": client.client_id,
            "client_name": client_name,
            "redirect_uris": list(redirect_uris),
        },
    )
    return client


async def get_client(db: AsyncSession, client_id: str) -> OAuthClient | None:
    return (
        await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
    ).scalar_one_or_none()


# ── Authorization endpoint (PKCE code flow) ──────────────────────────────────────────
async def build_authorization_request(
    db: AsyncSession,
    *,
    client_id: str | None,
    redirect_uri: str | None,
    response_type: str | None,
    scope: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    resource: str | None,
    state: str | None,
) -> AuthorizationRequest:
    """Validate an authorize request. Client/redirect errors are **not** redirectable."""
    client = await get_client(db, client_id) if client_id else None
    if client is None:
        raise OAuthError("invalid_client", "unknown client_id", redirectable=False)
    # Exact-match redirect_uri BEFORE trusting it as a redirect target (open-redirect guard).
    if not redirect_uri or redirect_uri not in client.redirect_uris:
        raise OAuthError(
            "invalid_request",
            "redirect_uri does not exactly match a registered URI",
            redirectable=False,
        )

    # Past this point redirect_uri is trusted → remaining errors may redirect back with ?error=.
    if response_type != "code":
        raise OAuthError("unsupported_response_type", "only response_type=code is supported")
    if not code_challenge:
        raise OAuthError("invalid_request", "code_challenge is required (PKCE)")
    if code_challenge_method != "S256":
        raise OAuthError("invalid_request", "code_challenge_method must be S256")
    scope_str = _validated_scope(scope)
    resource_str = _validated_resource(resource)
    return AuthorizationRequest(
        client=client,
        redirect_uri=redirect_uri,
        scope=scope_str,
        state=state,
        code_challenge=code_challenge,
        resource=resource_str,
    )


async def create_authorization_code(
    db: AsyncSession, *, request: AuthorizationRequest, user_id: uuid.UUID
) -> str:
    """Mint a single-use auth code for ``user_id`` (stores only its hash). Returns plaintext."""
    code = security.generate_opaque_token()
    now = datetime.now(UTC)
    db.add(
        OAuthAuthorizationCode(
            code_hash=security.hash_token(code),
            client_id=request.client.client_id,
            user_id=user_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            code_challenge=request.code_challenge,
            code_challenge_method="S256",
            resource=request.resource,
            expires_at=now + timedelta(seconds=get_settings().auth_code_ttl_seconds),
        )
    )
    await db.flush()
    logger.info(
        "oauth_code_issued",
        extra={
            "client_id": request.client.client_id,
            "user_id": str(user_id),
            "scope": request.scope,
        },
    )
    return code


# ── Token endpoint ───────────────────────────────────────────────────────────────────
async def exchange_authorization_code(
    db: AsyncSession,
    *,
    code: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    code_verifier: str | None,
    resource: str | None,
) -> IssuedTokens:
    """``grant_type=authorization_code``: validate, atomically consume, issue tokens."""
    if not (code and client_id and redirect_uri and code_verifier):
        raise OAuthError("invalid_request", "missing required parameter")

    row = (
        await db.execute(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.code_hash == security.hash_token(code)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise OAuthError("invalid_grant", "authorization code not found")
    now = datetime.now(UTC)
    if row.consumed_at is not None:
        raise OAuthError("invalid_grant", "authorization code has already been used")
    if row.expires_at <= now:
        raise OAuthError("invalid_grant", "authorization code has expired")
    if row.client_id != client_id:
        raise OAuthError("invalid_grant", "authorization code was issued to a different client")
    if row.redirect_uri != redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request")
    if not security.verify_pkce_s256(code_verifier, row.code_challenge):
        raise OAuthError("invalid_grant", "PKCE verification failed")
    if resource and resource != row.resource:
        raise OAuthError("invalid_target", "resource does not match the authorization request")

    # Single-use: only the request that flips consumed_at from NULL wins (race-safe).
    consumed = await db.execute(
        update(OAuthAuthorizationCode)
        .where(
            OAuthAuthorizationCode.id == row.id,
            OAuthAuthorizationCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    if cast("CursorResult[Any]", consumed).rowcount != 1:
        raise OAuthError("invalid_grant", "authorization code has already been used")

    return await _issue_token_pair(
        db,
        user_id=row.user_id,
        client_id=row.client_id,
        scope=row.scope or DEFAULT_SCOPE,
        resource=row.resource or get_settings().mcp_resource,
    )


async def refresh_access_token(
    db: AsyncSession,
    *,
    refresh_token: str | None,
    client_id: str | None,
    resource: str | None = None,
) -> IssuedTokens:
    """``grant_type=refresh_token``: rotate; reuse of a revoked token revokes the chain."""
    if not (refresh_token and client_id):
        raise OAuthError("invalid_request", "missing required parameter")

    row = (
        await db.execute(
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.token_hash == security.hash_token(refresh_token)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise OAuthError("invalid_grant", "refresh token not found")
    if row.client_id != client_id:
        raise OAuthError("invalid_grant", "refresh token was issued to a different client")

    now = datetime.now(UTC)
    if row.revoked_at is not None:
        # Reuse of an already-rotated token → token theft. Burn the whole lineage.
        await _revoke_chain(db, chain_id=row.chain_id, user_id=row.user_id, client_id=row.client_id)
        logger.warning(
            "oauth_refresh_reuse_detected",
            extra={
                "client_id": row.client_id,
                "user_id": str(row.user_id),
                "chain_id": str(row.chain_id),
            },
        )
        raise OAuthError("invalid_grant", "refresh token has been revoked")
    if row.expires_at <= now:
        raise OAuthError("invalid_grant", "refresh token has expired")
    if resource and resource != row.resource:
        raise OAuthError("invalid_target", "resource does not match")

    # Rotate: revoke the presented token first; only the winner of the race proceeds.
    revoked = await db.execute(
        update(OAuthRefreshToken)
        .where(OAuthRefreshToken.id == row.id, OAuthRefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if cast("CursorResult[Any]", revoked).rowcount != 1:
        raise OAuthError("invalid_grant", "refresh token has already been used")

    return await _issue_token_pair(
        db,
        user_id=row.user_id,
        client_id=row.client_id,
        scope=row.scope or DEFAULT_SCOPE,
        resource=row.resource or get_settings().mcp_resource,
        chain_id=row.chain_id,
        rotated_from=row.id,
    )


# ── Resource-server token resolution (the /mcp guard) ─────────────────────────────────
async def resolve_access_token(
    db: AsyncSession, *, token: str | None, required_resource: str | None
) -> TokenPrincipal | None:
    """Resolve a bearer token → principal, or ``None`` if invalid/expired/revoked/mis-audienced."""
    if not token:
        return None
    row = (
        await db.execute(
            select(OAuthAccessToken).where(
                OAuthAccessToken.token_hash == security.hash_token(token)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.revoked_at is not None or row.expires_at <= datetime.now(UTC):
        return None
    # Audience binding (docs/05 B5): the token must have been issued for this resource.
    if required_resource is not None and row.resource != required_resource:
        return None
    return TokenPrincipal(
        user_id=row.user_id,
        client_id=row.client_id,
        scopes=parse_scope(row.scope),
    )


# ── internals ─────────────────────────────────────────────────────────────────────────
async def _issue_token_pair(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    client_id: str,
    scope: str,
    resource: str,
    chain_id: uuid.UUID | None = None,
    rotated_from: uuid.UUID | None = None,
) -> IssuedTokens:
    settings = get_settings()
    now = datetime.now(UTC)
    access = security.generate_opaque_token()
    refresh = security.generate_opaque_token()

    db.add(
        OAuthAccessToken(
            token_hash=security.hash_token(access),
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=resource,
            expires_at=now + timedelta(seconds=settings.access_token_ttl_seconds),
        )
    )
    db.add(
        OAuthRefreshToken(
            token_hash=security.hash_token(refresh),
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=resource,
            # Set explicitly (not via server_default) to avoid an async lazy-refresh of the
            # column, and to thread the same chain_id through a rotation.
            chain_id=chain_id or uuid.uuid4(),
            rotated_from=rotated_from,
            expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    await db.flush()
    return IssuedTokens(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_seconds,
        scope=scope,
    )


async def _revoke_chain(
    db: AsyncSession, *, chain_id: uuid.UUID, user_id: uuid.UUID, client_id: str
) -> None:
    """Token-theft response: revoke every refresh token in the chain + the client's live
    access tokens, forcing a full re-authorization."""
    now = datetime.now(UTC)
    await db.execute(
        update(OAuthRefreshToken)
        .where(
            OAuthRefreshToken.chain_id == chain_id,
            OAuthRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.execute(
        update(OAuthAccessToken)
        .where(
            OAuthAccessToken.user_id == user_id,
            OAuthAccessToken.client_id == client_id,
            OAuthAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()
