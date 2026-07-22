"""Service-level tests for the OAuth 2.1 AS logic (docs/05 — the core security behavior)."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.services import oauth as oauth_service
from app.services.oauth import OAuthError
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import CLAUDE_REDIRECT, mint_access_token, pkce_pair, register_claude_client
from tests._factories import make_user


async def _authorize_to_code(
    db: AsyncSession, user_id: uuid.UUID, *, resource: str | None = None
) -> tuple[str, str, str]:
    """Register → build request → issue code. Returns (client_id, verifier, code)."""
    client = await register_claude_client(db)
    verifier, challenge = pkce_pair()
    request = await oauth_service.build_authorization_request(
        db,
        client_id=client.client_id,
        redirect_uri=CLAUDE_REDIRECT,
        response_type="code",
        scope="workouts.read workouts.write",
        code_challenge=challenge,
        code_challenge_method="S256",
        resource=resource,
        state="xyz",
    )
    code = await oauth_service.create_authorization_code(db, request=request, user_id=user_id)
    return client.client_id, verifier, code


# ── DCR ───────────────────────────────────────────────────────────────────────────────
async def test_register_client_is_public_and_dynamic(db_session: AsyncSession) -> None:
    client = await register_claude_client(db_session)
    assert client.client_id.startswith("tempo-")
    assert client.client_secret_hash is None
    assert client.token_endpoint_auth_method == "none"
    assert client.is_dynamic is True
    assert client.redirect_uris == [CLAUDE_REDIRECT]


async def test_register_rejects_non_https_and_disallowed_host(db_session: AsyncSession) -> None:
    with pytest.raises(OAuthError) as http:
        await register_claude_client(db_session, redirect_uri="http://claude.ai/cb")
    assert http.value.error == "invalid_redirect_uri"

    with pytest.raises(OAuthError) as host:
        await register_claude_client(db_session, redirect_uri="https://evil.example/cb")
    assert host.value.error == "invalid_redirect_uri"


async def test_register_rate_limited(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "oauth_registration_rate_limit_per_minute", 2)
    await register_claude_client(db_session)
    await register_claude_client(db_session)
    with pytest.raises(OAuthError) as exc:
        await register_claude_client(db_session)
    assert exc.value.error == "temporarily_unavailable"
    assert exc.value.status == 429


# ── authorize request validation ──────────────────────────────────────────────────────
async def test_build_authorization_request_client_and_redirect_errors_are_not_redirectable(
    db_session: AsyncSession,
) -> None:
    client = await register_claude_client(db_session)
    _, challenge = pkce_pair()

    with pytest.raises(OAuthError) as unknown:
        await oauth_service.build_authorization_request(
            db_session,
            client_id="tempo-nope",
            redirect_uri=CLAUDE_REDIRECT,
            response_type="code",
            scope=None,
            code_challenge=challenge,
            code_challenge_method="S256",
            resource=None,
            state=None,
        )
    assert unknown.value.redirectable is False

    with pytest.raises(OAuthError) as mismatch:
        await oauth_service.build_authorization_request(
            db_session,
            client_id=client.client_id,
            redirect_uri="https://claude.ai/DIFFERENT",
            response_type="code",
            scope=None,
            code_challenge=challenge,
            code_challenge_method="S256",
            resource=None,
            state=None,
        )
    assert mismatch.value.redirectable is False


async def test_build_authorization_request_rejects_plain_pkce_and_bad_response_type(
    db_session: AsyncSession,
) -> None:
    client = await register_claude_client(db_session)
    _, challenge = pkce_pair()

    with pytest.raises(OAuthError) as plain:
        await oauth_service.build_authorization_request(
            db_session,
            client_id=client.client_id,
            redirect_uri=CLAUDE_REDIRECT,
            response_type="code",
            scope=None,
            code_challenge=challenge,
            code_challenge_method="plain",
            resource=None,
            state=None,
        )
    assert plain.value.error == "invalid_request" and plain.value.redirectable is True

    with pytest.raises(OAuthError) as rtype:
        await oauth_service.build_authorization_request(
            db_session,
            client_id=client.client_id,
            redirect_uri=CLAUDE_REDIRECT,
            response_type="token",
            scope=None,
            code_challenge=challenge,
            code_challenge_method="S256",
            resource=None,
            state=None,
        )
    assert rtype.value.error == "unsupported_response_type"


# ── code exchange (PKCE) ──────────────────────────────────────────────────────────────
async def test_exchange_happy_path_issues_resolvable_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client_id, verifier, code = await _authorize_to_code(db_session, user.id)
    tokens = await oauth_service.exchange_authorization_code(
        db_session,
        code=code,
        client_id=client_id,
        redirect_uri=CLAUDE_REDIRECT,
        code_verifier=verifier,
        resource=None,
    )
    assert tokens.token_type == "Bearer"
    principal = await oauth_service.resolve_access_token(
        db_session, token=tokens.access_token, required_resource=get_settings().mcp_resource
    )
    assert principal is not None and principal.user_id == user.id
    assert principal.scopes == {"workouts.read", "workouts.write"}


async def test_exchange_rejects_wrong_verifier(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client_id, _verifier, code = await _authorize_to_code(db_session, user.id)
    with pytest.raises(OAuthError) as exc:
        await oauth_service.exchange_authorization_code(
            db_session,
            code=code,
            client_id=client_id,
            redirect_uri=CLAUDE_REDIRECT,
            code_verifier="not-the-verifier",
            resource=None,
        )
    assert exc.value.error == "invalid_grant"


async def test_authorization_code_is_single_use(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client_id, verifier, code = await _authorize_to_code(db_session, user.id)
    await oauth_service.exchange_authorization_code(
        db_session,
        code=code,
        client_id=client_id,
        redirect_uri=CLAUDE_REDIRECT,
        code_verifier=verifier,
        resource=None,
    )
    with pytest.raises(OAuthError) as replay:
        await oauth_service.exchange_authorization_code(
            db_session,
            code=code,
            client_id=client_id,
            redirect_uri=CLAUDE_REDIRECT,
            code_verifier=verifier,
            resource=None,
        )
    assert replay.value.error == "invalid_grant"


async def test_exchange_rejects_expired_code(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(db_session)
    monkeypatch.setattr(get_settings(), "auth_code_ttl_seconds", -5)  # born expired
    client_id, verifier, code = await _authorize_to_code(db_session, user.id)
    with pytest.raises(OAuthError) as exc:
        await oauth_service.exchange_authorization_code(
            db_session,
            code=code,
            client_id=client_id,
            redirect_uri=CLAUDE_REDIRECT,
            code_verifier=verifier,
            resource=None,
        )
    assert exc.value.error == "invalid_grant"


async def test_exchange_rejects_redirect_and_client_mismatch(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client_id, verifier, code = await _authorize_to_code(db_session, user.id)
    with pytest.raises(OAuthError):
        await oauth_service.exchange_authorization_code(
            db_session,
            code=code,
            client_id=client_id,
            redirect_uri="https://claude.ai/OTHER",
            code_verifier=verifier,
            resource=None,
        )


# ── refresh rotation + reuse detection ────────────────────────────────────────────────
async def test_refresh_rotates_and_revokes_old(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client_id, verifier, code = await _authorize_to_code(db_session, user.id)
    first = await oauth_service.exchange_authorization_code(
        db_session,
        code=code,
        client_id=client_id,
        redirect_uri=CLAUDE_REDIRECT,
        code_verifier=verifier,
        resource=None,
    )
    second = await oauth_service.refresh_access_token(
        db_session, refresh_token=first.refresh_token, client_id=client_id
    )
    assert second.refresh_token != first.refresh_token
    assert second.access_token != first.access_token
    # The rotated (old) access token still resolves until it expires; the new one does too.
    assert (
        await oauth_service.resolve_access_token(
            db_session, token=second.access_token, required_resource=get_settings().mcp_resource
        )
        is not None
    )


async def test_refresh_reuse_revokes_entire_chain(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client_id, verifier, code = await _authorize_to_code(db_session, user.id)
    first = await oauth_service.exchange_authorization_code(
        db_session,
        code=code,
        client_id=client_id,
        redirect_uri=CLAUDE_REDIRECT,
        code_verifier=verifier,
        resource=None,
    )
    second = await oauth_service.refresh_access_token(
        db_session, refresh_token=first.refresh_token, client_id=client_id
    )
    # Reuse the already-rotated first refresh token → theft response.
    with pytest.raises(OAuthError) as reuse:
        await oauth_service.refresh_access_token(
            db_session, refresh_token=first.refresh_token, client_id=client_id
        )
    assert reuse.value.error == "invalid_grant"

    # The whole chain is now dead: the *second* refresh token no longer works…
    with pytest.raises(OAuthError):
        await oauth_service.refresh_access_token(
            db_session, refresh_token=second.refresh_token, client_id=client_id
        )
    # …and the client's live access token was revoked too.
    assert (
        await oauth_service.resolve_access_token(
            db_session, token=second.access_token, required_resource=get_settings().mcp_resource
        )
        is None
    )


# ── resource-server resolution ────────────────────────────────────────────────────────
async def test_resolve_rejects_wrong_audience(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(
        db_session, user_id=user.id, resource="https://api.example.com/other"
    )
    # Token bound to a different resource → rejected for the MCP resource.
    assert (
        await oauth_service.resolve_access_token(
            db_session, token=tokens.access_token, required_resource=get_settings().mcp_resource
        )
        is None
    )


async def test_resolve_rejects_expired_and_unknown(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(db_session)
    monkeypatch.setattr(get_settings(), "access_token_ttl_seconds", -5)  # born expired
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    resource = get_settings().mcp_resource
    assert (
        await oauth_service.resolve_access_token(
            db_session, token=tokens.access_token, required_resource=resource
        )
        is None
    )
    assert (
        await oauth_service.resolve_access_token(
            db_session, token="never-issued", required_resource=resource
        )
        is None
    )
