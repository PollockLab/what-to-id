"""Explore as the home page in Chromium: the real map beside a stand-in Identify page, over the
stand-ins for MapLibre and deck.gl that test_map_groups_browser.py uses, so it runs offline. Beside
Identify the map's dots take the Identify levels' colours."""

import functools
import gzip
import http.server
import threading

import numpy as np
import pytest

from what_to_id import split_page
from what_to_id.page_identify import LEVELS
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from . import test_map_groups_browser as mg
from .embeddings_fixture import TREE, pool_frame

browser = eb.browser
N = 300
# the overlay keeps its layers, so a test can read the dots' colours
STUB = mg.STUB.replace(
    "MapboxOverlay: class { setProps() {} }",
    "MapboxOverlay: class { setProps(p) { window.__layers = p.layers; } }",
)
IDENTIFY = '<!doctype html><title>Identify</title><p id="status">300 to identify</p>'
GREEN, GREY = [0, 158, 115, 170], [150, 150, 150, 60]  # level 1 and no level, as in level_colour.js


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("explore-home")
    pool = pool_frame(range(1, N + 1))
    pool["iconic_taxon"] = [g for g, n in mg.SIZES.items() for _ in range(n)]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    # record i at level i % 6: none, the four levels, and 5 before the page names it
    (root / "pool-levels.bin").write_bytes(gzip.compress((np.arange(N) % 6).astype("u1").tobytes()))
    (root / "identify.html").write_text(IDENTIFY)
    split_page.build(root)
    served = []

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            served.append(self.path)

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", served
    server.shutdown()


def open_page(browser, url, width=1280):
    p = browser.new_page(viewport={"width": width, "height": 900})
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )
    p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    p.goto(url)
    return p


def map_frame(page):
    page.wait_for_function(
        "document.getElementById('map')?.contentDocument?.getElementById('count')?.textContent"
        ".startsWith('300 ')"
    )
    return next(f for f in page.frames if "map.html" in f.url)


# the fill colours of records 0, 1 and 5, and whether the legend shows
COLOURS = """() => { const c = window.__layers[0].props.data.attributes.getFillColor.value,
  at = i => Array.from(c.slice(4 * i, 4 * i + 4)), l = document.querySelector('.lvleg');
  return {c0: at(0), c1: at(1), c5: at(5), legend: !!l && !l.hidden,
    names: l ? [...l.querySelectorAll('span')].map(s => s.textContent) : []}; }"""


def test_beside_identify_the_dots_take_the_level_colours_and_go_back_without_it(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    frame.wait_for_function(f"({COLOURS})().legend")
    got = frame.evaluate(COLOURS)
    assert got["c0"] == GREY and got["c1"] == GREEN  # no level is faint grey, still drawn
    assert got["c5"] not in (GREY, GREEN) and got["c5"][3] > GREY[3]  # level 5 has its own colour
    assert got["names"] == [name for _, name, _ in LEVELS] + ["No level"]
    page.click("[data-p=identify]")  # the map alone: the group colours again
    frame.wait_for_function(f"!({COLOURS})().legend")
    got = frame.evaluate(COLOURS)
    assert got["c1"][3] == 110 and got["c1"] != GREEN
    page.click("[data-p=identify]")
    frame.wait_for_function(f"({COLOURS})().legend")
    assert page.errors == []
    page.close()


def test_the_standalone_map_keeps_the_group_colours_and_never_loads_the_levels(browser, site):
    base, served = site
    served.clear()
    page = open_page(browser, f"{base}/map.html?standalone=1")
    page.wait_for_function("document.getElementById('count').textContent.startsWith('300 ')")
    got = page.evaluate(COLOURS)
    assert got["c1"][3] == 110 and not got["legend"]
    assert not any("pool-levels.bin" in s for s in served)
    assert page.errors == []
    page.close()
