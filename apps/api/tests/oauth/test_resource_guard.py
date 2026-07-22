"""The ``/mcp`` resource guard: bearer enforcement + RFC 9728 401 pointer (docs/05 B5)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import bearer, mint_access_token
from tests._factories import make_user


async def test_mcp_unauthenticated_401_carries_prm_pointer(unauth_client: AsyncClient) -> None:
    response = await unauth_client.get("/mcp")
    assert response.status_code == 401
    www = response.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert 'resource_metadata="' in www
    assert "/.well-known/oauth-protected-resource" in www


async def test_mcp_accepts_valid_bearer(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    response = await unauth_client.get("/mcp", headers=bearer(tokens.access_token))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["user_id"] == str(user.id)


async def test_mcp_rejects_invalid_token(unauth_client: AsyncClient) -> None:
    response = await unauth_client.get("/mcp", headers=bearer("garbage-token"))
    assert response.status_code == 401
    assert "www-authenticate" in {k.lower() for k in response.headers}


async def test_mcp_insufficient_scope(unauth_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id, scope="")
    response = await unauth_client.get("/mcp", headers=bearer(tokens.access_token))
    assert response.status_code == 403
    assert response.json()["error"] == "insufficient_scope"
