"""Connected-apps service: list active grants and revoke them (user-scoped)."""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.core.errors import ServiceError
from app.services import connections
from app.services import oauth as oauth_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import mint_access_token, register_claude_client
from tests._factories import make_user


async def test_list_returns_one_row_per_client(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await mint_access_token(db_session, user_id=user.id)
    await mint_access_token(db_session, user_id=user.id)  # a second, distinct client

    rows = await connections.list_connections(db_session, user_id=user.id)
    assert len(rows) == 2
    assert all(r.client_name == "Claude" for r in rows)
    assert all(r.active_token_count == 1 for r in rows)
    assert all(r.connected_at is not None and r.last_active_at is not None for r in rows)


async def test_list_excludes_other_users(db_session: AsyncSession) -> None:
    mine = await make_user(db_session, email="me@example.com")
    other = await make_user(db_session, email="other@example.com")
    my_client, _ = await mint_access_token(db_session, user_id=mine.id)
    await mint_access_token(db_session, user_id=other.id)

    rows = await connections.list_connections(db_session, user_id=mine.id)
    assert len(rows) == 1
    assert rows[0].client_id == my_client.client_id


async def test_revoke_kills_the_access_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client, tokens = await mint_access_token(db_session, user_id=user.id)

    # Sanity: the token resolves before revocation.
    resource = get_settings().mcp_resource
    principal = await oauth_service.resolve_access_token(
        db_session, token=tokens.access_token, required_resource=resource
    )
    assert principal is not None

    result = await connections.revoke_connection(
        db_session, user_id=user.id, client_id=client.client_id
    )
    assert result.revoked_access == 1
    assert result.revoked_refresh == 1

    # After revocation the token no longer resolves and the grant disappears from the list.
    assert (
        await oauth_service.resolve_access_token(
            db_session, token=tokens.access_token, required_resource=resource
        )
        is None
    )
    assert await connections.list_connections(db_session, user_id=user.id) == []


async def test_revoke_is_idempotent(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    client, _ = await mint_access_token(db_session, user_id=user.id)

    first = await connections.revoke_connection(
        db_session, user_id=user.id, client_id=client.client_id
    )
    assert first.revoked_access == 1
    second = await connections.revoke_connection(
        db_session, user_id=user.id, client_id=client.client_id
    )
    assert second.revoked_access == 0 and second.revoked_refresh == 0


async def test_revoke_unknown_client_is_not_found(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as excinfo:
        await connections.revoke_connection(db_session, user_id=user.id, client_id="nope")
    assert excinfo.value.kind.value == "not_found"


async def test_revoke_does_not_touch_other_users(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="owner@example.com")
    intruder = await make_user(db_session, email="intruder@example.com")
    client = await register_claude_client(db_session)
    owner_tokens = await oauth_service._issue_token_pair(
        db_session,
        user_id=owner.id,
        client_id=client.client_id,
        scope="workouts.read",
        resource=get_settings().mcp_resource,
    )

    # The intruder revoking the *shared client id* must not affect the owner's token.
    result = await connections.revoke_connection(
        db_session, user_id=intruder.id, client_id=client.client_id
    )
    assert result.revoked_access == 0
    assert (
        await oauth_service.resolve_access_token(
            db_session,
            token=owner_tokens.access_token,
            required_resource=get_settings().mcp_resource,
        )
        is not None
    )
