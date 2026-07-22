"""Cost estimation for the batch report (docs/06 budget range)."""

from __future__ import annotations

from app.images import cost


def test_unit_cost_increases_with_quality() -> None:
    assert (
        cost.unit_cost_usd(quality="low")
        < cost.unit_cost_usd(quality="medium")
        < cost.unit_cost_usd(quality="high")
    )


def test_unknown_quality_falls_back_to_medium() -> None:
    assert cost.unit_cost_usd(quality="ultra") == cost.unit_cost_usd(quality="medium")


def test_estimate_scales_with_count() -> None:
    assert cost.estimate_cost_usd(0, quality="low") == 0.0
    unit = cost.unit_cost_usd(quality="low")
    assert cost.estimate_cost_usd(800, quality="low") == round(800 * unit, 2)


def test_estimate_negative_count_is_zero() -> None:
    assert cost.estimate_cost_usd(-5, quality="low") == 0.0


def test_full_catalog_estimate_is_in_docs_range() -> None:
    # docs/06 budgets ~$5–$35 at low/medium for the ~800-image catalog (estimate, not a bill).
    for quality in ("low", "medium"):
        estimate = cost.estimate_cost_usd(873, quality=quality)
        assert 4 <= estimate <= 45
