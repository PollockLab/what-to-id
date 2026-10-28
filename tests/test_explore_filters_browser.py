"""The map inside Explore in Chromium, over the stand-ins for MapLibre and deck.gl that
test_map_groups_browser.py uses: the scope switch and the top bar's filter line."""

import functools
import http.server
import threading

import pytest

from what_to_id import split_page
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_map_groups_browser import SIZES, STUB

browser = eb.browser
COUNTS = "document.getElementById('counts').textContent"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("explore-filters")
    pool = pool_frame(range(1, 301))
    pool["iconic_taxon"] = [g for g, n in SIZES.items() for _ in range(n)]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    split_page.build(root)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/explore.html?view=map"
    server.shutdown()


@pytest.fixture
def open_page(browser, site):
    pages = []

    def go(hash_="", width=1280):
        p = browser.new_page(viewport={"width": width, "height": 800})
        p.errors = []
        p.on("pageerror", lambda e: p.errors.append(str(e)))
        p.route(
            "https://unpkg.com/**",
            lambda r: r.fulfill(
                body=STUB if r.request.url.endswith(".js") else "",
                content_type="text/javascript",
            ),
        )
        p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
        p.goto(site + hash_)
        p.wait_for_function(f"/on map/.test({COUNTS}) && /\\d/.test({COUNTS})")
        pages.append(p)
        return p, next(f for f in p.frames if "/map.html" in f.url)

    yield go
    for p in pages:
        assert p.errors == []
        p.close()


def test_all_of_bc_counts_everything_and_drops_in_view_from_the_top_bar(open_page):
    page, frame = open_page()
    # the stand-in map shows the whole world, so a view is posted as the real map would send it
    frame.evaluate("parent.postMessage({type: 'wtid-view', area: 'abc'}, location.origin)")
    page.wait_for_function(f"/in view/.test({COUNTS})")
    frame.get_by_role("button", name="All of BC").click()
    page.wait_for_function(f"!/in view/.test({COUNTS})")
    assert frame.get_by_role("button", name="In view").get_attribute("aria-pressed") == "false"
    assert frame.locator("#count").inner_text() == "300 of 300 records"
    assert page.evaluate("document.getElementById('xbar').getBoundingClientRect().height") <= 40
    head = "document.querySelector('header')"
    assert frame.evaluate(f"{head}.scrollWidth <= {head}.clientWidth")
