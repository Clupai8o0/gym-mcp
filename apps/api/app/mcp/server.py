"""The Tempo MCP server: a thin Streamable-HTTP surface over ``services/`` (docs/04).

Every tool is a ~10-line adapter — it reads the authenticated ``user_id`` from the request
runtime, opens a DB session, calls **the same service function REST calls**, and returns the
**same Pydantic schema** REST returns (dumped to JSON). That keeps chat and UI in lockstep;
the MCP↔REST contract tests assert there is no drift. No domain logic lives here.

Transport: stateless Streamable-HTTP with JSON responses (``json_response=True``) — the shape
claude.ai speaks and the easiest to reason about server-side. Auth + the ``/mcp`` mount live
in :mod:`app.mcp.asgi`; identity/session plumbing in :mod:`app.mcp.runtime`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

from app.core import errors
from app.core.config import get_settings
from app.mcp import runtime
from app.mcp.guide import GUIDE
from app.mcp.runtime import WRITE_SCOPE
from app.schemas.analytics import FrequencyItem, FrequencyOut, VolumeItem, VolumeOut
from app.schemas.corrections import (
    IntegrityOut,
    PurgeOut,
    RecalculationOut,
    RestoreOut,
)
from app.schemas.exercises import (
    ExerciseDeleteOut,
    ExerciseDetailOut,
    ExerciseListOut,
    ExerciseOut,
)
from app.schemas.prs import PrDeleteOut, PrHistoryItem, PrHistoryOut, PrListOut, PrOut
from app.schemas.sessions import (
    ActiveSessionOut,
    SessionDeleteOut,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionWithSetsOut,
)
from app.schemas.sets import LoggedSetOut, LoggedSetsOut, SetOut
from app.schemas.skills import (
    SkillDetailOut,
    SkillOverviewItem,
    SkillProgressOut,
    SkillsOverviewOut,
)
from app.services import (
    analytics,
    corrections,
    exercises,
    integrity,
    prs,
    sessions,
    sets,
    skills,
)

__all__ = [
    "mcp",
    "ensure_session_manager",
    "reset_session_manager",
    "session_manager_started",
]

_INSTRUCTIONS = (
    "Tempo is a personal workout app (exercise library, logging, progress). These tools read "
    "and update the connected user's own training. Read tempo://guide for conventions: IDs are "
    "UUIDs but `exercise` also accepts a slug or name; weights are kg, holds are seconds."
)


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection for the Streamable-HTTP transport, from settings (docs/04)."""
    settings = get_settings()
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.mcp_dns_rebinding_protection,
        allowed_hosts=settings.mcp_allowed_hosts_list,
        allowed_origins=settings.mcp_allowed_origins_list,
    )


mcp: FastMCP = FastMCP(
    "tempo",
    instructions=_INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security(),
)


# ── Library ──────────────────────────────────────────────────────────────────────────
@mcp.tool()
async def search_exercises(
    query: str | None = None,
    muscle: str | None = None,
    equipment: str | None = None,
    category: str | None = None,
    level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Search the exercise catalog by name/muscle/equipment/category/level."""
    async with runtime.open_session() as db:
        rows, total = await exercises.list_exercises(
            db,
            user_id=runtime.current_user_id(),
            q=query,
            muscle=muscle,
            equipment=equipment,
            category=category,
            level=level,
            limit=limit,
            offset=offset,
        )
    return ExerciseListOut(
        items=[ExerciseOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    ).model_dump(mode="json")


@mcp.tool()
async def get_exercise(exercise: str) -> dict[str, Any]:
    """Get one exercise's full detail (incl. illustration) by UUID, slug, or name."""
    async with runtime.open_session() as db:
        row = await exercises.resolve_ref(db, user_id=runtime.current_user_id(), ref=exercise)
        return ExerciseDetailOut.model_validate(row).model_dump(mode="json")


@mcp.tool()
async def create_custom_exercise(
    name: str,
    category: str | None = None,
    force: str | None = None,
    level: str | None = None,
    mechanic: str | None = None,
    equipment: str | None = None,
    primary_muscles: list[str] | None = None,
    secondary_muscles: list[str] | None = None,
    instructions: list[str] | None = None,
) -> dict[str, Any]:
    """Create a custom exercise owned by the user (needs the write scope)."""
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        row = await exercises.create_custom(
            db,
            user_id=runtime.current_user_id(),
            name=name,
            category=category,
            force=force,
            level=level,
            mechanic=mechanic,
            equipment=equipment,
            primary_muscles=primary_muscles,
            secondary_muscles=secondary_muscles,
            instructions=instructions,
        )
        return ExerciseDetailOut.model_validate(row).model_dump(mode="json")


# ── Logging ──────────────────────────────────────────────────────────────────────────
@mcp.tool()
async def log_session(
    performed_at: datetime,
    title: str | None = None,
    type: str | None = None,
    notes: str | None = None,
    duration_minutes: int | None = None,
    client_key: str | None = None,
) -> dict[str, Any]:
    """Start or record a workout session (needs the write scope).

    Two shapes, and the arguments decide which:

    * **Starting one now** — pass ``performed_at`` as the current time and no duration. It stays
      in progress until ``finish_session``.
    * **Recording one that already happened** — pass its real ``performed_at``, and
      ``duration_minutes`` if you know it. The session is stored already finished, so a workout
      logged for last Tuesday never shows up as "in progress".

    A stated ``duration_minutes`` is kept exactly; ``finish_session`` will not recompute over it.

    ``client_key`` makes the call idempotent: pass any string you can reproduce, and a retry that
    never saw the first response returns the original session instead of creating a duplicate.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        row = await sessions.create(
            db,
            user_id=runtime.current_user_id(),
            performed_at=performed_at,
            title=title,
            type=type,
            notes=notes,
            duration_minutes=duration_minutes,
            client_key=client_key,
        )
        return SessionOut.model_validate(row).model_dump(mode="json")


@mcp.tool()
async def list_sessions(
    type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List the user's workout sessions, newest first, optionally filtered by type/date."""
    async with runtime.open_session() as db:
        rows, total = await sessions.list_sessions(
            db,
            user_id=runtime.current_user_id(),
            type=type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    return SessionListOut(
        items=[SessionOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    ).model_dump(mode="json")


@mcp.tool()
async def update_session(
    session_id: uuid.UUID,
    title: str | None = None,
    type: str | None = None,
    notes: str | None = None,
    performed_at: datetime | None = None,
    duration_minutes: int | None = None,
    ended_at: datetime | None = None,
    clear_notes: bool = False,
) -> dict[str, Any]:
    """Correct a session after the fact (needs the write scope).

    Fix a mistyped duration, move a workout to the day it actually happened, or add a note.
    Only the arguments you pass change: **omitting one leaves it as it is**. To empty the note,
    pass ``clear_notes=true`` — ``null`` already means "leave alone", so removing a value needs
    its own word.

    On a session that has already ended, changing ``performed_at`` or ``duration_minutes`` moves
    its end time to match. Passing ``ended_at`` explicitly overrides that: you are stating the
    end, not asking for one to be derived.

    Moving ``performed_at`` also moves any hand-entered record pinned to this session and
    recomputes the records for every exercise it touched — a session's date is *when its sets
    happened*, so changing it reorders the chronology those records come from.
    """
    runtime.require_scope(WRITE_SCOPE)
    changes: dict[str, Any] = {
        key: value
        for key, value in (
            ("title", title),
            ("type", type),
            ("notes", notes),
            ("performed_at", performed_at),
            ("duration_minutes", duration_minutes),
            ("ended_at", ended_at),
        )
        if value is not None
    }
    if not changes and not clear_notes:
        raise errors.validation(
            "Pass at least one field to change: title, type, notes, performed_at, "
            "duration_minutes, ended_at, or clear_notes"
        )
    async with runtime.open_session() as db:
        row = await sessions.update(
            db,
            user_id=runtime.current_user_id(),
            session_id=session_id,
            changes=changes,
            clear_notes=clear_notes,
        )
        return SessionOut.model_validate(row).model_dump(mode="json")


@mcp.tool()
async def get_active_session() -> dict[str, Any]:
    """The workout currently in progress, or ``{"session": null}`` if the user isn't training.

    ``set_count`` is how many sets have been logged into it so far — enough to answer "how is
    the workout going?" without fetching the whole session.
    """
    async with runtime.open_session() as db:
        active = await sessions.get_active_session(db, user_id=runtime.current_user_id())
        out = (
            ActiveSessionOut(session=None, set_count=0)
            if active is None
            else ActiveSessionOut(
                session=SessionOut.model_validate(active.session), set_count=active.set_count
            )
        )
        return out.model_dump(mode="json")


@mcp.tool()
async def finish_session(session_id: uuid.UUID) -> dict[str, Any]:
    """End a workout, storing its duration (needs the write scope). Safe to call twice."""
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        row = await sessions.finish_session(
            db, user_id=runtime.current_user_id(), session_id=session_id
        )
        return SessionOut.model_validate(row).model_dump(mode="json")


@mcp.tool()
async def get_session(session_id: uuid.UUID) -> dict[str, Any]:
    """Get a session with its sets grouped by exercise."""
    async with runtime.open_session() as db:
        detail = await sessions.get(db, user_id=runtime.current_user_id(), session_id=session_id)
        return SessionDetailOut.from_detail(detail).model_dump(mode="json")


@mcp.tool()
async def get_session_sets(session_id: uuid.UUID) -> dict[str, Any]:
    """List the raw sets of a session, ordered by exercise then set number."""
    async with runtime.open_session() as db:
        rows = await sets.list_session_sets(
            db, user_id=runtime.current_user_id(), session_id=session_id
        )
        return {
            "session_id": str(session_id),
            "items": [SetOut.model_validate(r).model_dump(mode="json") for r in rows],
        }


@mcp.tool()
async def log_set(
    session_id: uuid.UUID,
    exercise: str,
    set_number: int,
    weight_kg: float | None = None,
    reps: int | None = None,
    hold_seconds: int | None = None,
    rpe: float | None = None,
    notes: str | None = None,
    is_backfill: bool = False,
    client_key: str | None = None,
) -> dict[str, Any]:
    """Log a set into a session; auto-detects PRs. ``exercise`` is a UUID, slug, or name.

    Needs the write scope. The result carries a ``pr`` verdict — celebrate personal records.

    Set ``is_backfill=true`` for historical data you are entering after the fact rather than
    something that was measured. It still counts toward volume and frequency, but it is kept out
    of PR detection — a placeholder ``reps=1`` should not become a reps record of 1.

    ``client_key`` makes the call idempotent for a retry. For more than a few sets, prefer
    ``log_sets``: one transaction, no chance of a half-written session.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        row = await exercises.resolve_ref(db, user_id=user_id, ref=exercise)
        logged = await sets.log_set(
            db,
            user_id=user_id,
            session_id=session_id,
            exercise_id=row.id,
            set_number=set_number,
            weight_kg=weight_kg,
            reps=reps,
            hold_seconds=hold_seconds,
            rpe=rpe,
            notes=notes,
            is_backfill=is_backfill,
            client_key=client_key,
        )
        return LoggedSetOut.from_logged(logged).model_dump(mode="json")


@mcp.tool()
async def log_sets(session_id: uuid.UUID, sets_: list[dict[str, Any]]) -> dict[str, Any]:
    """Log many sets into one session in a single transaction (needs the write scope).

    Each element accepts the same fields as ``log_set`` minus ``session_id``: ``exercise``
    (UUID, slug or name), ``set_number``, and any of ``weight_kg``, ``reps``, ``hold_seconds``,
    ``rpe``, ``notes``, ``is_backfill``, ``client_key``.

    **All or nothing.** One bad element aborts the whole call, naming its index, rather than
    leaving a half-written session behind. Prefer this to a loop of ``log_set`` for anything
    bigger than a few sets: 62 separate calls is 62 chances to end up half-applied.

    Returns one result per set, each with its PR verdict, in the order given.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        drafts: list[sets.SetDraft] = []
        for index, raw in enumerate(sets_):
            ref = raw.get("exercise")
            if not ref:
                raise errors.validation(f"sets[{index}]: 'exercise' is required")
            row = await exercises.resolve_ref(db, user_id=user_id, ref=str(ref))
            drafts.append(
                sets.SetDraft(
                    exercise_id=row.id,
                    set_number=int(raw.get("set_number", index + 1)),
                    weight_kg=raw.get("weight_kg"),
                    reps=raw.get("reps"),
                    hold_seconds=raw.get("hold_seconds"),
                    rpe=raw.get("rpe"),
                    notes=raw.get("notes"),
                    is_backfill=bool(raw.get("is_backfill", False)),
                    client_key=raw.get("client_key"),
                )
            )
        logged = await sets.log_sets(db, user_id=user_id, session_id=session_id, drafts=drafts)
        return LoggedSetsOut(items=[LoggedSetOut.from_logged(row) for row in logged]).model_dump(
            mode="json"
        )


@mcp.tool()
async def log_session_with_sets(
    performed_at: datetime,
    sets_: list[dict[str, Any]],
    type: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    duration_minutes: int | None = None,
    client_key: str | None = None,
) -> dict[str, Any]:
    """Record a whole workout — the session and every set — in one transaction.

    Needs the write scope. ``sets_`` takes the same elements as ``log_sets``. The session and all
    its sets commit together or not at all, which is what you want when backfilling training
    history: a session that exists with half its sets is worse than one that never landed.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        session = await sessions.create(
            db,
            user_id=user_id,
            performed_at=performed_at,
            title=title,
            type=type,
            notes=notes,
            duration_minutes=duration_minutes,
            client_key=client_key,
        )
        drafts: list[sets.SetDraft] = []
        for index, raw in enumerate(sets_):
            ref = raw.get("exercise")
            if not ref:
                raise errors.validation(f"sets[{index}]: 'exercise' is required")
            row = await exercises.resolve_ref(db, user_id=user_id, ref=str(ref))
            drafts.append(
                sets.SetDraft(
                    exercise_id=row.id,
                    set_number=int(raw.get("set_number", index + 1)),
                    weight_kg=raw.get("weight_kg"),
                    reps=raw.get("reps"),
                    hold_seconds=raw.get("hold_seconds"),
                    rpe=raw.get("rpe"),
                    notes=raw.get("notes"),
                    is_backfill=bool(raw.get("is_backfill", False)),
                    client_key=raw.get("client_key"),
                )
            )
        logged = await sets.log_sets(db, user_id=user_id, session_id=session.id, drafts=drafts)
        return SessionWithSetsOut(
            session=SessionOut.model_validate(session),
            sets=[LoggedSetOut.from_logged(row) for row in logged],
        ).model_dump(mode="json")


@mcp.tool()
async def update_set(
    set_id: uuid.UUID,
    weight_kg: float | None = None,
    reps: int | None = None,
    rpe: float | None = None,
    hold_seconds: int | None = None,
    set_number: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Correct a logged set (needs the write scope). Only the fields you pass change.

    **Recalculates records for that exercise.** Editing the set that set a PR would otherwise
    leave a record pointing at a value that no longer exists anywhere in the log. The result
    carries the set's PR verdict as it now stands.
    """
    runtime.require_scope(WRITE_SCOPE)
    changes: dict[str, Any] = {
        key: value
        for key, value in (
            ("weight_kg", weight_kg),
            ("reps", reps),
            ("rpe", rpe),
            ("hold_seconds", hold_seconds),
            ("set_number", set_number),
            ("notes", notes),
        )
        if value is not None
    }
    if not changes:
        raise errors.validation(
            "Pass at least one field to change: weight_kg, reps, rpe, hold_seconds, set_number, "
            "notes"
        )
    async with runtime.open_session() as db:
        logged = await sets.update_set(
            db, user_id=runtime.current_user_id(), set_id=set_id, changes=changes
        )
        return LoggedSetOut.from_logged(logged).model_dump(mode="json")


@mcp.tool()
async def delete_set(set_id: uuid.UUID) -> dict[str, Any]:
    """Remove a logged set (needs the write scope), recalculating that exercise's records.

    Soft: the row is kept so ``restore`` can bring it back. If it held a record, the record falls
    back to your next best rather than disappearing.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        removed = await sets.delete_set(db, user_id=runtime.current_user_id(), set_id=set_id)
        return SetOut.model_validate(removed).model_dump(mode="json")


@mcp.tool()
async def delete_session(
    session_id: uuid.UUID, cascade: bool = True, dry_run: bool = False
) -> dict[str, Any]:
    """Remove a workout and, with ``cascade``, its sets (needs the write scope).

    Recalculates records for every exercise the session touched. Without ``cascade`` it refuses
    when sets exist, and says how many — a session and its sets are one workout, and keeping the
    rows while deleting the header would leave sets counting toward records under a workout that
    no longer happened.

    ``dry_run`` reports what would change and changes nothing. Soft, so ``restore`` undoes it.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        result = await sessions.delete(
            db,
            user_id=runtime.current_user_id(),
            session_id=session_id,
            cascade=cascade,
            dry_run=dry_run,
        )
        return SessionDeleteOut(
            session=SessionOut.model_validate(result.session),
            set_count=result.set_count,
            exercises_recalculated=result.exercises_recalculated,
            dry_run=result.dry_run,
        ).model_dump(mode="json")


@mcp.tool()
async def update_custom_exercise(
    exercise: str,
    name: str | None = None,
    category: str | None = None,
    equipment: str | None = None,
    level: str | None = None,
    mechanic: str | None = None,
    force: str | None = None,
    primary_muscles: list[str] | None = None,
    secondary_muscles: list[str] | None = None,
    instructions: list[str] | None = None,
) -> dict[str, Any]:
    """Correct one of the user's own custom exercises (needs the write scope).

    Catalog exercises are shared by every user and are refused with an explanation rather than a
    confusing "not found" — you can see them, you just cannot edit them.

    Renaming regenerates the slug and **keeps the old slug working** as an alias, so a reference
    you stored earlier does not break.
    """
    runtime.require_scope(WRITE_SCOPE)
    changes: dict[str, Any] = {
        key: value
        for key, value in (
            ("name", name),
            ("category", category),
            ("equipment", equipment),
            ("level", level),
            ("mechanic", mechanic),
            ("force", force),
            ("primary_muscles", primary_muscles),
            ("secondary_muscles", secondary_muscles),
            ("instructions", instructions),
        )
        if value is not None
    }
    if not changes:
        raise errors.validation("Pass at least one field to change")
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        row = await exercises.resolve_ref(db, user_id=user_id, ref=exercise)
        updated = await exercises.update_custom(
            db, user_id=user_id, exercise_id=row.id, changes=changes
        )
        return ExerciseDetailOut.model_validate(updated).model_dump(mode="json")


@mcp.tool()
async def delete_custom_exercise(
    exercise: str, reassign_to: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Remove one of the user's own custom exercises (needs the write scope).

    Refuses while sets still reference it — and says how many — unless ``reassign_to`` names the
    exercise those sets should belong to, in which case they are moved first and the records for
    both movements are recalculated. A set with no movement is worse than no deletion: it still
    carries weight and reps into your totals but can no longer say what it was.

    ``dry_run`` reports what would change and changes nothing. Soft, so ``restore`` undoes it.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        row = await exercises.resolve_ref(db, user_id=user_id, ref=exercise)
        target = None
        if reassign_to is not None:
            target = (await exercises.resolve_ref(db, user_id=user_id, ref=reassign_to)).id
        result = await exercises.delete_custom(
            db,
            user_id=user_id,
            exercise_id=row.id,
            reassign_to=target,
            dry_run=dry_run,
        )
        return ExerciseDeleteOut(
            exercise=ExerciseOut.model_validate(result.exercise),
            set_count=result.set_count,
            reassigned_to=(
                ExerciseOut.model_validate(result.reassigned_to) if result.reassigned_to else None
            ),
            dry_run=result.dry_run,
        ).model_dump(mode="json")


# ── Records ──────────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_prs(exercise: str | None = None) -> dict[str, Any]:
    """List the user's personal records, optionally for one exercise (UUID, slug, or name)."""
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        exercise_id = None
        if exercise is not None:
            exercise_id = (await exercises.resolve_ref(db, user_id=user_id, ref=exercise)).id
        rows = await prs.list_prs(db, user_id=user_id, exercise_id=exercise_id)
        return PrListOut(items=[PrOut.from_pair(r) for r in rows]).model_dump(mode="json")


@mcp.tool()
async def log_pr(
    exercise: str,
    pr_type: str,
    value: float,
    achieved_at: datetime,
    session_id: uuid.UUID | None = None,
    notes: str | None = None,
    client_key: str | None = None,
) -> dict[str, Any]:
    """Record a personal record by hand. ``exercise`` is a UUID, slug, or name.

    For records no logged set can express: an **estimated 1RM**, a **hold timed outside a
    session**, or a PR **carried over from another app**. ``pr_type`` is weight|reps|hold_time;
    ``value`` is kg for weight, a count for reps, seconds for hold_time.

    Needs the write scope. A claim has to **beat the record standing at its own moment**, exactly
    as a logged set does — that is what keeps PR history monotonic. Backdating still works: a claim
    dated January is judged against January. To change a record you already have, use
    ``update_pr``; that is a correction, not a new achievement.

    ``client_key`` makes the call idempotent — a retry with the same key returns the original
    record instead of creating a second one.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        row = await exercises.resolve_ref(db, user_id=user_id, ref=exercise)
        record = await prs.log_manual_pr(
            db,
            user_id=user_id,
            exercise_id=row.id,
            pr_type=pr_type,
            value=value,
            achieved_at=achieved_at,
            session_id=session_id,
            notes=notes,
            client_key=client_key,
        )
        return PrOut.from_pair(record).model_dump(mode="json")


@mcp.tool()
async def get_pr_history(exercise: str, pr_type: str) -> dict[str, Any]:
    """Chronology of one exercise + pr_type (weight|reps|hold_time), oldest first.

    Includes both auto-detected records and hand-entered ones, interleaved by date; each item
    carries its ``source``.
    """
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        row = await exercises.resolve_ref(db, user_id=user_id, ref=exercise)
        history = await prs.history(db, user_id=user_id, exercise_id=row.id, pr_type=pr_type)
        return PrHistoryOut(
            exercise_id=row.id,
            pr_type=pr_type,
            items=[PrHistoryItem.from_row(r) for r in history],
        ).model_dump(mode="json")


@mcp.tool()
async def update_pr(
    pr_id: uuid.UUID,
    value: float | None = None,
    achieved_at: datetime | None = None,
    notes: str | None = None,
    clear_notes: bool = False,
) -> dict[str, Any]:
    """Correct a hand-entered personal record in place (needs the write scope).

    Only records you entered by hand can be edited. An auto-detected record is a statement about
    a set that exists — correct the set with ``update_set`` and this follows. Editing it here
    would produce a record the log does not support, and the next recalculation would undo it.

    Returns whatever is standing afterwards, which may be a different record entirely: lowering a
    hand-entered value can hand the record to a logged set.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        record = await prs.update_pr(
            db,
            user_id=runtime.current_user_id(),
            pr_id=pr_id,
            value=value,
            achieved_at=achieved_at,
            notes=notes,
            clear_notes=clear_notes,
        )
        return PrOut.from_pair(record).model_dump(mode="json")


@mcp.tool()
async def delete_pr(pr_id: uuid.UUID) -> dict[str, Any]:
    """Withdraw a hand-entered personal record (needs the write scope).

    The next best value becomes current rather than leaving a gap. Only hand-entered records can
    be withdrawn; an auto-detected one describes a set that exists, so delete the set instead.
    Returns what is standing afterwards, or ``{"standing": null}`` if nothing supports a record.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        standing = await prs.delete_pr(db, user_id=runtime.current_user_id(), pr_id=pr_id)
        return PrDeleteOut(standing=PrOut.from_pair(standing) if standing else None).model_dump(
            mode="json"
        )


@mcp.tool()
async def delete_pr_history_entry(entry_id: uuid.UUID) -> dict[str, Any]:
    """Remove one entry from a record's chronology (needs the write scope).

    The tool for a bogus row — a value that a since-fixed bug wrote and that nothing now
    justifies. Removing it recalculates the record from what is left. Soft, so ``restore`` undoes
    it.

    Only hand-entered rows can be removed this way. An auto row is derived from a logged set, so
    deleting it here would be regenerated by the next recalculation — delete or correct the set,
    or run ``recalculate_prs`` if the row is simply stale.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        entry = await prs.delete_history_entry(
            db, user_id=runtime.current_user_id(), entry_id=entry_id
        )
        return PrHistoryItem.from_row(entry).model_dump(mode="json")


# ── Integrity ────────────────────────────────────────────────────────────────────────
@mcp.tool()
async def recalculate_prs(
    exercise: str | None = None, pr_type: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Rebuild personal records and their chronology from ground truth (needs the write scope).

    Ground truth is every live, non-backfilled set plus every hand-entered claim, replayed in
    order. Each entry counts only if it strictly beats the record standing at its own moment, so
    the chronology comes out monotonically increasing and the last value is the current record.

    Every correction already does this for the exercises it touches. Call it directly to repair
    data that is *already* wrong — a chronology corrupted by a bug that has since been fixed does
    not heal on its own, because nothing recomputes an exercise nobody touches.

    Omit ``exercise`` to rebuild everything. ``dry_run`` reports what would change and changes
    nothing. The result lists the metrics whose stored record actually moved.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        exercise_id = None
        if exercise is not None:
            exercise_id = (await exercises.resolve_ref(db, user_id=user_id, ref=exercise)).id
        report = await integrity.recalculate(
            db, user_id=user_id, exercise_id=exercise_id, pr_type=pr_type, dry_run=dry_run
        )
        return RecalculationOut.from_report(report, dry_run=dry_run).model_dump(mode="json")


@mcp.tool()
async def verify_pr_integrity(exercise: str | None = None) -> dict[str, Any]:
    """Check that the record tables agree with themselves. Read-only — changes nothing.

    Reports any exercise whose chronology steps downward, whose standing record is not the last
    entry in it, or where one exists without the other. ``ok: true`` means every exercise passed.
    Run it after a migration or a bulk correction; ``recalculate_prs`` is the fix.
    """
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        exercise_id = None
        if exercise is not None:
            exercise_id = (await exercises.resolve_ref(db, user_id=user_id, ref=exercise)).id
        report = await integrity.verify(db, user_id=user_id, exercise_id=exercise_id)
        return IntegrityOut.from_report(report).model_dump(mode="json")


@mcp.tool()
async def restore(entity_type: str, entity_id: uuid.UUID) -> dict[str, Any]:
    """Undo a soft delete (needs the write scope).

    ``entity_type`` is one of ``session``, ``set``, ``exercise``, ``pr_history_entry`` — the id
    alone cannot say which table it came from. Restoring a session brings back the sets that were
    deleted *with* it, not ones deleted separately beforehand. Records are recalculated for
    everything affected.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        result = await corrections.restore(
            db,
            user_id=runtime.current_user_id(),
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return RestoreOut.from_result(result).model_dump(mode="json")


@mcp.tool()
async def purge_deleted(older_than_days: int, dry_run: bool = False) -> dict[str, Any]:
    """Permanently erase rows deleted longer ago than ``older_than_days`` (needs the write scope).

    **Irreversible** — this is the only path that actually frees the storage, and after it
    ``restore`` cannot bring anything back. Nothing runs it on a timer. ``older_than_days`` must
    be at least 1; a purge with no window would take back the undo that soft delete exists to
    provide. ``dry_run`` reports the counts and erases nothing.
    """
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        report = await corrections.purge(
            db,
            user_id=runtime.current_user_id(),
            older_than_days=older_than_days,
            dry_run=dry_run,
        )
        return PurgeOut.from_report(report).model_dump(mode="json")


# ── Analytics ────────────────────────────────────────────────────────────────────────
@mcp.tool()
async def get_volume_summary(
    date_from: datetime, date_to: datetime, exercise: str | None = None
) -> dict[str, Any]:
    """Training volume (sets/reps/tonnage) per exercise between two instants (inclusive)."""
    async with runtime.open_session() as db:
        user_id = runtime.current_user_id()
        exercise_id = None
        if exercise is not None:
            exercise_id = (await exercises.resolve_ref(db, user_id=user_id, ref=exercise)).id
        buckets = await analytics.volume(
            db, user_id=user_id, date_from=date_from, date_to=date_to, exercise_id=exercise_id
        )
    return VolumeOut(
        date_from=date_from,
        date_to=date_to,
        items=[VolumeItem.model_validate(b) for b in buckets],
    ).model_dump(mode="json")


@mcp.tool()
async def get_session_frequency(weeks: int = 8) -> dict[str, Any]:
    """Session counts per ISO week for the last ``weeks`` weeks (Monday-anchored)."""
    async with runtime.open_session() as db:
        counts = await analytics.frequency(db, user_id=runtime.current_user_id(), weeks=weeks)
    return FrequencyOut(
        weeks=weeks, items=[FrequencyItem.model_validate(c) for c in counts]
    ).model_dump(mode="json")


# ── Skills (calisthenics tree, secondary module) ─────────────────────────────────────
@mcp.tool()
async def get_skill_overview() -> dict[str, Any]:
    """Every skill with the user's progress (stage 0 / 0% when not started)."""
    async with runtime.open_session() as db:
        pairs = await skills.overview(db, user_id=runtime.current_user_id())
        return SkillsOverviewOut(items=[SkillOverviewItem.from_pair(p) for p in pairs]).model_dump(
            mode="json"
        )


@mcp.tool()
async def get_skill_detail(slug: str) -> dict[str, Any]:
    """One skill's stages + the user's progress, by slug."""
    async with runtime.open_session() as db:
        pair = await skills.detail(db, user_id=runtime.current_user_id(), slug=slug)
        return SkillDetailOut.from_pair(pair).model_dump(mode="json")


@mcp.tool()
async def update_skill_progress(
    slug: str,
    current_stage: int,
    progress_percent: int,
    stage_name: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Set the user's current stage/percent for a skill (needs the write scope)."""
    runtime.require_scope(WRITE_SCOPE)
    async with runtime.open_session() as db:
        progress = await skills.upsert_progress(
            db,
            user_id=runtime.current_user_id(),
            slug=slug,
            current_stage=current_stage,
            progress_percent=progress_percent,
            stage_name=stage_name,
            notes=notes,
        )
        return SkillProgressOut.model_validate(progress).model_dump(mode="json")


# ── Resource ─────────────────────────────────────────────────────────────────────────
@mcp.resource("tempo://guide", mime_type="text/markdown")
def guide() -> str:
    """A concise how-to-use-these-tools reference (kept in sync with the tool set)."""
    return GUIDE


# ── Session-manager lifecycle (used by the mount + tests) ────────────────────────────
def ensure_session_manager() -> StreamableHTTPSessionManager:
    """Return the Streamable-HTTP session manager, creating it on first use.

    ``FastMCP`` builds it lazily inside ``streamable_http_app()``; we only need the manager
    (the mount in :mod:`app.mcp.asgi` calls ``handle_request`` directly), so trigger that
    construction once and hand it back.
    """
    if mcp._session_manager is None:  # noqa: SLF001 — the only supported way to force creation
        mcp.streamable_http_app()
    return mcp.session_manager


def session_manager_started() -> bool:
    """Whether the Streamable-HTTP session manager has been built yet.

    Lets a caller ask "has the MCP runtime been booted?" without importing anything further —
    the lazy transport in :mod:`app.mcp.asgi` is only meaningful if that stays observable.
    """
    return mcp._session_manager is not None  # noqa: SLF001 — no public accessor exists


def reset_session_manager() -> None:
    """Drop the session manager so a fresh one is created (test support only).

    ``StreamableHTTPSessionManager.run()`` may be entered only once per instance; tests run a
    manager per event loop, so they reset between cases.
    """
    mcp._session_manager = None  # noqa: SLF001
