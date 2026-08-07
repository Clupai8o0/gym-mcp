"""SQLAlchemy models — the source of truth for the Neon schema (docs/02-data-model.md).

Importing this package registers every table on ``Base.metadata``, which is what
Alembic's ``env.py`` targets for autogeneration and what the test harness builds.

OAuth tables (``oauth_clients`` and friends) were deferred out of the Phase 1 baseline so
the data-model phase could complete independently; they are added by Phase 3 (docs/05).
"""

from __future__ import annotations

from app.models.base import Base
from app.models.exercise import Exercise, ExerciseSlugAlias
from app.models.exercise_set import ExerciseSet
from app.models.oauth import (
    OAuthAccessToken,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthRefreshToken,
)
from app.models.personal_record import (
    PR_SOURCES,
    PR_TYPES,
    PR_UNITS,
    PersonalRecord,
    PersonalRecordHistory,
)
from app.models.planned_set import PlannedSet
from app.models.skill import Skill, SkillProgress
from app.models.user import User
from app.models.workout_session import WorkoutSession

__all__ = [
    "Base",
    "Exercise",
    "ExerciseSet",
    "ExerciseSlugAlias",
    "OAuthAccessToken",
    "OAuthAuthorizationCode",
    "OAuthClient",
    "OAuthRefreshToken",
    "PR_SOURCES",
    "PR_TYPES",
    "PR_UNITS",
    "PersonalRecord",
    "PersonalRecordHistory",
    "PlannedSet",
    "Skill",
    "SkillProgress",
    "User",
    "WorkoutSession",
]
