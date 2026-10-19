"""Photo-space page in Chromium: layout parts and the map's shards on a Range-capable server.

The iNaturalist API is stubbed and deck.gl is replaced by a recorder (the CDN build needs WebGL).
"""

import functools
import http.server
import json
import os
import threading
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest

from what_to_id.embeddings_page import build
from what_to_id.page_map import encode_points, render_map

from .atlas_index_fixture import FIXTURE_DELTA, FIXTURE_ROWS, write_fixture
from .embeddings_fixture import BBOX, GROUPS, pool_frame, write_layout
from .test_atlas_search_browser import PNG, RangeHandler

TOTAL = FIXTURE_ROWS + FIXTURE_DELTA
POOL_N = 2100  # the pool lacks the last 100 indexed observations, as if they had left Needs ID

DECK_STUB = """
window.deck = {
  Deck: class { constructor(p) { this.props = p; window.__deck = this; }
    setProps(p) { Object.assign(this.props, p); } },
  OrthographicView: class { constructor(p) { this.props = p; } },
  ScatterplotLayer: class { constructor(p) { this.props = p; this.id = p.id; } },
  DataFilterExtension: class { initializeState() {} },
};"""


@pytest.fixture(scope="module")
def browser():
    required = os.environ.get("WHAT_TO_ID_REQUIRE_BROWSER") == "1"
    api = __import__("playwright.sync_api").sync_api if required else None
    if not required:
        api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as pw:
        try:
            instance = pw.chromium.launch()
        except Exception as error:
            if required:
                pytest.fail(f"Required Chromium unavailable: {error}")
            pytest.skip(f"Chromium unavailable: {error}")
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("faiss")
    root = tmp_path_factory.mktemp("embeddings-site")
    atlas = root / "atlas"
    ref = write_fixture(atlas)
    ids = np.random.default_rng(1).choice(2**32 - 2, TOTAL, replace=False) + 1  # as the fixture
    rng = np.random.default_rng(5)
    xy = np.column_stack(
        [rng.uniform(BBOX[0], BBOX[2], TOTAL), rng.uniform(BBOX[1], BBOX[3], TOTAL)]
    )
    manifest = json.loads((atlas / "manifest.json").read_text())
    layout = write_layout(
        atlas,
        {
            "layout-base-20261025": (ids[:FIXTURE_ROWS], xy[:FIXTURE_ROWS]),
            "layout-delta-20260101-0000": (ids[FIXTURE_ROWS:], xy[FIXTURE_ROWS:]),
        },
        manifest,
    )
    pool = pool_frame(ids[:POOL_N])
    blobs, meta = encode_points(pool)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    build(root, data_url="atlas/")
    handler = functools.partial(RangeHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", ref, set(ids[:POOL_N].tolist()), layout
    server.shutdown()


def stub_inat(page, drop):
    """Every observation needs an ID with a photo, except `drop`, which is Research Grade."""
    calls = []

    def observations(route):
        ids = [int(i) for i in parse_qs(urlparse(route.request.url).query)["id"][0].split(",")]
        calls.append(ids)
        results = [
            {
                "id": i,
                "quality_grade": "research" if i == drop else "needs_id",
                "observed_on": "2026-05-01",
                "place_guess": "Vancouver, BC",
                "photos": [{"url": f"https://static.inaturalist.org/photos/{i}/square.jpg"}],
                "taxon": {"name": f"Taxon {i}", "preferred_common_name": f"Common {i}"},
            }
            for i in ids
        ]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=PNG, content_type="image/png")
    )
    page.route(
        "https://unpkg.com/**", lambda r: r.fulfill(body=DECK_STUB, content_type="text/javascript")
    )
    return calls


@pytest.fixture
def open_page(browser, site):
    base, ref, _, _ = site
    pages = []

    def opener(hash_="", drop=None, width=1280):
        page = browser.new_page(viewport={"width": width, "height": 900})
        pages.append(page)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: page.errors.append(f"failed {r.url}"))
        page.calls = stub_inat(page, drop)
        page.goto(f"{base}/embeddings.html{hash_}")
        return page

    yield opener
    for page in pages:
        page.close()


def layer(page, name):
    return page.evaluate(
        "n => { const l = __deck.props.layers.find(x => x.id === n);"
        " return l && {n: l.props.data.length, cats: l.props.filterCategories}; }",
        name,
    )


def ready(page):
    page.wait_for_function("window.__deck && __deck.props.layers.length > 0")
    page.wait_for_function("document.getElementById('status').textContent === ''")  # shards joined


def test_points_are_the_join_of_layout_and_pool(open_page):
    page = open_page()
    ready(page)
    assert layer(page, "pts")["n"] == POOL_N  # layout holds 2150, the pool 2100: the join is 2100
    assert page.locator("#count").inner_text() == f"{POOL_N:,} shown of {POOL_N:,}"
    assert page.locator("#groups button").count() == len(GROUPS)
    text = page.locator("#honest").inner_text()
    assert "Measured on the layout" in text and "50%" in text and "12" in text
    assert "not identification confidence" in text and "lossy" in text
    assert page.locator("#intro a[href='embeddings-sample.html']").count() == 1
    assert page.errors == []


def test_group_chip_steps_pick_leave_out_clear_and_all_groups_resets(open_page):
    page = open_page()
    ready(page)
    each = POOL_N // 3
    count = page.locator("#count")
    chip = page.locator("#groups button[data-g='0']")  # Aves
    chip.click()  # picked: only Aves
    assert count.inner_text() == f"{each:,} shown of {POOL_N:,}"
    assert layer(page, "pts")["cats"][0] == [0]
    assert (
        chip.get_attribute("aria-pressed") == "true"
        and page.evaluate("location.hash") == "#groups=Aves"
    )
    chip.click()  # left out: the other two
    assert count.inner_text() == f"{POOL_N - each:,} shown of {POOL_N:,}"
    assert layer(page, "pts")["cats"][0] == [1, 2]
    assert "not " in chip.inner_text() and page.evaluate("location.hash") == "#groups=-Aves"
    chip.click()  # cleared
    assert (
        count.inner_text() == f"{POOL_N:,} shown of {POOL_N:,}"
        and page.evaluate("location.hash") == ""
    )
    chip.click()
    page.get_by_role("button", name="All groups").click()
    assert count.inner_text() == f"{POOL_N:,} shown of {POOL_N:,}"
    assert layer(page, "pts")["cats"][0] == [0, 1, 2]
    assert page.evaluate("location.hash") == ""
    assert page.errors == []


def test_groups_in_the_hash_open_filtered_and_survive_a_selection(open_page):
    page = open_page("#groups=-Aves")
    ready(page)
    assert layer(page, "pts")["cats"][0] == [1, 2]
    assert page.locator("#count").inner_text() == f"{POOL_N - POOL_N // 3:,} shown of {POOL_N:,}"
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    page.wait_for_function("/^#groups=-Aves&id=\\d+$/.test(location.hash)")
    page.keyboard.press("Escape")
    assert page.evaluate("location.hash") == "#groups=-Aves"
    assert page.errors == []


def test_fit_to_selection_is_offered_and_zooms_only_on_click(open_page):
    page = open_page()
    ready(page)
    fit = page.get_by_role("button", name="Fit to selection")
    assert fit.is_hidden()
    before = page.evaluate("__deck.props.viewState")
    page.locator("#groups button[data-g='0']").click()
    assert fit.is_visible()
    assert page.evaluate("__deck.props.viewState") == before  # never zooms on its own
    fit.click()
    after = page.evaluate("__deck.props.viewState")
    # the fixture spreads each group over the whole layout: only "refit, close to before" shows
    assert after != before and abs(after["zoom"] - before["zoom"]) < 1
    page.get_by_role("button", name="All groups").click()
    assert fit.is_hidden()
    assert page.errors == []


def test_click_opens_card_with_neighbours_and_jump(open_page, site):
    _, _, in_pool, _ = site
    page = open_page(drop=None)
    ready(page)
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    page.wait_for_selector(".nbrs button")
    assert page.locator(".nbrs button").count() == 12
    card = page.locator("#card")
    mine = int(
        card.get_by_role("link", name="More like this").get_attribute("href").split("#id=")[1]
    )
    assert card.get_by_role("link", name="Help identify on iNaturalist").get_attribute("href") == (
        f"https://www.inaturalist.org/observations/{mine}"
    )
    assert card.get_by_role("link", name="Show on map").get_attribute("href") == (
        f"map.html#record={mine}"
    )
    assert "Vancouver" in card.inner_text() and page.locator(".ph img").count() == 1
    near = [int(b.get_attribute("data-id")) for b in page.locator(".nbrs button").all()]
    assert layer(page, "nbr")["n"] == len([i for i in near if i in in_pool])
    assert layer(page, "sel")["n"] == 1
    target = next(i for i in near if i in in_pool)
    page.locator(f".nbrs button[data-id='{target}']").click()
    page.wait_for_function(f"location.hash === '#id={target}'")
    page.wait_for_function(f"document.querySelector('#card a[href$=\"#id={target}\"]')")
    page.keyboard.press("Escape")
    assert page.locator("#card").is_hidden() and layer(page, "sel") is None
    assert page.errors == []


def test_deep_link_lists_the_exact_neighbours_and_drops_those_that_left_needs_id(open_page, site):
    _, ref, _, _ = site
    source = ref["lookups"][0]
    want = source["neighbors"][0]
    page = open_page(f"#id={source['id']}", drop=want[3])
    page.wait_for_selector(".nbrs button")
    got = [int(b.get_attribute("data-id")) for b in page.locator(".nbrs button").all()]
    assert got == [i for i in want if i != want[3]]
    assert "1 no longer need an ID" in page.locator("#card").inner_text()
    assert page.calls == [[source["id"], *want]]
    assert page.errors == []


def test_missing_layout_says_so(browser, site):
    base, *_ = site
    page = browser.new_page()
    try:
        page.on("pageerror", lambda e: pytest.fail(str(e)))

        def without_layout(route):
            manifest = json.loads(route.fetch().text())
            manifest.pop("layout")
            route.fulfill(json=manifest)

        page.route("**/atlas/manifest.json", without_layout)
        page.route("https://unpkg.com/**", lambda r: r.fulfill(body=DECK_STUB))
        page.goto(f"{base}/embeddings.html")
        page.wait_for_function(
            "document.getElementById('status').textContent.includes('no photo-space')"
        )
        assert "Could not load" in page.locator("#count").inner_text()
    finally:
        page.close()


def test_points_draw_and_click_before_the_shards_arrive(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    held = []
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        page.calls = stub_inat(page, None)

        page.route(
            "**/pool-*.bin*", lambda r: held.append(r)
        )  # park the shard requests until released
        page.goto(f"{base}/embeddings.html")
        ready_early = "window.__deck && __deck.props.layers.length > 0"
        page.wait_for_function(ready_early)
        assert layer(page, "pts")["n"] == TOTAL  # the layout alone, nothing joined yet
        assert "Loading groups and names" in page.locator("#status").inner_text()
        assert page.locator("#groups button").count() == 0
        page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
        page.wait_for_selector(".nbrs button")
        assert "Loading groups and names" in page.locator("#card .muted").first.inner_text()
        assert held  # the shard requests were parked, not answered
        for route in held:
            route.continue_()
        page.wait_for_function("document.getElementById('status').textContent === ''")
        assert layer(page, "pts")["n"] == POOL_N
        assert page.locator("#groups button").count() == len(GROUPS)
        assert page.locator("#card").is_visible()  # the open card survives the join
        assert page.errors == []
    finally:
        page.close()


def test_failed_shards_leave_the_plot_usable(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        stub_inat(page, None)
        page.route("**/pool-*.bin*", lambda r: r.fulfill(status=500))
        page.goto(f"{base}/embeddings.html")
        page.wait_for_function(
            "document.getElementById('status').textContent.includes('unavailable')"
        )
        assert layer(page, "pts")["n"] == TOTAL
    finally:
        page.close()
