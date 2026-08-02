"""OpenAI GPT Image 2 protocol adapter (docs/06). ``httpx`` only — no DB, no web framework.

An isolated I/O boundary (like ``auth/google.py``): it turns a prompt into PNG bytes via the
Images API and nothing else. Model / size / quality / transparent-background default from
settings (pinned; docs/06). Tests stub :func:`generate_png`, so the suite never needs a key or
the network.

The exact request/response contract should be confirmed against the current OpenAI Images API
before the first live batch run; it is deliberately confined to this one module.
"""

from __future__ import annotations

import base64

import httpx

from app.core.config import get_settings

_ENDPOINT = "https://api.openai.com/v1/images/generations"
# Image generation is slow; give it a wide ceiling. Batch concurrency is bounded by the caller.
_HTTP_TIMEOUT_SECONDS = 120.0


class ImageGenerationError(Exception):
    """Image generation failed — missing key, upstream error, or a malformed response."""


class ImageSafetyRejection(ImageGenerationError):
    """The prompt was refused by OpenAI's safety system.

    Distinguished from a generic failure because it is **deterministic**: the same prompt is
    refused identically on every retry, so the batch's normal resume-and-retry does nothing. The
    caller must vary the prompt instead (see ``services.images.generate_and_store``).

    In practice this fires on exercise *names*, not on the locked style clauses — the catalog
    contains entries like "Bottoms Up" and "Groiners" that read as suggestive out of context, and
    others like "Rope Crunch" / "Neck-SMR" that read as depicting harm to a person.
    """


# Substrings that identify a moderation refusal in the error body, rather than a transport,
# quota, or malformed-request 400.
_SAFETY_MARKERS = ("safety system", "moderation_blocked", "content_policy")


async def generate_png(
    *,
    prompt: str,
    size: str | None = None,
    quality: str | None = None,
    model: str | None = None,
    background: str | None = None,
) -> bytes:
    """Generate one PNG for ``prompt`` and return its raw bytes.

    GPT-Image models return base64-encoded image data (``b64_json``); we decode it to bytes for
    upload. Raises :class:`ImageGenerationError` on any failure.
    """
    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        raise ImageGenerationError("OPENAI_API_KEY is not configured")

    body = {
        "model": model or settings.openai_image_model,
        "prompt": prompt,
        "size": size or settings.openai_image_size,
        "quality": quality or settings.openai_image_quality,
        "background": background or settings.openai_image_background,
        "n": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _ENDPOINT, json=body, headers={"Authorization": f"Bearer {api_key}"}
            )
    except httpx.HTTPError as exc:
        raise ImageGenerationError(f"OpenAI request failed: {exc}") from exc

    if response.status_code != 200:
        # NB: not `body` — that name holds the *request* payload above.
        error_body = response.text
        message = f"OpenAI image generation failed ({response.status_code}): {error_body[:200]}"
        if any(marker in error_body.lower() for marker in _SAFETY_MARKERS):
            raise ImageSafetyRejection(message)
        raise ImageGenerationError(message)
    try:
        b64 = response.json()["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ImageGenerationError("OpenAI response contained no image data") from exc
    return base64.b64decode(b64)
