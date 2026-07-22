"""Authorize + consent HTTP behavior (docs/05 B3)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import (
    CLAUDE_REDIRECT,
    extract_approval,
    pkce_pair,
    register_claude_client,
    session_cookies,
)
from tests._factories import make_user


def _params(client_id: str, challenge: str, **overrides: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CLAUDE_REDIRECT,
        "scope": "workouts.read workouts.write",
        "state": "st-1",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return params


async def test_authorize_without_session_redirects_to_login(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    client = await register_claude_client(db_session)
    _verifier, challenge = pkce_pair()
    response = await unauth_client.get(
        "/oauth/authorize", params=_params(client.client_id, challenge), follow_redirects=False
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "/oauth/login/google" in location
    assert "return_to=" in location


async def test_authorize_with_session_shows_consent(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    client = await register_claude_client(db_session)
    _verifier, challenge = pkce_pair()
    response = await unauth_client.get(
        "/oauth/authorize",
        params=_params(client.client_id, challenge),
        cookies=session_cookies(user.id),
    )
    assert response.status_code == 200
    assert "wants to connect" in response.text
    assert extract_approval(response.text)  # a signed approval token is embedded


async def test_consent_deny_redirects_with_error(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    client = await register_claude_client(db_session)
    _verifier, challenge = pkce_pair()
    page = await unauth_client.get(
        "/oauth/authorize",
        params=_params(client.client_id, challenge),
        cookies=session_cookies(user.id),
    )
    approval = extract_approval(page.text)
    response = await unauth_client.post(
        "/oauth/authorize/consent",
        data={"approval": approval, "decision": "deny"},
        cookies=session_cookies(user.id),
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(CLAUDE_REDIRECT)
    assert "error=access_denied" in location
    assert "state=st-1" in location


async def test_authorize_bad_redirect_uri_renders_error_not_redirect(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    client = await register_claude_client(db_session)
    _verifier, challenge = pkce_pair()
    response = await unauth_client.get(
        "/oauth/authorize",
        params=_params(client.client_id, challenge, redirect_uri="https://claude.ai/EVIL"),
        cookies=session_cookies(uuid.uuid4()),
        follow_redirects=False,
    )
    # Unregistered redirect_uri must NOT be used as a redirect target (open-redirect guard).
    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    assert "location" not in {k.lower() for k in response.headers}


async def test_consent_rejects_forged_approval(unauth_client: AsyncClient) -> None:
    response = await unauth_client.post(
        "/oauth/authorize/consent",
        data={"approval": "not.a.valid.token", "decision": "approve"},
        follow_redirects=False,
    )
    assert response.status_code == 400
