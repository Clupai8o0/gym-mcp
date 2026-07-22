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
    assert "transparent background" in text
    assert "off-white lines" in text
    assert "No text, no logos" in text


def test_build_prompt_bodyweight_has_no_equipment_clause() -> None:
    text = prompt.build_prompt(name="Pull-up", equipment="body only", primary_muscles=["lats"])
    assert "Using a" not in text


def test_build_prompt_null_equipment_and_muscles_fall_back() -> None:
    text = prompt.build_prompt(name="Mystery Move", equipment=None, primary_muscles=None)
    assert "Using a" not in text
    assert "the primary working" in text  # muscle fallback


def test_build_prompt_is_pure_monochrome_by_default() -> None:
    assert "accent" not in prompt.build_prompt(name="X")


def test_build_prompt_supports_an_accent_override() -> None:
    assert "crimson accent" in prompt.build_prompt(name="X", accent="crimson")


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
