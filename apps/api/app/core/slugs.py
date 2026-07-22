"""URL-safe slug generation (shared by services that mint slugs, e.g. custom exercises)."""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, collapse non-alphanumerics to single hyphens, and trim.

    ``"Barbell Bench Press"`` → ``"barbell-bench-press"``. Returns ``""`` for input
    with no alphanumeric characters (callers validate/raise on empty).
    """
    return _NON_ALNUM.sub("-", value.strip().lower()).strip("-")
