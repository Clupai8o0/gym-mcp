"""The LOCKED illustration prompt (docs/06 — "Illustration style (LOCKED SPEC)"). Pure; no I/O.

Every catalog image must read as one set: minimal single-weight line art, off-white lines on a
fully transparent background, a faceless neutral mannequin, square with generous margins. Only
the **pose** varies per image — the style clauses are identical everywhere, which is exactly
what keeps ~800 generated images visually consistent.

:data:`STYLE_VERSION` stamps every image's provenance; bump it if the locked style changes so a
future batch can detect and regenerate stale art.
"""

from __future__ import annotations

import hashlib

STYLE_VERSION = "1"

# The locked style is **pure monochrome** (no accent). The template still supports a single,
# identical accent color if the style is ever re-locked to use one (docs/06) — but the batch
# passes ``accent=None`` so all images match.
LOCKED_ACCENT: str | None = None

_TEMPLATE = (
    'Minimal single-weight line-art illustration of a person performing "{name}". '
    "{equipment_clause}Show the movement at its most recognizable position, emphasizing the "
    "{muscles} working. Clean continuous linework, off-white lines, fully transparent "
    "background, no shading, no color fills{accent_clause}, faceless neutral mannequin, "
    "centered, generous margins, square composition. Instructional, iconographic, consistent "
    "proportions. No text, no logos, no background scenery."
)

# Dataset ``equipment`` values that mean "no implement" (body-weight movement).
_BODYWEIGHT = frozenset({"body only", "none", ""})


def build_prompt(
    *,
    name: str,
    equipment: str | None = None,
    primary_muscles: list[str] | None = None,
    accent: str | None = LOCKED_ACCENT,
) -> str:
    """Render the locked template for one exercise. Deterministic (same inputs → same string)."""
    if equipment and equipment.strip().lower() not in _BODYWEIGHT:
        equipment_clause = f"Using a {equipment.strip()}. "
    else:
        equipment_clause = ""
    muscles = ", ".join(m for m in (primary_muscles or []) if m) or "primary"
    accent_clause = f", except a single {accent} accent on the primary muscle" if accent else ""
    return _TEMPLATE.format(
        name=name,
        equipment_clause=equipment_clause,
        muscles=muscles,
        accent_clause=accent_clause,
    )


def prompt_hash(prompt: str) -> str:
    """Stable SHA-256 of the prompt — stored in provenance for reproducibility (docs/06)."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
