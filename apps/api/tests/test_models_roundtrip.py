"""Round-trip (insert -> select) coverage for every core + skills model.

Also exercises the schema behaviors that are easy to get wrong: server-side defaults,
the partial-unique slug indexes, and a representative CHECK constraint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models import (
    Exercise,
    ExerciseSet,
    PersonalRecord,
    PlannedSet,
    Skill,
    SkillProgress,
    User,
    WorkoutSession,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


async def _make_user(db: AsyncSession, *, email: str = "lifter@example.com") -> User:
    user = User(email=email, google_sub=f"sub-{email}", name="Test Lifter")
    db.add(user)
    await db.flush()
    return user


async def test_user_defaults_roundtrip(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    await db_session.refresh(user)

    assert user.id is not None
    assert user.created_at is not None
    assert user.unit_pref == "kg"  # server default
    assert user.last_login_at is None


async def test_global_exercise_defaults(db_session: AsyncSession) -> None:
    exercise = Exercise(slug="barbell-bench-press", name="Barbell Bench Press")
    db_session.add(exercise)
    await db_session.flush()
    await db_session.refresh(exercise)

    assert exercise.created_by_user_id is None  # global row
    assert exercise.source == "free-exercise-db"  # server default
    assert exercise.illustration_status == "pending"  # server default
    assert exercise.primary_muscles == []  # server default '{}'
    assert exercise.secondary_muscles == []
    assert exercise.instructions == []
    assert exercise.updated_at is not None


async def test_full_training_log_roundtrip(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    exercise = Exercise(
        slug="pull-up",
        name="Pull Up",
        created_by_user_id=user.id,  # a custom exercise
        primary_muscles=["lats", "biceps"],
        instructions=["Hang from the bar", "Pull chin over the bar"],
    )
    db_session.add(exercise)
    await db_session.flush()

    session = WorkoutSession(
        user_id=user.id, title="Upper — Power", type="upper", performed_at=_utcnow()
    )
    db_session.add(session)
    await db_session.flush()

    exercise_set = ExerciseSet(
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=Decimal("20.5"),
        reps=8,
        rpe=Decimal("8.5"),
    )
    db_session.add(exercise_set)
    await db_session.flush()

    pr = PersonalRecord(
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=Decimal("20.5"),
        unit="kg",
        achieved_at=_utcnow(),
        session_id=session.id,
    )
    db_session.add(pr)
    await db_session.flush()

    # Capture ids before expiring so the re-reads below genuinely hit the DB.
    set_id, exercise_id, pr_id = exercise_set.id, exercise.id, pr.id
    db_session.expire_all()

    fetched = (
        await db_session.execute(select(ExerciseSet).where(ExerciseSet.id == set_id))
    ).scalar_one()
    assert fetched.reps == 8
    assert fetched.weight_kg == Decimal("20.5")
    assert fetched.is_pr is False  # server default
    assert fetched.pr_type is None

    fetched_ex = (
        await db_session.execute(select(Exercise).where(Exercise.id == exercise_id))
    ).scalar_one()
    assert fetched_ex.primary_muscles == ["lats", "biceps"]
    assert fetched_ex.instructions[1] == "Pull chin over the bar"

    fetched_pr = (
        await db_session.execute(select(PersonalRecord).where(PersonalRecord.id == pr_id))
    ).scalar_one()
    assert fetched_pr.value == Decimal("20.5")
    assert fetched_pr.unit == "kg"


async def test_skill_progress_roundtrip(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    skill = (await db_session.execute(select(Skill).limit(1))).scalar_one()

    progress = SkillProgress(
        user_id=user.id,
        skill_id=skill.id,
        current_stage=2,
        stage_name="tuck planche",
        progress_percent=40,
    )
    db_session.add(progress)
    await db_session.flush()
    await db_session.refresh(progress)

    assert progress.id is not None
    assert progress.current_stage == 2
    assert progress.progress_percent == 40
    assert progress.updated_at is not None


async def test_global_slug_uniqueness_conflicts(db_session: AsyncSession) -> None:
    db_session.add(Exercise(slug="squat", name="Squat"))
    db_session.add(Exercise(slug="squat", name="Squat (dup)"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_global_and_custom_can_share_a_slug(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    db_session.add(Exercise(slug="dip", name="Dip"))  # global
    db_session.add(Exercise(slug="dip", name="Dip", created_by_user_id=user.id))  # custom

    # The two partial-unique indexes are independent, so this must NOT conflict.
    await db_session.flush()


async def test_unit_pref_check_constraint(db_session: AsyncSession) -> None:
    db_session.add(User(email="bad@example.com", google_sub="sub-bad", unit_pref="stone"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_planned_set_roundtrip_and_defaults(db_session: AsyncSession) -> None:
    """A prescribed line stores its targets, defaults its position, and starts uncompleted."""
    user = await _make_user(db_session)
    exercise = Exercise(slug="front-squat", name="Front Squat")
    db_session.add(exercise)
    await db_session.flush()
    session = WorkoutSession(user_id=user.id, performed_at=_utcnow())
    db_session.add(session)
    await db_session.flush()

    planned = PlannedSet(
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=2,
        target_reps_min=8,
        target_reps_max=10,
        target_weight_kg=Decimal("62.5"),
        target_rpe=Decimal("8"),
    )
    db_session.add(planned)
    await db_session.flush()

    planned_id = planned.id
    db_session.expire_all()

    fetched = (
        await db_session.execute(select(PlannedSet).where(PlannedSet.id == planned_id))
    ).scalar_one()
    assert (fetched.target_reps_min, fetched.target_reps_max) == (8, 10)
    assert fetched.target_weight_kg == Decimal("62.5")
    assert fetched.order_index == 0  # server default
    assert fetched.completed_set_id is None
    assert fetched.deleted_at is None


async def test_planned_set_rep_range_check_constraint(db_session: AsyncSession) -> None:
    """A range that counts down is refused by the database, not only by the service."""
    user = await _make_user(db_session, email="ranges@example.com")
    exercise = Exercise(slug="press", name="Press")
    db_session.add(exercise)
    await db_session.flush()
    session = WorkoutSession(user_id=user.id, performed_at=_utcnow())
    db_session.add(session)
    await db_session.flush()

    db_session.add(
        PlannedSet(
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            target_reps_min=10,
            target_reps_max=8,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_logged_set_can_complete_only_one_planned_set(
    db_session: AsyncSession,
) -> None:
    """Otherwise a session could report more work completed than was ever logged."""
    user = await _make_user(db_session, email="claims@example.com")
    exercise = Exercise(slug="dip", name="Dip")
    db_session.add(exercise)
    await db_session.flush()
    session = WorkoutSession(user_id=user.id, performed_at=_utcnow())
    db_session.add(session)
    await db_session.flush()
    logged = ExerciseSet(
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        reps=10,
    )
    db_session.add(logged)
    await db_session.flush()

    for number in (1, 2):
        db_session.add(
            PlannedSet(
                user_id=user.id,
                session_id=session.id,
                exercise_id=exercise.id,
                set_number=number,
                completed_set_id=logged.id,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()
