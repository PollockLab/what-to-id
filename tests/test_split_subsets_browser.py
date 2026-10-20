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
