"""Catalog import service (docs/06): idempotent upsert of dataset records → ``exercises``.

Keyed on ``(source, source_id)``. Touches **global catalog rows only**; user ``custom`` rows
are never seen (they carry ``source='custom'``, not the dataset source). Generated art
(``illustration_*``) is **preserved** across re-imports — only descriptive metadata is
refreshed — so re-seeding never throws away images. Idempotent: re-running an unchanged
dataset reports every row ``skipped``.

Business logic + DB writes live here (framework-free). The offline ``seed_catalog.py`` script
is a thin wrapper that fetches/parses the dataset, calls :func:`upsert_exercises`, and commits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.dataset import CatalogRecord
from app.models import Exercise

# Descriptive columns refreshed on re-import. Deliberately excludes ``source``/``source_id``
# (the identity), ``created_by_user_id`` (ownership), and every ``illustration_*`` column
# (generated art must survive a re-seed).
_SYNCED_FIELDS = (
    "name",
    "slug",
    "category",
    "force",
    "level",
    "mechanic",
    "equipment",
    "primary_muscles",
    "secondary_muscles",
    "instructions",
)


@dataclass(frozen=True)
class ImportSummary:
    """Counts from one import run."""

    inserted: int
    updated: int
    skipped: int

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.skipped


async def upsert_exercises(db: AsyncSession, records: Sequence[CatalogRecord]) -> ImportSummary:
    """Insert new / update changed / skip unchanged catalog rows; return the counts.

    One bulk read of the existing rows for the record sources, then an in-memory diff — so a
    full ~800-row seed is a couple of queries plus one flush, not a query per row. The caller
    owns the transaction (commit).
    """
    if not records:
        return ImportSummary(inserted=0, updated=0, skipped=0)

    sources = {record.source for record in records}
    existing_rows = (
        (await db.execute(select(Exercise).where(Exercise.source.in_(sources)))).scalars().all()
    )
    existing: dict[tuple[str, str], Exercise] = {
        (row.source, row.source_id): row for row in existing_rows if row.source_id is not None
    }

    inserted = updated = skipped = 0
    for record in records:
        current = existing.get((record.source, record.source_id))
        if current is None:
            db.add(
                Exercise(
                    source=record.source,
                    source_id=record.source_id,
                    slug=record.slug,
                    name=record.name,
                    category=record.category,
                    force=record.force,
                    level=record.level,
                    mechanic=record.mechanic,
                    equipment=record.equipment,
                    primary_muscles=record.primary_muscles,
                    secondary_muscles=record.secondary_muscles,
                    instructions=record.instructions,
                )
            )
            inserted += 1
            continue

        changed = [
            field for field in _SYNCED_FIELDS if getattr(current, field) != getattr(record, field)
        ]
        if not changed:
            skipped += 1
            continue
        for field in changed:
            setattr(current, field, getattr(record, field))
        updated += 1  # ``updated_at`` auto-bumps via the model's onupdate

    await db.flush()
    return ImportSummary(inserted=inserted, updated=updated, skipped=skipped)
