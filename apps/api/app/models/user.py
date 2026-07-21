"""``users`` — real accounts. Identity comes from Google OIDC; no passwords stored."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("unit_pref in ('kg','lb')", name="unit_pref"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    google_sub: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    unit_pref: Mapped[str] = mapped_column(Text, nullable=False, server_default="kg")
    created_at: Mapped[datetime] = created_at_col()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
