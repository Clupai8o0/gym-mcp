"""Real ``current_user`` resolution + CSRF enforcement (docs/05 CSRF, deps.current_user)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import bearer, mint_access_token, session_cookies
from tests._factories import make_user


async def test_unauthenticated_request_is_401(unauth_client: AsyncClient) -> None:
    response = await unauth_client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["kind"] == "unauthorized"


async def test_session_cookie_authenticates(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    response = await unauth_client.get("/api/me", cookies=session_cookies(user.id))
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


async def test_bearer_token_authenticates(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    response = await unauth_client.get("/api/me", headers=bearer(tokens.access_token))
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


async def test_cookie_mutation_requires_csrf_header(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    # No X-Tempo-Client header on a cookie-authenticated write → blocked before any work.
    blocked = await unauth_client.delete(
        f"/api/sessions/{uuid.uuid4()}", cookies=session_cookies(user.id)
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["kind"] == "forbidden"

    # With the header, CSRF passes → the (nonexistent) session is simply not found.
    allowed = await unauth_client.delete(
        f"/api/sessions/{uuid.uuid4()}",
        cookies=session_cookies(user.id),
        headers={"X-Tempo-Client": "web"},
    )
    assert allowed.status_code == 404


async def test_bearer_mutation_is_exempt_from_csrf(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    # Bearer clients carry no cookie → no CSRF requirement; nonexistent session → 404.
    response = await unauth_client.delete(
        f"/api/sessions/{uuid.uuid4()}", headers=bearer(tokens.access_token)
    )
    assert response.status_code == 404
