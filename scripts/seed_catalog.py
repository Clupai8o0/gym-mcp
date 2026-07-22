#!/usr/bin/env python
"""Seed the exercise catalog from the pinned free-exercise-db (docs/06). **Offline only.**

Idempotent: upserts by ``(source, source_id)`` — re-running an unchanged dataset changes
nothing (and preserves any generated art). Uses the **unpooled** Neon URL (bulk writes must
not go through PgBouncer). Never run on Vercel (300s function limit).

All logic lives in the shared app layer (``app.catalog.dataset`` validates/maps;
``app.services.catalog`` upserts); this file is a thin CLI over them.

Usage (from the repo root, with DATABASE_URL_UNPOOLED in the environment or ./.env):
    uv run --project scripts python scripts/seed_catalog.py                  # fetch the pin
    uv run --project scripts python scripts/seed_catalog.py --source f.json  # a local file
    uv run --project scripts python scripts/seed_catalog.py --ref <sha>      # a different ref
    uv run --project scripts python scripts/seed_catalog.py --dry-run        # parse only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Import the api's shared code (see scripts/pyproject.toml).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.catalog import dataset  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import make_asyncpg_url  # noqa: E402
from app.services import catalog  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


async def _load(args: argparse.Namespace) -> list[dict[str, object]]:
    if args.source:
        return list(json.loads(Path(args.source).read_text()))
    return await dataset.fetch_dataset(ref=args.ref)


async def run(args: argparse.Namespace) -> int:
    raw = await _load(args)
    records = dataset.parse_dataset(raw)
    origin = args.source if args.source else f"{dataset.SOURCE}@{args.ref[:10]}"
    print(f"parsed {len(records)} records from {origin}")
    if args.dry_run:
        print("dry-run: no database writes")
        return 0

    url, connect_args = make_asyncpg_url(get_settings().database_url_unpooled)
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            summary = await catalog.upsert_exercises(db, records)
            await db.commit()
    finally:
        await engine.dispose()

    print(
        f"catalog import: inserted={summary.inserted} updated={summary.updated} "
        f"skipped={summary.skipped} total={summary.total}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the exercise catalog (free-exercise-db).")
    parser.add_argument("--source", help="path to a local exercises.json (skips the network fetch)")
    parser.add_argument(
        "--ref",
        default=dataset.PINNED_SHA,
        help=f"git ref/SHA to fetch (default: the pin {dataset.PINNED_SHA[:10]})",
    )
    parser.add_argument("--dry-run", action="store_true", help="parse + validate only, no writes")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
