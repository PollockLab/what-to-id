"""The tree of life page in Chromium, with iNaturalist stubbed: it draws, selects, opens by key and
fetches tip photos. Its split-view pane is covered in test_split_subsets_browser.py."""

import functools
import gzip
import http.server
import json
import threading
from urllib.parse import urlparse

import numpy as np
import pytest

from what_to_id import tree_page
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import pool_frame
from .test_atlas_search_browser import PNG
from .test_tree_page import write_site

browser = eb.browser


def stub_taxa(page):
    """iNaturalist's taxa endpoint, every asked id with a default photo. Returns the id lists."""
    calls = []

    def taxa(route):
        ids = [int(i) for i in urlparse(route.request.url).path.rsplit("/", 1)[1].split(",")]
        calls.append(ids)
        photo = {
            "square_url": "https://static.inaturalist.org/p/1/square.jpg",
            "attribution": "(c) x",
        }
        results = [{"id": i, "default_photo": photo} for i in ids]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/taxa/**", taxa)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=PNG, content_type="image/png")
    )
    return calls


def serve(root):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("tree-site")
    write_site(root)
    tree_page.build(root)
    server, url = serve(root)
    yield url
    server.shutdown()


# Life > Animalia > Aves > a robin, and Life > Bacteria: 20 birds, then 20 Unknown records, 10 in
# Bacteria, 5 identified only to Life and 5 with no taxon
LIFE_TREE = {
    2000: [3, "Turdus migratorius", "American Robin", "species"],
    3: [1, "Aves", "Birds", "class"],
    1: [48460, "Animalia", "Animals", "kingdom"],
    48460: [None, "Life", "Life", "stateofmatter"],
    67333: [48460, "Bacteria", "", "kingdom"],
}


@pytest.fixture(scope="module")
def life_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("tree-life")
    pool = pool_frame(np.arange(1, 41))
    pool["taxon_id"] = [2000] * 20 + [67333] * 10 + [48460] * 5 + [None] * 5
    pool["taxon_name"] = ["x"] * 35 + [None] * 5
    pool["iconic_taxon"] = ["Aves"] * 20 + [None] * 20
    blobs, meta = encode_points(pool, LIFE_TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    tree_page.build(root)
    server, url = serve(root)
    yield url
    server.shutdown()


def open_tree(browser, site, w=1280, h=800, hash_=""):
    page = browser.new_page(viewport={"width": w, "height": h})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.calls = stub_taxa(page)
    page.goto(f"{site}/tree.html{hash_}")
    page.wait_for_selector("#outline [role=treeitem]")
    return page


def test_draws_the_tree_and_the_outline(browser, site):
    page = open_tree(browser, site)
    items = page.locator("#outline [role=treeitem] .nm").all_inner_texts()
    assert any("Genus A" in t for t in items) and any("Genus B" in t for t in items)
    assert page.locator("#svg .nd").count() >= 3 and page.locator("#svg .lk").count() >= 2
    assert page.inner_text("#status") == ""
    page.wait_for_selector("#svg image")  # a tip with room shows its photo once it has loaded
    assert page.errors == []
    page.close()


def test_a_click_selects_and_the_card_links_out(browser, site):
    page = open_tree(browser, site)
    page.locator("#outline .nm", has_text="Genus A").click()
    page.wait_for_selector("#card:not([hidden])")
    assert "Genus A" in page.inner_text("#card h2")
    assert page.get_attribute("#card a:has-text('Show on map')", "href") == "map.html#taxa=900"
    ident = page.get_attribute("#card a:has-text('Help identify')", "href")
    assert "taxon_id=900" in ident and "place_id=" in ident
    assert "sel=900" in page.evaluate("location.hash")
    page.wait_for_selector("#card .kids .th img")  # the tips' photos, from the stubbed taxa API
    assert all(len(ids) <= 30 for ids in page.calls)
    page.go_back()
    page.wait_for_selector("#card", state="hidden")
    assert page.errors == []
    page.close()


def test_the_outline_works_by_keyboard(browser, site):
    page = open_tree(browser, site)
    first = page.locator("#outline [role=treeitem]").first
    assert first.get_attribute("tabindex") == "0"
    first.focus()
    page.keyboard.press("ArrowDown")
    key = page.evaluate("document.activeElement.dataset.k")
    assert key and key != first.get_attribute("data-k")
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.getAttribute('aria-selected')") == "true"
    assert page.errors == []
    page.close()


def test_a_hash_reopens_the_selection(browser, site):
    page = open_tree(browser, site, hash_="#sel=1003")
    page.wait_for_selector("#card:not([hidden])")
    assert "Taxon 3" in page.inner_text("#card h2")
    sel = page.locator("#outline [aria-selected=true] .nm").inner_text()
    assert "Taxon 3" in sel
    page.close()


def test_a_phone_shows_the_outline_and_switches_to_the_radial_tree(browser, site):
    page = open_tree(browser, site, 390, 800)
    assert page.locator("#side").is_visible() and page.locator("#radial").is_hidden()
    page.click("#mode")
    page.wait_for_selector("#svg .nd")
    assert page.locator("#radial").is_visible() and page.locator("#side").is_hidden()
    assert page.errors == []
    page.close()


def test_the_page_names_the_missing_tree(browser, site):
    page = browser.new_page()
    old = gzip.compress(json.dumps([["x", "", 1, 0, -1]]).encode())  # no counts
    page.route("**/pool-taxa.bin*", lambda r: r.fulfill(body=old))
    page.goto(f"{site}/tree.html")
    page.wait_for_function("document.getElementById('status').textContent.includes('without')")
    page.close()


def test_the_root_is_life_and_the_group_cards_link_to_their_records(browser, life_site):
    page = open_tree(browser, life_site, hash_="#sel=0")
    page.wait_for_selector("#card:not([hidden])")
    assert page.inner_text("#card h2") == "Life" and "40" in page.inner_text("#card dl")
    page.close()
    page = open_tree(browser, life_site, hash_="#sel=48460")
    page.wait_for_selector("#card:not([hidden])")
    assert page.inner_text("#card h2") == "Unknown"
    assert page.inner_text("#card .body > p.muted") == (
        "Records not identified past Life, or with no taxon."
    )
    dl = page.locator("#card dd").all_inner_texts()
    assert dl[:3] == ["20", "5 (25%)", "5"]  # need an ID, only to Life, no taxon
    assert "No taxon" in page.inner_text("#card dl")
    ident = page.get_attribute("#card a:has-text('Help identify')", "href")
    assert "iconic_taxa=unknown" in ident and "taxon_id" not in ident  # not all of Life
    on_map = page.get_attribute("#card a:has-text('Show on map')", "href")
    assert on_map == "map.html#groups=Unknown"
    page.close()
    page = open_tree(browser, life_site, hash_="#sel=3")
    page.wait_for_selector("#card:not([hidden])")
    ident = page.get_attribute("#card a:has-text('Help identify')", "href")
    assert "iconic_taxa=Aves" in ident and "taxon_id" not in ident
    assert "No taxon" not in page.inner_text("#card dl")
    assert page.errors == []
    page.close()
