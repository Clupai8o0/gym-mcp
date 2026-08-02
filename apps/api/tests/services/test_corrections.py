"""Correction tooling: update, delete, restore, recalculation, and the integrity invariant.

Tempo was append-only in practice — every write was permanent — and three concrete cases proved
the write path was only half built: a bug wrote ``duration_minutes = 136070`` with no way to
correct it, a bogus 60 kg history row sat under a squat whose real record was 100, and a typo in a
custom exercise's name would have been forever.

The invariant every test here circles is the one :func:`app.services.integrity.verify` checks:
**for every (exercise, metric) the counted chronology strictly increases, and its last value is
the standing record.** A correction that leaves that false has not corrected anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.errors import ErrorKind, ServiceError
from app.models import Exercise, PersonalRecordHistory, User, WorkoutSession
from app.services import corrections, exercises, integrity, prs, sessions, sets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise, make_session, make_user

_DAY = timedelta(days=1)
_BASE = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def _fixture(db: AsyncSession) -> tuple[User, Exercise, WorkoutSession]:
    user = await make_user(db)
    exercise = await make_global_exercise(db, slug="barbell-squat", name="Barbell Squat")
    session = await make_session(db, user_id=user.id, performed_at=_BASE)
    return user, exercise, session


async def _log(
    db: AsyncSession,
    user: User,
    session: WorkoutSession,
    exercise: Exercise,
    *,
    number: int,
    weight: float | None = None,
    reps: int | None = None,
    **kwargs: object,
) -> sets.LoggedSet:
    return await sets.log_set(
        db,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=number,
        weight_kg=weight,
        reps=reps,
        **kwargs,  # type: ignore[arg-type]
    )


async def _weight_history(db: AsyncSession, user: User, exercise: Exercise) -> list[float]:
    rows = await prs.history(db, user_id=user.id, exercise_id=exercise.id, pr_type="weight")
    return [float(row.value) for row in rows]


async def _weight_record(db: AsyncSession, user: User, exercise: Exercise) -> tuple[float, str]:
    listed = await prs.list_prs(db, user_id=user.id, exercise_id=exercise.id)
    record = next(row.pr for row in listed if row.pr.pr_type == "weight")
    return float(record.value), record.source


# ── Deleting the thing a record rests on ──────────────────────────────────────────────
async def test_deleting_the_set_that_set_the_record_falls_back_to_next_best(
    db_session: AsyncSession,
) -> None:
    """The record must not point at a value that no longer exists anywhere in the log."""
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    top = await _log(db_session, user, session, exercise, number=2, weight=120, reps=3)

    assert await _weight_record(db_session, user, exercise) == (120.0, "auto")

    await sets.delete_set(db_session, user_id=user.id, set_id=top.set.id)

    assert await _weight_record(db_session, user, exercise) == (100.0, "auto")
    assert await _weight_history(db_session, user, exercise) == [100.0]
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_deleting_a_manual_pr_that_outranks_every_set_promotes_the_best_set(
    db_session: AsyncSession,
) -> None:
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    record = await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=140,
        achieved_at=_BASE + _DAY,
        notes="estimated 1RM",
    )
    assert await _weight_record(db_session, user, exercise) == (140.0, "manual")

    standing = await prs.delete_pr(db_session, user_id=user.id, pr_id=record.pr.id)

    assert standing is not None and float(standing.pr.value) == 100.0
    assert await _weight_record(db_session, user, exercise) == (100.0, "auto")
    assert await _weight_history(db_session, user, exercise) == [100.0]
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_deleting_the_only_record_leaves_no_gap_and_no_ghost(
    db_session: AsyncSession,
) -> None:
    """With nothing left to support it, the record goes — rather than lingering unsupported."""
    user, exercise, _session = await _fixture(db_session)
    record = await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=140,
        achieved_at=_BASE,
    )

    assert await prs.delete_pr(db_session, user_id=user.id, pr_id=record.pr.id) is None
    assert await prs.list_prs(db_session, user_id=user.id, exercise_id=exercise.id) == []
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_an_auto_record_refuses_to_be_deleted_and_says_what_to_do(
    db_session: AsyncSession,
) -> None:
    """Deleting derived state directly is a no-op the next recalculation would undo."""
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    listed = await prs.list_prs(db_session, user_id=user.id, exercise_id=exercise.id)
    record = next(row.pr for row in listed if row.pr.pr_type == "weight")

    with pytest.raises(ServiceError) as caught:
        await prs.delete_pr(db_session, user_id=user.id, pr_id=record.id)
    assert caught.value.kind is ErrorKind.VALIDATION
    assert "delete_set" in caught.value.message


# ── Editing ───────────────────────────────────────────────────────────────────────────
async def test_editing_a_set_downward_recalculates_and_history_stays_monotonic(
    db_session: AsyncSession,
) -> None:
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    top = await _log(db_session, user, session, exercise, number=2, weight=120, reps=3)
    assert await _weight_history(db_session, user, exercise) == [100.0, 120.0]

    await sets.update_set(db_session, user_id=user.id, set_id=top.set.id, changes={"weight_kg": 90})

    # 90 no longer beats 100, so it is not a record and leaves the chronology entirely.
    assert await _weight_history(db_session, user, exercise) == [100.0]
    assert await _weight_record(db_session, user, exercise) == (100.0, "auto")
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_update_pr_corrects_a_hand_entered_record_in_place(
    db_session: AsyncSession,
) -> None:
    user, exercise, _session = await _fixture(db_session)
    record = await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=140,
        achieved_at=_BASE,
        notes="typo",
    )

    corrected = await prs.update_pr(
        db_session, user_id=user.id, pr_id=record.pr.id, value=145, clear_notes=True
    )

    assert float(corrected.pr.value) == 145.0 and corrected.pr.source == "manual"
    assert corrected.pr.notes is None
    assert await _weight_history(db_session, user, exercise) == [145.0]
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_update_pr_refuses_an_auto_record(db_session: AsyncSession) -> None:
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    listed = await prs.list_prs(db_session, user_id=user.id, exercise_id=exercise.id)
    record = next(row.pr for row in listed if row.pr.pr_type == "weight")

    with pytest.raises(ServiceError) as caught:
        await prs.update_pr(db_session, user_id=user.id, pr_id=record.id, value=200)
    assert "update_set" in caught.value.message


# ── Sessions ──────────────────────────────────────────────────────────────────────────
async def test_delete_session_cascade_recalculates_every_exercise_it_touched(
    db_session: AsyncSession,
) -> None:
    user, squat, session = await _fixture(db_session)
    bench = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")

    earlier = await make_session(db_session, user_id=user.id, performed_at=_BASE - _DAY)
    await _log(db_session, user, earlier, squat, number=1, weight=100, reps=5)

    await _log(db_session, user, session, squat, number=1, weight=140, reps=3)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bench.id,
        set_number=1,
        weight_kg=80,
        reps=5,
    )
    assert await _weight_record(db_session, user, squat) == (140.0, "auto")

    result = await sessions.delete(db_session, user_id=user.id, session_id=session.id)
    assert result.set_count == 2 and result.exercises_recalculated == 2

    # The squat falls back to the earlier session; the bench loses its only record entirely.
    assert await _weight_record(db_session, user, squat) == (100.0, "auto")
    assert await prs.list_prs(db_session, user_id=user.id, exercise_id=bench.id) == []
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_correcting_a_sessions_date_moves_its_manual_record_with_it(
    db_session: AsyncSession,
) -> None:
    """A record pinned to a session must not claim a day the workout no longer happened on."""
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    record = await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=140,
        achieved_at=_BASE,
        session_id=session.id,
    )
    assert record.pr.achieved_at == _BASE

    moved = _BASE - 7 * _DAY
    await sessions.update(
        db_session,
        user_id=user.id,
        session_id=session.id,
        changes={"performed_at": moved},
    )

    entry = (
        await db_session.execute(
            select(PersonalRecordHistory).where(
                PersonalRecordHistory.user_id == user.id,
                PersonalRecordHistory.source == "manual",
            )
        )
    ).scalar_one()
    assert entry.achieved_at == moved
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_restore_brings_back_a_session_and_the_sets_deleted_with_it(
    db_session: AsyncSession,
) -> None:
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    await sessions.delete(db_session, user_id=user.id, session_id=session.id)
    assert await prs.list_prs(db_session, user_id=user.id, exercise_id=exercise.id) == []

    await corrections.restore(
        db_session, user_id=user.id, entity_type="session", entity_id=session.id
    )

    detail = await sessions.get(db_session, user_id=user.id, session_id=session.id)
    assert len(detail.sets) == 1
    assert await _weight_record(db_session, user, exercise) == (100.0, "auto")
    assert (await integrity.verify(db_session, user_id=user.id)).ok


# ── Custom exercises ──────────────────────────────────────────────────────────────────
async def test_delete_custom_exercise_with_sets_is_refused_with_the_count(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    custom = await exercises.create_custom(db_session, user_id=user.id, name="Ring Dip")
    session = await make_session(db_session, user_id=user.id, performed_at=_BASE)
    for number in (1, 2, 3):
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=custom.id,
            set_number=number,
            reps=8,
        )

    with pytest.raises(ServiceError) as caught:
        await exercises.delete_custom(db_session, user_id=user.id, exercise_id=custom.id)
    assert "3 logged sets" in caught.value.message
    assert caught.value.details is not None and caught.value.details["set_count"] == 3


async def test_delete_custom_exercise_with_reassign_moves_the_sets_and_recalculates(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    typo = await exercises.create_custom(db_session, user_id=user.id, name="Rign Dip")
    correct = await exercises.create_custom(db_session, user_id=user.id, name="Ring Dip")
    session = await make_session(db_session, user_id=user.id, performed_at=_BASE)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=typo.id,
        set_number=1,
        weight_kg=20,
        reps=8,
    )

    result = await exercises.delete_custom(
        db_session, user_id=user.id, exercise_id=typo.id, reassign_to=correct.id
    )
    assert result.set_count == 1 and result.reassigned_to is not None

    # The record left one chronology and joined the other; neither is left holding a ghost.
    assert await prs.list_prs(db_session, user_id=user.id, exercise_id=typo.id) == []
    moved = await prs.list_prs(db_session, user_id=user.id, exercise_id=correct.id)
    assert {row.pr.pr_type for row in moved} == {"weight"}
    with pytest.raises(ServiceError):
        await exercises.get(db_session, user_id=user.id, exercise_id=typo.id)
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_a_catalog_exercise_cannot_be_edited_or_deleted(
    db_session: AsyncSession,
) -> None:
    """Shared reference data is not one user's to change — and the error says so."""
    user, exercise, _session = await _fixture(db_session)

    for call in (
        exercises.update_custom(
            db_session, user_id=user.id, exercise_id=exercise.id, changes={"name": "Mine"}
        ),
        exercises.delete_custom(db_session, user_id=user.id, exercise_id=exercise.id),
    ):
        with pytest.raises(ServiceError) as caught:
            await call
        assert caught.value.kind is ErrorKind.VALIDATION
        assert "catalog exercise" in caught.value.message


async def test_renaming_a_custom_exercise_keeps_the_old_slug_resolvable(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    custom = await exercises.create_custom(db_session, user_id=user.id, name="Rign Dip")
    assert custom.slug == "rign-dip"

    renamed = await exercises.update_custom(
        db_session, user_id=user.id, exercise_id=custom.id, changes={"name": "Ring Dip"}
    )
    assert renamed.slug == "ring-dip"

    by_new = await exercises.resolve_ref(db_session, user_id=user.id, ref="ring-dip")
    by_old = await exercises.resolve_ref(db_session, user_id=user.id, ref="rign-dip")
    assert by_new.id == custom.id and by_old.id == custom.id


# ── Idempotency ───────────────────────────────────────────────────────────────────────
async def test_the_same_client_key_twice_creates_one_session(db_session: AsyncSession) -> None:
    """The failure this exists for: a retry left two identical sessions dated 1 May."""
    user = await make_user(db_session)

    first = await sessions.create(
        db_session, user_id=user.id, performed_at=_BASE, title="Upper", client_key="import-1"
    )
    second = await sessions.create(
        db_session, user_id=user.id, performed_at=_BASE, title="Upper", client_key="import-1"
    )

    assert first.id == second.id
    _rows, total = await sessions.list_sessions(db_session, user_id=user.id)
    assert total == 1


async def test_the_same_client_key_twice_creates_one_set(db_session: AsyncSession) -> None:
    user, exercise, session = await _fixture(db_session)

    first = await _log(
        db_session, user, session, exercise, number=1, weight=100, reps=5, client_key="s1"
    )
    second = await _log(
        db_session, user, session, exercise, number=1, weight=100, reps=5, client_key="s1"
    )

    assert first.set.id == second.set.id
    assert (
        len(await sets.list_session_sets(db_session, user_id=user.id, session_id=session.id)) == 1
    )


async def test_the_same_client_key_twice_creates_one_pr(db_session: AsyncSession) -> None:
    user, exercise, _session = await _fixture(db_session)
    kwargs = dict(
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=140,
        achieved_at=_BASE,
        client_key="pr-1",
    )

    first = await prs.log_manual_pr(db_session, **kwargs)  # type: ignore[arg-type]
    second = await prs.log_manual_pr(db_session, **kwargs)  # type: ignore[arg-type]

    assert first.pr.id == second.pr.id
    assert await _weight_history(db_session, user, exercise) == [140.0]


# ── Bulk ──────────────────────────────────────────────────────────────────────────────
async def test_log_sets_is_transactional_and_returns_a_verdict_per_set(
    db_session: AsyncSession,
) -> None:
    user, exercise, session = await _fixture(db_session)

    logged = await sets.log_sets(
        db_session,
        user_id=user.id,
        session_id=session.id,
        drafts=[
            sets.SetDraft(exercise_id=exercise.id, set_number=n, weight_kg=90 + n * 10, reps=5)
            for n in (1, 2, 3)
        ],
    )

    assert [row.pr.is_pr for row in logged] == [True, True, True]
    assert await _weight_history(db_session, user, exercise) == [100.0, 110.0, 120.0]
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_a_bad_element_aborts_the_whole_batch_and_names_its_index(
    db_session: AsyncSession,
) -> None:
    user, exercise, session = await _fixture(db_session)

    with pytest.raises(ServiceError) as caught:
        await sets.log_sets(
            db_session,
            user_id=user.id,
            session_id=session.id,
            drafts=[
                sets.SetDraft(exercise_id=exercise.id, set_number=1, weight_kg=100, reps=5),
                sets.SetDraft(exercise_id=exercise.id, set_number=2),  # no measurement
            ],
        )
    assert "sets[1]" in caught.value.message


# ── The two reported detection bugs ───────────────────────────────────────────────────
async def test_a_zero_weight_set_is_not_a_weight_pr(db_session: AsyncSession) -> None:
    """Bodyweight and assisted work are logged at 0 kg. That is not a record of 0.0."""
    user, exercise, session = await _fixture(db_session)

    logged = await _log(db_session, user, session, exercise, number=1, weight=0, reps=10)

    assert logged.pr.pr_type != "weight"
    records = {row.pr.pr_type for row in await prs.list_prs(db_session, user_id=user.id)}
    assert "weight" not in records, "0 kg is 'no load', not a load of zero"
    assert "reps" in records, "…and the exercise still progresses on reps"


async def test_a_backfilled_set_does_not_fire_pr_detection(db_session: AsyncSession) -> None:
    """A placeholder `reps=1` in imported history used to register as a reps PR of 1."""
    user, exercise, session = await _fixture(db_session)

    logged = await _log(db_session, user, session, exercise, number=1, reps=1, is_backfill=True)

    assert logged.pr.is_pr is False
    assert await prs.list_prs(db_session, user_id=user.id, exercise_id=exercise.id) == []

    # …but it is still training that happened, so a real set after it is judged from scratch.
    real = await _log(db_session, user, session, exercise, number=2, reps=8)
    assert real.pr.is_pr is True


# ── Repair ────────────────────────────────────────────────────────────────────────────
async def test_recalculate_repairs_a_chronology_corrupted_by_a_past_bug(
    db_session: AsyncSession,
) -> None:
    """The reported case: a bogus 60 kg row under barbell-squat, real record 100 kg manual.

    Written straight into the tables, the way the since-fixed bug left it — so this proves the
    repair path works on data that is *already* wrong, not just that new writes are correct.
    """
    user, exercise, session = await _fixture(db_session)
    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        pr_type="weight",
        value=100,
        achieved_at=_BASE,
    )
    below = await _log(db_session, user, session, exercise, number=1, weight=60, reps=5)

    # Forge the corruption the old code produced: a 60 kg "record" below the standing 100.
    db_session.add(
        PersonalRecordHistory(
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=60,
            unit="kg",
            achieved_at=_BASE + timedelta(minutes=1),
            source="auto",
            set_id=below.set.id,
            session_id=session.id,
        )
    )
    await db_session.flush()

    broken = await integrity.verify(db_session, user_id=user.id)
    assert not broken.ok
    assert any(p.kind == "non_monotonic_history" for p in broken.problems)

    report = await integrity.recalculate(db_session, user_id=user.id)

    assert report.exercises >= 1
    assert await _weight_history(db_session, user, exercise) == [100.0]
    assert await _weight_record(db_session, user, exercise) == (100.0, "manual")
    assert (await integrity.verify(db_session, user_id=user.id)).ok


async def test_verify_passes_across_a_whole_mixed_dataset(db_session: AsyncSession) -> None:
    """The post-migration assertion: every exercise, both sources, after a run of corrections."""
    user, squat, session = await _fixture(db_session)
    bench = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    later = await make_session(db_session, user_id=user.id, performed_at=_BASE + _DAY)

    await _log(db_session, user, session, squat, number=1, weight=100, reps=5)
    await _log(db_session, user, session, squat, number=2, weight=110, reps=3)
    await _log(db_session, user, later, squat, number=1, weight=120, reps=1)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=later.id,
        exercise_id=bench.id,
        set_number=1,
        weight_kg=80,
        reps=5,
        hold_seconds=None,
    )
    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=squat.id,
        pr_type="weight",
        value=150,
        achieved_at=_BASE + 2 * _DAY,
    )

    # …then churn it: edit, delete, restore.
    top = (await sets.list_session_sets(db_session, user_id=user.id, session_id=later.id))[0]
    await sets.update_set(db_session, user_id=user.id, set_id=top.id, changes={"weight_kg": 115})
    await sessions.delete(db_session, user_id=user.id, session_id=session.id)
    await corrections.restore(
        db_session, user_id=user.id, entity_type="session", entity_id=session.id
    )

    report = await integrity.verify(db_session, user_id=user.id)
    assert report.ok, [f"{p.exercise_name}/{p.pr_type}: {p.detail}" for p in report.problems]
    assert report.checked_exercises == 2


async def test_recalculate_dry_run_reports_without_writing(db_session: AsyncSession) -> None:
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)

    before = await _weight_record(db_session, user, exercise)
    report = await integrity.recalculate(db_session, user_id=user.id, dry_run=True)

    assert report.exercises == 1
    assert await _weight_record(db_session, user, exercise) == before


# ── Purge ─────────────────────────────────────────────────────────────────────────────
async def test_purge_refuses_a_zero_day_window(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as caught:
        await corrections.purge(db_session, user_id=user.id, older_than_days=0)
    assert "older_than_days" in caught.value.message


async def test_purge_erases_only_what_is_old_enough(db_session: AsyncSession) -> None:
    user, exercise, session = await _fixture(db_session)
    await _log(db_session, user, session, exercise, number=1, weight=100, reps=5)
    now = datetime.now(tz=UTC)
    await sessions.delete(db_session, user_id=user.id, session_id=session.id, at=now - 40 * _DAY)

    preview = await corrections.purge(
        db_session, user_id=user.id, older_than_days=30, dry_run=True, now=now
    )
    assert preview.total == 2 and preview.dry_run is True
    assert (
        await db_session.execute(select(WorkoutSession).where(WorkoutSession.id == session.id))
    ).scalar_one_or_none() is not None

    # Too recent for a 60-day window: nothing goes.
    untouched = await corrections.purge(db_session, user_id=user.id, older_than_days=60, now=now)
    assert untouched.total == 0

    erased = await corrections.purge(db_session, user_id=user.id, older_than_days=30, now=now)
    assert erased.total == 2
    assert (
        await db_session.execute(select(WorkoutSession).where(WorkoutSession.id == session.id))
    ).scalar_one_or_none() is None
