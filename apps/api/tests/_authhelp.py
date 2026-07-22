"""Shared helpers for the Phase 3 auth/OAuth tests (docs/05)."""

from __future__ import annotations

import re
import uuid

from app.auth import session as auth_session
from app.core import security
from app.core.config import get_settings
from app.models import OAuthClient
from app.services import oauth as oauth_service
from sqlalchemy.ext.asyncio import AsyncSession

# The real claude.ai MCP callback (an allowed redirect host by default).
CLAUDE_REDIRECT = "https://claude.ai/api/mcp/auth_callback"

_APPROVAL_RE = re.compile(r'name="approval" value="([^"]+)"')


def pkce_pair() -> tuple[str, str]:
    """A fresh ``(code_verifier, code_challenge)`` PKCE S256 pair."""
    verifier = security.generate_opaque_token()
    return verifier, security.compute_s256_challenge(verifier)


def session_cookies(user_id: uuid.UUID) -> dict[str, str]:
    """A cookie dict carrying a valid signed web session for ``user_id``."""
    return {auth_session.SESSION_COOKIE: auth_session.issue_session_token(user_id)}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def extract_approval(html: str) -> str:
    """Pull the signed ``approval`` token out of a rendered consent page."""
    match = _APPROVAL_RE.search(html)
    assert match, "consent page did not contain an approval token"
    return match.group(1)


async def register_claude_client(
    db: AsyncSession, *, redirect_uri: str = CLAUDE_REDIRECT
) -> OAuthClient:
    return await oauth_service.register_client(
        db, client_name="Claude", redirect_uris=[redirect_uri], grant_types=None, scope=None
    )


async def mint_access_token(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    scope: str = "workouts.read workouts.write",
    resource: str | None = None,
) -> tuple[OAuthClient, oauth_service.IssuedTokens]:
    """Register a client and mint a token pair directly (bypasses the interactive flow)."""
    client = await register_claude_client(db)
    tokens = await oauth_service._issue_token_pair(  # test seam into the issuance internals
        db,
        user_id=user_id,
        client_id=client.client_id,
        scope=scope,
        resource=resource or get_settings().mcp_resource,
    )
    return client, tokens
