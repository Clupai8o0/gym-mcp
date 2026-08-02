"""Manual PR entry, and how it coexists with auto-detection.

The contract under test (``services/prs`` + ``services/sets._sync_records``):

* a hand-entered record wins immediately — it is the user correcting the log, not a guess;
* auto-detection reclaims the record only by **strictly beating** the stated value;
* every accepted write of either kind lands in ``personal_records_history``, which is what
  ``get_pr_history`` reads. That last point is the regression guard: history used to be derived
  from PR-flagged sets, so a manual record — having no set — could never appear.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.errors import ErrorKind, ServiceError
from app.models import Exercise, User, WorkoutSession
from app.services import prs, sets
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import (
    make_custom_exercise,
    make_global_exercise,
    make_session,
    make_user,
)

_ACHIEVED = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def _fixture(db: AsyncSession) -> tuple[User, Exercise, WorkoutSession]:
    user = await make_user(db)
    exercise = await make_global_exercise(db, slug="squat", name="Squat")
    session = await make_session(db, user_id=user.id, performed_at=_ACHIEVED)
    return user, exercise, session


async def test_manual_pr_survives_a_lower_auto_set(db_session: AsyncSession) -> None:
    """A 100kg estimated 1RM is not displaced by an 80kg working set."""
    user, exercise, session = await _fixture(db_session)

    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=100,
        achieved_at=_ACHIEVED,
        notes="estimated 1RM",
    )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=80,
        reps=5,
    )

    listed = await prs.list_prs(db_session, user_id=user.id)
    weight = next(row.pr for row in listed if row.pr.pr_type == "weight")
    assert weight.value == 100
    assert weight.source == "manual"
    assert weight.notes == "estimated 1RM"


async def test_higher_auto_set_reclaims_the_record(db_session: AsyncSession) -> None:
    """A real 105kg squat *does* replace a 100kg estimate, and the source flips back to auto."""
    user, exercise, session = await _fixture(db_session)

    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=100,
        achieved_at=_ACHIEVED,
        notes="estimated 1RM",
    )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=105,
        reps=1,
    )

    listed = await prs.list_prs(db_session, user_id=user.id)
    weight = next(row.pr for row in listed if row.pr.pr_type == "weight")
    assert weight.value == 105
    assert weight.source == "auto"
    # The estimate's note does not survive onto a record it no longer describes.
    assert weight.notes is None


async def test_equal_auto_set_does_not_reclaim(db_session: AsyncSession) -> None:
    """ "Strictly beats" means strictly: matching the stated value leaves the manual record."""
    user, exercise, session = await _fixture(db_session)

    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=100,
        achieved_at=_ACHIEVED,
    )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=100,
        reps=1,
    )

    listed = await prs.list_prs(db_session, user_id=user.id)
    assert next(row.pr for row in listed if row.pr.pr_type == "weight").source == "manual"


async def test_second_manual_pr_overwrites_and_both_appear_in_history(
    db_session: AsyncSession,
) -> None:
    user, exercise, _ = await _fixture(db_session)

    for value in (100, 110):
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=value,
            achieved_at=_ACHIEVED,
        )

    listed = await prs.list_prs(db_session, user_id=user.id)
    assert len(listed) == 1
    assert listed[0].pr.value == 110

    history = await prs.history(
        db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
    )
    # Append-only: the superseded claim is still part of the story.
    assert [float(row.value) for row in history] == [100.0, 110.0]
    assert {row.source for row in history} == {"manual"}


async def test_history_interleaves_manual_and_auto(db_session: AsyncSession) -> None:
    """The regression guard: history used to scan PR-flagged sets, so manual entries vanished."""
    user, exercise, _ = await _fixture(db_session)

    early = await make_session(db_session, user_id=user.id, performed_at=_ACHIEVED)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=early.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=90,
        reps=5,
    )
    # A hold timed at the gym a week later, with no session to attach it to.
    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=120,
        achieved_at=_ACHIEVED + timedelta(days=7),
    )

    history = await prs.history(
        db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
    )
    assert [(float(r.value), r.source) for r in history] == [(90.0, "auto"), (120.0, "manual")]
    # The auto entry points back at its set; the manual one has none.
    assert history[0].set_id is not None
    assert history[1].set_id is None


async def test_auto_history_is_rebuilt_not_appended(db_session: AsyncSession) -> None:
    """Editing a set rewrites its auto history rather than stacking a second entry."""
    user, exercise, session = await _fixture(db_session)

    logged = await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=90,
        reps=5,
    )
    await sets.update_set(
        db_session, user_id=user.id, set_id=logged.set.id, changes={"weight_kg": 95}
    )

    history = await prs.history(
        db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
    )
    assert [float(r.value) for r in history] == [95.0]


async def test_manual_history_survives_a_later_set_write(db_session: AsyncSession) -> None:
    """The auto rebuild must not sweep up manual rows on its way through."""
    user, exercise, session = await _fixture(db_session)

    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=100,
        achieved_at=_ACHIEVED,
    )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=80,
        reps=5,
    )

    history = await prs.history(
        db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
    )
    # Both entries claim the same instant here, so assert on membership rather than order —
    # the ordering contract is covered by `test_history_interleaves_manual_and_auto`.
    assert {(float(r.value), r.source) for r in history} == {(80.0, "auto"), (100.0, "manual")}


# ── validation ───────────────────────────────────────────────────────────────────────────
async def test_rejects_non_positive_value(db_session: AsyncSession) -> None:
    user, exercise, _ = await _fixture(db_session)
    with pytest.raises(ServiceError) as caught:
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=0,
            achieved_at=_ACHIEVED,
        )
    assert caught.value.kind is ErrorKind.VALIDATION


async def test_rejects_unknown_pr_type_and_lists_the_valid_ones(db_session: AsyncSession) -> None:
    user, exercise, _ = await _fixture(db_session)
    with pytest.raises(ServiceError) as caught:
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="tonnage",
            value=100,
            achieved_at=_ACHIEVED,
        )
    assert caught.value.kind is ErrorKind.VALIDATION
    for valid in ("weight", "reps", "hold_time"):
        assert valid in caught.value.message


async def test_rejects_future_achieved_at(db_session: AsyncSession) -> None:
    user, exercise, _ = await _fixture(db_session)
    with pytest.raises(ServiceError) as caught:
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=datetime.now(UTC) + timedelta(days=1),
        )
    assert caught.value.kind is ErrorKind.VALIDATION


async def test_rejects_someone_elses_session(db_session: AsyncSession) -> None:
    user, exercise, _ = await _fixture(db_session)
    intruder = await make_user(db_session, email="mallory@example.com")
    theirs = await make_session(db_session, user_id=intruder.id)

    with pytest.raises(ServiceError) as caught:
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
            session_id=theirs.id,
        )
    assert caught.value.kind is ErrorKind.NOT_FOUND


async def test_rejects_an_exercise_the_user_cannot_see(db_session: AsyncSession) -> None:
    user, _, _ = await _fixture(db_session)
    other = await make_user(db_session, email="other@example.com")
    theirs = await make_custom_exercise(
        db_session, user_id=other.id, slug="secret-move", name="Secret Move"
    )
    with pytest.raises(ServiceError) as caught:
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=theirs.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
        )
    assert caught.value.kind is ErrorKind.NOT_FOUND


async def test_naive_achieved_at_is_read_as_utc(db_session: AsyncSession) -> None:
    """MCP clients send whatever their JSON carried; a bare timestamp must not raise."""
    user, exercise, _ = await _fixture(db_session)
    row = await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="hold_time",
        value=45,
        achieved_at=datetime(2026, 6, 1, 12, 0),  # noqa: DTZ001 — the point of the test
    )
    assert row.pr.achieved_at.tzinfo is not None
    assert row.pr.unit == "s"
