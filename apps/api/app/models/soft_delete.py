"""Shared column helpers for correction tooling: soft delete and client-supplied idempotency.

**Why soft delete.** Tempo was append-only in practice — every write was permanent, so a bug that
wrote ``duration_minutes = 136070`` or a stray 60 kg history row could never be taken back. A hard
``DELETE`` swaps one irreversible state for another. ``deleted_at`` makes removal a correction:
the row leaves every read immediately, and :func:`app.services.corrections.restore` puts it back.
``purge_deleted`` is the only path that actually frees the storage, and it has to be asked for.

**Why the client key.** An MCP client that retries a call it never saw the answer to creates a
duplicate — this already happened once, leaving two identical `upper_hypertrophy` sessions dated
1 May. A ``client_key`` the caller chooses makes the write idempotent: the second call with the
same key returns the first call's row instead of creating another. Scoped per user, so two people
can pick the same key.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column


def deleted_at_col() -> Mapped[datetime | None]:
    """``NULL`` = live. Any timestamp = removed, and excluded from reads by default."""
    return mapped_column(DateTime(timezone=True), nullable=True)


def deleted_at_index(table: str) -> Index:
    """Partial index over the deleted rows only.

    Every read filters ``deleted_at IS NULL``, which is nearly the whole table and is served by
    the existing indexes. The rows worth indexing are the deleted minority — that is what
    ``purge_deleted`` and the include-deleted paths actually scan.
    """
    return Index(
        f"{table}_deleted_at_idx",
        "deleted_at",
        postgresql_where=text("deleted_at IS NOT NULL"),
    )


def client_key_col() -> Mapped[str | None]:
    """A caller-chosen idempotency key, unique per user (see :func:`client_key_index`)."""
    return mapped_column(Text, nullable=True)


def client_key_index(table: str) -> Index:
    """Partial unique index on ``(user_id, client_key)`` — ``NULL`` keys don't collide.

    Partial rather than a plain ``UniqueConstraint`` because Postgres treats every ``NULL`` as
    distinct anyway; being explicit keeps the index to the rows that actually use the feature.
    """
    return Index(
        f"{table}_client_key_uidx",
        "user_id",
        "client_key",
        unique=True,
        postgresql_where=text("client_key IS NOT NULL"),
    )
