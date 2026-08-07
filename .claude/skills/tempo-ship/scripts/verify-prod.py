"""Read-only verification of production after migration 0008.

Runs only SELECTs. Proves the query that was 500ing now executes, and asserts the two
things `alembic check` does not compare: CHECK-constraint names and the partial-index
predicate. Prints no credential.
"""

import asyncio
import os
import pathlib
import re
import subprocess
import sys

# Resolve the repo from this file's own location: .claude/skills/tempo-ship/scripts/
REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "apps" / "api"))

url = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()
if not url.startswith(("postgres://", "postgresql://")):
    print("FAIL: clipboard no longer holds the connection string.")
    raise SystemExit(1)
os.environ["DATABASE_URL"] = url
os.environ["DATABASE_URL_UNPOOLED"] = url

from sqlalchemy import text  # noqa: E402

from app.core.db import make_asyncpg_url  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


def redact(s: str) -> str:
    return re.sub(r"postgres(ql)?(\+\w+)?://[^\s\"]*", "postgresql://<redacted>", s)


async def main() -> None:
    async_url, connect_args = make_asyncpg_url(url)
    engine = create_async_engine(async_url, connect_args=connect_args)
    async with engine.connect() as conn:
        print("=== planned_sets exists ===")
        r = await conn.execute(text("select to_regclass('public.planned_sets') is not null"))
        print(f"  {r.scalar()}")

        print("=== CHECK constraint names (alembic check does NOT compare these) ===")
        r = await conn.execute(
            text(
                "select conname from pg_constraint "
                "where conrelid = 'public.planned_sets'::regclass and contype = 'c' "
                "order by conname"
            )
        )
        for (name,) in r:
            doubled = "_check_check" in name
            print(f"  {name}{'   <-- DOUBLED PREFIX/SUFFIX BUG' if doubled else ''}")

        print("=== partial-index predicate (must match plans._claimant) ===")
        r = await conn.execute(
            text(
                "select indexdef from pg_indexes "
                "where tablename = 'planned_sets' and indexname = "
                "'planned_sets_completed_set_uidx'"
            )
        )
        row = r.scalar()
        print(f"  {row}")

        print("=== the query that was 500ing: analytics.frequency EXISTS clause ===")
        r = await conn.execute(
            text(
                "select count(*) from workout_sessions ws "
                "where ws.deleted_at is null "
                "and not (exists (select 1 from planned_sets ps where ps.session_id = ws.id) "
                "and not exists (select 1 from exercise_sets es "
                "where es.session_id = ws.id and es.deleted_at is null))"
            )
        )
        print(f"  executed OK, sessions counted as trained: {r.scalar()}")

        print("=== row counts ===")
        r = await conn.execute(
            text(
                "select (select count(*) from users), (select count(*) from exercises), "
                "(select count(*) from workout_sessions), (select count(*) from exercise_sets), "
                "(select count(*) from planned_sets)"
            )
        )
        u, e, s, st, p = r.one()
        print(f"  users={u} exercises={e} sessions={s} sets={st} planned_sets={p}")
    await engine.dispose()


try:
    asyncio.run(main())
except Exception as exc:
    print(redact(f"FAILED: {type(exc).__name__}: {exc}"))
    raise SystemExit(1)
