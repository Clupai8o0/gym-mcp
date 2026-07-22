"""Shared pytest fixtures.

``_migrated_db`` (session scope) creates a throwaway database and brings it to
``head`` via the real Alembic migrations — so every test runs against the exact
schema the app ships, extensions and all. ``db_session`` (function scope) hands out
an ``AsyncSession`` wrapped in an outer transaction that is rolled back after each
test, keeping tests isolated without re-running migrations.
"""

from __future__ import annotations

import os

# The app's Settings require the Neon URLs at construction (fail-fast). Router tests
# build the app via ``create_app()`` but never touch the real engine — ``get_db`` is
# overridden with the rolled-back test session below — so dummy values are enough to let
# settings load. ``setdefault`` means a real environment (CI/local) still wins.
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/tempo_unused")
os.environ.setdefault("DATABASE_URL_UNPOOLED", "postgresql://localhost:5432/tempo_unused")

from collections.abc import AsyncIterator, Iterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.core.db import make_asyncpg_url  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests import _dbadmin  # noqa: E402

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


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An ``httpx`` client bound to a fresh app whose ``get_db`` is the test session.

    ``current_user`` is left as the real Phase 2 stub, so requests run through
    ``ensure_dev_user`` against the same rolled-back transaction — exercising the actual
    auth-stub path. Writes are visible within the test and discarded at teardown.
    """
    from app.api import deps
    from app.main import create_app

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session  # no commit: the fixture owns the transaction lifecycle

    application = create_app()
    application.dependency_overrides[deps.get_db] = _override_get_db
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    application.dependency_overrides.clear()
