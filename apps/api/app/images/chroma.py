"""Turn the generated key field into real transparency, and derive the light-mode twin (docs/06).

**Why this exists.** The locked style (``prompt.py``) is bold off-white line art with a single
amber accent on the working muscle, on a *fully transparent* background. GPT Image 2 cannot emit
alpha: ``background: "transparent"`` is rejected with "Transparent background is not supported
for this model" — the API accepts only ``opaque``/``auto``. So the prompt asks for a flat magenta
field the artwork never contains, and :func:`key_out_background` removes it here.

**Why the key is hue-aware.** An earlier revision keyed on *any* saturation, which was valid
while the style was strictly monochrome — every colored pixel was background by definition. The
amber accent (STYLE_VERSION 3) broke that: a saturation key erases the accent along with the
ground. So the mask is now "saturated **and** magenta-hued", which leaves amber untouched.

Within the mask each pixel is decomposed as

    chroma  = max(R,G,B) - min(R,G,B)     # ~0 for neutral linework, ~255 for the key field
    neutral = min(R,G,B)                  # the achromatic component of the pixel

Alpha comes from ``chroma``; masked pixels are rebuilt from ``neutral``. That tolerates the
uneven, noisy magenta the model actually returns (a generated background is never one flat RGB
value) and despills for free — an antialiased edge that is part line, part magenta loses its
color cast instead of leaving the purple fringe a naive "delete the exact key color" pass leaves.

**Light mode.** The delivered art is off-white, which is invisible on a light surface, and CSS
cannot fix it: ``filter: invert()`` cannot act selectively and would drag the amber to blue.
:func:`invert_neutral` derives the light twin locally instead — achromatic pixels flip, the
accent is passed through byte-identical — so a second variant costs image processing, not a
second API call.

Every pass is Pillow channel ops (C-speed LUTs), so a 1024x1024 image costs ~milliseconds and
the batch stays I/O-bound on the generation calls.
"""

from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageOps

# For a pixel that is fraction ``f`` line over the magenta ground, the channels blend to roughly
# (255-10f, 245f, 255-15f), so
#
#     chroma = max - min ≈ 255 - 255f      →      raw coverage ≈ 255 - chroma
#
# Coverage and chroma are near-perfectly anti-correlated, so ``255 - chroma`` recovers an edge
# pixel's true alpha. Using it *raw* is not enough in either direction, hence a toe and shoulder:
#
#   * Toe — the model never returns one flat RGB value for the ground; real background pixels
#     scatter around the key color and land at a raw coverage of ~10-30. Left alone that paints a
#     faint dark haze over the entire frame (the output RGB is the near-black min channel), which
#     is exactly the artifact a naive "delete the exact key color" pass leaves. Anything under the
#     toe is background — snap it to 0. This is the aggressive part.
#   * Shoulder — the artwork's own off-white carries a small cast; snap the top to solid so line
#     cores are never slightly translucent.
#
# Between them coverage is rescaled linearly, so mid-range antialiased edges keep a smooth,
# monotonic ramp and strokes hold their intended weight. Very faint edges (under ~15% coverage)
# are deliberately sacrificed to the toe — invisible in the render, and the price of a background
# that keys to exactly zero.
_ALPHA_TOE = 40
_ALPHA_SHOULDER = 235

# Pillow packs hue into 0-255; magenta (300°) lands at ~212. The tolerance is wide enough to
# swallow the model's uneven ground but nowhere near amber (~30° → ~21), so the accent is safe.
_KEY_HUE = 212
_HUE_TOLERANCE = 34
# Below this saturation a pixel is artwork, not key field, whatever its nominal hue.
_KEY_SATURATION_FLOOR = 70
# Chroma above which a pixel counts as "the accent" for the light-mode inversion. Comfortably
# above the artwork's own faint cast and far below a saturated amber fill.
_ACCENT_CHROMA_FLOOR = 60


class ChromaKeyError(Exception):
    """The generated image could not be decoded or keyed."""


def _alpha_lut(toe: int, shoulder: int) -> list[int]:
    """256-entry LUT mapping a pixel's chroma to its alpha.

    Indexed by chroma; recovers coverage as ``255 - chroma``, then applies the toe/shoulder.
    """
    if not 0 <= toe < shoulder <= 255:
        raise ValueError(f"invalid alpha toe/shoulder: {toe}..{shoulder}")
    span = shoulder - toe
    lut = []
    for chroma in range(256):
        coverage = 255 - chroma
        if coverage <= toe:
            lut.append(0)
        elif coverage >= shoulder:
            lut.append(255)
        else:
            lut.append(round(255 * (coverage - toe) / span))
    return lut


def _decode(png: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(png)) as source:
            return source.convert("RGBA")
    except OSError as exc:  # Pillow raises OSError for undecodable/truncated data
        raise ChromaKeyError(f"could not decode image: {exc}") from exc


def _encode(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _key_mask(rgb: Image.Image) -> Image.Image:
    """255 where a pixel belongs to the magenta key field, 0 where it is artwork."""
    hue, saturation, _ = rgb.convert("HSV").split()
    # Hue is circular: distance must wrap around the 0/255 seam.
    hue_distance = hue.point(lambda h: min(abs(h - _KEY_HUE), 255 - abs(h - _KEY_HUE)))
    near_key_hue = hue_distance.point(lambda d: 255 if d <= _HUE_TOLERANCE else 0)
    saturated = saturation.point(lambda s: 255 if s >= _KEY_SATURATION_FLOOR else 0)
    return ImageChops.multiply(near_key_hue, saturated)


def key_out_background(
    png: bytes,
    *,
    toe: int = _ALPHA_TOE,
    shoulder: int = _ALPHA_SHOULDER,
) -> bytes:
    """Return ``png`` as RGBA with the magenta ground removed and the accent preserved.

    Raises :class:`ChromaKeyError` if the bytes are not a decodable image.
    """
    rgb = _decode(png).convert("RGB")
    is_key = _key_mask(rgb)

    red, green, blue = rgb.split()
    neutral = ImageChops.darker(ImageChops.darker(red, green), blue)
    brightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    chroma = ImageChops.subtract(brightest, neutral)

    # Alpha ramps only inside the key mask; artwork (including the amber) stays fully opaque.
    ramp = chroma.point(_alpha_lut(toe, shoulder))
    alpha = Image.composite(ramp, Image.new("L", rgb.size, 255), is_key)
    # Despill: key-hued pixels collapse to their achromatic component; the accent is untouched.
    despilled = Image.composite(Image.merge("RGB", (neutral, neutral, neutral)), rgb, is_key)

    return _encode(Image.merge("RGBA", (*despilled.split(), alpha)))


def invert_neutral(png: bytes) -> bytes:
    """Return the light-mode twin of a keyed illustration.

    Achromatic pixels are inverted (off-white linework becomes near-black, so it reads on a
    light surface); anything carrying real chroma — the amber accent — is passed through
    unchanged, which a blanket ``filter: invert()`` could never do. Alpha is preserved, so the
    twin still composites onto any background.

    Raises :class:`ChromaKeyError` if the bytes are not a decodable image.
    """
    rgba = _decode(png)
    rgb = rgba.convert("RGB")

    red, green, blue = rgb.split()
    neutral = ImageChops.darker(ImageChops.darker(red, green), blue)
    brightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    chroma = ImageChops.subtract(brightest, neutral)
    is_accent = chroma.point(lambda c: 255 if c > _ACCENT_CHROMA_FLOOR else 0)

    flipped = Image.composite(rgb, ImageOps.invert(rgb), is_accent)
    return _encode(Image.merge("RGBA", (*flipped.split(), rgba.getchannel("A"))))
