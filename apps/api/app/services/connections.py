"""Connected-apps management — the user-facing view over their OAuth grants (docs/07).

Settings → *Connected apps* lets the account owner see which chat clients (claude.ai, …) are
connected via OAuth and **revoke** them. Everything here is strictly scoped to the acting
``user_id``: a user can only ever list or revoke their **own** tokens.

This does **not** touch the Authorization-Server's issuance/PKCE/rotation semantics (docs/05):
revoking just sets ``revoked_at`` on the caller's own access + refresh tokens — the same
column the reuse-detection path in :mod:`app.services.oauth` writes. A revoked token then fails
``resolve_access_token`` on its next use, forcing the client to re-authorize.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import OAuthAccessToken, OAuthClient, OAuthRefreshToken


@dataclass(frozen=True)
class Connection:
    """One connected client and the state of this user's grant to it."""

    client_id: str
    client_name: str | None
    scope: str | None
    connected_at: datetime
    last_active_at: datetime | None
    active_token_count: int


async def list_connections(db: AsyncSession, *, user_id: uuid.UUID) -> Sequence[Connection]:
    """Active OAuth grants for ``user_id`` — one row per client with a live refresh token.

    A refresh token is the durable grant (access tokens are ~1h), so a client appears while it
    holds an unrevoked, unexpired refresh token. ``connected_at`` is the earliest such grant;
    ``last_active_at`` is the newest access token minted (each authorize/refresh mints one).
    """
    now = datetime.now(UTC)

    # Clients with a live refresh grant → these are the "connected" apps, plus first-seen time.
    grants = (
        await db.execute(
            select(
                OAuthRefreshToken.client_id,
                func.min(OAuthRefreshToken.created_at),
            )
            .where(
                OAuthRefreshToken.user_id == user_id,
                OAuthRefreshToken.revoked_at.is_(None),
                OAuthRefreshToken.expires_at > now,
            )
            .group_by(OAuthRefreshToken.client_id)
        )
    ).all()
    if not grants:
        return []
    connected_at: dict[str, datetime] = {cid: first for cid, first in grants}
    client_ids = list(connected_at)

    # Last activity = most recent access token (live or not) issued for the client.
    last_active: dict[str, datetime] = {
        cid: latest
        for cid, latest in (
            await db.execute(
                select(OAuthAccessToken.client_id, func.max(OAuthAccessToken.created_at))
                .where(
                    OAuthAccessToken.user_id == user_id,
                    OAuthAccessToken.client_id.in_(client_ids),
                )
                .group_by(OAuthAccessToken.client_id)
            )
        ).all()
    }

    # Count of currently-valid access tokens (live sessions), for display.
    active_counts: dict[str, int] = {
        cid: count
        for cid, count in (
            await db.execute(
                select(OAuthAccessToken.client_id, func.count())
                .where(
                    OAuthAccessToken.user_id == user_id,
                    OAuthAccessToken.client_id.in_(client_ids),
                    OAuthAccessToken.revoked_at.is_(None),
                    OAuthAccessToken.expires_at > now,
                )
                .group_by(OAuthAccessToken.client_id)
            )
        ).all()
    }

    clients: dict[str, tuple[str | None, str | None]] = {
        cid: (name, scope)
        for cid, name, scope in (
            await db.execute(
                select(OAuthClient.client_id, OAuthClient.client_name, OAuthClient.scope).where(
                    OAuthClient.client_id.in_(client_ids)
                )
            )
        ).all()
    }

    connections = [
        Connection(
            client_id=cid,
            client_name=clients.get(cid, (None, None))[0],
            scope=clients.get(cid, (None, None))[1],
            connected_at=connected_at[cid],
            last_active_at=last_active.get(cid),
            active_token_count=active_counts.get(cid, 0),
        )
        for cid in client_ids
    ]
    # Most recently active first (fall back to first-connected for never-used grants).
    connections.sort(key=lambda c: c.last_active_at or c.connected_at, reverse=True)
    return connections


@dataclass(frozen=True)
class RevokeResult:
    revoked_access: int
    revoked_refresh: int


async def revoke_connection(
    db: AsyncSession, *, user_id: uuid.UUID, client_id: str
) -> RevokeResult:
    """Revoke every one of the user's live tokens for ``client_id`` (idempotent).

    Raises ``not_found`` only when the client itself is unknown. Revoking a client the user has
    no live tokens for is a no-op that returns zero counts.
    """
    client = (
        await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
    ).scalar_one_or_none()
    if client is None:
        raise errors.not_found("Connection not found", client_id=client_id)

    now = datetime.now(UTC)
    access = await db.execute(
        update(OAuthAccessToken)
        .where(
            OAuthAccessToken.user_id == user_id,
            OAuthAccessToken.client_id == client_id,
            OAuthAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    refresh = await db.execute(
        update(OAuthRefreshToken)
        .where(
            OAuthRefreshToken.user_id == user_id,
            OAuthRefreshToken.client_id == client_id,
            OAuthRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()
    return RevokeResult(
        revoked_access=cast("CursorResult[Any]", access).rowcount,
        revoked_refresh=cast("CursorResult[Any]", refresh).rowcount,
    )
