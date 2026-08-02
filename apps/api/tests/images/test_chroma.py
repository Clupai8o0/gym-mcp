"""The chroma pass that turns GPT Image 2's flat key field into real transparency (docs/06).

The model cannot return alpha, so every generated image arrives as off-white line art with an
amber accent on a solid magenta ground. These tests pin the properties the catalog depends on:
the ground keys to nothing, the linework survives as opaque neutral grey, antialiased edges keep
a smooth ramp instead of thinning out, and — the constraint that forced the key to become
hue-aware — the amber accent is never mistaken for background.
"""

from __future__ import annotations

import io

import pytest
from app.images import chroma
from PIL import Image

_KEY = (255, 0, 255)  # magenta — prompt.KEY_COLOR_HEX
_LINE = (245, 245, 240)  # the locked "off-white lines"
_ACCENT = (242, 160, 61)  # prompt.ACCENT_COLOR_HEX — the working-muscle fill


def _png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """Encode a small RGB image from a row-major pixel grid."""
    height, width = len(pixels), len(pixels[0])
    img = Image.new("RGB", (width, height))
    img.putdata([px for row in pixels for px in row])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _rgba(png: bytes, xy: tuple[int, int] = (0, 0)) -> tuple[int, int, int, int]:
    """Decode ``png`` and read one pixel as a concrete RGBA 4-tuple."""
    with Image.open(io.BytesIO(png)) as img:
        pixel = img.convert("RGBA").getpixel(xy)
    assert isinstance(pixel, tuple) and len(pixel) == 4
    return int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3])


def _alpha(png: bytes, xy: tuple[int, int] = (0, 0)) -> int:
    return _rgba(png, xy)[3]


def _blend(coverage: float) -> tuple[int, int, int]:
    """A pixel that is ``coverage`` off-white line composited over the magenta ground."""
    r, g, b = (
        round(line * coverage + key * (1 - coverage)) for line, key in zip(_LINE, _KEY, strict=True)
    )
    return r, g, b


def test_key_color_becomes_fully_transparent_and_line_stays_opaque() -> None:
    out = chroma.key_out_background(_png([[_KEY, _LINE], [_KEY, _LINE]]))

    assert _alpha(out, (0, 0)) == 0, "magenta ground must be fully transparent"
    assert _alpha(out, (1, 0)) == 255, "off-white linework must stay fully opaque"


def test_linework_passes_through_light_and_near_neutral() -> None:
    """Artwork outside the key mask is left alone.

    An earlier revision flattened *every* pixel to its achromatic component, which was safe while
    the style was monochrome. It cannot be done now — it would drain the amber accent — so the
    guarantee is weaker but sufficient: linework stays light and carries no real chroma.
    """
    red, green, blue, alpha = _rgba(chroma.key_out_background(_png([[_LINE]])))

    assert alpha == 255
    assert red >= 200, "an off-white line must stay light, not be crushed to black"
    assert max(red, green, blue) - min(red, green, blue) < 20, "linework must not be color-cast"


def test_uneven_key_field_is_still_removed() -> None:
    """Generated backgrounds are never one flat RGB value; keying on chroma tolerates that."""
    out = chroma.key_out_background(_png([[(255, 0, 255), (230, 12, 240), (255, 4, 210)]]))

    assert [_alpha(out, (x, 0)) for x in range(3)] == [0, 0, 0]


def test_partial_coverage_ramps_monotonically() -> None:
    """Antialiased edges must ramp smoothly, or strokes stair-step and lose their weight."""
    alphas = [
        _alpha(chroma.key_out_background(_png([[_blend(c)]]))) for c in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]

    assert alphas == sorted(alphas), f"alpha must increase with coverage, got {alphas}"
    assert alphas[0] == 0 and alphas[-1] == 255, "the ends must be fully keyed / fully solid"
    assert 0 < alphas[2] < 255, "a half-covered edge must be genuinely semi-transparent"


def test_half_covered_edge_keeps_most_of_its_weight() -> None:
    """The toe trims faint edges on purpose, but a 50% pixel must not collapse toward zero."""
    assert _alpha(chroma.key_out_background(_png([[_blend(0.5)]]))) == pytest.approx(128, abs=45)


def test_amber_accent_survives_the_key() -> None:
    """The regression that forced a hue-aware key: a saturation key erased the accent.

    The accent is saturated, exactly like the ground — only its *hue* distinguishes it. If this
    fails, every illustration ships with a hole where the working muscle should be.
    """
    out = chroma.key_out_background(_png([[_KEY, _ACCENT, _LINE]]))

    assert _alpha(out, (0, 0)) == 0, "ground must key out"
    assert _alpha(out, (1, 0)) == 255, "accent must stay fully opaque"
    assert _rgba(out, (1, 0))[:3] == pytest.approx(_ACCENT, abs=4), "accent hue must be intact"
    assert _alpha(out, (2, 0)) == 255


def test_invert_neutral_flips_linework_but_not_the_accent() -> None:
    """Light-mode twin: CSS ``filter: invert()`` cannot do this — it would drag amber to blue."""
    keyed = chroma.key_out_background(_png([[_LINE, _ACCENT, _KEY]]))
    light = chroma.invert_neutral(keyed)

    line_before, line_after = _rgba(keyed, (0, 0)), _rgba(light, (0, 0))
    assert line_before[0] > 200 and line_after[0] < 55, "off-white linework must become dark"
    assert _rgba(light, (1, 0))[:3] == pytest.approx(_ACCENT, abs=4), "accent must be untouched"


def test_invert_neutral_preserves_alpha() -> None:
    """The twin still has to composite onto any surface, so transparency must carry over."""
    keyed = chroma.key_out_background(_png([[_KEY, _LINE]]))
    light = chroma.invert_neutral(keyed)

    assert [_alpha(light, (x, 0)) for x in range(2)] == [_alpha(keyed, (x, 0)) for x in range(2)]


def test_invert_neutral_is_an_involution_on_neutral_pixels() -> None:
    """Inverting twice returns the original — a cheap guard against a lossy transform."""
    keyed = chroma.key_out_background(_png([[_LINE, _ACCENT]]))
    round_tripped = chroma.invert_neutral(chroma.invert_neutral(keyed))

    for x in range(2):
        assert _rgba(round_tripped, (x, 0)) == pytest.approx(_rgba(keyed, (x, 0)), abs=2)


def test_undecodable_bytes_raise_chroma_key_error() -> None:
    with pytest.raises(chroma.ChromaKeyError):
        chroma.key_out_background(b"this is not a png")
    with pytest.raises(chroma.ChromaKeyError):
        chroma.invert_neutral(b"this is not a png")
