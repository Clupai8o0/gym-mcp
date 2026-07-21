"""SQLAlchemy models — the source of truth for the Neon schema (docs/02-data-model.md).

Importing this package registers every table on ``Base.metadata``, which is what
Alembic's ``env.py`` targets for autogeneration and what the test harness builds.

OAuth tables (``oauth_clients`` and friends) are intentionally deferred to Phase 3's
migration so the data-model phase can complete independently.
"""

from __future__ import annotations

from app.models.base import Base
from app.models.exercise import Exercise
from app.models.exercise_set import ExerciseSet
from app.models.personal_record import PersonalRecord
from app.models.skill import Skill, SkillProgress
from app.models.user import User
from app.models.workout_session import WorkoutSession

__all__ = [
    "Base",
    "Exercise",
    "ExerciseSet",
    "PersonalRecord",
    "Skill",
    "SkillProgress",
    "User",
    "WorkoutSession",
]
