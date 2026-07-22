"""Connected-apps router: list the user's grants and revoke one (docs/07)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import mint_access_token
from tests._factories import make_user  # noqa: F401  (kept for symmetry with service tests)


async def test_list_then_revoke(app_client: AsyncClient, db_session: AsyncSession) -> None:
    from app.services import users

    dev = await users.ensure_dev_user(db_session)
    client, _ = await mint_access_token(db_session, user_id=dev.id)

    listed = await app_client.get("/api/connections")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["client_id"] == client.client_id
    assert items[0]["client_name"] == "Claude"
    assert items[0]["active_token_count"] == 1

    revoked = await app_client.delete(f"/api/connections/{client.client_id}")
    assert revoked.status_code == 200
    body = revoked.json()
    assert body["revoked_access"] == 1 and body["revoked_refresh"] == 1

    # The grant is gone from the list after revocation.
    again = await app_client.get("/api/connections")
    assert again.json()["items"] == []


async def test_revoke_unknown_client_is_404(app_client: AsyncClient) -> None:
    response = await app_client.delete("/api/connections/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


async def test_list_empty_by_default(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/connections")
    assert response.status_code == 200
    assert response.json() == {"items": []}
