"""Declarative base + shared column helpers for all SQLAlchemy models.

The models are the source of truth for the schema (docs/02-data-model.md); Alembic
migrations are derived from them. A deterministic naming convention keeps constraint
and index names stable across autogenerate runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable auto-naming for constraints/indexes (Alembic-friendly).
NAMING_CONVENTION = {
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Base class carrying the shared metadata (naming convention)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """UUID primary key defaulted server-side via ``gen_random_uuid()`` (pgcrypto)."""
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


def created_at_col() -> Mapped[datetime]:
    """``timestamptz`` set to ``now()`` on insert."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_col() -> Mapped[datetime]:
    """``timestamptz`` maintained by the app: ``now()`` on insert and on update."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
