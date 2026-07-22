"""User-facing profile schema (`GET /api/me`)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import ORMModel


class MeOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str | None
    avatar_url: str | None
    unit_pref: str
    created_at: datetime
    last_login_at: datetime | None


class MeUpdate(BaseModel):
    """Patch the current user's display preferences (Settings → units, docs/07)."""

    unit_pref: Literal["kg", "lb"]
