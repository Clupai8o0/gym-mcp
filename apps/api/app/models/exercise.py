"""``exercises`` — the catalog (global seed rows + user-created custom rows).

Global rows have ``created_by_user_id IS NULL``; custom rows are scoped to a user.
The partial unique indexes enforce "unique slug among global rows" and "unique slug
per owner among custom rows" independently.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint("force in ('push','pull','static') or force is null", name="force"),
        CheckConstraint(
            "level in ('beginner','intermediate','expert') or level is null", name="level"
        ),
        CheckConstraint(
            "mechanic in ('compound','isolation') or mechanic is null", name="mechanic"
        ),
        CheckConstraint(
            "illustration_status in ('pending','generating','ready','failed')",
            name="illustration_status",
        ),
        # Global catalog slugs are unique; custom slugs are unique per owner.
        Index(
            "exercises_global_slug_uidx",
            "slug",
            unique=True,
            postgresql_where=text("created_by_user_id IS NULL"),
        ),
        Index(
            "exercises_custom_slug_uidx",
            "created_by_user_id",
            "slug",
            unique=True,
            postgresql_where=text("created_by_user_id IS NOT NULL"),
        ),
        Index(
            "exercises_source_uidx",
            "source",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
        Index("exercises_category_idx", "category"),
        Index("exercises_primary_muscles_gin", "primary_muscles", postgresql_using="gin"),
        Index("exercises_illustration_status_idx", "illustration_status"),
        # Trigram search on name (requires the pg_trgm extension).
        Index(
            "exercises_name_trgm",
            text("name gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    force: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)
    mechanic: Mapped[str | None] = mapped_column(Text)
    equipment: Mapped[str | None] = mapped_column(Text)
    primary_muscles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    secondary_muscles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    instructions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    # provenance & art
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="free-exercise-db")
    source_id: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    illustration_url: Mapped[str | None] = mapped_column(Text)
    illustration_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    illustration_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
