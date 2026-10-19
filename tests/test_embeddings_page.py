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


def test_links_to_map_and_search(tmp_path):
    html = build(tmp_path).read_text()
    for href in ("split.html", "search.html"):
        assert f'href="{href}"' in html


def test_empty_data_url_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="data_url"):
        build(tmp_path, data_url="")


def test_deck_pin_matches_the_map():
    assert DECK_JS == page_map.DECK_JS


def test_group_palette_has_no_repeats_at_fifteen_groups():
    src = (
        Path(embeddings_page.__file__).parent / "embeddings_assets" / "embeddings_app.js"
    ).read_text()
    pal = re.search(r"var PAL=(\[\[.*?\]\]);", src).group(1)
    colours = [tuple(c) for c in json.loads(pal)]
    assert len(set(colours)) == len(colours) >= 15
