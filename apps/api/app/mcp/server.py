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
from app.schemas.exercises import ExerciseDetailOut, ExerciseListOut, ExerciseOut
from app.schemas.prs import PrHistoryItem, PrHistoryOut, PrListOut, PrOut
from app.schemas.sessions import ActiveSessionOut, SessionDetailOut, SessionListOut, SessionOut
from app.schemas.sets import LoggedSetOut, SetOut
from app.schemas.skills import (
    SkillDetailOut,
    SkillOverviewItem,
    SkillProgressOut,
    SkillsOverviewOut,
)
from app.services import analytics, exercises, prs, sessions, sets, skills

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
) -> dict[str, Any]:
    """Start or record a workout session (needs the write scope).

    Two shapes, and the arguments decide which:

    * **Starting one now** — pass ``performed_at`` as the current time and no duration. It stays
      in progress until ``finish_session``.
    * **Recording one that already happened** — pass its real ``performed_at``, and
      ``duration_minutes`` if you know it. The session is stored already finished, so a workout
      logged for last Tuesday never shows up as "in progress".

    A stated ``duration_minutes`` is kept exactly; ``finish_session`` will not recompute over it.
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
) -> dict[str, Any]:
    """Correct a session after the fact (needs the write scope).

    Fix a mistyped duration, move a workout to the day it actually happened, or add a note.
    Only the arguments you pass change; **omitting one leaves it as it is**, so this cannot be
    used to clear a field back to empty — pass an empty string for ``title``/``type``/``notes``
    if that is what you want.

    On a session that has already ended, changing ``performed_at`` or ``duration_minutes`` moves
    its end time to match, so the record stays consistent.
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
        )
        if value is not None
    }
    if not changes:
        raise errors.validation(
            "Pass at least one field to change: title, type, notes, performed_at, duration_minutes"
        )
    async with runtime.open_session() as db:
        row = await sessions.update(
            db, user_id=runtime.current_user_id(), session_id=session_id, changes=changes
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
) -> dict[str, Any]:
    """Log a set into a session; auto-detects PRs. ``exercise`` is a UUID, slug, or name.

    Needs the write scope. The result carries a ``pr`` verdict — celebrate personal records.
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
        )
        return LoggedSetOut.from_logged(logged).model_dump(mode="json")


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
) -> dict[str, Any]:
    """Record a personal record by hand. ``exercise`` is a UUID, slug, or name.

    For records no logged set can express: an **estimated 1RM**, a **hold timed outside a
    session**, or a PR **carried over from another app**. ``pr_type`` is weight|reps|hold_time;
    ``value`` is kg for weight, a count for reps, seconds for hold_time.

    Needs the write scope. This overwrites whatever is currently stored for the exercise + metric
    — it is treated as the user correcting the record, so it wins on the spot. Auto-detection will
    only replace it later if a logged set strictly beats it.
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
