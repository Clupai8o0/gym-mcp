#!/usr/bin/env python
"""Batch-generate exercise illustrations: GPT Image 2 → Vercel Blob (docs/06). **Offline only.**

Idempotent + resumable: only ``pending``/``failed`` rows are processed (add ``--retry-stale`` to
also reclaim ``generating`` rows left by a crashed run); ``ready`` rows are skipped. Bounded
concurrency; each row commits on its own, so Ctrl-C is safe and the next run continues. Uses the
**unpooled** Neon URL. Never run on Vercel (300s function limit).

The per-image work (prompt → generate → upload → persist + provenance) is the shared
``app.services.images.generate_and_store`` — identical to the on-demand endpoint. This file only
selects rows, bounds concurrency, and reports.

Usage (from the repo root, with DATABASE_URL_UNPOOLED, OPENAI_API_KEY, BLOB_READ_WRITE_TOKEN set):
    uv run --project scripts python scripts/generate_illustrations.py                 # full batch
    uv run --project scripts python scripts/generate_illustrations.py --limit 20      # cap count
    uv run --project scripts python scripts/generate_illustrations.py --concurrency 8
    uv run --project scripts python scripts/generate_illustrations.py --retry-stale    # + generating
    uv run --project scripts python scripts/generate_illustrations.py --exemplars ./out
        # generate the 5–8 style exemplars to ./out for the docs/06 design sign-off (no DB/Blob)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Import the api's shared code (see scripts/pyproject.toml).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_asyncpg_url  # noqa: E402
from app.core.slugs import slugify  # noqa: E402
from app.images import cost, openai_images  # noqa: E402
from app.images import prompt as prompt_builder  # noqa: E402
from app.images.blob import BlobUploadError  # noqa: E402
from app.images.openai_images import ImageGenerationError  # noqa: E402
from app.models import Exercise  # noqa: E402
from app.services import images  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)  # noqa: E402

# The reference-locking set (docs/06): a spread of categories to iterate the style on before
# spending on the full catalog. Each is (name, equipment, primary_muscles).
_EXEMPLARS: tuple[tuple[str, str | None, list[str]], ...] = (
    ("Barbell Back Squat", "barbell", ["quadriceps", "glutes"]),
    ("Barbell Bench Press", "barbell", ["chest"]),
    ("Pull-up", "body only", ["lats"]),
    ("Plank", "body only", ["abdominals"]),
    ("Cable Triceps Pushdown", "cable", ["triceps"]),
    ("Dumbbell Shoulder Press", "dumbbell", ["shoulders"]),
    ("Conventional Deadlift", "barbell", ["hamstrings", "glutes"]),
    ("Push-up", "body only", ["chest"]),
)


async def _pending_ids(
    maker: async_sessionmaker, *, limit: int | None, retry_stale: bool
) -> list[uuid.UUID]:
    statuses = [images.STATUS_PENDING, images.STATUS_FAILED]
    if retry_stale:
        statuses.append(images.STATUS_GENERATING)
    async with maker() as db:
        stmt = (
            select(Exercise.id)
            .where(Exercise.illustration_status.in_(statuses))
            .order_by(Exercise.name)
        )
        if limit:
            stmt = stmt.limit(limit)
        return list((await db.execute(stmt)).scalars().all())


async def _one(maker: async_sessionmaker, exercise_id: uuid.UUID, sem: asyncio.Semaphore) -> str:
    """Generate one row in its own transaction; returns the terminal status."""
    async with sem, maker() as db:
        exercise = await db.get(Exercise, exercise_id)
        if exercise is None:
            return "missing"
        try:
            await images.generate_and_store(db, exercise, trigger="batch")
        except (ImageGenerationError, BlobUploadError):
            # generate_and_store already flushed 'failed'; commit it so the run is resumable.
            await db.commit()
            return images.STATUS_FAILED
        await db.commit()
        return images.STATUS_READY


async def _run_batch(engine: AsyncEngine, args: argparse.Namespace) -> int:
    settings = get_settings()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _pending_ids(maker, limit=args.limit, retry_stale=args.retry_stale)
    if not ids:
        print("nothing to do: no pending/failed illustrations")
        return 0

    print(f"generating {len(ids)} illustrations (concurrency={args.concurrency})…")
    sem = asyncio.Semaphore(args.concurrency)
    outcomes = await asyncio.gather(*(_one(maker, i, sem) for i in ids))

    ready = sum(1 for status in outcomes if status == images.STATUS_READY)
    failures = [i for i, status in zip(ids, outcomes, strict=True) if status != images.STATUS_READY]
    estimate = cost.estimate_cost_usd(
        ready, quality=settings.openai_image_quality, size=settings.openai_image_size
    )
    print(f"\nreport: ready={ready} failed={len(failures)} of {len(ids)}")
    print(
        f"estimated cost: ~${estimate} "
        f"({settings.openai_image_quality} {settings.openai_image_size}, {ready} images)"
    )
    if failures:
        print("failures (retried on the next run):")
        for exercise_id in failures:
            print(f"  {exercise_id}")
    return 0 if not failures else 1


async def _run_exemplars(args: argparse.Namespace) -> int:
    settings = get_settings()
    out = Path(args.exemplars)
    out.mkdir(parents=True, exist_ok=True)
    for name, equipment, muscles in _EXEMPLARS:
        prompt = prompt_builder.build_prompt(
            name=name, equipment=equipment, primary_muscles=muscles
        )
        png = await openai_images.generate_png(
            prompt=prompt,
            size=settings.openai_image_size,
            quality=settings.openai_image_quality,
            model=settings.openai_image_model,
            background=settings.openai_image_background,
        )
        (out / f"{slugify(name)}.png").write_bytes(png)
        print(f"wrote {name}")
    print(
        f"\n{len(_EXEMPLARS)} exemplars written to {out}/ — review for the docs/06 style "
        "sign-off before running the full batch."
    )
    return 0


async def run(args: argparse.Namespace) -> int:
    if args.exemplars:
        return await _run_exemplars(args)
    url, connect_args = make_asyncpg_url(get_settings().database_url_unpooled)
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        return await _run_batch(engine, args)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-generate exercise illustrations.")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of rows this run")
    parser.add_argument("--concurrency", type=int, default=6, help="max concurrent generations")
    parser.add_argument(
        "--retry-stale",
        action="store_true",
        help="also reclaim rows stuck in 'generating' (from a crashed run)",
    )
    parser.add_argument(
        "--exemplars",
        metavar="DIR",
        help="generate the style exemplars to DIR for design sign-off (no DB/Blob writes)",
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
