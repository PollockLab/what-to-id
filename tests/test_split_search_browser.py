"""The split page's search box in Chromium: what the map frame offers, then the photo search.

The map here is a photo space (the real one needs a CDN), so a listener in its frame stands in
for map_suggest.js; the real map's end is in test_split_map_browser.py."""

import json

import pytest

from . import test_embeddings_browser as eb
from .test_embeddings_browser import stub_inat

browser, site = eb.browser, eb.site

STAND_IN = """rows => { window.asked = []; window.got = []; window.rows = rows;
  addEventListener('message', e => { const d = e.data;
    if (d.type === 'wtid-suggest') { asked.push(d.q); parent.postMessage(
      {type: 'wtid-suggest', seq: d.seq, rows: window.rows}, location.origin); }
    else if (d.type === 'wtid-apply') got.push({group: d.group, key: d.key}); }); }"""
PLANTS = {
    "group": "Taxon",
    "key": "47126",
    "label": "Plants",
    "sub": "Plants",
    "count": 12,
    "exact": True,
}
LAKE = {"group": "Place", "key": "0007", "label": "Plants Lake Park", "sub": "Park", "exact": False}
CHIP = "#selbar li:has-text('Photo search')"


@pytest.fixture
def explore(browser, site):
    pages = []

    def open_(rows=None):
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        pages.append(page)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.add_init_script(
            "window.encoded = []; window.AtlasEncoderOverride = {encode: async t => "
            f"(window.encoded.push(t), Float32Array.from({json.dumps(site[1]['queries'][0])}))}};"
        )
        stub_inat(page, None)
        page.goto(f"{site[0]}/explore.html?view=map-space")
        page.wait_for_function(
            "[...document.querySelectorAll('iframe')].every(f =>"
            " f.contentDocument.getElementById('status').textContent === '')"
        )
        page.map = page.query_selector("#map").content_frame()
        if rows is not None:
            page.map.evaluate(STAND_IN, rows)
        return page

    yield open_
    for page in pages:
        page.close()


def options(page):
    return page.eval_on_selector_all("#sg li", "e => e.map(x => x.textContent)")


def selected(page):
    return page.eval_on_selector_all(
        "#sg li", "e => e.findIndex(x => x.getAttribute('aria-selected') === 'true')"
    )


def test_an_exact_name_lists_first_and_enter_applies_it_without_a_photo_subset(explore):
    page = explore([LAKE, PLANTS])
    page.fill("#sq", "plants")
    page.wait_for_function("document.querySelectorAll('#sg li').length === 3")
    got = options(page)
    assert got[0].startswith("TaxonPlants") and "12 records" in got[0]
    assert got[1].startswith("PlacePlants Lake Park")
    assert got[2].startswith("Photos") and "Photos like “plants”" in got[2]
    assert selected(page) == 0
    assert page.get_attribute("#sq", "aria-expanded") == "true"
    assert page.get_attribute("#sq", "aria-activedescendant") == "sg0"
    page.press("#sq", "Enter")
    page.wait_for_function("document.getElementById('sq').value === ''")
    page.map.wait_for_function("got.length")
    assert page.map.evaluate("got") == [{"group": "Taxon", "key": "47126"}]
    assert page.get_attribute("#sq", "aria-expanded") == "false"
    page.wait_for_timeout(300)
    assert page.frame_locator("#space").locator(CHIP).count() == 0  # no photo subset
    assert page.errors == []


def test_a_free_phrase_highlights_the_photo_option_and_enter_runs_the_photo_search(explore):
    page = explore([{**PLANTS, "exact": False}])
    page.fill("#sq", "a hummingbird at a flower")
    page.wait_for_function("document.querySelectorAll('#sg li').length === 2")
    assert selected(page) == 1
    assert options(page)[1].endswith("Photos like “a hummingbird at a flower”")
    page.press("#sq", "ArrowUp")
    assert selected(page) == 0
    page.press("#sq", "ArrowDown")
    assert selected(page) == 1
    page.press("#sq", "Enter")
    page.frame_locator("#space").locator(CHIP).wait_for(state="attached")
    assert page.evaluate("encoded") == ["a photo of a hummingbird at a flower"]
    assert page.map.evaluate("got") == []
    assert page.errors == []


def test_escape_closes_the_list(explore):
    page = explore([PLANTS])
    page.fill("#sq", "a hummingbird")
    page.wait_for_selector("#sg li")
    page.press("#sq", "Escape")
    assert page.get_attribute("#sq", "aria-expanded") == "false" and not page.is_visible("#sg")
    assert page.map.evaluate("got") == []


def test_an_observation_link_skips_the_map_and_goes_to_the_photo_search(explore, site):
    page = explore([PLANTS])
    seed = int(sorted(site[2])[0])
    page.fill("#sq", f"https://www.inaturalist.org/observations/{seed}")
    page.wait_for_selector("#sg li")
    assert len(options(page)) == 1 and selected(page) == 0
    page.press("#sq", "Enter")
    page.frame_locator("#space").locator(CHIP).wait_for(state="attached")
    assert page.map.evaluate("asked") == [] and page.evaluate("encoded") == []
    assert page.errors == []


def test_a_map_that_does_not_answer_leaves_only_the_photo_option(explore):
    page = explore()  # the frame has no stand-in: no reply
    page.fill("#sq", "plants")
    page.wait_for_timeout(500)
    assert len(options(page)) == 1 and selected(page) == 0
    page.fill("#sq", "")
    assert not page.is_visible("#sg")
    assert page.errors == []
