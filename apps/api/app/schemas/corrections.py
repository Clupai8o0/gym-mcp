"""Schemas for the repair surface: recalculation, integrity checks, restore and purge.

Shared verbatim by the REST routers and the MCP tools, so a chat client and the web app can never
be told a different story about what a correction did.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.services.corrections import PurgeReport, Restored
    from app.services.integrity import IntegrityReport, RecalculationReport


class MetricResultOut(BaseModel):
    """What a rebuild produced for one (exercise, metric)."""

    exercise_id: uuid.UUID
    exercise_name: str
    pr_type: str
    value: float | None
    source: str | None
    entries: int
    changed: bool


class RecalculationOut(BaseModel):
    exercises: int
    #: Only the metrics whose stored record actually moved — the interesting half of the report.
    changed: list[MetricResultOut]
    metrics: list[MetricResultOut]
    dry_run: bool = False

    @classmethod
    def from_report(cls, report: RecalculationReport, *, dry_run: bool = False) -> RecalculationOut:
        metrics = [
            MetricResultOut(
                exercise_id=m.exercise_id,
                exercise_name=m.exercise_name,
                pr_type=m.pr_type,
                value=float(m.value) if m.value is not None else None,
                source=m.source,
                entries=m.entries,
                changed=m.changed,
            )
            for m in report.metrics
        ]
        return cls(
            exercises=report.exercises,
            changed=[m for m in metrics if m.changed],
            metrics=metrics,
            dry_run=dry_run,
        )


class IntegrityProblemOut(BaseModel):
    exercise_id: uuid.UUID
    exercise_name: str
    pr_type: str
    kind: str
    detail: str


class IntegrityOut(BaseModel):
    ok: bool
    checked_exercises: int
    problems: list[IntegrityProblemOut]

    @classmethod
    def from_report(cls, report: IntegrityReport) -> IntegrityOut:
        return cls(
            ok=report.ok,
            checked_exercises=report.checked_exercises,
            problems=[
                IntegrityProblemOut(
                    exercise_id=p.exercise_id,
                    exercise_name=p.exercise_name,
                    pr_type=p.pr_type,
                    kind=p.kind,
                    detail=p.detail,
                )
                for p in report.problems
            ],
        )


class RestoreIn(BaseModel):
    entity_type: str
    entity_id: uuid.UUID


class RestoreOut(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    exercises_recalculated: int

    @classmethod
    def from_result(cls, result: Restored) -> RestoreOut:
        return cls(
            entity_type=result.entity_type,
            entity_id=result.entity_id,
            exercises_recalculated=result.exercises_recalculated,
        )


class PurgeIn(BaseModel):
    #: At least 1: a purge with no window would take back the undo soft delete exists to provide.
    older_than_days: int = Field(ge=1)
    dry_run: bool = False


class PurgeOut(BaseModel):
    older_than_days: int
    total: int
    counts: dict[str, int]
    dry_run: bool

    @classmethod
    def from_report(cls, report: PurgeReport) -> PurgeOut:
        return cls(
            older_than_days=report.older_than_days,
            total=report.total,
            counts=report.counts,
            dry_run=report.dry_run,
        )
