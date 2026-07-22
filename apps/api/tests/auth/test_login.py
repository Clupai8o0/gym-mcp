"""Google OIDC login endpoints (docs/05 Part A) — Google calls are stubbed."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from app.auth import google
from app.auth import session as auth_session
from app.auth.google import GoogleIdentity
from app.core.config import get_settings
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_login_redirects_to_google_with_pkce(
    unauth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", "cid.apps.googleusercontent.com")
    response = await unauth_client.get("/oauth/login/google", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    query = parse_qs(urlsplit(location).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"] and query["nonce"] and query["code_challenge"]
    # The login transaction (state/nonce/PKCE verifier) is planted in a cookie.
    assert auth_session.OIDC_TX_COOKIE in response.cookies


async def test_login_unconfigured_is_unavailable(unauth_client: AsyncClient) -> None:
    # Default google_client_id is empty in tests → login is not offered.
    response = await unauth_client.get("/oauth/login/google", follow_redirects=False)
    assert response.status_code == 503


async def test_callback_verifies_and_establishes_session(
    unauth_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    tx = auth_session.issue_oidc_tx(
        state="st-abc", nonce="n-1", code_verifier="v-1", return_to=settings.web_origin
    )

    async def fake_exchange(*, code: str, code_verifier: str) -> str:
        return "id-token"

    async def fake_verify(id_token: str, *, nonce: str) -> GoogleIdentity:
        return GoogleIdentity(sub="g-123", email="new@example.com", name="New", picture=None)

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    monkeypatch.setattr(google, "verify_id_token", fake_verify)

    response = await unauth_client.get(
        "/oauth/callback/google",
        params={"code": "abc", "state": "st-abc"},
        cookies={auth_session.OIDC_TX_COOKIE: tx},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert auth_session.SESSION_COOKIE in response.cookies

    # The established session authenticates a real, upserted user.
    session_cookie = response.cookies[auth_session.SESSION_COOKIE]
    me = await unauth_client.get("/api/me", cookies={auth_session.SESSION_COOKIE: session_cookie})
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


async def test_callback_rejects_forged_state(
    unauth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tx = auth_session.issue_oidc_tx(
        state="real-state", nonce="n", code_verifier="v", return_to=get_settings().web_origin
    )
    response = await unauth_client.get(
        "/oauth/callback/google",
        params={"code": "abc", "state": "forged-state"},
        cookies={auth_session.OIDC_TX_COOKIE: tx},
        follow_redirects=False,
    )
    assert response.status_code == 400


async def test_callback_without_transaction_cookie_fails(unauth_client: AsyncClient) -> None:
    response = await unauth_client.get(
        "/oauth/callback/google",
        params={"code": "abc", "state": "whatever"},
        follow_redirects=False,
    )
    assert response.status_code == 400
