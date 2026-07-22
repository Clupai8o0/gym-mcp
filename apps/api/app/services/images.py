"""Illustration service (docs/06): on-demand generation + the shared single-image routine.

The batch job (``scripts/generate_illustrations.py``) and the on-demand endpoint both funnel
through :func:`generate_and_store`, so a row's art + provenance are produced identically no
matter what triggered it (the "keep it in lockstep" guardrail, applied to the image pipeline).

Business logic + DB writes live here; the OpenAI + Blob network calls are isolated in
``app/images/`` adapters (stubbed in tests). Per the codebase rule, services only ``flush`` —
the request's ``get_db`` (on-demand) or the script (batch) owns commit/rollback.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import get_settings
from app.images import blob, openai_images
from app.images import prompt as prompt_builder
from app.images.blob import BlobUploadError
from app.images.openai_images import ImageGenerationError
from app.models import Exercise
from app.services import exercises as exercises_service

# ``exercises.illustration_status`` values (docs/02 CHECK).
STATUS_PENDING = "pending"
STATUS_GENERATING = "generating"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
# Statuses the on-demand path will (re)generate for. ``generating`` is intentionally excluded
# so a concurrent/in-flight generation is reported as in-progress, not duplicated.
_REGENERABLE = frozenset({STATUS_PENDING, STATUS_FAILED})


class _Generator(Protocol):
    async def __call__(
        self,
        *,
        prompt: str,
        size: str | None,
        quality: str | None,
        model: str | None,
        background: str | None,
    ) -> bytes: ...


class _Uploader(Protocol):
    async def __call__(self, *, key: str, data: bytes) -> str: ...


def _lock_key(exercise_id: uuid.UUID) -> int:
    """A stable signed 64-bit key from the UUID for ``pg_advisory_xact_lock(bigint)``."""
    return int.from_bytes(exercise_id.bytes[:8], byteorder="big", signed=True)


async def generate_and_store(
    db: AsyncSession,
    exercise: Exercise,
    *,
    trigger: str = "on_demand",
    generate: _Generator | None = None,
    upload: _Uploader | None = None,
) -> Exercise:
    """Generate one illustration for ``exercise``, upload it, and persist url + status + meta.

    Always flushes a **terminal** status before returning or raising: ``ready`` on success, or
    ``failed`` (with an error note in ``illustration_meta``) before re-raising
    :class:`ImageGenerationError` / :class:`BlobUploadError`. The caller decides whether to
    commit that terminal state (batch) or let it roll back (on-demand request).
    """
    settings = get_settings()
    _generate = generate if generate is not None else openai_images.generate_png
    _upload = upload if upload is not None else blob.upload_png

    prompt = prompt_builder.build_prompt(
        name=exercise.name,
        equipment=exercise.equipment,
        primary_muscles=list(exercise.primary_muscles),
    )
    exercise.illustration_status = STATUS_GENERATING
    await db.flush()

    try:
        png = await _generate(
            prompt=prompt,
            size=settings.openai_image_size,
            quality=settings.openai_image_quality,
            model=settings.openai_image_model,
            background=settings.openai_image_background,
        )
        url = await _upload(key=blob.blob_key(exercise.slug), data=png)
    except (ImageGenerationError, BlobUploadError) as exc:
        exercise.illustration_status = STATUS_FAILED
        exercise.illustration_meta = {
            **(exercise.illustration_meta or {}),
            "error": str(exc)[:300],
            "failed_at": datetime.now(UTC).isoformat(),
            "style_version": prompt_builder.STYLE_VERSION,
        }
        await db.flush()
        raise

    exercise.illustration_url = url
    exercise.illustration_status = STATUS_READY
    exercise.illustration_meta = {
        "model": settings.openai_image_model,
        "prompt": prompt,
        "prompt_hash": prompt_builder.prompt_hash(prompt),
        "size": settings.openai_image_size,
        "quality": settings.openai_image_quality,
        "background": settings.openai_image_background,
        "style_version": prompt_builder.STYLE_VERSION,
        "trigger": trigger,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    await db.flush()
    # Reload the row so ``updated_at`` (server ``onupdate``) and all columns are populated
    # before the caller serializes it — avoids a lazy load in a sync (Pydantic) context.
    await db.refresh(exercise)
    return exercise


async def ensure(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    generate: _Generator | None = None,
    upload: _Uploader | None = None,
) -> Exercise:
    """Ensure a **visible** exercise has an illustration; generate one on demand if missing.

    Resolves the exercise through the catalog service (so global + own-custom visibility and the
    404 are shared, not re-implemented). Concurrency-safe: a transaction-scoped Postgres advisory
    lock serializes generations for the same exercise across requests, so two concurrent callers
    can't double-generate (and double-bill). Already-``ready`` rows return immediately (no cost);
    a row a batch left ``generating`` is returned as-is (in progress). A provider/Blob failure
    surfaces as a 503 (:func:`errors.unavailable`) and the transaction rolls back cleanly.
    """
    exercise = await exercises_service.get(db, user_id=user_id, exercise_id=exercise_id)
    if exercise.illustration_status == STATUS_READY and exercise.illustration_url:
        return exercise

    # Serialize concurrent generation for this exercise; released at transaction end.
    await db.execute(select(func.pg_advisory_xact_lock(_lock_key(exercise.id))))
    await db.refresh(exercise)  # re-read under the lock — another request may have finished
    if exercise.illustration_status == STATUS_READY and exercise.illustration_url:
        return exercise
    if exercise.illustration_status not in _REGENERABLE:
        # A batch run committed ``generating``; report in-progress rather than regenerating.
        return exercise

    try:
        return await generate_and_store(
            db, exercise, trigger="on_demand", generate=generate, upload=upload
        )
    except (ImageGenerationError, BlobUploadError) as exc:
        raise errors.unavailable("Illustration generation is temporarily unavailable") from exc
