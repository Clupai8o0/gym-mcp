"""Unit tests for the libpq/Neon -> asyncpg URL normalization (no DB required)."""

from __future__ import annotations

from app.core.db import make_asyncpg_url


def test_plain_url_gets_asyncpg_driver() -> None:
    url, connect_args = make_asyncpg_url("postgresql://u:p@host:5432/db")
    assert url == "postgresql+asyncpg://u:p@host:5432/db"
    assert connect_args == {}


def test_postgres_scheme_is_normalized() -> None:
    url, _ = make_asyncpg_url("postgres://u:p@host/db")
    assert url.startswith("postgresql+asyncpg://")


def test_existing_driver_is_forced_to_asyncpg() -> None:
    url, _ = make_asyncpg_url("postgresql+psycopg://u:p@host/db")
    assert url.startswith("postgresql+asyncpg://")


def test_sslmode_is_lifted_into_connect_args() -> None:
    url, connect_args = make_asyncpg_url(
        "postgresql://u:p@ep-x-pooler.neon.tech/db?sslmode=require"
    )
    assert "sslmode" not in url
    assert connect_args == {"ssl": "require"}


def test_sslmode_disable_is_dropped_without_ssl_arg() -> None:
    _url, connect_args = make_asyncpg_url("postgresql://u:p@host/db?sslmode=disable")
    assert connect_args == {}


def test_libpq_only_params_are_dropped() -> None:
    url, connect_args = make_asyncpg_url(
        "postgresql://u:p@host/db?sslmode=require&channel_binding=require&pgbouncer=true"
    )
    assert "channel_binding" not in url
    assert "pgbouncer" not in url
    assert connect_args == {"ssl": "require"}


def test_unknown_params_are_preserved() -> None:
    url, _ = make_asyncpg_url("postgresql://u:p@host/db?application_name=tempo")
    assert "application_name=tempo" in url
