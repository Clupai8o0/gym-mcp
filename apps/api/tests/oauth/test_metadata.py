"""Discovery well-knowns serve spec-conformant metadata (docs/05 B1)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_authorization_server_metadata(unauth_client: AsyncClient) -> None:
    response = await unauth_client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 200
    meta = response.json()

    # claude.ai checks these exactly.
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert meta["response_types_supported"] == ["code"]
    assert meta["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert meta["token_endpoint_auth_methods_supported"] == ["none"]
    assert set(meta["scopes_supported"]) == {"workouts.read", "workouts.write"}

    # issuer must be exactly the base of every advertised endpoint.
    issuer = meta["issuer"]
    assert meta["authorization_endpoint"] == f"{issuer}/oauth/authorize"
    assert meta["token_endpoint"] == f"{issuer}/oauth/token"
    assert meta["registration_endpoint"] == f"{issuer}/oauth/register"


async def test_protected_resource_metadata(unauth_client: AsyncClient) -> None:
    response = await unauth_client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    meta = response.json()
    assert meta["resource"].endswith("/mcp")
    assert meta["bearer_methods_supported"] == ["header"]
    assert set(meta["scopes_supported"]) == {"workouts.read", "workouts.write"}
    assert meta["authorization_servers"], "must advertise at least one AS"
