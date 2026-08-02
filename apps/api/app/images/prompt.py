"""The LOCKED illustration prompt (docs/06 — "Illustration style (LOCKED SPEC)"). Pure; no I/O.

Every catalog image must read as one set: **bold** graphic line art — thick, uniform off-white
strokes and strongly simplified anatomy — with a single amber fill on the primary working muscle,
on a fully transparent background, faceless mannequin, square with generous margins. Only the
**pose** and the accented muscle vary per image; the style clauses are identical everywhere,
which is what keeps ~800 generated images visually consistent.

Two properties of this style were chosen against rendered evidence, not taste:

* **Bold, not thin.** Catalog art renders at ≤240px on cards (see ``apps/web/next.config.ts``).
  Single-weight hairlines survive a 1024px exemplar and then dissolve at card size; heavy uniform
  strokes stay legible down to ~64px.
* **One amber accent.** It marks the muscle the movement trains, so the illustration carries
  information at a glance rather than decoration — and it survives downscaling when fine
  interior linework does not.

**Transparency is produced in two steps, not one.** GPT Image 2 rejects
``background: "transparent"`` (it accepts only ``opaque``/``auto``), so the prompt asks for a flat
:data:`KEY_COLOR_NAME` field, and ``chroma.key_out_background`` removes it afterwards. The key
color is chosen to sit far from :data:`ACCENT_COLOR_HEX` in hue so the keying pass can separate
ground from accent — see ``chroma.py``.

:data:`STYLE_VERSION` stamps every image's provenance; bump it if the locked style changes so a
future batch can detect and regenerate stale art.
"""

from __future__ import annotations

import hashlib

# 1 → 2: background clause moved from "fully transparent" to the chroma key field.
# 2 → 3: style re-locked to bold strokes + the amber working-muscle accent (docs/06 sign-off).
STYLE_VERSION = "3"

# The key color the model paints behind the figure. Must be fully saturated and impossible in the
# artwork, and far enough from ACCENT_COLOR_HEX in hue that chroma.py can tell them apart.
KEY_COLOR_NAME = "magenta"
KEY_COLOR_HEX = "#FF00FF"

# The single accent, filled on the primary working muscle. Warm amber reads on both the dark and
# the light (neutral-inverted) variant, and is ~180° from the magenta key in hue.
ACCENT_COLOR_NAME = "warm amber"
ACCENT_COLOR_HEX = "#F2A03D"

# The locked style uses exactly one accent. ``build_prompt(accent=None)`` still renders a pure
# monochrome image if a caller ever needs one, but the batch uses the locked value.
LOCKED_ACCENT: str | None = ACCENT_COLOR_HEX

# ``{subject}`` is the only thing that differs between the named prompt and the anonymous
# fallback; every style clause is shared, so fallback art is stylistically identical to the rest.
_TEMPLATE = (
    "Bold graphic line-art illustration of {subject}. "
    "{equipment_clause}Show the movement at its most recognizable position. Thick heavy uniform "
    "off-white strokes, strongly simplified anatomy, high contrast, no interior detail beyond "
    "the accent, no shading, no gradients{accent_clause}. On a completely flat solid {key_color} "
    "({key_hex}) background. Faceless neutral mannequin, centered, generous margins, square "
    "composition. Instructional, iconographic, consistent proportions. No text, no logos, no "
    "background scenery, no equipment racks or frames beyond the implement named. The background "
    "must be one uniform {key_color} with nothing else in it, and {key_color} must appear "
    "nowhere in the figure itself."
)

# Dataset ``equipment`` values that mean "no implement" (body-weight movement).
_BODYWEIGHT = frozenset({"body only", "none", ""})


def _equipment_clause(equipment: str | None) -> str:
    if equipment and equipment.strip().lower() not in _BODYWEIGHT:
        return f"Using a {equipment.strip()}. "
    return ""


def _muscle_phrase(primary_muscles: list[str] | None) -> str:
    return ", ".join(m for m in (primary_muscles or []) if m) or "primary working"


def _accent_clause(muscles: str, accent: str | None) -> str:
    """Naming the muscle group (not "the primary muscle") is what makes the accent land on the
    right anatomy — it is the illustration's only piece of information, not decoration."""
    if not accent:
        return ", no color fills"
    return (
        f". The {muscles} muscles are filled solid {ACCENT_COLOR_NAME} ({accent}) — exactly one "
        "accent color, everything else off-white"
    )


def build_prompt(
    *,
    name: str,
    equipment: str | None = None,
    primary_muscles: list[str] | None = None,
    accent: str | None = LOCKED_ACCENT,
) -> str:
    """Render the locked template for one exercise. Deterministic (same inputs → same string).

    ``accent`` defaults to the locked amber; pass ``None`` for a pure monochrome render.
    """
    muscles = _muscle_phrase(primary_muscles)
    return _TEMPLATE.format(
        subject=f'a person performing "{name}"',
        equipment_clause=_equipment_clause(equipment),
        accent_clause=_accent_clause(muscles, accent),
        key_color=KEY_COLOR_NAME,
        key_hex=KEY_COLOR_HEX,
    )


def build_anonymous_prompt(
    *,
    category: str | None = None,
    force: str | None = None,
    mechanic: str | None = None,
    equipment: str | None = None,
    primary_muscles: list[str] | None = None,
    accent: str | None = LOCKED_ACCENT,
) -> str:
    """Render the locked style for a movement described **without its name**.

    The fallback for :class:`~app.images.openai_images.ImageSafetyRejection`. A handful of catalog
    names are refused by the safety system — some read as suggestive out of context ("Bottoms Up",
    "Groiners"), others as depicting harm ("Rope Crunch", "Neck-SMR"). The refusal is deterministic,
    so retrying the same prompt is futile; dropping the name and describing the movement from its
    structured attributes clears the filter while keeping the illustration correct and on-style.

    Deliberately not a word blocklist: the refusals do not share a vocabulary, so a term map would
    have to be guessed at and maintained. This needs no list and cannot go stale.
    """
    descriptor = (
        " ".join(p.strip() for p in (force, mechanic, category) if p and p.strip()) or "strength"
    )
    muscles = _muscle_phrase(primary_muscles)
    return _TEMPLATE.format(
        subject=f"a person performing a {descriptor} exercise that works the {muscles} muscles",
        equipment_clause=_equipment_clause(equipment),
        accent_clause=_accent_clause(muscles, accent),
        key_color=KEY_COLOR_NAME,
        key_hex=KEY_COLOR_HEX,
    )


def prompt_hash(prompt: str) -> str:
    """Stable SHA-256 of the prompt — stored in provenance for reproducibility (docs/06)."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
