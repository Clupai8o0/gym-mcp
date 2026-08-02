"""Vercel Blob upload adapter (docs/06). ``httpx`` only — no DB, no web framework.

Uploads a PNG to a **stable public key** ``exercises/{slug}.png`` so regenerating overwrites in
place and keeps the same URL (docs/06). An isolated I/O boundary; tests stub :func:`upload_png`.

The exact Blob HTTP contract (API version header, response shape) should be confirmed against
the current Vercel Blob docs before the first live batch run; it is confined to this module.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings

_BASE_URL = "https://blob.vercel-storage.com"
_API_VERSION = "7"
_HTTP_TIMEOUT_SECONDS = 60.0


class BlobUploadError(Exception):
    """Uploading the illustration to Vercel Blob failed."""


# The light-mode twin (chroma.invert_neutral) is stored beside the dark original under the same
# slug. Suffixing rather than using a separate prefix keeps the pair adjacent in the Blob store.
VARIANT_DARK = "dark"
VARIANT_LIGHT = "light"


def blob_key(slug: str, variant: str = VARIANT_DARK) -> str:
    """The stable object key for an exercise's illustration in ``variant``."""
    if variant == VARIANT_DARK:
        return f"exercises/{slug}.png"
    return f"exercises/{slug}-{variant}.png"


async def upload_png(
    *,
    key: str,
    data: bytes,
    token: str | None = None,
    content_type: str = "image/png",
) -> str:
    """Upload ``data`` to ``key`` (public, overwrite-in-place) and return its public URL."""
    token = token or get_settings().blob_read_write_token
    if not token:
        raise BlobUploadError("BLOB_READ_WRITE_TOKEN is not configured")

    headers = {
        "authorization": f"Bearer {token}",
        "x-api-version": _API_VERSION,
        "x-content-type": content_type,
        # Stable key: no random suffix, allow overwrite → regenerating keeps the same URL.
        "x-add-random-suffix": "0",
        "x-allow-overwrite": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.put(f"{_BASE_URL}/{key}", content=data, headers=headers)
    except httpx.HTTPError as exc:
        raise BlobUploadError(f"Vercel Blob request failed: {exc}") from exc

    if response.status_code not in (200, 201):
        raise BlobUploadError(
            f"Vercel Blob upload failed ({response.status_code}): {response.text[:200]}"
        )
    url = response.json().get("url")
    if not url:
        raise BlobUploadError("Vercel Blob response contained no url")
    return str(url)
