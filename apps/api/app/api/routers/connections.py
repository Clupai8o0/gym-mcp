"""Connected-apps endpoints (Settings → Connected apps, docs/07).

List the user's active OAuth grants and revoke one. Thin adapters over
``services/connections`` — the revoke is a cookie-authenticated mutation, so the CSRF
``X-Tempo-Client`` header is enforced by ``current_user`` (docs/05).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.connections import ConnectionListOut, ConnectionOut, RevokeConnectionOut
from app.services import connections

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("", response_model=ConnectionListOut)
async def list_connections(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConnectionListOut:
    items = await connections.list_connections(db, user_id=cu.user_id)
    return ConnectionListOut(items=[ConnectionOut.model_validate(c) for c in items])


@router.delete("/{client_id}", response_model=RevokeConnectionOut)
async def revoke_connection(
    client_id: str,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RevokeConnectionOut:
    result = await connections.revoke_connection(db, user_id=cu.user_id, client_id=client_id)
    return RevokeConnectionOut(
        client_id=client_id,
        revoked_access=result.revoked_access,
        revoked_refresh=result.revoked_refresh,
    )
