"""The locked illustration prompt: clauses, body-weight handling, monochrome default, hashing."""

from __future__ import annotations

from app.images import prompt


def test_build_prompt_includes_name_equipment_and_muscles() -> None:
    text = prompt.build_prompt(
        name="Back Squat", equipment="barbell", primary_muscles=["quadriceps", "glutes"]
    )
    assert '"Back Squat"' in text
    assert "Using a barbell." in text
    assert "quadriceps, glutes" in text
    # Locked style clauses are always present.
    assert "Thick heavy uniform off-white strokes" in text
    assert "No text, no logos" in text


def test_build_prompt_asks_for_the_chroma_key_field() -> None:
    """GPT Image 2 cannot emit alpha, so the prompt must request the flat key background.

    Transparency comes from app.images.chroma afterwards; if this clause ever regresses to
    "transparent background" the API 400s and the whole batch fails.
    """
    text = prompt.build_prompt(name="X")
    assert prompt.KEY_COLOR_NAME in text
    assert prompt.KEY_COLOR_HEX in text
    assert "transparent" not in text


def test_build_prompt_bodyweight_has_no_equipment_clause() -> None:
    text = prompt.build_prompt(name="Pull-up", equipment="body only", primary_muscles=["lats"])
    assert "Using a" not in text


def test_build_prompt_null_equipment_and_muscles_fall_back() -> None:
    text = prompt.build_prompt(name="Mystery Move", equipment=None, primary_muscles=None)
    assert "Using a" not in text
    assert "primary working muscles are filled" in text  # muscle fallback still accents


def test_build_prompt_accents_the_named_muscle_group_by_default() -> None:
    """The accent is the illustration's only information, so it must name the real muscles.

    "the primary muscle" would let the model pick; naming them is what makes the amber land on
    quads for a squat and lats for a pull-up (docs/06 style sign-off).
    """
    text = prompt.build_prompt(name="Back Squat", primary_muscles=["quadriceps", "glutes"])
    assert prompt.ACCENT_COLOR_HEX in text
    assert "quadriceps, glutes muscles are filled" in text


def test_build_prompt_supports_a_monochrome_render() -> None:
    text = prompt.build_prompt(name="X", accent=None)
    assert prompt.ACCENT_COLOR_HEX not in text
    assert "no color fills" in text


def test_build_prompt_accent_stays_clear_of_the_key_colour() -> None:
    """chroma.py separates ground from accent by hue; identical hues would erase the accent."""
    assert prompt.ACCENT_COLOR_HEX != prompt.KEY_COLOR_HEX
    assert prompt.KEY_COLOR_NAME not in prompt.ACCENT_COLOR_NAME


def test_anonymous_prompt_omits_the_name_but_keeps_the_movement() -> None:
    """The safety fallback: the refused *name* is what must go, not the exercise's meaning."""
    text = prompt.build_anonymous_prompt(
        category="stretching",
        force="static",
        mechanic=None,
        equipment="body only",
        primary_muscles=["adductors"],
    )
    assert "static stretching exercise" in text
    assert "adductors muscles" in text
    assert "Using a" not in text  # body-weight
    assert prompt.ACCENT_COLOR_HEX in text  # still accented


def test_anonymous_prompt_shares_every_style_clause_with_the_named_one() -> None:
    """Fallback art sits in the same catalog, so only the subject may differ.

    If the style clauses ever diverge, the ~7 fallback illustrations would visibly not match the
    other ~866 — the exact failure the locked spec exists to prevent.
    """
    marker = "Show the movement"
    named = prompt.build_prompt(name="Groiners", equipment="dumbbell", primary_muscles=["glutes"])
    anon = prompt.build_anonymous_prompt(
        category="strength", equipment="dumbbell", primary_muscles=["glutes"]
    )

    assert named.split(marker)[1] == anon.split(marker)[1]
    assert "Groiners" not in anon


def test_anonymous_prompt_falls_back_when_every_attribute_is_missing() -> None:
    """A catalog row with no category/force/mechanic must still yield a usable prompt."""
    text = prompt.build_anonymous_prompt()
    assert "strength exercise" in text
    assert "primary working muscles" in text


def test_build_prompt_is_deterministic() -> None:
    first = prompt.build_prompt(
        name="Deadlift", equipment="barbell", primary_muscles=["hamstrings"]
    )
    second = prompt.build_prompt(
        name="Deadlift", equipment="barbell", primary_muscles=["hamstrings"]
    )
    assert first == second


def test_prompt_hash_is_stable_sha256() -> None:
    text = prompt.build_prompt(name="X")
    digest = prompt.prompt_hash(text)
    assert digest == prompt.prompt_hash(text)
    assert len(digest) == 64
