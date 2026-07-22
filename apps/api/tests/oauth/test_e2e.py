"""The Phase 3 DoD: the full OAuth flow end-to-end through HTTP (docs/05 Testing).

discovery → register (DCR) → authorize (logged-in) → consent → token (PKCE) → call /mcp →
refresh (rotation) → reuse the old refresh (→ chain revocation). Google login is bypassed by
forging a valid web-session cookie; every other step is the real endpoint.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import (
    CLAUDE_REDIRECT,
    bearer,
    extract_approval,
    pkce_pair,
    session_cookies,
)
from tests._factories import make_user


async def test_full_oauth_connector_flow(
    unauth_client: AsyncClient, db_session: AsyncSession
) -> None:
    # 1. Discovery
    as_meta = (await unauth_client.get("/.well-known/oauth-authorization-server")).json()
    prm = (await unauth_client.get("/.well-known/oauth-protected-resource")).json()
    resource = prm["resource"]
    assert as_meta["code_challenge_methods_supported"] == ["S256"]

    # 2. Dynamic client registration
    registration = await unauth_client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_REDIRECT]},
    )
    assert registration.status_code == 201
    client_id = registration.json()["client_id"]

    # A logged-in user (Google login stubbed by forging the session cookie).
    user = await make_user(db_session)
    cookies = session_cookies(user.id)

    # 3. Authorize → consent screen
    verifier, challenge = pkce_pair()
    authorize_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CLAUDE_REDIRECT,
        "scope": "workouts.read workouts.write",
        "state": "state-xyz",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
    consent_page = await unauth_client.get(
        "/oauth/authorize", params=authorize_params, cookies=cookies
    )
    assert consent_page.status_code == 200
    approval = extract_approval(consent_page.text)

    # 4. Approve consent → redirect back to the client with code + state
    approved = await unauth_client.post(
        "/oauth/authorize/consent",
        data={"approval": approval, "decision": "approve"},
        cookies=cookies,
        follow_redirects=False,
    )
    assert approved.status_code == 302
    location = approved.headers["location"]
    assert location.startswith(CLAUDE_REDIRECT)
    returned = parse_qs(urlsplit(location).query)
    assert returned["state"] == ["state-xyz"]
    code = returned["code"][0]

    # 5. Exchange the code for tokens (PKCE)
    token_response = await unauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": CLAUDE_REDIRECT,
            "code_verifier": verifier,
            "resource": resource,
        },
    )
    assert token_response.status_code == 200
    assert token_response.headers["cache-control"] == "no-store"
    tokens = token_response.json()
    assert tokens["token_type"] == "Bearer"
    access_token, refresh_token = tokens["access_token"], tokens["refresh_token"]

    # 6. Call the protected resource with the access token
    mcp = await unauth_client.get("/mcp", headers=bearer(access_token))
    assert mcp.status_code == 200
    assert mcp.json()["user_id"] == str(user.id)

    # 7. Refresh → rotation (new refresh + access)
    refreshed = await unauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated["refresh_token"] != refresh_token
    assert rotated["access_token"] != access_token

    # The rotated access token works against /mcp (refresh without re-auth).
    mcp_after_refresh = await unauth_client.get("/mcp", headers=bearer(rotated["access_token"]))
    assert mcp_after_refresh.status_code == 200

    # 8. Reuse the OLD refresh token → theft response: invalid_grant + chain revocation
    reuse = await unauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"

    # The whole chain is revoked: the rotated refresh token no longer works…
    dead_refresh = await unauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rotated["refresh_token"],
            "client_id": client_id,
        },
    )
    assert dead_refresh.status_code == 400

    # …and the rotated access token was revoked too → /mcp now 401.
    mcp_revoked = await unauth_client.get("/mcp", headers=bearer(rotated["access_token"]))
    assert mcp_revoked.status_code == 401
