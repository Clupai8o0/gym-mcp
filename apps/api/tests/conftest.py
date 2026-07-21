"""Shared pytest fixtures.

``_migrated_db`` (session scope) creates a throwaway database and brings it to
``head`` via the real Alembic migrations — so every test runs against the exact
schema the app ships, extensions and all. ``db_session`` (function scope) hands out
an ``AsyncSession`` wrapped in an outer transaction that is rolled back after each
test, keeping tests isolated without re-running migrations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from app.core.db import make_asyncpg_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests import _dbadmin

_TEST_DB = "tempo_test"


@pytest.fixture(scope="session")
def _migrated_db() -> Iterator[str]:
    """Create a fresh DB, migrate it to head, and yield its (libpq) URL."""
    _dbadmin.create_database(_TEST_DB)
    url = _dbadmin.url_for(_TEST_DB)
    _dbadmin.upgrade(url, "head")
    try:
        yield url
    finally:
        _dbadmin.drop_database(_TEST_DB)


@pytest_asyncio.fixture
async def db_session(_migrated_db: str) -> AsyncIterator[AsyncSession]:
    """An ``AsyncSession`` bound to a transaction rolled back after the test."""
    async_url, connect_args = make_asyncpg_url(_migrated_db)
    engine = create_async_engine(async_url, connect_args=connect_args)
    connection: AsyncConnection = await engine.connect()
    transaction = await connection.begin()
    maker = async_sessionmaker(bind=connection, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        await session.close()
        # A failed flush inside the test may already have rolled the outer
        # transaction back (deassociating it); only roll back if still active.
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()
