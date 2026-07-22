"""User-facing profile schema (`GET /api/me`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class MeOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str | None
    avatar_url: str | None
    unit_pref: str
    created_at: datetime
    last_login_at: datetime | None
