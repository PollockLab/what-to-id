"""The map's record card in Chromium: its closest matches (thumbnails and numbered dots), its range
chip, and the Identify pane opening it. MapLibre and deck.gl come from the CDN, so this runs with
-m network. The basemap is blank and iNaturalist is stubbed."""

import functools
import http.server
import re
import threading
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest

from what_to_id import split_page
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from . import test_identify_ranges_browser as rb
from .atlas_index_fixture import write_fixture
from .embeddings_fixture import TREE, pool_frame
from .test_atlas_search_browser import PNG, RangeHandler

pytestmark = pytest.mark.network
browser = eb.browser
BLANK = '{"version":8,"sources":{},"layers":[]}'
# the layers the map last gave deck.gl, to read the numbered dots (deck loads after the page starts)
HOOK = """(() => { const t = setInterval(() => { const O = window.deck && deck.MapboxOverlay;
  if (!O) return; clearInterval(t); const f = O.prototype.setProps;
  O.prototype.setProps = function (p) { if (p && p.layers) window.__layers = p.layers;
    return f.call(this, p); }; }, 1); })()"""


def serve(root, handler=RangeHandler):
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(handler, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="module")
def atlas_site(tmp_path_factory):
    """A map whose card reads the closest matches of the faiss fixture's index."""
    pytest.importorskip("faiss")
    root = tmp_path_factory.mktemp("map-card-atlas")
    ref = write_fixture(root / "atlas")
    ids = np.random.default_rng(1).choice(2**32 - 2, eb.TOTAL, replace=False) + 1  # as the fixture
    in_pool = set(ids[: eb.POOL_N].tolist())
    blobs, meta = encode_points(pool_frame(ids[: eb.POOL_N]), TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None, data_url="atlas/"))
    source = next(x for x in ref["lookups"] if x["id"] in in_pool and x["neighbors"])
    server = serve(root)
    yield f"http://127.0.0.1:{server.server_port}", source["id"], source["neighbors"][0], in_pool
    server.shutdown()


@pytest.fixture(scope="module")
def range_site(tmp_path_factory):
    """The Identify range fixture's ten records, with the map, Identify and Explore pages."""
    root = tmp_path_factory.mktemp("map-card-ranges")
    rb.write_site(root)
    split_page.build(root)
    server = serve(root, rb.ib.Quiet)
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def stub(page):
    """Every observation needs an ID and has a photo; the basemap is blank."""

    def inat(route):
        url = urlparse(route.request.url)
        ids = parse_qs(url.query).get("id", [url.path.rsplit("/", 1)[1]])[0].split(",")
        results = [
            {
                "id": int(i),
                "quality_grade": "needs_id",
                "observed_on": "2026-05-01",
                "place_guess": "Vancouver, BC",
                "photos": [{"url": f"https://static.inaturalist.org/photos/{i}/square.jpg"}],
                "taxon": {"name": f"Taxon {i}", "preferred_common_name": f"Common {i}"},
            }
            for i in ids
        ]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    page.route(re.compile(r"https://api\.inaturalist\.org/v1/observations.*"), inat)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=PNG, content_type="image/png")
    )
    page.route("https://basemaps.cartocdn.com/**", lambda r: r.fulfill(body=BLANK))


def open_map(browser, url, width=1280):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub(page)
    page.add_init_script(HOOK)
    page.goto(url)
    return page


def layer(page, name):
    return page.evaluate(
        "n => { const l = (window.__layers || []).find(x => x.id === n);"
        " return l && l.props.data.length; }",
        name,
    )


def card_id(page):
    return int(page.locator("#card a.btn").get_attribute("href").rsplit("/", 1)[1])


def test_the_card_lists_its_closest_matches_and_a_click_opens_that_record(browser, atlas_site):
    base, mine, want, in_pool = atlas_site
    page = open_map(browser, f"{base}/map.html?standalone=1#record={mine}&at=9/49/-123")
    page.wait_for_selector("#nbrs button")
    assert card_id(page) == mine
    buttons = page.locator("#nbrs button")
    assert [int(b.get_attribute("data-id")) for b in buttons.all()] == want
    assert page.locator("#nbrs .rank").all_inner_texts() == [str(k + 1) for k in range(len(want))]
    link = page.locator("#nbrs a", has_text="More like this")
    assert link.get_attribute("href") == f"search.html#id={mine}"
    on_map = [i for i in want if i in in_pool]
    assert on_map and layer(page, "nbr") == len(on_map) and layer(page, "nbr-rank") == len(on_map)
    target = on_map[0]
    page.locator(f"#nbrs button[data-id='{target}']").click()
    page.wait_for_function(f"document.querySelector('#card a.btn').href.endsWith('/{target}')")
    page.wait_for_function(f"location.hash.includes('record={target}')")
    page.wait_for_selector("#nbrs button")
    assert page.locator("#card").is_visible() and layer(page, "sel") is not None
    page.keyboard.press("Escape")
    assert page.locator("#card").is_hidden() and layer(page, "nbr") is None
    assert not any(w in page.inner_text("body").lower() for w in rb.FORBIDDEN)
    assert page.errors == []
    page.close()


def test_a_card_without_neighbour_data_hides_the_section(browser, atlas_site, range_site):
    base, mine, *_ = atlas_site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub(page)
    page.route("**/atlas/manifest.json", lambda r: r.fulfill(status=404))
    page.goto(f"{base}/map.html?standalone=1#record={mine}&at=9/49/-123")
    page.wait_for_selector("#card .ph img")
    page.wait_for_timeout(500)
    assert page.locator("#nbrs").is_hidden() and page.locator("#nbrs button").count() == 0
    page.close()
    page = open_map(browser, f"{range_site}/map.html?standalone=1#record=3000&at=9/49/-123")
    page.wait_for_selector("#card .ph img")  # a map built without an index has no matches either
    assert page.locator("#nbrs").is_hidden()
    assert page.errors == []
    page.close()


def test_the_card_has_a_range_chip_that_opens_the_map_on_hover_and_closes_on_escape(
    browser, range_site
):
    page = open_map(browser, f"{range_site}/map.html?standalone=1#record=3000&at=9/49/-123")
    chip = page.locator("#card .rchip")
    chip.wait_for()
    assert chip.inner_text() == "About 1,200 km outside" and "bad" in chip.get_attribute("class")
    pop = page.locator("#rpop")
    chip.hover()
    pop.wait_for(state="visible")
    assert pop.locator("canvas").get_attribute("aria-label") == (
        "Range map: this record is outside the range of Taxon 2. "
        "About 1,200 km outside the label's usual range."
    )
    assert pop.locator(".rleg").inner_text().split("\n") == ["Taxon 2", "this record"]
    page.keyboard.press("Escape")
    assert pop.is_hidden() and page.locator("#card").is_visible()  # the first Escape is the map's
    page.keyboard.press("Escape")
    assert page.locator("#card").is_hidden()
    page.locator("#rpop").evaluate("e => e.remove()")
    assert page.errors == []
    page.close()


def test_the_chip_moves_with_the_card_and_is_absent_without_the_range_file(browser, range_site):
    page = open_map(browser, f"{range_site}/map.html?standalone=1#record=1000&at=9/49/-123")
    page.locator("#card .rchip").wait_for()
    assert page.locator("#card .rchip").inner_text() == "In range"
    page.locator("#card .rchip").hover()
    page.locator("#rpop").wait_for(state="visible")
    page.evaluate("document.querySelector('#card .x').click()")
    page.locator("#rpop").wait_for(state="hidden")  # the popover goes with its card
    page.close()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub(page)
    page.route("**/pool-levels-range.bin*", lambda r: r.fulfill(status=404))
    with page.expect_response(lambda r: "pool-levels-range" in r.url):
        page.goto(f"{range_site}/map.html?standalone=1#record=3000&at=9/49/-123")
    page.wait_for_selector("#card .ph img")
    page.wait_for_timeout(300)
    assert page.locator("#card").is_visible() and page.locator(".rchip").count() == 0
    assert page.errors == []
    page.close()


def test_an_identify_card_click_opens_the_map_card_but_hover_does_not(browser, range_site):
    page = open_map(browser, f"{range_site}/explore.html")
    page.wait_for_function(
        "() => { const d = document.getElementById('identify')?.contentDocument;"
        " return d && d.querySelectorAll('#grid .card').length > 0; }",
        timeout=60000,
    )
    ident = next(f for f in page.frames if f.url.split("?")[0].endswith("/identify.html"))
    left = next(f for f in page.frames if f.url.split("?")[0].endswith("/map.html"))
    left.wait_for_function("/records$|of 10/.test(document.getElementById('count').textContent)")
    card = ident.locator("#grid .card").first
    want = int(card.get_attribute("data-id"))
    card.hover()
    page.wait_for_timeout(400)
    assert left.locator("#card").is_hidden()
    card.locator(".title").click()
    left.locator("#card").wait_for(state="visible")
    assert int(left.locator("#card a.btn").get_attribute("href").rsplit("/", 1)[1]) == want
    assert page.errors == []
    page.close()
