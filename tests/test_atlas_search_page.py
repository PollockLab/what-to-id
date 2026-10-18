"""The search page builder inlines every script and the data URL."""

import re

import pytest

from what_to_id.atlas_search_page import build


def test_build_inlines_scripts_and_config(tmp_path):
    html = build(tmp_path / "site", data_url="https://data.example/atlas/").read_text()
    assert not re.search(r"__[A-Z_]+__", html)
    assert '"dataUrl": "https://data.example/atlas/"' in html
    assert "var IdentifyLinks" in html and "var ClipTokenizer" in html
    assert "AtlasSearchIndex" in html and "<script src=" not in html


def test_build_rejects_empty_data_url(tmp_path):
    with pytest.raises(ValueError, match="data_url"):
        build(tmp_path, data_url="")
