"""Planned (prescribed) sets: writing a plan, working through it, and staying out of the numbers.

The load-bearing class here is :class:`TestAPlanIsNotTraining`. Everything else describes how the
prescription behaves; that one describes the property the whole design exists to hold, and it is
the one a future change is most likely to break by accident.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.errors import ErrorKind, ServiceError
from app.models import Exercise, PlannedSet, User, WorkoutSession
from app.services import (
    analytics,
    corrections,
    exercises,
    integrity,
    plans,
    prs,
    sessions,
    sets,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise, make_planned_set, make_session, make_user

_TOMORROW = datetime.now(tz=UTC) + timedelta(days=1)


async def _fixture(
    db: AsyncSession, *, performed_at: datetime | None = None
) -> tuple[User, Exercise, WorkoutSession]:
    """A user, a bench-press exercise, and a session — the setup nearly every test here needs."""
    user = await make_user(db)
    exercise = await make_global_exercise(db)
    session = await make_session(
        db, user_id=user.id, performed_at=performed_at or datetime.now(tz=UTC)
    )
    return user, exercise, session


# ── Writing a plan ───────────────────────────────────────────────────────────────────
async def test_plan_session_creates_the_session_and_its_prescription(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)

    plan = await plans.plan_session(
        db_session,
        user_id=user.id,
        performed_at=_TOMORROW,
        title="Upper — Power",
        type="upper",
        drafts=[
            plans.PlannedSetDraft(
                exercise_id=bench.id,
                set_number=n,
                target_reps_min=5,
                target_reps_max=5,
                target_weight_kg=100,
            )
            for n in (1, 2, 3)
        ],
    )

    assert plan.session.title == "Upper — Power"
    assert plan.planned_total == 3 and plan.completed_count == 0
    # Numbered in the order given, so a plan reads back the way it was written.
    assert [item.planned.order_index for item in plan.items] == [0, 1, 2]
    assert all(item.planned.target_weight_kg == Decimal(100) for item in plan.items)
    assert all(not item.is_completed for item in plan.items)


async def test_a_plan_line_may_carry_no_target_at_all(db_session: AsyncSession) -> None:
    """ "Bench press, three sets, work up to something heavy" is a real instruction."""
    user, bench, session = await _fixture(db_session)
    rows = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=1, notes="work up")],
    )
    assert rows[0].target_reps_min is None and rows[0].target_weight_kg is None
    assert plans.describe(rows[0]) == "no explicit target"


async def test_a_rep_range_that_counts_down_is_rejected(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    with pytest.raises(ServiceError) as caught:
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                plans.PlannedSetDraft(exercise_id=bench.id, target_reps_min=5, target_reps_max=5),
                plans.PlannedSetDraft(exercise_id=bench.id, target_reps_min=10, target_reps_max=8),
            ],
        )
    assert caught.value.kind is ErrorKind.VALIDATION
    # Named, so a twelve-set week does not have to be bisected to find the bad line.
    assert "planned_sets[1]" in caught.value.message
    # All or nothing: the good line in front of it is not left behind either.
    assert (await plans.get_plan(db_session, user_id=user.id, session_id=session.id)).items == []


async def test_added_lines_continue_the_existing_numbering(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=1)],
    )
    added = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=2)],
    )
    assert added[0].order_index == 1


async def test_the_same_client_key_twice_writes_one_plan(db_session: AsyncSession) -> None:
    """A retried `plan_session` that never saw its response must not write the workout twice."""
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)
    drafts = [plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)]

    first = await plans.plan_session(
        db_session, user_id=user.id, performed_at=_TOMORROW, drafts=drafts, client_key="tue-upper"
    )
    second = await plans.plan_session(
        db_session, user_id=user.id, performed_at=_TOMORROW, drafts=drafts, client_key="tue-upper"
    )

    assert second.session.id == first.session.id
    assert second.planned_total == 2, "the prescription is returned, not doubled"


async def test_planning_against_someone_elses_session_is_not_found(
    db_session: AsyncSession,
) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    bench = await make_global_exercise(db_session)
    bob_session = await make_session(db_session, user_id=bob.id)

    with pytest.raises(ServiceError) as caught:
        await plans.add_planned_sets(
            db_session,
            user_id=alice.id,
            session_id=bob_session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
        )
    assert caught.value.kind is ErrorKind.NOT_FOUND


# ── Working through a plan ───────────────────────────────────────────────────────────
async def test_completing_a_line_logs_a_real_set_and_links_it(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                plans.PlannedSetDraft(
                    exercise_id=bench.id, set_number=1, target_reps_min=5, target_weight_kg=100
                )
            ],
        )
    )[0]

    done = await plans.complete(
        db_session, user_id=user.id, planned_set_id=line.id, weight_kg=102.5, reps=5
    )

    assert done.logged.set.session_id == session.id
    assert done.logged.set.weight_kg == Decimal("102.5"), "what happened, not what was prescribed"
    assert done.logged.pr.is_pr is True, "PR detection runs exactly as it does for any set"
    assert done.item.planned.completed_set_id == done.logged.set.id
    # And it is a real set as far as the rest of the app is concerned.
    detail = await sessions.get(db_session, user_id=user.id, session_id=session.id)
    assert len(detail.sets) == 1


async def test_completing_needs_what_you_actually_did(db_session: AsyncSession) -> None:
    """The targets are never used as results — that would make adherence agree with itself."""
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                plans.PlannedSetDraft(
                    exercise_id=bench.id,
                    target_reps_min=8,
                    target_reps_max=10,
                    target_weight_kg=60,
                )
            ],
        )
    )[0]

    with pytest.raises(ServiceError) as caught:
        await plans.complete(db_session, user_id=user.id, planned_set_id=line.id)
    assert caught.value.kind is ErrorKind.VALIDATION
    assert "8-10 reps @ 60 kg" in caught.value.message, "the error quotes the line it is about"


async def test_completing_the_same_line_twice_is_a_conflict(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
        )
    )[0]
    first = await plans.complete(
        db_session, user_id=user.id, planned_set_id=line.id, weight_kg=100, reps=5
    )

    with pytest.raises(ServiceError) as caught:
        await plans.complete(
            db_session, user_id=user.id, planned_set_id=line.id, weight_kg=105, reps=5
        )
    assert caught.value.kind is ErrorKind.CONFLICT
    assert caught.value.details is not None
    assert caught.value.details["completed_set_id"] == str(first.logged.set.id)


async def test_completing_is_idempotent_under_a_client_key(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
        )
    )[0]

    first = await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=line.id,
        weight_kg=100,
        reps=5,
        client_key="set-1",
    )
    # The retry a client makes when it never saw the first answer: same set, same link, no second
    # row and no "already completed" refusal.
    second = await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=line.id,
        weight_kg=100,
        reps=5,
        client_key="set-1",
    )
    assert second.logged.set.id == first.logged.set.id
    progress = await plans.progress(db_session, user_id=user.id, session_id=session.id)
    assert progress.logged_total == 1 and progress.adherence.completed_count == 1


async def test_deleting_the_logged_set_reopens_the_line(db_session: AsyncSession) -> None:
    """Completion is read through the link, so removing the set is enough — no second write."""
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
        )
    )[0]
    done = await plans.complete(
        db_session, user_id=user.id, planned_set_id=line.id, weight_kg=100, reps=5
    )

    await sets.delete_set(db_session, user_id=user.id, set_id=done.logged.set.id)

    plan = await plans.get_plan(db_session, user_id=user.id, session_id=session.id)
    assert plan.completed_count == 0
    assert plan.items[0].is_completed is False
    # …and it can simply be done again.
    redone = await plans.complete(
        db_session, user_id=user.id, planned_set_id=line.id, weight_kg=95, reps=5
    )
    assert redone.logged.set.id != done.logged.set.id


async def test_logging_off_plan_is_never_blocked(db_session: AsyncSession) -> None:
    """A tool that refuses training because nobody wrote it down first is worse than no plan."""
    user, bench, session = await _fixture(db_session)
    extra = await make_global_exercise(db_session, slug="row", name="Barbell Row")
    await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=1)],
    )

    logged = await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=extra.id,
        set_number=1,
        weight_kg=80,
        reps=8,
    )
    assert logged.set.id is not None

    report = await plans.progress(db_session, user_id=user.id, session_id=session.id)
    assert report.adherence.off_plan_count == 1
    assert report.adherence.completed_count == 0, "an unprescribed set completes nothing"
    assert report.logged_total == 1


# ── Reading a plan ───────────────────────────────────────────────────────────────────
async def test_progress_reports_what_is_left_and_what_is_next(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    squat = await make_global_exercise(db_session, slug="squat", name="Back Squat")
    # Written as a superset: squat, bench, squat, bench.
    lines = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[
            plans.PlannedSetDraft(exercise_id=squat.id, set_number=1),
            plans.PlannedSetDraft(exercise_id=bench.id, set_number=1),
            plans.PlannedSetDraft(exercise_id=squat.id, set_number=2),
            plans.PlannedSetDraft(exercise_id=bench.id, set_number=2),
        ],
    )
    await plans.complete(
        db_session, user_id=user.id, planned_set_id=lines[0].id, weight_kg=140, reps=5
    )

    report = await plans.progress(db_session, user_id=user.id, session_id=session.id)
    assert (report.adherence.planned_total, report.adherence.completed_count) == (4, 1)
    assert report.adherence.pending_count == 3
    assert report.adherence.percent == 25.0
    # Next up follows the plan's own order, which is why the superset was not regrouped.
    assert report.next_up is not None and report.next_up.planned.id == lines[1].id
    # Breakdown reads in the order the movements first appear, not alphabetically.
    assert [row.exercise.name for row in report.exercises] == ["Back Squat", "Bench Press"]
    assert [row.remaining for row in report.exercises] == [1, 2]
    assert [row.exercise.name for row in report.remaining_exercises] == [
        "Back Squat",
        "Bench Press",
    ]


async def test_progress_works_on_a_session_nobody_planned(db_session: AsyncSession) -> None:
    """ "Nothing was prescribed" is a legitimate answer, not a 404."""
    user, bench, session = await _fixture(db_session)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bench.id,
        set_number=1,
        weight_kg=100,
        reps=5,
    )

    report = await plans.progress(db_session, user_id=user.id, session_id=session.id)
    assert report.adherence.planned_total == 0
    assert report.adherence.percent is None, "neither 0% nor 100% is true of a session with no plan"
    assert report.adherence.off_plan_count == 1
    assert report.next_up is None


async def test_finish_session_reports_adherence(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    lines = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2, 3, 4)],
    )
    for line in lines[:3]:
        await plans.complete(
            db_session, user_id=user.id, planned_set_id=line.id, weight_kg=100, reps=5
        )

    finished = await sessions.finish_session(db_session, user_id=user.id, session_id=session.id)
    assert finished.session.ended_at is not None
    assert finished.adherence.completed_count == 3 and finished.adherence.planned_total == 4
    assert finished.adherence.pending_count == 1
    assert finished.adherence.percent == 75.0


# ── The active session ───────────────────────────────────────────────────────────────
async def test_a_session_with_a_plan_and_no_sets_is_still_active(
    db_session: AsyncSession,
) -> None:
    """The whole point of writing the plan first is that it is there before anything is logged."""
    user, bench, session = await _fixture(db_session)
    await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )

    active = await sessions.get_active_session(db_session, user_id=user.id)
    assert active is not None and active.session.id == session.id
    assert active.set_count == 0
    assert active.planned_total == 2 and active.completed_count == 0


async def test_a_plan_for_a_later_day_is_not_the_active_session(
    db_session: AsyncSession,
) -> None:
    """A future-dated open session used to sort above the live one and take its place."""
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)
    live = await make_session(
        db_session, user_id=user.id, performed_at=datetime.now(tz=UTC) - timedelta(minutes=10)
    )
    await plans.plan_session(
        db_session,
        user_id=user.id,
        performed_at=datetime.now(tz=UTC) + timedelta(days=3),
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
    )

    active = await sessions.get_active_session(db_session, user_id=user.id)
    assert active is not None and active.session.id == live.id


async def test_a_scheduled_plan_is_not_swept_as_abandoned(db_session: AsyncSession) -> None:
    """It cannot be abandoned before it was due — the staleness clauses measure a negative age."""
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)
    plan = await plans.plan_session(
        db_session,
        user_id=user.id,
        performed_at=datetime.now(tz=UTC) + timedelta(days=3),
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
    )

    assert await sessions.get_active_session(db_session, user_id=user.id) is None
    await db_session.refresh(plan.session)
    assert plan.session.ended_at is None, "still waiting for its day, not retired"


async def test_a_plan_becomes_active_when_its_time_arrives(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)
    start = datetime.now(tz=UTC) + timedelta(hours=6)
    plan = await plans.plan_session(
        db_session,
        user_id=user.id,
        performed_at=start,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )

    assert await sessions.get_active_session(db_session, user_id=user.id) is None
    active = await sessions.get_active_session(
        db_session, user_id=user.id, now=start + timedelta(minutes=1)
    )
    assert active is not None and active.session.id == plan.session.id
    assert active.planned_total == 2


# ── Correcting a plan ────────────────────────────────────────────────────────────────
async def test_update_changes_only_what_is_passed(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = await make_planned_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bench.id,
        target_reps_min=5,
        target_weight_kg=100,
    )

    updated = await plans.update_planned_set(
        db_session,
        user_id=user.id,
        planned_set_id=line.id,
        changes={"target_weight_kg": 105},
    )
    assert updated.target_weight_kg == Decimal(105)
    assert updated.target_reps_min == 5, "untouched"


async def test_update_cannot_move_a_line_to_another_movement(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = await make_planned_set(
        db_session, user_id=user.id, session_id=session.id, exercise_id=bench.id
    )
    with pytest.raises(ServiceError) as caught:
        await plans.update_planned_set(
            db_session,
            user_id=user.id,
            planned_set_id=line.id,
            changes={"exercise_id": bench.id},
        )
    assert caught.value.kind is ErrorKind.VALIDATION


async def test_editing_a_completed_line_never_rewrites_the_log(db_session: AsyncSession) -> None:
    """The plan said one thing and the training was another; the log is the part that is true."""
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id, target_weight_kg=100)],
        )
    )[0]
    done = await plans.complete(
        db_session, user_id=user.id, planned_set_id=line.id, weight_kg=102.5, reps=5
    )

    await plans.update_planned_set(
        db_session, user_id=user.id, planned_set_id=line.id, changes={"target_weight_kg": 110}
    )

    logged = await sets.get_set(db_session, user_id=user.id, set_id=done.logged.set.id)
    assert logged.weight_kg == Decimal("102.5")


async def test_deleting_a_line_leaves_the_set_it_recorded(db_session: AsyncSession) -> None:
    """Taking a line out of the plan is a statement about the plan, not about the training."""
    user, bench, session = await _fixture(db_session)
    line = (
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
        )
    )[0]
    done = await plans.complete(
        db_session, user_id=user.id, planned_set_id=line.id, weight_kg=100, reps=5
    )

    await plans.delete_planned_set(db_session, user_id=user.id, planned_set_id=line.id)

    report = await plans.progress(db_session, user_id=user.id, session_id=session.id)
    assert report.adherence.planned_total == 0
    assert report.logged_total == 1, "the set is still in the log"
    assert report.adherence.off_plan_count == 1, "…now as work nobody prescribed"
    logged = await sets.get_set(db_session, user_id=user.id, set_id=done.logged.set.id)
    assert logged.deleted_at is None


async def test_a_deleted_line_can_be_restored(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = await make_planned_set(
        db_session, user_id=user.id, session_id=session.id, exercise_id=bench.id
    )
    await plans.delete_planned_set(db_session, user_id=user.id, planned_set_id=line.id)
    assert (await plans.get_plan(db_session, user_id=user.id, session_id=session.id)).items == []

    restored = await corrections.restore(
        db_session, user_id=user.id, entity_type="planned_set", entity_id=line.id
    )
    assert restored.exercises_recalculated == 0, "nothing is derived from a prescription"
    assert (
        len((await plans.get_plan(db_session, user_id=user.id, session_id=session.id)).items) == 1
    )


async def test_deleting_a_session_takes_its_plan_and_restore_brings_both_back(
    db_session: AsyncSession,
) -> None:
    user, bench, session = await _fixture(db_session)
    await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )

    removed = await sessions.delete(db_session, user_id=user.id, session_id=session.id)
    assert removed.planned_count == 2
    rows = (
        (
            await db_session.execute(
                select(PlannedSet).where(
                    PlannedSet.session_id == session.id, PlannedSet.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []

    await corrections.restore(
        db_session, user_id=user.id, entity_type="session", entity_id=session.id
    )
    plan = await plans.get_plan(db_session, user_id=user.id, session_id=session.id)
    assert plan.planned_total == 2


async def test_purge_erases_a_deleted_line(db_session: AsyncSession) -> None:
    user, bench, session = await _fixture(db_session)
    line = await make_planned_set(
        db_session, user_id=user.id, session_id=session.id, exercise_id=bench.id
    )
    await plans.delete_planned_set(
        db_session,
        user_id=user.id,
        planned_set_id=line.id,
        at=datetime.now(tz=UTC) - timedelta(days=40),
    )

    preview = await corrections.purge(db_session, user_id=user.id, older_than_days=30, dry_run=True)
    assert preview.counts["planned_set"] == 1
    erased = await corrections.purge(db_session, user_id=user.id, older_than_days=30)
    assert erased.counts["planned_set"] == 1
    assert (
        await db_session.execute(select(PlannedSet).where(PlannedSet.id == line.id))
    ).scalar_one_or_none() is None


# ── The property the whole design exists to hold ─────────────────────────────────────
class TestAPlanIsNotTraining:
    """A prescription must not reach volume, tonnage, frequency or personal records.

    It is held by construction — planned rows live in their own table and no aggregate query
    joins it — which is exactly why it needs a test: nothing in ``services/analytics`` or
    ``services/sets`` mentions planning, so nothing there would fail if the invariant were lost.
    """

    async def test_a_prescription_moves_no_number(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        bench = await make_global_exercise(db_session)
        moment = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
        session = await make_session(db_session, user_id=user.id, performed_at=moment)

        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                plans.PlannedSetDraft(
                    exercise_id=bench.id,
                    set_number=n,
                    target_reps_min=5,
                    target_reps_max=5,
                    target_weight_kg=300,
                )
                for n in (1, 2, 3, 4, 5)
            ],
        )

        volume = await analytics.volume(
            db_session,
            user_id=user.id,
            date_from=moment - timedelta(days=1),
            date_to=moment + timedelta(days=1),
        )
        assert volume == [], "five prescribed sets at 300 kg are not 1500 kg of tonnage"
        assert await prs.list_prs(db_session, user_id=user.id) == []
        assert (await integrity.verify(db_session, user_id=user.id)).ok

    async def test_a_planned_session_is_not_a_session_you_trained(
        self, db_session: AsyncSession
    ) -> None:
        """`frequency` counts sessions, not sets, so this is the one arm of the invariant that a
        separate table does not hold on its own — `plan_session` creates a real session row."""
        user = await make_user(db_session)
        bench = await make_global_exercise(db_session)
        moment = datetime.now(tz=UTC)

        before = await analytics.frequency(db_session, user_id=user.id, weeks=2, now=moment)
        plan = await plans.plan_session(
            db_session,
            user_id=user.id,
            performed_at=moment,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2, 3)],
        )
        after = await analytics.frequency(db_session, user_id=user.id, weeks=2, now=moment)
        assert after == before, "a workout you only planned is not one you did"

        # Doing any of it makes it a session you trained.
        await plans.complete(
            db_session,
            user_id=user.id,
            planned_set_id=plan.items[0].planned.id,
            weight_kg=100,
            reps=5,
        )
        trained = await analytics.frequency(db_session, user_id=user.id, weeks=2, now=moment)
        assert sum(week.count for week in trained) == sum(week.count for week in before) + 1

    async def test_an_ordinary_empty_session_still_counts(self, db_session: AsyncSession) -> None:
        """Planning is not a reason to redefine what "I started a workout" has always meant."""
        user = await make_user(db_session)
        moment = datetime.now(tz=UTC)
        before = await analytics.frequency(db_session, user_id=user.id, weeks=2, now=moment)
        await sessions.create(db_session, user_id=user.id, performed_at=moment)
        after = await analytics.frequency(db_session, user_id=user.id, weeks=2, now=moment)
        assert sum(w.count for w in after) == sum(w.count for w in before) + 1

    async def test_completing_the_plan_is_what_moves_them(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        bench = await make_global_exercise(db_session)
        moment = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
        session = await make_session(db_session, user_id=user.id, performed_at=moment)
        lines = await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                plans.PlannedSetDraft(exercise_id=bench.id, set_number=n, target_weight_kg=100)
                for n in (1, 2)
            ],
        )

        await plans.complete(
            db_session, user_id=user.id, planned_set_id=lines[0].id, weight_kg=100, reps=5
        )

        volume = await analytics.volume(
            db_session,
            user_id=user.id,
            date_from=moment - timedelta(days=1),
            date_to=moment + timedelta(days=1),
        )
        assert len(volume) == 1
        assert volume[0].total_sets == 1, "one completed set, not two prescribed ones"
        assert volume[0].total_tonnage_kg == 500.0
        records = await prs.list_prs(db_session, user_id=user.id)
        assert {row.pr.pr_type: float(row.pr.value) for row in records} == {"weight": 100.0}
        assert (await integrity.verify(db_session, user_id=user.id)).ok


# ── Regressions found by review ──────────────────────────────────────────────────────
class TestClientKeyCannotAdoptTheWrongSet:
    """`sets.log_set` resolves a `client_key` replay on `(user_id, key)` alone and returns before
    it checks the session or exercise it was handed — correctly, since a replay is meant to hand
    back the first call's row. `complete` therefore has to check what it got back."""

    async def test_a_key_from_another_session_is_refused(self, db_session: AsyncSession) -> None:
        user, bench, session = await _fixture(db_session)
        elsewhere = await make_session(db_session, user_id=user.id)
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=elsewhere.id,
            exercise_id=bench.id,
            set_number=1,
            weight_kg=60,
            reps=5,
            client_key="reused",
        )
        line = (
            await plans.add_planned_sets(
                db_session,
                user_id=user.id,
                session_id=session.id,
                drafts=[plans.PlannedSetDraft(exercise_id=bench.id)],
            )
        )[0]

        with pytest.raises(ServiceError) as caught:
            await plans.complete(
                db_session,
                user_id=user.id,
                planned_set_id=line.id,
                weight_kg=100,
                reps=5,
                client_key="reused",
            )
        assert caught.value.kind is ErrorKind.CONFLICT
        assert "client_key" in caught.value.message
        # The line is untouched, so adherence cannot claim a set from another workout.
        report = await plans.progress(db_session, user_id=user.id, session_id=session.id)
        assert report.adherence.completed_count == 0 and report.logged_total == 0

    async def test_a_key_whose_set_was_deleted_is_refused(self, db_session: AsyncSession) -> None:
        user, bench, session = await _fixture(db_session)
        lines = await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
        )
        done = await plans.complete(
            db_session,
            user_id=user.id,
            planned_set_id=lines[0].id,
            weight_kg=100,
            reps=5,
            client_key="set-1",
        )
        await sets.delete_set(db_session, user_id=user.id, set_id=done.logged.set.id)

        with pytest.raises(ServiceError) as caught:
            await plans.complete(
                db_session,
                user_id=user.id,
                planned_set_id=lines[1].id,
                weight_kg=100,
                reps=5,
                client_key="set-1",
            )
        assert caught.value.kind is ErrorKind.CONFLICT
        assert "deleted" in caught.value.message


async def test_a_deleted_line_releases_its_claim_on_a_set(db_session: AsyncSession) -> None:
    """The unique index is partial on *live* rows, so a removed line cannot keep holding a set —
    otherwise the index, not the service, refuses the next completion, and a domain error becomes
    a 500."""
    user, bench, session = await _fixture(db_session)
    lines = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )
    done = await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=lines[0].id,
        weight_kg=100,
        reps=5,
        client_key="the-set",
    )
    await plans.delete_planned_set(db_session, user_id=user.id, planned_set_id=lines[0].id)

    # The same set now satisfies the surviving line — a clean write, not an IntegrityError.
    moved = await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=lines[1].id,
        weight_kg=100,
        reps=5,
        client_key="the-set",
    )
    assert moved.logged.set.id == done.logged.set.id
    report = await plans.progress(db_session, user_id=user.id, session_id=session.id)
    assert (report.adherence.planned_total, report.adherence.completed_count) == (1, 1)


async def test_one_client_key_twice_in_one_batch_is_a_clean_refusal(
    db_session: AsyncSession,
) -> None:
    """Both lookups run before either row is written, so neither finds the other — without this
    check both are created and the partial unique index answers with a 500."""
    user, bench, session = await _fixture(db_session)
    with pytest.raises(ServiceError) as caught:
        await plans.add_planned_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                plans.PlannedSetDraft(exercise_id=bench.id, set_number=1, client_key="dup"),
                plans.PlannedSetDraft(exercise_id=bench.id, set_number=2, client_key="dup"),
            ],
        )
    assert caught.value.kind is ErrorKind.VALIDATION
    assert "planned_sets[1]" in caught.value.message and "planned_sets[0]" in caught.value.message


async def test_a_retry_does_not_restore_a_plan_that_was_edited_away(
    db_session: AsyncSession,
) -> None:
    """A plan whose lines were deleted one by one is a plan someone took apart on purpose."""
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)
    drafts = [plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)]
    first = await plans.plan_session(
        db_session, user_id=user.id, performed_at=_TOMORROW, drafts=drafts, client_key="wed"
    )
    for item in first.items:
        await plans.delete_planned_set(db_session, user_id=user.id, planned_set_id=item.planned.id)

    replayed = await plans.plan_session(
        db_session, user_id=user.id, performed_at=_TOMORROW, drafts=drafts, client_key="wed"
    )
    assert replayed.session.id == first.session.id
    assert replayed.planned_total == 0, "the retry must not rewrite what was deliberately removed"


async def test_a_custom_exercise_with_a_prescription_cannot_be_orphaned(
    db_session: AsyncSession,
) -> None:
    """`planned_sets.exercise_id` has no `ON DELETE`, so an orphan surfaces later as a foreign-key
    violation inside `purge_deleted` rather than as a refusal here."""
    from tests._factories import make_custom_exercise

    user = await make_user(db_session)
    mine = await make_custom_exercise(db_session, user_id=user.id, slug="my-move", name="My Move")
    other = await make_global_exercise(db_session)
    session = await make_session(db_session, user_id=user.id)
    await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=mine.id)],
    )

    with pytest.raises(ServiceError) as caught:
        await exercises.delete_custom(db_session, user_id=user.id, exercise_id=mine.id)
    assert caught.value.kind is ErrorKind.VALIDATION
    assert "1 planned set" in caught.value.message
    assert caught.value.details is not None and caught.value.details["planned_count"] == 1

    # `reassign_to` moves the prescription with the sets, so the plan still says do something.
    result = await exercises.delete_custom(
        db_session, user_id=user.id, exercise_id=mine.id, reassign_to=other.id
    )
    assert result.planned_count == 1
    plan = await plans.get_plan(db_session, user_id=user.id, session_id=session.id)
    assert plan.items[0].planned.exercise_id == other.id


async def test_restoring_a_line_whose_set_was_adopted_reopens_it(
    db_session: AsyncSession,
) -> None:
    """A deleted line releases its set — that is what the partial index means — so the set can be
    completed against another line while it is gone. Restoring it with the claim intact would put
    two live rows in that index and turn the **undo** into a 500."""
    user, bench, session = await _fixture(db_session)
    lines = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )
    await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=lines[0].id,
        weight_kg=100,
        reps=5,
        client_key="the-set",
    )
    await plans.delete_planned_set(db_session, user_id=user.id, planned_set_id=lines[0].id)
    await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=lines[1].id,
        weight_kg=100,
        reps=5,
        client_key="the-set",
    )

    await corrections.restore(
        db_session, user_id=user.id, entity_type="planned_set", entity_id=lines[0].id
    )

    plan = await plans.get_plan(db_session, user_id=user.id, session_id=session.id)
    assert plan.planned_total == 2
    # It comes back outstanding: the set it used to name belongs to the other line now.
    by_id = {item.planned.id: item for item in plan.items}
    assert by_id[lines[0].id].is_completed is False
    assert by_id[lines[0].id].planned.completed_set_id is None
    assert by_id[lines[1].id].is_completed is True
    assert plan.completed_count == 1


async def test_restoring_a_session_reopens_lines_whose_sets_were_adopted(
    db_session: AsyncSession,
) -> None:
    """The same hazard reaches `restore(entity_type="session")`, which un-deletes many at once."""
    user, bench, session = await _fixture(db_session)
    lines = await plans.add_planned_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )
    await plans.complete(
        db_session,
        user_id=user.id,
        planned_set_id=lines[0].id,
        weight_kg=100,
        reps=5,
        client_key="k",
    )
    stamp = datetime.now(tz=UTC)
    await sessions.delete(db_session, user_id=user.id, session_id=session.id, at=stamp)
    # While the session is away, the set is restored on its own and taken by the other line.
    await corrections.restore(
        db_session, user_id=user.id, entity_type="planned_set", entity_id=lines[1].id
    )
    logged = await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bench.id,
        set_number=9,
        weight_kg=90,
        reps=5,
    )
    lines[1].completed_set_id = logged.set.id
    await db_session.flush()

    restored = await corrections.restore(
        db_session, user_id=user.id, entity_type="session", entity_id=session.id
    )
    assert restored.entity_type == "session"
    plan = await plans.get_plan(db_session, user_id=user.id, session_id=session.id)
    assert plan.planned_total == 2


async def test_tidying_away_a_plan_you_never_started_cannot_raise_your_training_count(
    db_session: AsyncSession,
) -> None:
    """Keyed on live lines, deleting the last one would flip the session from 0 to 1 — a
    destructive correction *increasing* the training you are credited with."""
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session)
    moment = datetime.now(tz=UTC)
    plan = await plans.plan_session(
        db_session,
        user_id=user.id,
        performed_at=moment,
        drafts=[plans.PlannedSetDraft(exercise_id=bench.id, set_number=n) for n in (1, 2)],
    )

    def total(weeks: Sequence[analytics.WeekCount]) -> int:
        return sum(week.count for week in weeks)

    assert total(await analytics.frequency(db_session, user_id=user.id, now=moment)) == 0
    for item in plan.items:
        await plans.delete_planned_set(db_session, user_id=user.id, planned_set_id=item.planned.id)
    assert total(await analytics.frequency(db_session, user_id=user.id, now=moment)) == 0


async def test_purge_skips_an_exercise_something_still_points_at(
    db_session: AsyncSession,
) -> None:
    """Each table is filtered by its *own* age, so an exercise deleted 90 days ago and a line
    deleted 5 days ago fall on opposite sides of any cutoff — and neither FK has an `ON DELETE`."""
    from tests._factories import make_custom_exercise

    user = await make_user(db_session)
    mine = await make_custom_exercise(db_session, user_id=user.id, slug="my-move", name="My Move")
    session = await make_session(db_session, user_id=user.id)
    line = await make_planned_set(
        db_session, user_id=user.id, session_id=session.id, exercise_id=mine.id
    )
    now = datetime.now(tz=UTC)
    await plans.delete_planned_set(
        db_session, user_id=user.id, planned_set_id=line.id, at=now - timedelta(days=5)
    )
    await exercises.delete_custom(
        db_session, user_id=user.id, exercise_id=mine.id, at=now - timedelta(days=90)
    )

    # Would have raised a foreign-key violation — a 500 on a purge — before the guard.
    report = await corrections.purge(db_session, user_id=user.id, older_than_days=30, now=now)
    assert report.counts["exercise"] == 0, "still referenced, so it waits"
    assert report.counts["planned_set"] == 0, "the line is only 5 days old"

    # Once the line has aged out too, both go.
    later = now + timedelta(days=40)
    swept = await corrections.purge(db_session, user_id=user.id, older_than_days=30, now=later)
    assert swept.counts["planned_set"] == 1 and swept.counts["exercise"] == 1
