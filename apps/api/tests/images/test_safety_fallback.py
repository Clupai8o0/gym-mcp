"""Safety-rejection classification in the OpenAI adapter (docs/06).

A moderation refusal is deterministic — the same prompt is refused identically forever — so it
must be distinguishable from a transient 400. Misclassifying it either way is costly: treated as
transient, the batch retries a doomed prompt on every resume; treated as fatal, a genuine
rate-limit blip would permanently anonymise an exercise that never needed it.
"""

from __future__ import annotations

import httpx
import pytest
from app.core.config import get_settings
from app.images import openai_images

_SAFETY_BODY = (
    '{"error": {"message": "Your request was rejected by the safety system.", '
    '"type": "image_generation_user_error", "code": "moderation_blocked"}}'
)
_QUOTA_BODY = (
    '{"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}'
)


def _transport(status: int, body: str) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _req: httpx.Response(status, text=body))


async def _generate(monkeypatch: pytest.MonkeyPatch, status: int, body: str) -> None:
    transport = _transport(status, body)
    original = httpx.AsyncClient

    def client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-key", raising=False)
    await openai_images.generate_png(
        prompt="x", size=None, quality=None, model=None, background=None
    )


@pytest.mark.asyncio
async def test_safety_refusal_raises_the_dedicated_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(openai_images.ImageSafetyRejection):
        await _generate(monkeypatch, 400, _SAFETY_BODY)


@pytest.mark.asyncio
async def test_other_400s_stay_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    """A quota error must NOT be mistaken for a safety refusal — it is retryable."""
    with pytest.raises(openai_images.ImageGenerationError) as excinfo:
        await _generate(monkeypatch, 400, _QUOTA_BODY)
    assert not isinstance(excinfo.value, openai_images.ImageSafetyRejection)


def test_safety_rejection_is_a_generation_error() -> None:
    """Callers that only catch ImageGenerationError must still handle it (batch, on-demand)."""
    assert issubclass(openai_images.ImageSafetyRejection, openai_images.ImageGenerationError)
