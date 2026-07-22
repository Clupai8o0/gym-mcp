"""Connected-apps (OAuth grant) schemas for Settings (docs/07 §Connected apps)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ConnectionOut(ORMModel):
    """A connected chat client + the state of the user's grant to it."""

    client_id: str
    client_name: str | None
    scope: str | None
    connected_at: datetime
    last_active_at: datetime | None
    active_token_count: int


class ConnectionListOut(BaseModel):
    items: list[ConnectionOut]


class RevokeConnectionOut(BaseModel):
    """How many of the user's tokens were revoked for the client."""

    client_id: str
    revoked_access: int
    revoked_refresh: int
