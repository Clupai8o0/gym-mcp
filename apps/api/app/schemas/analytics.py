"""Analytics response schemas (volume by exercise, frequency by week)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from app.schemas.common import ORMModel


class VolumeItem(ORMModel):
    exercise_id: uuid.UUID
    exercise_name: str
    total_sets: int
    total_reps: int
    total_tonnage_kg: float | None


class VolumeOut(ORMModel):
    date_from: datetime
    date_to: datetime
    items: list[VolumeItem]


class FrequencyItem(ORMModel):
    week_start: date
    count: int


class FrequencyOut(ORMModel):
    weeks: int
    items: list[FrequencyItem]
