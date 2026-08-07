"""Test-database administration helpers (create/drop DBs, run Alembic, inspect).

Tests run against a real Postgres (a local server or a Neon **test** branch — never
prod), configured via ``TEST_DATABASE_URL`` (default: a local Docker/Homebrew server).
Each helper derives per-purpose databases from that base URL so suites stay isolated.

All Alembic/asyncpg work is funneled through :func:`_call_without_loop` so it is safe
to invoke from pytest-asyncio's synchronous session-scoped fixtures regardless of
whether an event loop happens to be running on the calling thread.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from alembic import command
from alembic.config import Config

DEFAULT_BASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"

_API_DIR = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _API_DIR / "alembic.ini"
_MIGRATIONS_DIR = _API_DIR / "migrations"


def base_url() -> str:
    """The base test-server URL (its database name is ignored; callers swap it)."""
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_BASE_URL)


def _with_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", "", ""))


def url_for(dbname: str) -> str:
    """A libpq URL for ``dbname`` on the configured test server."""
    return _with_db(base_url(), dbname)


def _admin_url() -> str:
    return _with_db(base_url(), "postgres")


def _call_without_loop[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call ``fn`` from a context with no running event loop (thread if needed)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn(*args, **kwargs)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(fn, *args, **kwargs).result()


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion, off any already-running loop (thread if needed)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


async def _exec_admin(sql: str) -> None:
    conn = await asyncpg.connect(_admin_url())
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def create_database(dbname: str) -> None:
    """Drop (if present) and recreate ``dbname`` — a clean slate."""
    _run(_exec_admin(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    _run(_exec_admin(f'CREATE DATABASE "{dbname}"'))


def drop_database(dbname: str) -> None:
    _run(_exec_admin(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))


def _alembic_config(url: str) -> Config:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade(url: str, revision: str = "head") -> None:
    _call_without_loop(command.upgrade, _alembic_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    _call_without_loop(command.downgrade, _alembic_config(url), revision)


async def _fetch_column(url: str, sql: str) -> list[Any]:
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(sql)
        return [row[0] for row in rows]
    finally:
        await conn.close()


def public_tables(url: str) -> set[str]:
    """Names of user tables in the ``public`` schema (excludes ``alembic_version``)."""
    sql = (
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
    )
    return set(_run(_fetch_column(url, sql)))


def installed_extensions(url: str) -> set[str]:
    return set(_run(_fetch_column(url, "SELECT extname FROM pg_extension")))


def check_constraints(url: str, table: str) -> set[str]:
    """The names of the CHECK constraints on ``table`` as the database actually has them."""
    sql = (
        "SELECT conname FROM pg_constraint "
        f"WHERE conrelid = '{table}'::regclass AND contype = 'c'"
    )
    return set(_run(_fetch_column(url, sql)))


def index_predicate(url: str, index: str) -> str:
    """The full ``CREATE INDEX`` statement Postgres reports for ``index`` (predicate included)."""
    sql = f"SELECT indexdef FROM pg_indexes WHERE indexname = '{index}'"
    found = _run(_fetch_column(url, sql))
    return found[0] if found else ""
