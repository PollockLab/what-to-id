"""The Life groups setting in every view in Chromium: by default (iNaturalist) Identify, the map,
the photo space, the tree and Explore show one Plants group and never the split plant groups; with
plants=split they show the three; a switch in one Explore pane switches the others."""

import functools
import http.server
import json
import threading

import numpy as np
import pytest

from what_to_id import tree_page
from what_to_id.embeddings_page import build as build_space
from what_to_id.split_page import build as build_split

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .atlas_index_fixture import FIXTURE_ROWS, write_fixture
from .embeddings_fixture import BBOX, pool_frame, write_layout
from .test_atlas_search_browser import PNG, RangeHandler
from .test_map_groups_browser import STUB

browser = eb.browser
CYCLE = ["Tracheophyta", "Bryophytes", "Algae", "Insecta", "Aves"]
SPLIT = ["Vascular plants", "Mosses, liverworts and hornworts", "Green and red algae"]
# both the map's and the photo space's stand-ins, whichever script a page asks unpkg for
JS = STUB + eb.DECK_STUB + "window.deck.MapboxOverlay = class { setProps() {} };"
# a view's own words: the page less its scripts and styles (map_groups.js names the split groups)
TEXT = """s => { const b = document.querySelector(s).cloneNode(true);
  b.querySelectorAll('script,style,template').forEach(e => e.remove()); return b.textContent; }"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("faiss")
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("plants-everywhere")
    atlas = root / "atlas"
    write_fixture(atlas)
    ids = np.random.default_rng(1).choice(2**32 - 2, eb.TOTAL, replace=False) + 1
    xy = np.random.default_rng(5).uniform(BBOX[:2], BBOX[2:], (eb.TOTAL, 2))
    manifest = json.loads((atlas / "manifest.json").read_text())
    write_layout(
        atlas,
        {
            "layout-base-20261025": (ids[:FIXTURE_ROWS], xy[:FIXTURE_ROWS]),
            "layout-delta-20260101-0000": (ids[FIXTURE_ROWS:], xy[FIXTURE_ROWS:]),
        },
        manifest,
    )
    pool = pool_frame(ids[: eb.POOL_N])
    pool["iconic_taxon"] = [CYCLE[i % len(CYCLE)] for i in range(len(pool))]
    score = np.random.default_rng(2).normal(size=len(pool)).astype("float32")
    plain, _ = ib.serve(root, pool, score)  # the map, the levels and Identify
    plain.shutdown()
    build_space(root, data_url="atlas/")
    tree_page.build(root)
    build_split(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(RangeHandler, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def open_page(browser, site):
    pages = []

    def opener(path, width=1280):
        p = browser.new_page(viewport={"width": width, "height": 900})
        p.errors = []
        p.on("pageerror", lambda e: p.errors.append(str(e)))
        p.route(
            "https://unpkg.com/**", lambda r: r.fulfill(body=JS, content_type="text/javascript")
        )
        p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
        p.route("https://static.inaturalist.org/**", lambda r: r.fulfill(body=PNG))
        p.goto(f"{site}/{path}")
        pages.append(p)
        return p

    yield opener
    for p in pages:
        assert p.errors == []
        p.close()


LI = "window.__identify && document.querySelector('#groups li')"
MAP = "document.querySelector('#groups .gc')?.textContent"
SPACE = "document.querySelector('#groups [data-g]')"
# (view, its address, a test that its groups are in, the element that lists them)
VIEWS = [
    ("identify", "identify.html?", LI, "#groups"),
    ("map", "map.html?standalone=1&", MAP, "#groups"),
    ("space", "embeddings.html?standalone=1&", SPACE, "#groups"),
    ("tree", "tree.html?standalone=1&", "document.querySelector('#outline li')", "#outline"),
]


@pytest.mark.parametrize(("view", "path", "ready", "box"), VIEWS, ids=[v[0] for v in VIEWS])
def test_every_view_shows_one_plants_group_by_default_and_three_when_split(
    open_page, view, path, ready, box
):
    page = open_page(path)
    page.wait_for_function(ready)
    assert page.evaluate("MapGroups.current") == "inat"
    text = page.evaluate(TEXT, box)
    assert not [s for s in SPLIT if s in text]
    if view != "tree":  # the fixture's taxa table holds no plant, so the tree lists no plant group
        assert "Plants" in text
    split = open_page(path + "plants=split")
    split.wait_for_function(ready)
    assert split.evaluate("MapGroups.current") == "split"
    if view != "tree":
        text = split.evaluate(TEXT, box)
        assert all(s in text for s in SPLIT)


def test_identify_totals_and_a_split_link_read_as_plants(open_page):
    page = open_page("identify.html#groups=Tracheophyta")
    page.wait_for_function(LI)
    text = page.evaluate(TEXT, "#groups")
    assert "Plants" in text and not [s for s in SPLIT if s in text]
    page.wait_for_function("document.querySelector('#groups .gb[aria-pressed=true] .nm')")
    assert page.locator("#groups .gb[aria-pressed=true] .nm").text_content() == "Plants"
    assert page.locator("#gmode button[aria-pressed=true]").text_content() == "iNaturalist"


def mode_of(page, pane):
    return page.evaluate(
        "n => { const w = document.getElementById(n)?.contentWindow;"
        " return w && w.MapGroups && w.MapGroups.current; }",
        pane,
    )


def test_a_switch_in_one_explore_pane_switches_the_others_and_the_address(open_page):
    page = open_page("explore.html?view=identify-map&plants=inat")
    page.wait_for_function("document.querySelectorAll('iframe').length === 2")
    for n in ("identify", "map"):
        page.wait_for_function(f"document.getElementById('{n}').contentWindow.MapGroups?.current")
    assert {mode_of(page, n) for n in ("identify", "map")} == {"inat"}
    map_ = next(f for f in page.frames if "/map.html" in f.url)
    map_.wait_for_function("document.querySelector('#groups .gc')?.textContent")
    map_.locator("#gmode button[data-m=split]").click()
    page.wait_for_function("location.search.includes('plants=split')")
    for n in ("identify", "map"):
        page.wait_for_function(
            f"document.getElementById('{n}').contentWindow.MapGroups?.current === 'split'"
        )
    page.evaluate("localStorage.removeItem('wtid-plants')")
