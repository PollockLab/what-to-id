"""The photo-space page builder inlines its scripts and config, and keeps the deck.gl pin."""

import json
import re
from pathlib import Path

import pytest

from what_to_id import embeddings_page, page_map
from what_to_id.embeddings_page import DECK_JS, build


def test_build_inlines_scripts_and_config(tmp_path):
    html = build(tmp_path, data_url="https://example.org/atlas/").read_text()
    assert not re.search(r"__[A-Z_]+__", html)
    config = re.search(r"var EMBEDDINGS_CONFIG=(\{.*?\});", html)
    assert json.loads(config.group(1))["dataUrl"] == "https://example.org/atlas/"
    for needle in ("EmbeddingsLayout", "AtlasSearchIndex", DECK_JS):
        assert needle in html


def test_links_to_explore_not_to_search(tmp_path):
    html = build(tmp_path).read_text()
    assert 'href="split.html"' in html and 'href="search.html"' not in html


def test_empty_data_url_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="data_url"):
        build(tmp_path, data_url="")


def test_deck_pin_matches_the_map():
    assert DECK_JS == page_map.DECK_JS


def test_group_palette_has_no_repeats_at_fifteen_groups():
    src = (Path(embeddings_page.__file__).parent / "map_assets" / "map_filter.js").read_text()
    pal = re.search(r"MapFilter.PAL=(\[\[.*?\]\]);", src).group(1)
    colours = [tuple(c) for c in json.loads(pal)]
    assert len(set(colours)) == len(colours) >= 15


def _lum(c):
    lin = [v / 255 / 12.92 if v <= 10 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_named_group_colours_are_distinct_and_readable_on_both_pages():
    src = (Path(embeddings_page.__file__).parent / "map_assets" / "map_filter.js").read_text()
    body = re.search(r"MapFilter.BY=(\{.*?\});", src).group(1)
    by = json.loads(re.sub(r"(\w+):", r'"\1":', body))
    assert len(by) >= 14 and len({tuple(c) for c in by.values()}) == len(by)
    light, dark = _lum((0xFB, 0xFB, 0xF9)), _lum((0x1A, 0x1A, 0x19))
    for name, c in by.items():
        assert _contrast(_lum(c), light) >= 2 and _contrast(_lum(c), dark) >= 2, name
    gap = sum((x - y) ** 2 for x, y in zip(by["Plantae"], by["Insecta"], strict=True)) ** 0.5
    assert gap > 150
