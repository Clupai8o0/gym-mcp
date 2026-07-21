"""Async database engine + session factory (SQLAlchemy 2.0).

The app runtime uses the **pooled** Neon URL; Neon's server-side PgBouncer does the
heavy pooling, so the client-side pool is kept modest. Alembic/seed jobs use the
**unpooled** URL (see ``migrations/env.py`` and docs/02-data-model.md).

Neon (and libpq generally) hand out ``postgresql://…?sslmode=require`` URLs. asyncpg
does not accept libpq-style query params as connect kwargs, so :func:`make_asyncpg_url`
rewrites the scheme to ``postgresql+asyncpg`` and lifts ``sslmode`` into asyncpg's
``ssl`` connect argument, dropping the libpq-only params asyncpg would choke on.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# libpq params asyncpg cannot take as connect kwargs. ``sslmode`` is translated to
# asyncpg's ``ssl`` argument; the rest are simply dropped.
_SSLMODE_KEY = "sslmode"
_DROP_KEYS = frozenset({"channel_binding", "pgbouncer", "options", "target_session_attrs"})


def make_asyncpg_url(raw: str) -> tuple[str, dict[str, Any]]:
    """Normalize a libpq/Neon URL into an asyncpg SQLAlchemy URL + connect_args.

    Returns ``(url, connect_args)`` where ``url`` uses the ``postgresql+asyncpg``
    driver and ``connect_args`` carries any translated ``ssl`` setting.
    """
    split = urlsplit(raw)
    scheme = split.scheme
    if scheme in ("postgres", "postgresql") or scheme.startswith("postgresql+"):
        scheme = "postgresql+asyncpg"

    connect_args: dict[str, Any] = {}
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered == _SSLMODE_KEY:
            # asyncpg accepts the same vocabulary as libpq sslmode
            # ('disable'|'allow'|'prefer'|'require'|'verify-ca'|'verify-full').
            if value and value != "disable":
                connect_args["ssl"] = value
        elif lowered in _DROP_KEYS:
            continue
        else:
            kept.append((key, value))

    url = urlunsplit((scheme, split.netloc, split.path, urlencode(kept), split.fragment))
    return url, connect_args


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine bound to the pooled Neon URL."""
    from app.core.config import get_settings

    url, connect_args = make_asyncpg_url(get_settings().database_url)
    return create_async_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        # Serverless: Neon's PgBouncer pools server-side. Final tuning lands in
        # the deploy phase (docs/09); a small client pool is the safe default.
        pool_size=5,
        max_overflow=5,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory (one session per request)."""
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
