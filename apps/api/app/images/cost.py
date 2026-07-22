"""GPT Image 2 cost estimation for the batch report (docs/06). Pure; no I/O.

The one-time batch is ~800 images; docs/06 budgets ~$5–$35 at low/medium quality. These
per-image figures are the midpoints of OpenAI's published quality×size pricing at 1024² and
are used only to print an *estimate* — reconcile against real billing after the first live run.
"""

from __future__ import annotations

# Approximate USD per 1024×1024 image by quality tier (docs/06 range: ~$0.005–$0.211).
_UNIT_USD_1024: dict[str, float] = {"low": 0.011, "medium": 0.042, "high": 0.167}
_DEFAULT_UNIT_USD = 0.042


def unit_cost_usd(*, quality: str, size: str = "1024x1024") -> float:
    """Approximate cost of one image at ``quality``/``size`` (falls back to the medium tier)."""
    return _UNIT_USD_1024.get(quality.lower(), _DEFAULT_UNIT_USD)


def estimate_cost_usd(count: int, *, quality: str, size: str = "1024x1024") -> float:
    """Estimated total USD for ``count`` images, rounded to cents."""
    return round(max(count, 0) * unit_cost_usd(quality=quality, size=size), 2)
