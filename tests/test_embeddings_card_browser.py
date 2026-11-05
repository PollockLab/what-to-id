"""Photo-space page in Chromium: the record card, and the map before and after its shards arrive.

Fixtures and helpers live in test_embeddings_browser.py.
"""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

from . import test_embeddings_browser as eb
from .embeddings_fixture import GROUPS
from .test_embeddings_browser import DECK_STUB, POOL_N, TOTAL, layer, ready, stub_inat

browser, site, open_page = eb.browser, eb.site, eb.open_page


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
        f"https://www.inaturalist.ca/observations/{mine}"
    )
    assert card.get_by_role("link", name="Show on map").get_attribute("href") == (
        f"map.html#record={mine}"
    )
    assert (
        card.get_by_role("link", name="Show in tree")
        .get_attribute("href")
        .startswith("tree.html#sel=")
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

        page.route(  # park the shard requests until released; the map's look-alike file comes after
            "**/pool-*.bin*",
            lambda r: r.continue_() if "lookalike" in r.request.url else held.append(r),
        )
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


def test_minimize_shrinks_the_card_to_a_strip_and_survives_picks(open_page):
    page = open_page(drop=None)
    ready(page)
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    btn = page.locator("#card .mn")
    assert btn.get_attribute("aria-label") == "Minimize card"
    btn.click()
    height = "document.getElementById('card').getBoundingClientRect().height"
    assert page.locator("#card.min").count() == 1 and page.evaluate(height) == 48
    assert not page.locator("#card a.btn").first.is_visible()
    assert btn.get_attribute("aria-expanded") == "false"
    page.evaluate("__deck.props.onClick({index: 3, layer: {id: 'pts'}})")
    assert page.locator("#card.min").count() == 1  # the next pick stays a strip
    page.locator("#card h2").click()  # a click on the strip restores it
    assert page.locator("#card.min").count() == 0 and page.locator("#card a.btn").first.is_visible()
    page.locator("#card .mn").click()
    page.locator("#card .x").click()
    assert page.locator("#card").is_hidden()
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    assert page.locator("#card.min").count() == 0  # after ×, the next pick opens in full


def test_card_saves_records_and_opens_them_in_identify(open_page):
    page = open_page(drop=None)
    ready(page)
    card = page.locator("#card")
    save = card.locator(".sv button[aria-pressed]")
    saved = {}
    for index in (7, 8):
        page.evaluate(f"__deck.props.onClick({{index: {index}, layer: {{id: 'pts'}}}})")
        page.wait_for_selector(".nbrs button")
        saved[index] = int(
            card.get_by_role("link", name="Help identify on iNaturalist")
            .get_attribute("href")
            .rsplit("/", 1)[1]
        )
        assert save.get_attribute("aria-pressed") == "false"
        assert card.get_by_role("link", name="Saved (1)").is_visible() == (
            index == 8
        )  # none yet at 7
        save.click()
        assert save.get_attribute("aria-pressed") == "true" and "Saved" in save.inner_text()
    link = card.get_by_role("link", name="Saved (2)")
    ids = parse_qs(urlparse(link.get_attribute("href")).query)["id"][0].split(",")
    assert sorted(ids) == sorted(str(i) for i in saved.values())
    page.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")  # reopened: still saved
    page.wait_for_selector(".nbrs button")
    assert save.get_attribute("aria-pressed") == "true"
    save.click()
    assert save.get_attribute("aria-pressed") == "false"
    assert card.get_by_role("link", name="Saved (1)").is_visible()
    page.reload()  # the list outlives the page
    ready(page)
    assert page.evaluate("SavedRecords.ids()") == [saved[8]]
    page.evaluate("__deck.props.onClick({index: 8, layer: {id: 'pts'}})")
    page.wait_for_selector(".nbrs button")
    card.get_by_role("button", name="Clear saved").click()
    assert page.evaluate("SavedRecords.ids()") == []
    assert save.get_attribute("aria-pressed") == "false"
    assert card.get_by_role("link", name=re.compile(r"Saved \(")).is_hidden()
    assert page.errors == []
