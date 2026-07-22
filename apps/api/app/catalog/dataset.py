"""free-exercise-db dataset adapter (docs/06): pinned fetch + validation + field mapping.

Pure/framework-free (no DB, no web framework). The source is a JSON **array** of ~800
exercise records under the Unlicense (public domain — Decision D9), so it is safe to use with
no attribution. We consume the **metadata only**: the dataset's photos are ignored (Tempo
generates its own consistent line-art). This module validates each record against the
published shape and normalizes it into a :class:`CatalogRecord` — the DTO that
``services/catalog.upsert_exercises`` upserts.

Reproducibility: the dataset commit is **pinned** (:data:`PINNED_SHA`) so a fetch resolves to
the exact same bytes on every run. ``seed_catalog.py`` may override the ref, but the default is
the pin.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.slugs import slugify

# Pinned free-exercise-db commit (docs/06). yuhonas/free-exercise-db @ 2026-05-24 — 873
# exercises. Bump deliberately (and re-run the seed) to adopt catalog changes.
PINNED_SHA = "b0eed061e1c832b3ed815fbaa4b45b3cdc14df49"
SOURCE = "free-exercise-db"
_RAW_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/{ref}/dist/exercises.json"
_HTTP_TIMEOUT_SECONDS = 30.0

# Allowed enum values, mirroring the ``exercises`` CHECK constraints (docs/02). A dataset
# value outside these would violate a CHECK on insert; we surface it as drift rather than
# letting the seed fail mid-transaction on an opaque IntegrityError.
_ENUMS: dict[str, frozenset[str]] = {
    "force": frozenset({"push", "pull", "static"}),
    "level": frozenset({"beginner", "intermediate", "expert"}),
    "mechanic": frozenset({"compound", "isolation"}),
}


class DatasetError(Exception):
    """The dataset could not be fetched or failed schema/drift validation."""


class FreeExerciseRecord(BaseModel):
    """One record from ``dist/exercises.json`` (only the fields we map; ``images`` ignored)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    category: str | None = None
    force: str | None = None
    level: str | None = None
    mechanic: str | None = None
    equipment: str | None = None
    primaryMuscles: list[str] = Field(default_factory=list)  # noqa: N815 (dataset field name)
    secondaryMuscles: list[str] = Field(default_factory=list)  # noqa: N815 (dataset field name)
    instructions: list[str] = Field(default_factory=list)


class CatalogRecord(BaseModel):
    """A normalized catalog row ready for upsert (docs/06 field mapping)."""

    source: str
    source_id: str
    slug: str
    name: str
    category: str | None
    force: str | None
    level: str | None
    mechanic: str | None
    equipment: str | None
    primary_muscles: list[str]
    secondary_muscles: list[str]
    instructions: list[str]


def _dedupe_slug(base: str, taken: set[str]) -> str:
    """Return ``base`` (or ``base-2``/``base-3``/…) not already in ``taken``; register it.

    Deterministic in dataset order, so a re-run produces identical slugs. In practice the
    free-exercise-db names are collision-free; this is a defensive guarantee for the global
    unique-slug index (docs/02).
    """
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    taken |= {candidate}
    return candidate


def parse_dataset(raw: object) -> list[CatalogRecord]:
    """Validate + normalize the raw dataset (a list of dicts) into ``CatalogRecord``s.

    Raises :class:`DatasetError` on the wrong top-level shape, a record that fails validation,
    duplicate ``source_id``s, or any enum value that would violate a CHECK constraint (drift).
    """
    if not isinstance(raw, list):
        raise DatasetError(f"expected a JSON array of exercises, got {type(raw).__name__}")

    records: list[CatalogRecord] = []
    drift: list[str] = []
    seen_source_ids: set[str] = set()
    taken_slugs: set[str] = set()

    for index, item in enumerate(raw):
        try:
            rec = FreeExerciseRecord.model_validate(item)
        except ValidationError as exc:
            raise DatasetError(f"dataset record {index} failed validation: {exc}") from exc

        for field, allowed in _ENUMS.items():
            value = getattr(rec, field)
            if value is not None and value not in allowed:
                drift.append(f"{rec.id}.{field}={value!r}")

        source_id = rec.id or rec.name
        if source_id in seen_source_ids:
            raise DatasetError(f"duplicate source_id {source_id!r} in dataset")
        seen_source_ids |= {source_id}

        slug = _dedupe_slug(slugify(rec.name) or slugify(source_id), taken_slugs)
        records.append(
            CatalogRecord(
                source=SOURCE,
                source_id=source_id,
                slug=slug,
                name=rec.name,
                category=rec.category,
                force=rec.force,
                level=rec.level,
                mechanic=rec.mechanic,
                equipment=rec.equipment,
                primary_muscles=rec.primaryMuscles,
                secondary_muscles=rec.secondaryMuscles,
                instructions=rec.instructions,
            )
        )

    if drift:
        raise DatasetError(
            "dataset enum drift (would violate exercises CHECK constraints): " + ", ".join(drift)
        )
    return records


async def fetch_dataset(*, ref: str = PINNED_SHA) -> list[dict[str, object]]:
    """Fetch ``dist/exercises.json`` at ``ref`` (default the pin). Returns the raw list.

    Network I/O lives here (isolated from :func:`parse_dataset`, which stays pure and unit-
    testable). Imported lazily so the pure path never requires ``httpx``.
    """
    import httpx

    url = _RAW_URL.format(ref=ref)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise DatasetError(f"could not fetch dataset from {url} ({response.status_code})")
    data = response.json()
    if not isinstance(data, list):
        raise DatasetError("dataset endpoint did not return a JSON array")
    return data
