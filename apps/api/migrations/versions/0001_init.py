"""init — extensions + all core & skills tables (docs/02-data-model.md).

Baseline schema for the greenfield Neon database. Creates the ``pgcrypto`` (for
``gen_random_uuid()``) and ``pg_trgm`` (for the exercise-name trigram index) extensions,
then every core + skills table with its indexes and constraints. OAuth tables are
deferred to Phase 3's migration.

Revision ID: 0001_init
Revises:
Create Date: 2026-07-21 15:23:21.248238+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions first: pgcrypto backs the gen_random_uuid() PK default, and pg_trgm
    # provides the gin_trgm_ops opclass used by the exercises_name_trgm index below.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("google_sub", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("unit_pref", sa.Text(), server_default="kg", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("unit_pref in ('kg','lb')", name=op.f("users_unit_pref_check")),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
        sa.UniqueConstraint("email", name=op.f("users_email_key")),
        sa.UniqueConstraint("google_sub", name=op.f("users_google_sub_key")),
    )
    op.create_table(
        "exercises",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("force", sa.Text(), nullable=True),
        sa.Column("level", sa.Text(), nullable=True),
        sa.Column("mechanic", sa.Text(), nullable=True),
        sa.Column("equipment", sa.Text(), nullable=True),
        sa.Column(
            "primary_muscles",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "secondary_muscles",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "instructions",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), server_default="free-exercise-db", nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("illustration_url", sa.Text(), nullable=True),
        sa.Column("illustration_status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("illustration_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "force in ('push','pull','static') or force is null",
            name=op.f("exercises_force_check"),
        ),
        sa.CheckConstraint(
            "illustration_status in ('pending','generating','ready','failed')",
            name=op.f("exercises_illustration_status_check"),
        ),
        sa.CheckConstraint(
            "level in ('beginner','intermediate','expert') or level is null",
            name=op.f("exercises_level_check"),
        ),
        sa.CheckConstraint(
            "mechanic in ('compound','isolation') or mechanic is null",
            name=op.f("exercises_mechanic_check"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("exercises_created_by_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("exercises_pkey")),
    )
    op.create_index("exercises_category_idx", "exercises", ["category"], unique=False)
    op.create_index(
        "exercises_custom_slug_uidx",
        "exercises",
        ["created_by_user_id", "slug"],
        unique=True,
        postgresql_where=sa.text("created_by_user_id IS NOT NULL"),
    )
    op.create_index(
        "exercises_global_slug_uidx",
        "exercises",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("created_by_user_id IS NULL"),
    )
    op.create_index(
        "exercises_illustration_status_idx", "exercises", ["illustration_status"], unique=False
    )
    op.create_index(
        "exercises_name_trgm",
        "exercises",
        [sa.literal_column("name gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "exercises_primary_muscles_gin",
        "exercises",
        ["primary_muscles"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "exercises_source_uidx",
        "exercises",
        ["source", "source_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("workout_sessions_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("workout_sessions_pkey")),
    )
    op.create_index(
        "workout_sessions_type_idx", "workout_sessions", ["user_id", "type"], unique=False
    )
    op.create_index(
        "workout_sessions_user_date_idx",
        "workout_sessions",
        ["user_id", sa.literal_column("performed_at DESC")],
        unique=False,
    )
    op.create_table(
        "exercise_sets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("exercise_id", sa.UUID(), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("hold_seconds", sa.Integer(), nullable=True),
        sa.Column("rpe", sa.Numeric(), nullable=True),
        sa.Column("is_pr", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pr_type", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pr_type in ('weight','reps','hold_time','first_log') or pr_type is null",
            name=op.f("exercise_sets_pr_type_check"),
        ),
        sa.CheckConstraint(
            "rpe is null or (rpe >= 1 and rpe <= 10)", name=op.f("exercise_sets_rpe_check")
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercises.id"], name=op.f("exercise_sets_exercise_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["workout_sessions.id"],
            name=op.f("exercise_sets_session_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("exercise_sets_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("exercise_sets_pkey")),
    )
    op.create_index(
        "exercise_sets_pr_idx",
        "exercise_sets",
        ["user_id", "exercise_id", "is_pr"],
        unique=False,
    )
    op.create_index("exercise_sets_session_idx", "exercise_sets", ["session_id"], unique=False)
    op.create_index(
        "exercise_sets_user_exercise_idx",
        "exercise_sets",
        ["user_id", "exercise_id"],
        unique=False,
    )
    op.create_table(
        "personal_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("exercise_id", sa.UUID(), nullable=False),
        sa.Column("pr_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "pr_type in ('weight','reps','hold_time')",
            name=op.f("personal_records_pr_type_check"),
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercises.id"], name=op.f("personal_records_exercise_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["workout_sessions.id"],
            name=op.f("personal_records_session_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("personal_records_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("personal_records_pkey")),
        sa.UniqueConstraint("user_id", "exercise_id", "pr_type", name="personal_records_uidx"),
    )
    op.create_index("personal_records_user_idx", "personal_records", ["user_id"], unique=False)
    op.create_table(
        "skills",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("total_stages", sa.Integer(), nullable=False),
        sa.Column("stages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("related_exercise_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["related_exercise_id"], ["exercises.id"], name=op.f("skills_related_exercise_id_fkey")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("skills_pkey")),
        sa.UniqueConstraint("slug", name=op.f("skills_slug_key")),
    )
    op.create_table(
        "skill_progress",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("current_stage", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("stage_name", sa.Text(), nullable=True),
        sa.Column("progress_percent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "progress_percent between 0 and 100",
            name=op.f("skill_progress_progress_percent_check"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("skill_progress_skill_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("skill_progress_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("skill_progress_pkey")),
        sa.UniqueConstraint("user_id", "skill_id", name="skill_progress_uidx"),
    )


def downgrade() -> None:
    op.drop_table("skill_progress")
    op.drop_table("skills")
    op.drop_index("personal_records_user_idx", table_name="personal_records")
    op.drop_table("personal_records")
    op.drop_index("exercise_sets_user_exercise_idx", table_name="exercise_sets")
    op.drop_index("exercise_sets_session_idx", table_name="exercise_sets")
    op.drop_index("exercise_sets_pr_idx", table_name="exercise_sets")
    op.drop_table("exercise_sets")
    op.drop_index("workout_sessions_user_date_idx", table_name="workout_sessions")
    op.drop_index("workout_sessions_type_idx", table_name="workout_sessions")
    op.drop_table("workout_sessions")
    op.drop_index(
        "exercises_source_uidx",
        table_name="exercises",
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )
    op.drop_index("exercises_primary_muscles_gin", table_name="exercises", postgresql_using="gin")
    op.drop_index("exercises_name_trgm", table_name="exercises", postgresql_using="gin")
    op.drop_index("exercises_illustration_status_idx", table_name="exercises")
    op.drop_index(
        "exercises_global_slug_uidx",
        table_name="exercises",
        postgresql_where=sa.text("created_by_user_id IS NULL"),
    )
    op.drop_index(
        "exercises_custom_slug_uidx",
        table_name="exercises",
        postgresql_where=sa.text("created_by_user_id IS NOT NULL"),
    )
    op.drop_index("exercises_category_idx", table_name="exercises")
    op.drop_table("exercises")
    op.drop_table("users")

    # Drop the extensions last, after every object that depended on them is gone.
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
