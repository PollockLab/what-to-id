"""Source-level checks for the design rules in what-to-id-docs/DESIGN.md: one green, one focus ring,
the radius scale, and taxon colours that hold 3:1 against the dark surfaces."""

import json
import re
from pathlib import Path

from what_to_id import page_blind, page_nav, page_style

SRC = Path(page_nav.__file__).parent
STYLED = [p for p in SRC.rglob("*") if p.suffix in {".css", ".html", ".py"}]


def lum(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = map(lin, rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def colours():
    js = (SRC / "map_assets" / "map_filter.js").read_text()

    def table(name):
        body = re.search(r"MapFilter\." + name + r"=([\[{].*?[\]}]);\n", js, re.S).group(1)
        return body

    by = {k: json.loads(v) for k, v in re.findall(r"(\w+):(\[[\d,]+\])", table("BY"))}
    byd = {k: json.loads(v) for k, v in re.findall(r"(\w+):(\[[\d,]+\])", table("BYD"))}
    pal = json.loads(table("PAL"))
    pald = {int(k): json.loads(v) for k, v in re.findall(r"(\d+):(\[[\d,]+\])", table("PALD"))}
    return {**by, **byd}, by, {i: pald.get(i, c) for i, c in enumerate(pal)}


def test_taxon_colours_hold_three_to_one_on_dark_surfaces():
    chip = (0x2C, 0x2C, 0x2A)
    dark_by, by, dark_pal = colours()
    for name in by:
        assert ratio(dark_by[name], chip) >= 3, name
    for i, c in dark_pal.items():
        assert ratio(c, chip) >= 3, i


def test_muted_taxon_mix_holds_three_to_one_in_light():
    _, by, _ = colours()
    muted, surfaces = (0x5F, 0x5E, 0x58), [(0xFB, 0xFB, 0xF9), (255, 255, 255), (0xF0, 0xEF, 0xE9)]
    light = list(by.values())
    js = (SRC / "map_assets" / "map_filter.js").read_text()
    light += json.loads(re.search(r"MapFilter\.PAL=(\[\[.*?\]\]);", js).group(1))
    for c in light:
        mix = [0.5 * a + 0.5 * b for a, b in zip(c, muted, strict=True)]
        assert min(ratio(mix, s) for s in surfaces) >= 3, c


def test_no_legacy_green_or_ink_focus_ring():
    for p in STYLED:
        text = p.read_text()
        assert "#22c55e" not in text and "#2e7d32" not in text, p
        assert not re.search(r"focus[^{}]*\{[^}]*outline:2px", text), p


def test_radii_follow_the_scale():
    ok = {"0", "6px", "12px", "20px", "999px", "50%", "inherit", "3px"}
    for p in STYLED:
        for v in re.findall(r"border-radius:\s*([^;}]*)", p.read_text()):
            assert set(v.split()) <= ok, (p, v)


def test_legacy_and_blind_pages_use_the_shared_type():
    assert "font:14px/1.4 system-ui,-apple-system," in page_style.CSS
    assert "max-width:1100px" in page_style.CSS and "#22c55e" not in page_style.CSS
    assert '"Segoe UI"' in page_blind.CSS
