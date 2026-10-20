"""The split page's two subset relays in Chromium: the map's area into the photo space, and the
photo space's lasso into the map. The fixture loads the photo space in both frames, so these pin the
relay and the photo space's two ends; map.js's end is covered in test_map_projects.py."""

import pytest

from . import test_embeddings_browser as eb
from .test_embeddings_browser import POOL_N, ready, shown, stub_inat

browser, site, open_page = eb.browser, eb.site, eb.open_page

RING = "[[-123.6,48,-123,48,-123,50,-123.6,50]]"


@pytest.fixture
def split(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html")
    page.wait_for_function(
        "[...document.querySelectorAll('iframe')].every(f =>"
        " f.contentDocument.getElementById('status').textContent === '')"
    )
    frames = [f for f in page.frames if "embed=1" in f.url]
    assert len(frames) == 2
    yield page, frames
    page.close()


def test_the_maps_area_subsets_the_photo_space_which_cannot_clear_it(split, open_page):
    page, (left, right) = split
    h = left.evaluate(f"MapArea.encode({RING})")
    west = open_page(f"#area={h}")
    ready(west)
    left.evaluate("h => parent.postMessage({type: 'wtid-area', area: h}, location.origin)", h)
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert shown(right) == shown(west) < POOL_N
    assert shown(left) == POOL_N  # the sender keeps its own area
    chip = right.locator("#selbar li", has_text="Map area")
    assert chip.count() == 1 and chip.locator("button.x").count() == 0
    left.evaluate("parent.postMessage({type: 'wtid-area', area: ''}, location.origin)")
    right.wait_for_function(
        f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert right.locator("#selbar li").count() == 0
    assert page.errors == []


def test_the_maps_view_subsets_the_photo_space_which_cannot_clear_it(split, open_page):
    page, (left, right) = split
    h = left.evaluate(f"MapArea.encode({RING})")
    west = open_page(f"#area={h}")
    ready(west)
    left.evaluate("h => parent.postMessage({type: 'wtid-view', area: h}, location.origin)", h)
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert shown(right) == shown(west) < POOL_N
    chip = right.locator("#selbar li", has_text="Map view")
    assert chip.count() == 1 and chip.locator("button.x").count() == 0
    left.evaluate("parent.postMessage({type: 'wtid-view', area: ''}, location.origin)")
    right.wait_for_function(
        f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert right.locator("#selbar li").count() == 0
    assert page.errors == []


def test_the_maps_view_and_area_intersect(split, open_page):
    page, (left, right) = split
    small = "[[-123.4,48.5,-123.1,48.5,-123.1,49.5,-123.4,49.5]]"
    h, v = left.evaluate(f"[MapArea.encode({RING}), MapArea.encode({small})]")
    west = open_page(f"#area={v}")
    ready(west)
    left.evaluate(
        "([h, v]) => {parent.postMessage({type: 'wtid-area', area: h}, location.origin);"
        "parent.postMessage({type: 'wtid-view', area: v}, location.origin);}",
        [h, v],
    )
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert shown(right) == shown(west) < POOL_N
    assert page.errors == []


def test_an_area_sent_before_the_frame_loads_still_arrives(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html?view=map")
    joined = (
        "(f => f && f.contentDocument && f.contentDocument.getElementById('status') &&"
        " f.contentDocument.getElementById('status').textContent === '')"
        "(document.querySelector('%s'))"
    )
    page.wait_for_function(joined % "#map")
    left = next(f for f in page.frames if "embed=1" in f.url)
    h = left.evaluate(f"MapArea.encode({RING})")
    left.evaluate("h => parent.postMessage({type: 'wtid-area', area: h}, location.origin)", h)
    page.click("[data-v='side']")  # the second frame is created now, after the message
    page.wait_for_function(joined % "#space")
    right = next(f for f in page.frames if "embed=1" in f.url and f is not left)
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert 0 < shown(right) < POOL_N
    assert page.errors == []
    page.close()


LASSO = [(10, 10), (50, 10), (50, 30), (10, 30)]  # plot pixels; the deck stub unprojects 1:1
INSIDE = """() => {
  const l = __deck.props.layers.find(x => x.id === 'pts'), a = l.props.data.attributes,
    pos = a.getPosition.value, c = a.getFilterCategory.value;
  let inside = 0, bad = 0;
  for (let i = 0; i < l.props.data.length; i++) {
    const ok = pos[2*i] > 10 && pos[2*i] < 50 && pos[2*i+1] > 10 && pos[2*i+1] < 30;
    inside += ok; if (ok !== !!c[3*i+2]) bad++; }
  return {inside, bad, ring: !!__deck.props.layers.find(x => x.id === 'lasso')}; }"""


def test_a_shift_drag_lasso_keeps_the_dots_inside_and_sends_their_ids_to_the_map(split):
    page, (left, right) = split
    page.evaluate(
        "window.__keep = []; addEventListener('message', e => { if (e.data && e.data.type ==="
        " 'wtid-keep') __keep.push(e.data.ids && Array.from(e.data.ids)); })"
    )
    box = left.locator("#plot").bounding_box()
    page.keyboard.down("Shift")
    page.mouse.move(box["x"] + LASSO[0][0], box["y"] + LASSO[0][1])
    page.mouse.down()
    for x, y in LASSO[1:]:
        page.mouse.move(box["x"] + x, box["y"] + y)
    page.mouse.up()
    page.keyboard.up("Shift")
    page.wait_for_function("__keep.length === 1")
    got = left.evaluate(INSIDE)
    assert got["bad"] == 0 and got["ring"] and 0 < got["inside"] < POOL_N
    assert shown(left) == got["inside"] == len(page.evaluate("__keep[0]"))
    assert shown(right) == POOL_N  # a photo space ignores the ids; only the map applies them
    chips = "[...document.querySelectorAll('#selbar li')].map(l => l.textContent)"
    assert left.evaluate(chips) == ["Lasso×"]
    assert left.locator("#lclear").is_visible()
    left.click("#lclear")
    page.wait_for_function("__keep.length === 2")
    assert page.evaluate("__keep[1]") is None
    assert shown(left) == POOL_N and not left.evaluate(INSIDE)["ring"]
    assert left.locator("#lclear").is_hidden()
    assert page.errors == []
