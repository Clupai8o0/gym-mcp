"""DCR endpoint — ``POST /oauth/register`` (docs/05 B2)."""

from __future__ import annotations

from httpx import AsyncClient

from tests._authhelp import CLAUDE_REDIRECT


async def test_register_public_client(unauth_client: AsyncClient) -> None:
    response = await unauth_client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_REDIRECT]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["client_id"].startswith("tempo-")
    assert "client_secret" not in body  # public client
    assert body["token_endpoint_auth_method"] == "none"
    assert body["redirect_uris"] == [CLAUDE_REDIRECT]
    assert body["grant_types"] == ["authorization_code", "refresh_token"]


async def test_register_rejects_non_https_redirect(unauth_client: AsyncClient) -> None:
    response = await unauth_client.post(
        "/oauth/register", json={"redirect_uris": ["http://claude.ai/api/mcp/auth_callback"]}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


async def test_register_rejects_disallowed_host(unauth_client: AsyncClient) -> None:
    response = await unauth_client.post(
        "/oauth/register", json={"redirect_uris": ["https://evil.example.com/cb"]}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


async def test_register_requires_at_least_one_redirect_uri(unauth_client: AsyncClient) -> None:
    response = await unauth_client.post(
        "/oauth/register", json={"client_name": "x", "redirect_uris": []}
    )
    assert response.status_code == 422  # pydantic min_length guard
