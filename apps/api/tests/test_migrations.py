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
    "planned_sets",
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


def test_check_constraints_carry_the_conventional_names(fresh_db: str) -> None:
    """The migrations must produce the names the *models* declare, or the two drift silently.

    `alembic check` does not compare CHECK-constraint names, so a migration that spells a name in
    full — where the metadata naming convention (`%(table_name)s_%(constraint_name)s_check`) is
    going to add the prefix and the suffix anyway — ships
    `planned_sets_planned_sets_target_rpe_check_check` and nothing ever notices.
    """
    _dbadmin.upgrade(fresh_db, "head")

    names = _dbadmin.check_constraints(fresh_db, "planned_sets")
    assert {"planned_sets_target_rpe_check", "planned_sets_reps_range_check"} <= names, names
    # The same convention the pre-existing tables already follow.
    assert {"exercise_sets_rpe_check", "exercise_sets_pr_type_check"} <= _dbadmin.check_constraints(
        fresh_db, "exercise_sets"
    )


def test_the_completed_set_index_is_scoped_to_live_rows(fresh_db: str) -> None:
    """`alembic check` does not compare partial-index predicates either, so this half of the
    schema has no other guard.

    Both clauses are load-bearing. Uniqueness stops two lines claiming one logged set; the
    `deleted_at IS NULL` scope releases a *removed* line's claim, so the service's own conflict
    check — not the index — is what refuses the next completion. The predicate must stay identical
    to the filter in `plans._claimant`.
    """
    _dbadmin.upgrade(fresh_db, "head")

    definition = _dbadmin.index_predicate(fresh_db, "planned_sets_completed_set_uidx")
    assert "UNIQUE" in definition, definition
    assert "completed_set_id IS NOT NULL" in definition, definition
    assert "deleted_at IS NULL" in definition, definition


def test_upgrade_is_repeatable_after_downgrade(fresh_db: str) -> None:
    _dbadmin.upgrade(fresh_db, "head")
    _dbadmin.downgrade(fresh_db, "base")
    _dbadmin.upgrade(fresh_db, "head")

    assert EXPECTED_TABLES <= _dbadmin.public_tables(fresh_db)
