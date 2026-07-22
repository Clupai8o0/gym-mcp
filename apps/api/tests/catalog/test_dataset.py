"""Dataset adapter: field mapping, null-handling, drift detection, slug de-collision."""

from __future__ import annotations

import pytest
from app.catalog.dataset import PINNED_SHA, SOURCE, DatasetError, parse_dataset


def _item(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "X_Id",
        "name": "X Move",
        "category": "strength",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "barbell",
        "primaryMuscles": ["chest"],
        "secondaryMuscles": ["triceps"],
        "instructions": ["Do the thing."],
        "images": ["X_Id/0.jpg", "X_Id/1.jpg"],
    }
    base.update(overrides)
    return base


def test_parse_maps_every_field() -> None:
    (record,) = parse_dataset([_item()])
    assert record.source == SOURCE
    assert record.source_id == "X_Id"
    assert record.slug == "x-move"
    assert record.name == "X Move"
    assert record.category == "strength"
    assert record.force == "push"
    assert record.level == "beginner"
    assert record.mechanic == "compound"
    assert record.equipment == "barbell"
    assert record.primary_muscles == ["chest"]
    assert record.secondary_muscles == ["triceps"]
    assert record.instructions == ["Do the thing."]


def test_parse_allows_null_optionals() -> None:
    (record,) = parse_dataset([_item(force=None, mechanic=None, equipment=None)])
    assert record.force is None
    assert record.mechanic is None
    assert record.equipment is None


def test_parse_ignores_images_and_unknown_fields() -> None:
    (record,) = parse_dataset([_item(surprise="ignored")])
    assert not hasattr(record, "images")
    assert not hasattr(record, "surprise")


def test_parse_rejects_non_list() -> None:
    with pytest.raises(DatasetError):
        parse_dataset({"exercises": []})


def test_parse_rejects_missing_required_field() -> None:
    with pytest.raises(DatasetError):
        parse_dataset([{"name": "No Id Here"}])


def test_parse_rejects_enum_drift() -> None:
    with pytest.raises(DatasetError) as excinfo:
        parse_dataset([_item(force="sideways")])
    assert "force" in str(excinfo.value)


def test_parse_rejects_duplicate_source_id() -> None:
    with pytest.raises(DatasetError):
        parse_dataset([_item(id="dup"), _item(id="dup", name="Different Name")])


def test_parse_dedupes_colliding_slugs_deterministically() -> None:
    records = parse_dataset([_item(id="a", name="Bench Press"), _item(id="b", name="Bench  Press")])
    assert records[0].slug == "bench-press"
    assert records[1].slug == "bench-press-2"


def test_pinned_sha_is_a_full_commit_hash() -> None:
    assert len(PINNED_SHA) == 40
    assert all(character in "0123456789abcdef" for character in PINNED_SHA)
