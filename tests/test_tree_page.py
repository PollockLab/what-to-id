"""The tree of life page: one self-contained file, the map's META copied in, clear errors."""

import gzip
import json
import re

import numpy as np
import pytest

from what_to_id import page_nav, split_page, tree_page
from what_to_id.page_map import encode_points, render_map

from .embeddings_fixture import TREE, pool_frame


def write_site(root, tree=TREE, pool=None):
    blobs, meta = encode_points(pool_frame(np.arange(1, 301)) if pool is None else pool, tree)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    return meta


def test_build_inlines_everything_and_copies_the_map_meta(tmp_path):
    meta = write_site(tmp_path)
    html = tree_page.build(tmp_path).read_text()
    assert not re.findall(r"__[A-Z_]+__", html)
    assert "<script src=" not in html
    assert 'href="tree.html" aria-current="page"' in html
    cfg = json.loads(re.search(r"var CFG=(.*?);</script>", html).group(1))
    assert cfg["meta"]["taxa"].startswith(meta["taxa"] + "?v=") and cfg["mapUrl"] == "map.html"
    assert cfg["meta"]["group_ids"] == meta["group_ids"]


def test_without_the_map_it_says_to_build_the_map_first(tmp_path):
    with pytest.raises(FileNotFoundError, match="build the map first"):
        tree_page.build(tmp_path)


def test_a_taxa_file_without_counts_is_refused(tmp_path):
    meta = write_site(tmp_path)
    taxa = tmp_path / meta["taxa"].split("?")[0]
    rows = [r[:5] for r in json.loads(gzip.decompress(taxa.read_bytes()))]
    taxa.write_bytes(gzip.compress(json.dumps(rows).encode()))
    with pytest.raises(ValueError, match="--tree"):
        tree_page.build(tmp_path)


def test_every_page_offers_the_tree_and_only_when_built():
    assert 'href="tree.html"' in page_nav.nav("split.html", set(dict(page_nav.PAGES)))
    html = page_nav.nav("map.html")
    assert re.search(r'href="tree.html"[^>]*data-optional', html) and "data-probe" in html


def test_the_split_page_offers_the_tree_only_once_it_is_built(tmp_path):
    html = split_page.build(tmp_path).read_text()
    assert 'data-v="tree"' not in html and 'href="tree.html"' not in html and "tree:null" in html
    write_site(tmp_path)
    tree_page.build(tmp_path)
    html = split_page.build(tmp_path).read_text()
    assert 'data-v="tree"' in html and 'href="tree.html"' in html and 'tree:"tree.html"' in html


def test_the_split_page_links_an_optional_page_only_once_it_is_built(tmp_path):
    assert 'href="confusion.html"' not in split_page.build(tmp_path).read_text()
    (tmp_path / "confusion.html").write_text("<html></html>")
    assert 'href="confusion.html"' in split_page.build(tmp_path).read_text()
