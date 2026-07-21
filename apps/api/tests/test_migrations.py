"""Migration acceptance: ``upgrade head`` builds everything; ``downgrade base`` reverses.

Uses its own throwaway database so the up/down/up cycle can't disturb the shared
``_migrated_db`` schema other tests rely on.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests import _dbadmin

EXPECTED_TABLES = {
    "users",
    "exercises",
    "workout_sessions",
    "exercise_sets",
    "personal_records",
    "skills",
    "skill_progress",
}
EXPECTED_EXTENSIONS = {"pgcrypto", "pg_trgm"}
_MIGRATION_DB = "tempo_test_migrations"


@pytest.fixture
def fresh_db() -> Iterator[str]:
    _dbadmin.create_database(_MIGRATION_DB)
    try:
        yield _dbadmin.url_for(_MIGRATION_DB)
    finally:
        _dbadmin.drop_database(_MIGRATION_DB)


def test_upgrade_head_builds_all_tables_and_extensions(fresh_db: str) -> None:
    _dbadmin.upgrade(fresh_db, "head")

    tables = _dbadmin.public_tables(fresh_db)
    assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"

    extensions = _dbadmin.installed_extensions(fresh_db)
    assert EXPECTED_EXTENSIONS <= extensions


def test_downgrade_base_reverses_cleanly(fresh_db: str) -> None:
    _dbadmin.upgrade(fresh_db, "head")
    _dbadmin.downgrade(fresh_db, "base")

    tables = _dbadmin.public_tables(fresh_db)
    assert EXPECTED_TABLES.isdisjoint(tables), f"leftover tables: {EXPECTED_TABLES & tables}"

    extensions = _dbadmin.installed_extensions(fresh_db)
    assert EXPECTED_EXTENSIONS.isdisjoint(extensions)


def test_upgrade_is_repeatable_after_downgrade(fresh_db: str) -> None:
    _dbadmin.upgrade(fresh_db, "head")
    _dbadmin.downgrade(fresh_db, "base")
    _dbadmin.upgrade(fresh_db, "head")

    assert EXPECTED_TABLES <= _dbadmin.public_tables(fresh_db)
