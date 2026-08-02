"""A stand-in for what GPT Image 2 actually returns, for tests that stub the provider.

Both callers used to hand back a placeholder like ``b"PNGDATA"``. That was fine while
``generate_and_store`` only forwarded the provider's bytes to Blob, but the pipeline now keys the
magenta ground out and derives the light twin (``app.images.chroma``), and those steps decode the
image — so the placeholders raised ``ChromaKeyError`` and three tests failed for a reason that had
nothing to do with what they were asserting.

A real image is also the stronger fixture: the stub now carries the two things the style is
defined by (a magenta key field and off-white linework), so a test that stubs the provider still
exercises the keying it feeds.
"""

from __future__ import annotations

import io

from PIL import Image

# prompt.KEY_COLOR_HEX, and the bold off-white the locked style draws in.
_KEY = (255, 0, 255)
_LINE = (245, 245, 240)


def fake_generated_png(size: int = 8) -> bytes:
    """A tiny PNG shaped like the real output: magenta ground, a stroke of linework down it."""
    image = Image.new("RGB", (size, size), _KEY)
    for y in range(size):
        image.putpixel((size // 2, y), _LINE)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
