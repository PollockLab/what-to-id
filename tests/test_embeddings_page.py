"""The photo-space page builder inlines its scripts and config, and keeps the deck.gl pin."""

import json
import re

import pytest

from what_to_id import page_map
from what_to_id.embeddings_page import DECK_JS, build


def test_build_inlines_scripts_and_config(tmp_path):
    html = build(tmp_path, data_url="https://example.org/atlas/").read_text()
    assert not re.search(r"__[A-Z_]+__", html)
    config = re.search(r"var EMBEDDINGS_CONFIG=(\{.*?\});", html)
    assert json.loads(config.group(1))["dataUrl"] == "https://example.org/atlas/"
    for needle in ("EmbeddingsLayout", "AtlasSearchIndex", DECK_JS):
        assert needle in html


def test_links_to_map_search_and_sample(tmp_path):
    html = build(tmp_path).read_text()
    for href in ("map.html", "search.html", "embeddings-sample.html"):
        assert f'href="{href}"' in html


def test_empty_data_url_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="data_url"):
        build(tmp_path, data_url="")


def test_deck_pin_matches_the_map():
    assert DECK_JS == page_map.DECK_JS
