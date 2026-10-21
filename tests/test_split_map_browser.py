"""The real map in the split view, picked from the tree: MapLibre and deck.gl come from the CDN, so
this runs with -m network. The basemap is a blank style, so no tiles load."""

import functools
import http.server
import threading

import pytest

from what_to_id import split_page, tree_page
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_tree_browser import stub_taxa

pytestmark = pytest.mark.network
browser = eb.browser
PAD = 40  # map.js fitTo's padding

# Taxon 6 keeps two records far apart, Taxon 4 one; the rest go to their genus siblings
SPREAD = [(-124.0, 48.6), (-122.5, 49.4)]
ONE = (-123.2, 49.1)
BLANK = '{"version":8,"sources":{},"layers":[]}'
# every MapLibre map a frame makes, so the test can project points with it
HOOK = """(() => { let lib; Object.defineProperty(window, 'maplibregl', {configurable: true,
  get: () => lib, set: v => { const M = v.Map; v.Map = class extends M {
    constructor(o) { super(o); window.__map = this; } }; lib = v; }}); })()"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("split-map")
    pool = pool_frame(range(1, 301))
    six, four = pool.index[pool.taxon_id == 1006], pool.index[pool.taxon_id == 1004]
    pool.loc[six[2:], ["taxon_id", "taxon_name"]] = [1005, "Taxon 5"]
    pool.loc[four[1:], ["taxon_id", "taxon_name"]] = [1003, "Taxon 3"]
    pool.loc[six[:2], ["lon", "lat"]] = SPREAD
    pool.loc[four[:1], ["lon", "lat"]] = [ONE]
    pool["pos_acc"] = [50 if i % 2 else 5000 for i in range(300)]  # 150 within 100 m
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    tree_page.build(root)
    split_page.build(root)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.parametrize(("name", "points"), [("Taxon 6", SPREAD), ("Taxon 4", [ONE])])
def test_a_tiny_taxon_picked_in_the_tree_fits_the_map_pane(browser, site, name, points):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_taxa(page)
    page.route("https://basemaps.cartocdn.com/**", lambda r: r.fulfill(body=BLANK))
    page.add_init_script(HOOK)
    page.goto(f"{site}/split.html")
    page.wait_for_function(
        "() => { const d = document.getElementById('map')?.contentDocument;"
        " return d && /^300 of 300/.test(d.getElementById('count').textContent); }",
        timeout=60000,
    )
    tree = next(f for f in page.frames if "tree.html" in f.url)
    left = next(f for f in page.frames if "map.html" in f.url)
    tree.locator("#q").fill(name)
    tree.locator("#sugg li").first.wait_for()
    tree.locator("#q").press("Enter")
    left.wait_for_function(
        f"/^{len(points)} of 300/.test(document.getElementById('count').textContent)"
    )
    left.wait_for_function("window.__map && !__map.isMoving()", polling=200)
    left.wait_for_timeout(300)
    got = left.evaluate(
        "pts => { const c = __map.getContainer(); return {w: c.clientWidth, h: c.clientHeight,"
        " win: innerWidth, at: pts.map(p => [__map.project(p).x, __map.project(p).y])}; }",
        points,
    )
    assert got["w"] <= got["win"] < 1400  # the map pane of the split, not the window
    xs, ys = [x for x, _ in got["at"]], [y for _, y in got["at"]]
    assert min(xs) >= PAD - 1 and max(xs) <= got["w"] - PAD + 1, got
    assert min(ys) >= PAD - 1 and max(ys) <= got["h"] - PAD + 1, got
    # the points' box is centred, a single point in the middle
    assert abs((min(xs) + max(xs)) / 2 - got["w"] / 2) < 2, got
    assert abs((min(ys) + max(ys)) / 2 - got["h"] / 2) < 2, got
    assert page.errors == []
    page.close()


def test_an_accuracy_choice_sent_by_the_other_frame_reaches_the_map(browser, site):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_taxa(page)
    page.route("https://basemaps.cartocdn.com/**", lambda r: r.fulfill(body=BLANK))
    page.goto(f"{site}/split.html")
    page.wait_for_function(
        "() => { const d = document.getElementById('map')?.contentDocument;"
        " return d && /^300 of 300/.test(d.getElementById('count').textContent); }",
        timeout=60000,
    )
    left = next(f for f in page.frames if "map.html" in f.url)
    page.evaluate(
        "document.querySelector('#map').contentWindow.postMessage("
        "{type: 'wtid-selection', sel: 'acc=100'}, location.origin)"
    )
    left.wait_for_function("/^150 of 300/.test(document.getElementById('count').textContent)")
    assert left.locator("#acc button[aria-pressed=true]").inner_text() == "Within 100 m"
    assert page.errors == []
    page.close()
