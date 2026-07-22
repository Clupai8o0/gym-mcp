"""Shared schema base + pagination helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for response models read directly off ORM rows / service dataclasses."""

    model_config = ConfigDict(from_attributes=True)


class PageMeta(BaseModel):
    """Pagination echo included on every list response."""

    total: int
    limit: int
    offset: int
