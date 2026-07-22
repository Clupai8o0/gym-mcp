"""Shared pytest fixtures.

``_migrated_db`` (session scope) creates a throwaway database and brings it to
``head`` via the real Alembic migrations — so every test runs against the exact
schema the app ships, extensions and all. ``db_session`` (function scope) hands out
an ``AsyncSession`` wrapped in an outer transaction that is rolled back after each
test, keeping tests isolated without re-running migrations.
"""

from __future__ import annotations

import asyncio
import os

# The app's Settings require the Neon URLs at construction (fail-fast). Router tests
# build the app via ``create_app()`` but never touch the real engine — ``get_db`` is
# overridden with the rolled-back test session below — so dummy values are enough to let
# settings load. ``setdefault`` means a real environment (CI/local) still wins.
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/tempo_unused")
os.environ.setdefault("DATABASE_URL_UNPOOLED", "postgresql://localhost:5432/tempo_unused")
# The MCP transport (docs/04) validates the Host header; the ASGI test clients use
# ``testserver``/``localhost`` — allow them so the Streamable-HTTP endpoint is reachable.
os.environ.setdefault("MCP_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

from collections.abc import AsyncIterator, Iterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from typing import Any  # noqa: E402

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


def _client_for(application: object, db_session: AsyncSession) -> AsyncClient:
    """An ``httpx`` client whose ``get_db`` yields the rolled-back test session."""
    from app.api import deps

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session  # no commit: the fixture owns the transaction lifecycle

    application.dependency_overrides[deps.get_db] = _override_get_db  # type: ignore[attr-defined]
    transport = ASGITransport(app=application)  # type: ignore[arg-type]
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client authenticated as a fixed test user (``current_user`` overridden).

    Router tests exercise routing/serialization/ownership, not the auth mechanism, so
    ``current_user`` is overridden to a real, provisioned ``users`` row (via the test-only
    ``ensure_dev_user`` helper). The real ``current_user`` — session cookie, bearer token,
    401, CSRF — is exercised by the auth suite through :func:`unauth_client`.
    """
    from app.api import deps
    from app.main import create_app
    from app.services import users

    async def _override_current_user() -> deps.CurrentUser:
        user = await users.ensure_dev_user(db_session)
        return deps.CurrentUser(user_id=user.id, scopes=deps.SESSION_SCOPES, via="session")

    application = create_app()
    application.dependency_overrides[deps.current_user] = _override_current_user
    client = _client_for(application, db_session)
    async with client:
        yield client
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client with **only** ``get_db`` overridden — the real ``current_user`` runs.

    Used to test the auth boundary (session/bearer/401/CSRF) and the full OAuth surface,
    which authenticate via cookies/bearer tokens rather than a dependency override.
    """
    from app.main import create_app

    application = create_app()
    client = _client_for(application, db_session)
    async with client:
        yield client
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def mcp_http(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client bound to the app with the MCP Streamable-HTTP session manager **running**.

    The MCP tools/auth resolve their own DB session (not FastAPI's ``get_db``), so we point
    that at the rolled-back test session. The session manager runs in a **dedicated task** —
    its ``anyio`` task group must be entered and exited in one task, and pytest-asyncio may
    run a fixture's setup and teardown in different tasks; this also mirrors production, where
    the lifespan task owns the group while request tasks call ``handle_request``. A fresh
    manager is made per test (``run()`` is one-shot per instance).
    """
    from app.main import create_app
    from app.mcp import runtime, server

    @asynccontextmanager
    async def _factory() -> Any:
        yield db_session  # no commit/close: the db_session fixture owns the transaction

    runtime.set_session_factory(lambda: _factory())
    server.reset_session_manager()
    manager = server.ensure_session_manager()

    ready = asyncio.Event()
    stop = asyncio.Event()

    async def _run_manager() -> None:
        async with manager.run():
            ready.set()
            await stop.wait()

    manager_task = asyncio.create_task(_run_manager())
    await ready.wait()
    try:
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            yield client
    finally:
        stop.set()
        await manager_task
        runtime.reset_session_factory()
        server.reset_session_manager()
