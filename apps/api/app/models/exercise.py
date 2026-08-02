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
from app.models.soft_delete import deleted_at_col, deleted_at_index


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
        deleted_at_index("exercises"),
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
    # The light-mode twin: the same art with its achromatic linework inverted so it reads on a
    # light surface, amber accent untouched (app/images/chroma.invert_neutral). Derived locally
    # from the same generation — no second model call — and written in the same upload step, so
    # it is non-NULL exactly when illustration_url is.
    illustration_url_light: Mapped[str | None] = mapped_column(Text)
    illustration_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    illustration_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    #: Soft delete — only ever set on a **custom** row. A catalog row is shared reference data;
    #: deleting one is not a correction, it is a schema change, and the service refuses.
    deleted_at: Mapped[datetime | None] = deleted_at_col()

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ExerciseSlugAlias(Base):
    """A slug an exercise used to have, still resolvable.

    Renaming a custom exercise regenerates its slug, and a slug is a public identifier: an MCP
    client that stored ``rings-dip`` should not get a 404 because the name was corrected to
    "Ring Dips". The alias keeps the old reference working; the exercise's own ``slug`` column is
    always the current one, so nothing about display or new links changes.

    Aliases lose to live slugs on lookup (``services/exercises.resolve_ref``) — a name that is
    somebody's current slug can never be shadowed by somebody else's history.
    """

    __tablename__ = "exercise_slug_aliases"
    __table_args__ = (
        # Same shape as the live-slug indexes: unique among global rows, unique per owner among
        # custom ones, so an alias can never introduce an ambiguity a live slug could not.
        Index(
            "exercise_slug_aliases_global_uidx",
            "slug",
            unique=True,
            postgresql_where=text("created_by_user_id IS NULL"),
        ),
        Index(
            "exercise_slug_aliases_custom_uidx",
            "created_by_user_id",
            "slug",
            unique=True,
            postgresql_where=text("created_by_user_id IS NOT NULL"),
        ),
        Index("exercise_slug_aliases_exercise_idx", "exercise_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )
    #: Denormalized from the exercise so the partial unique indexes above can be expressed here.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
