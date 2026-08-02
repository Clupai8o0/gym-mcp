"""Manual PR entry, and how it coexists with auto-detection.

The contract under test (``services/prs`` + ``services/sets._sync_records``):

* a hand-entered record wins immediately — it is the user correcting the log, not a guess;
* auto-detection reclaims the record only by **strictly beating** the stated value;
* every accepted write of either kind lands in ``personal_records_history``, which is what
  ``get_pr_history`` reads. That last point is the regression guard: history used to be derived
  from PR-flagged sets, so a manual record — having no set — could never appear;
* and the **verdict** agrees with both. See ``TestVerdictSeesManualRecords`` — the first shipped
  version guarded the stored record but not the verdict, so a 60kg set logged after a 100kg
  hand-entered PR came back ``is_pr=True, previous_best=None`` and wrote a history row at 60.
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
    """The auto rebuild must not sweep up manual rows on its way through.

    It must also not add a row *below* the manual one. An earlier version of this test asserted
    an 80kg auto entry alongside the 100kg manual — that entry was the bug.
    """
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
    )

    history = await prs.history(
        db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
    )
    assert [(float(r.value), r.source) for r in history] == [(100.0, "manual")]


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


# ── the verdict must see the standing record, not just prior sets ────────────────────────────
class TestVerdictSeesManualRecords:
    """Regression: `log_set`'s PR verdict ignored hand-entered `personal_records` rows.

    `_recompute` derived its running best from the logged sets alone, so with a 100kg manual PR
    standing, a 60kg set reported `is_pr=True, previous_best=None`, stamped `set.is_pr`, and
    inserted a 60kg `auto` history row — while `_sync_records` correctly refused to lower the
    record. The guard worked; the verdict did not.
    """

    async def test_lower_set_is_not_a_pr(self, db_session: AsyncSession) -> None:
        user, exercise, session = await _fixture(db_session)
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
        )

        # Weight only — the repro. Adding reps would make it a genuine *reps* PR (there is no
        # standing reps record), which is correct but a different question; see
        # `test_reps_is_judged_separately`.
        logged = await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=60,
        )

        assert logged.pr.is_pr is False
        assert logged.pr.pr_type is None
        assert logged.pr.previous_best == 100
        # The set itself is not stamped…
        assert logged.set.is_pr is False
        assert logged.set.pr_type is None
        # …and nothing was written to the chronology below the standing record.
        history = await prs.history(
            db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
        )
        assert [(float(r.value), r.source) for r in history] == [(100.0, "manual")]

    async def test_equal_set_is_not_a_pr(self, db_session: AsyncSession) -> None:
        """Ties do not count — a PR has to beat the record, not match it."""
        user, exercise, session = await _fixture(db_session)
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
        )

        logged = await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=100,
        )

        assert logged.pr.is_pr is False
        assert logged.pr.previous_best == 100
        history = await prs.history(
            db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
        )
        assert [float(r.value) for r in history] == [100.0]

    async def test_reps_is_judged_separately(self, db_session: AsyncSession) -> None:
        """The floor is per-metric. A weight record says nothing about your rep count."""
        user, exercise, session = await _fixture(db_session)
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
        )

        logged = await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=60,
            reps=5,
        )

        # Not a weight PR — but five reps is the most reps on record, so it is a reps PR.
        assert logged.pr.is_pr is True
        assert logged.pr.pr_type == "reps"
        assert logged.pr.previous_best is None

        weight_history = await prs.history(
            db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
        )
        assert [float(r.value) for r in weight_history] == [100.0], "no weight row below the floor"

    async def test_higher_set_is_a_pr_and_reports_the_manual_best(
        self, db_session: AsyncSession
    ) -> None:
        user, exercise, session = await _fixture(db_session)
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
        )

        logged = await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=105,
            reps=1,
        )

        assert logged.pr.is_pr is True
        assert logged.pr.pr_type == "weight"
        assert logged.pr.previous_best == 100
        assert logged.pr.new_value == 105

        listed = await prs.list_prs(db_session, user_id=user.id)
        weight = next(row.pr for row in listed if row.pr.pr_type == "weight")
        assert weight.value == 105
        assert weight.source == "auto"

        history = await prs.history(
            db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
        )
        assert [(float(r.value), r.source) for r in history] == [
            (100.0, "manual"),
            (105.0, "auto"),
        ]

    async def test_genuine_first_log_still_reports_no_previous_best(
        self, db_session: AsyncSession
    ) -> None:
        """With nothing standing, the first set *is* a PR and `previous_best` is honestly null."""
        user, exercise, session = await _fixture(db_session)

        logged = await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=60,
            reps=5,
        )

        assert logged.pr.is_pr is True
        assert logged.pr.previous_best is None
        assert logged.set.is_pr is True

    async def test_a_claim_below_the_standing_record_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """`log_pr` states an achievement; it is not how you lower a record.

        This used to be accepted unconditionally — "an explicit correction wins" — and it is what
        made history non-monotonic: 120 then 90 is not a chronology of records. The rule is now
        the same one sets are held to (beat what was standing at your moment), and the error
        points at the tool that *does* correct things.
        """
        user, exercise, session = await _fixture(db_session)
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=120,
            reps=3,
        )

        with pytest.raises(ServiceError) as caught:
            await prs.log_manual_pr(
                db_session,
                user_id=user.id,
                exercise_id=exercise.id,
                pr_type="weight",
                value=90,
                achieved_at=_ACHIEVED,
                notes="the 120 was mis-entered",
            )
        assert caught.value.kind is ErrorKind.VALIDATION
        assert "does not beat" in caught.value.message
        assert "update_pr" in caught.value.message

        # …and the standing record is untouched by the refusal.
        listed = await prs.list_prs(db_session, user_id=user.id)
        weight = next(row.pr for row in listed if row.pr.pr_type == "weight")
        assert weight.value == 120 and weight.source == "auto"

    async def test_a_backdated_claim_is_judged_against_its_own_moment(
        self, db_session: AsyncSession
    ) -> None:
        """Beating "what was standing" means *then*, not now — backfilling history still works."""
        user, exercise, session = await _fixture(db_session)
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=120,
            reps=3,
        )

        # Dated well before the session: at that moment nothing was standing, so it counts —
        # even though it is below today's record.
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=90,
            achieved_at=_ACHIEVED - timedelta(days=30),
        )

        history = await prs.history(
            db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
        )
        assert [(float(r.value), r.source) for r in history] == [(90.0, "manual"), (120.0, "auto")]

    async def test_hold_pr_unaffected_by_a_manual_weight_record(
        self, db_session: AsyncSession
    ) -> None:
        """The floor is per-metric: a weight record says nothing about your first hold."""
        user, exercise, session = await _fixture(db_session)
        await prs.log_manual_pr(
            db_session,
            user_id=user.id,
            exercise_id=exercise.id,
            pr_type="weight",
            value=100,
            achieved_at=_ACHIEVED,
        )

        logged = await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            hold_seconds=45,
        )

        assert logged.pr.is_pr is True
        assert logged.pr.pr_type == "hold_time"
        assert logged.pr.previous_best is None


async def test_history_is_monotonically_increasing(db_session: AsyncSession) -> None:
    """A chronology of *records* only ever goes up. That is the whole invariant.

    The shipped bug broke it directly: a 60kg set after a 100kg manual PR appended a 60 to the
    end. Mixed manual/auto, interleaved by date, across two exercises.
    """
    user = await make_user(db_session)
    squat = await make_global_exercise(db_session, slug="squat", name="Squat")
    bench = await make_global_exercise(db_session, slug="bench", name="Bench")

    await prs.log_manual_pr(
        db_session,
        user_id=user.id,
        exercise_id=squat.id,
        pr_type="weight",
        value=100,
        achieved_at=_ACHIEVED,
    )

    # A run of sets on both exercises, deliberately including regressions and ties.
    for day, (exercise, weight) in enumerate(
        [
            (squat, 60),  # below the manual floor
            (bench, 40),  # first ever bench → a PR
            (squat, 100),  # ties the floor
            (bench, 35),  # a regression
            (squat, 110),  # finally beats it
            (bench, 40),  # ties
            (squat, 105),  # below the new best
            (bench, 55),  # a PR
        ]
    ):
        session = await make_session(
            db_session, user_id=user.id, performed_at=_ACHIEVED + timedelta(days=day + 1)
        )
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            weight_kg=weight,
            reps=3,
        )

    for exercise in (squat, bench):
        history = await prs.history(
            db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
        )
        values = [float(r.value) for r in history]
        assert values == sorted(values), f"{exercise.name} history not ascending: {values}"
        assert len(set(values)) == len(values), f"{exercise.name} history repeats: {values}"

    # And the endpoints agree with the records.
    listed = {row.exercise.slug: row.pr for row in await prs.list_prs(db_session, user_id=user.id)}
    assert listed["squat"].value == 110
    assert listed["bench"].value == 55
