"""Alembic environment — async, targeting the SQLAlchemy models' metadata.

URL resolution order:
  1. the ``sqlalchemy.url`` main option (set programmatically by the test harness), then
  2. the ``DATABASE_URL_UNPOOLED`` environment variable (the CLI path).

The raw libpq/Neon URL is normalized to the ``postgresql+asyncpg`` driver via
``app.core.db.make_asyncpg_url`` (which also lifts ``sslmode`` into connect args).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from app.core.db import make_asyncpg_url
from app.models import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _raw_url() -> str:
    # 1. explicit override (the test harness sets this), then 2. the environment,
    # then 3. settings (which also loads .env for local `alembic`/`pnpm migrate`).
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL_UNPOOLED")
    if url:
        return url
    try:
        from app.core.config import get_settings

        return get_settings().database_url_unpooled
    except Exception as exc:
        # Re-raise any settings/validation failure as one clear, actionable error.
        raise RuntimeError(
            "No database URL. Set DATABASE_URL_UNPOOLED (the direct Neon URL) in the "
            "environment or .env, or pass sqlalchemy.url to Alembic."
        ) from exc


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB connection (``alembic upgrade --sql``)."""
    async_url, _connect_args = make_asyncpg_url(_raw_url())
    context.configure(
        url=async_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    async_url, connect_args = make_asyncpg_url(_raw_url())
    connectable = create_async_engine(async_url, connect_args=connect_args, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
