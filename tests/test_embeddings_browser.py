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
from what_to_id.split_page import build as build_split

from .atlas_index_fixture import FIXTURE_DELTA, FIXTURE_ROWS, write_fixture
from .embeddings_fixture import BBOX, GROUPS, TREE, pool_frame, write_layout
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
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    build(root, data_url="atlas/")
    # the map needs MapLibre from a CDN, so the split page here holds two photo spaces
    build_split(root, map_url="embeddings.html")
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
        page.goto(f"{base}/embeddings.html?standalone=1{hash_}")
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
    assert page.locator("#groups button[data-g]").count() == len(GROUPS)
    text = page.locator("#honest").inner_text()
    assert "Measured on the layout" in text and "50%" in text and "12" in text
    assert "not identification confidence" in text and "lossy" in text
    assert "sample" not in page.locator("#intro").inner_text()
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


def shown_in(page, name):
    return int(
        page.locator("#tree .tn", has_text=name).first.locator(".tc").inner_text().replace(",", "")
    )


def shown(page):
    return int(page.locator("#count").inner_text().split(" shown")[0].replace(",", ""))


def test_taxon_in_the_hash_keeps_everything_below_it(open_page):
    page = open_page("#taxa=900")  # Genus A holds three of the seven species
    ready(page)
    assert shown(page) == POOL_N * 3 // 7
    assert layer(page, "pts")["cats"][2] == [1]
    assert (
        page.locator("#selbar li").count() == 1
        and "Genus A" in page.locator("#selbar").inner_text()
    )
    page.locator("#selbar li .x").click()
    assert shown(page) == POOL_N and page.evaluate("location.hash") == ""
    assert page.errors == []


def test_taxon_search_picks_and_combines_with_group_chips_as_on_the_map(open_page):
    page = open_page()
    ready(page)
    page.locator("#q").fill("Genus B")
    page.locator("#sugg li").first.click()
    assert shown(page) == POOL_N * 4 // 7 and page.evaluate("location.hash") == "#taxa=901"
    page.locator("#q").fill("Genus A")
    page.locator("#sugg li").first.click()
    assert shown(page) == POOL_N and page.evaluate("location.hash") == "#taxa=901,900"
    page.get_by_role("button", name="Clear all").click()
    assert shown(page) == POOL_N and page.evaluate("location.hash") == ""
    # a picked group beside a taxon adds to it, a left-out one subtracts (CH.groupPass)
    page = open_page("#groups=Aves&taxa=900")
    ready(page)
    assert shown(page) == POOL_N // 3 + POOL_N * 3 // 7 - POOL_N // 7
    page = open_page("#groups=-Aves&taxa=900")
    ready(page)
    assert shown(page) == POOL_N * 3 // 7 - POOL_N // 7
    assert page.errors == []


def test_group_opens_to_its_ranks_and_nodes_take_the_chip_clicks(open_page):
    page = open_page()
    ready(page)
    page.locator("#groups .gt").first.click()
    assert page.locator("#tree .tl").all_inner_texts() == ["Genus B", "Genus A"]
    assert shown_in(page, "Genus A") + shown_in(page, "Genus B") == POOL_N // 3
    assert page.evaluate("location.hash") == ""
    page.get_by_role("button", name="Open Genus A").click()
    assert page.locator("#tree .tn").count() == 5 and page.evaluate("location.hash") == ""
    page.locator("#tree .tl", has_text="Genus A").click()
    assert page.evaluate("location.hash") == "#taxa=900" and shown(page) == POOL_N * 3 // 7
    page.locator("#tree .tl", has_text="Genus A").click()
    assert page.evaluate("location.hash") == "#taxa=-900"
    page.locator("#tree .tl", has_text="Genus A").click()
    assert page.evaluate("location.hash") == "" and shown(page) == POOL_N
    assert page.errors == []


def test_picking_from_the_search_box_opens_the_path_to_the_taxon(open_page):
    page = open_page()
    ready(page)
    page.locator("#q").fill("Taxon 4")
    page.locator("#sugg li").first.click()
    assert page.locator("#tree .tn[data-r] .tl[aria-pressed=true]").inner_text() == "Taxon 4"
    assert page.errors == []


def test_filters_the_page_does_not_apply_stay_in_the_hash(open_page):
    page = open_page("#months=8&area=abc&groups=Aves")
    ready(page)
    page.locator("#groups button[data-g='1']").click()
    assert page.evaluate("location.hash") == "#months=8&groups=Aves,Insecta&area=abc"
    assert page.errors == []


def bar_labels(page):
    return page.locator("#selbar li").all_inner_texts()


def test_months_and_dates_in_the_hash_filter_the_page_and_show_in_the_bar(open_page):
    aug = open_page("#months=8")
    ready(aug)
    sep = open_page("#months=9")
    ready(sep)
    assert shown(aug) > 0 and shown(sep) > 0
    assert shown(aug) + shown(sep) == POOL_N  # the fixture observes in August and September only
    assert layer(aug, "pts")["n"] == POOL_N
    assert any("August" in t for t in bar_labels(aug))
    late = open_page("#from=2026-09-01")
    ready(late)
    assert 0 < shown(late) <= shown(sep)
    assert any("Observed 2026-09-01 to" in t for t in bar_labels(late)), bar_labels(late)
    late.locator("#selbar li", has_text="Observed").locator("button.x").click()
    assert shown(late) == POOL_N
    assert "from=" not in late.evaluate("location.hash")
    assert aug.errors == [] and late.errors == []


def test_area_in_the_hash_filters_by_position_and_chips_count_what_is_left(open_page):
    ring = "[[-123.6,48,-123,48,-123,50,-123.6,50]]"
    h = open_page("").evaluate(f"MapArea.encode({ring})")
    west = open_page(f"#area={h}")
    ready(west)
    assert 0 < shown(west) < POOL_N
    chips = west.locator("#groups button[data-g]").all_inner_texts()
    assert sum(int(t.replace(",", "").split()[-1]) for t in chips) == shown(west)
    assert any("Drawn area" in t and "map only" not in t for t in bar_labels(west))
    assert west.evaluate("location.hash") == f"#area={h}"
    west.locator("#selbar li", has_text="Drawn area").locator("button.x").click()
    assert shown(west) == POOL_N
    assert west.errors == []


def test_filters_left_to_the_map_show_as_map_only_and_stay_in_the_hash(open_page):
    page = open_page("#park=1,2&bcpark=Foo&projects=bar&groups=Aves")
    ready(page)
    labels = bar_labels(page)
    assert sum("map only" in t for t in labels) == 3
    assert 0 < shown(page) < POOL_N
    page.locator("#groups button[data-g='1']").click()
    assert page.evaluate("location.hash") == "#groups=Aves,Insecta&park=1,2&bcpark=Foo&projects=bar"
    page.locator("#selbar li", has_text="BC park").locator("button.x").click()
    assert "bcpark" not in page.evaluate("location.hash")
    assert "park=1,2" in page.evaluate("location.hash")
    assert page.errors == []


def test_clear_all_resets_every_filter_the_bar_shows(open_page):
    page = open_page("#months=8&groups=Aves&park=1")
    ready(page)
    page.locator("#selbar button", has_text="Clear all").click()
    assert shown(page) == POOL_N
    assert page.evaluate("location.hash") == ""
    assert page.errors == []


def test_filters_in_the_hash_wait_for_the_join(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    held = []
    page.route("**/pool-*.bin*", lambda r: held.append(r))
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/embeddings.html?standalone=1#months=8&groups=Aves")
    page.wait_for_function("window.__deck && __deck.props.layers.length > 0")
    assert layer(page, "pts")["n"] == TOTAL
    # nothing is rewritten before the join
    assert page.evaluate("location.hash") == "#months=8&groups=Aves"
    for route in held:
        route.continue_()
    page.wait_for_function("document.getElementById('status').textContent === ''")
    assert 0 < shown(page) < POOL_N
    assert page.errors == []
    page.close()


def test_hash_changes_apply_in_place_including_back_and_forward(open_page):
    page = open_page("")
    ready(page)
    page.evaluate("window.marker = 1")
    page.evaluate("location.hash = '#months=8'")
    page.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    aug = shown(page)
    assert 0 < aug < POOL_N
    assert any("August" in t for t in bar_labels(page))
    page.go_back()
    page.wait_for_function(f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')")
    page.go_forward()
    page.wait_for_function(f"document.getElementById('count').textContent.startsWith('{aug:,}')")
    assert page.evaluate("window.marker") == 1  # nothing reloaded
    assert page.errors == []


def test_split_page_relays_the_selection_between_frames_without_reloads(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html#months=8")
    counts = (
        "[...document.querySelectorAll('iframe')].map(f => f.contentDocument &&"
        " f.contentDocument.getElementById('count') &&"
        " f.contentDocument.getElementById('count').textContent)"
    )
    page.wait_for_function(f"{counts}.every(c => c && c.includes('shown'))")
    left, right = page.frame_locator("#map"), page.frame_locator("#space")
    before = left.locator("#count").inner_text()
    assert before == right.locator("#count").inner_text()
    for f in ("#map", "#space"):
        page.evaluate(f"document.querySelector('{f}').contentWindow.marker = 1")
    left.locator("#groups button[data-g='1']").click()  # pick Insecta in the left frame
    page.wait_for_function(f"{counts}.every(c => c !== {before!r}) && new Set({counts}).size === 1")
    assert "groups=Insecta" in page.evaluate("location.hash")
    assert right.locator("#selbar li", has_text="Insecta").count() == 1
    for f in ("#map", "#space"):
        assert page.evaluate(f"document.querySelector('{f}').contentWindow.marker") == 1
    assert page.errors == []
    page.close()


def test_split_page_mirrors_a_picked_record_in_the_other_frame(browser, site):
    # the fixture loads the photo space in both frames, so this pins the relay, not map.js
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html")
    page.wait_for_function(
        "[...document.querySelectorAll('iframe')].every(f =>"
        " f.contentDocument.getElementById('count').textContent.includes('shown'))"
    )
    pick = [f for f in page.frames if "embed=1" in f.url]
    assert len(pick) == 2
    pick[1].evaluate(
        "window.got = []; addEventListener('message', e =>"
        " e.data.type === 'wtid-matches' && got.push(e.data))"
    )
    pick[0].evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    sel = "__deck.props.layers.find(x => x.id === 'sel').props.data[0]"
    for f in pick:
        f.wait_for_function("__deck.props.layers.some(x => x.id === 'sel')")
        assert f.evaluate(sel) == 7
    pick[0].wait_for_selector(".nbrs li .score")
    assert pick[0].locator(".nbrs li .score").first.inner_text().startswith("Cosine 0.")
    assert pick[0].locator(".nbrs li .rank").first.inner_text() == "1"
    pick[1].wait_for_function("got.length === 1")  # the matches reached the other frame
    hits = pick[1].evaluate("got[0].hits")
    assert len(hits) == 12 and all(0 <= h["score"] <= 1 for h in hits)
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    pick[1].evaluate("document.querySelector('#card .x').click()")
    for f in pick:
        f.wait_for_function("!__deck.props.layers.some(x => x.id === 'sel')")
    assert page.errors == []
    page.close()


def test_split_photo_search_narrows_both_frames_and_the_chip_clears_it(browser, site):
    base, _, pool, _ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html")
    counts = (
        "[...document.querySelectorAll('iframe')].map(f => f.contentDocument &&"
        " f.contentDocument.getElementById('count') &&"
        " f.contentDocument.getElementById('count').textContent)"
    )
    page.wait_for_function(f"{counts}.every(c => c && c.includes('shown'))")
    before = page.evaluate(counts)
    seed = int(sorted(pool)[0])
    page.fill("#sq", f"https://www.inaturalist.org/observations/{seed}")
    page.press("#sq", "Enter")
    chip = "#selbar li:has-text('Photo search')"
    for f in ("#map", "#space"):
        page.frame_locator(f).locator(chip).wait_for(state="attached")  # the peer folds its panel
    now = page.evaluate(counts)
    num = [int(c.split(" ")[0].replace(",", "")) for c in (*now, *before)]
    assert 0 < num[0] == num[1] < num[2] == num[3]
    page.frame_locator("#map").locator(chip + " button").click()
    for f in ("#map", "#space"):
        page.frame_locator(f).locator(chip).wait_for(state="detached")
    page.wait_for_function(f"{counts}.every(c => c === {before[0]!r})")
    assert page.input_value("#sq") == ""
    assert page.errors == []
    page.close()


def test_split_divider_resizes_by_keys_and_double_click_and_remembers(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{base}/split.html")
    width = "document.getElementById('map').getBoundingClientRect().width"
    page.wait_for_selector("#map")
    half = page.evaluate(width)
    sep = page.locator("#sep")
    sep.focus()
    for _ in range(5):
        page.keyboard.press("ArrowRight")
    assert page.evaluate(width) == pytest.approx(half + 0.1 * 1280, abs=3)
    page.reload()
    page.wait_for_selector("#map")
    assert page.evaluate(width) > half + 100  # remembered
    sep.dblclick()
    assert page.evaluate(width) == pytest.approx(half, abs=3)
    page.close()


def test_card_resizes_from_its_left_edge_and_remembers(open_page):
    page = open_page(drop=None)
    ready(page)
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    width = "document.getElementById('card').getBoundingClientRect().width"
    assert page.evaluate(width) == 300
    rz = page.locator("#card .rz")
    rz.focus()
    for _ in range(5):
        page.keyboard.press("ArrowLeft")
    assert page.evaluate(width) == 400
    box = rz.bounding_box()
    page.mouse.move(box["x"] + 3, box["y"] + 50)
    page.mouse.down()
    page.mouse.move(box["x"] + 100, box["y"] + 50, steps=4)
    page.mouse.up()
    assert page.evaluate(width) == pytest.approx(300, abs=3)
    page.reload()
    ready(page)
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    assert (
        page.evaluate(width) == pytest.approx(300, abs=3) and page.evaluate(width) != 300
    )  # remembered
    page.locator("#card .rz").dblclick()
    assert page.evaluate(width) == 300
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
        page.goto(f"{base}/embeddings.html?standalone=1")
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
        page.goto(f"{base}/embeddings.html?standalone=1")
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
        assert page.locator("#groups button[data-g]").count() == len(GROUPS)
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
        page.goto(f"{base}/embeddings.html?standalone=1")
        page.wait_for_function(
            "document.getElementById('status').textContent.includes('unavailable')"
        )
        assert layer(page, "pts")["n"] == TOTAL
    finally:
        page.close()


def _split(browser, site, w, h, query="", hash_=""):
    base, *_ = site
    page = browser.new_page(viewport={"width": w, "height": h})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html{query}{hash_}")
    return page


FRAMES = "[...document.querySelectorAll('iframe')].filter(f => !f.hidden).map(f => f.id)"


def test_split_shows_both_views_wide_and_the_map_alone_when_narrower(browser, site):
    page = _split(browser, site, 1280, 800)
    assert page.evaluate(FRAMES) == ["map", "space"]
    assert page.locator("[data-v=side]").get_attribute("aria-pressed") == "true"
    page.close()
    page = _split(browser, site, 1100, 800)
    assert page.evaluate(FRAMES) == ["map"]
    page.click("[data-v=space]")
    page.wait_for_function(f"{FRAMES}.join() === 'space'")
    assert "view=space" in page.evaluate("location.search")
    page.click("[data-v=side]")
    page.wait_for_function(f"{FRAMES}.join() === 'map,space'")
    page.close()


def test_split_has_one_header_and_the_note_behind_an_i_button(browser, site):
    page = _split(browser, site, 1280, 800)
    page.wait_for_function(f"{FRAMES}.length === 2")
    assert page.locator(".site-shell:visible").count() == 1
    for f in ("#map", "#space"):
        shell = page.frame_locator(f).locator(".site-shell")
        assert shell.count() == 0 or not shell.is_visible()
    assert page.locator("#note").is_hidden()
    page.click("#i")
    assert page.locator("#note").is_visible() and "share one selection" in page.inner_text("#note")
    page.keyboard.press("Escape")
    assert page.locator("#note").is_hidden()
    assert page.errors == []
    page.close()


def test_a_phone_holds_one_frame_at_a_time(browser, site):
    page = _split(browser, site, 390, 800, hash_="#months=8")
    assert page.evaluate("document.querySelectorAll('iframe').length") == 1
    assert page.locator("[data-v=side]").is_hidden()
    page.click("[data-v=space]")
    page.wait_for_function(
        "document.querySelectorAll('iframe').length === 1 && document.querySelector('#space')"
    )
    assert "months=8" in page.evaluate("document.querySelector('#space').src")
    page.close()


def test_old_page_urls_open_the_matching_explore_view_with_the_hash(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    stub_inat(page, None)
    page.goto(f"{base}/embeddings.html#months=8")
    page.wait_for_url(f"{base}/split.html?view=space#months=8")
    assert page.evaluate(FRAMES) == ["space"]
    page.close()
