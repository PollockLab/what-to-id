"""The Pollination page in Chromium: the Food web template on pollination data, without cards."""

import json

import pytest

from what_to_id import page_eating

from . import test_embeddings_browser as eb
from .foodweb_page import META, OBS, open_page, serve

browser = eb.browser

POLLEN = {
    "source": "test",
    "rule": "r",
    "pairs": [["Apis", "Trifolium repens", 0.9], ["Bombus", "Trifolium repens", 0.5]],
    "common": {"Trifolium repens": "White Clover"},
    "parent": {"Trifolium repens": "Plantae"},
    "rank": {},
    "groups": {},
}
POLLEN_OBS = {
    "fetched": "2026-11-25",
    "field": "Interaction->Visited flower of",
    "n": {"obs": 1, "named": 1},
    "obs": [
        {
            "id": 1,
            "t": ["Apis mellifera", 1, "Western Honey Bee"],
            "k": "visit",
            "c": 0,
            "q": "research",
            "on": "",
            "at": "",
            "ph": "",
            "f": ["Trifolium repens", 2],
        }
    ],
}


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    root = tmp_path_factory.mktemp("pollination-site")
    for name, data in (
        (page_eating.OBS_FILE, OBS),
        (page_eating.METAWEB_FILE, META),
        (page_eating.POLLINATION_OBS, POLLEN_OBS),
        (page_eating.POLLINATION_METAWEB, POLLEN),
    ):
        (root / name).write_text(json.dumps(data))
    assert page_eating.build(root).name == "food-web.html"
    yield next(serve(root, "pollination.html")), next(serve(root, "food-web.html"))


def test_the_pollination_page_asks_about_visits_and_leaves_the_cards_out(browser, sites):
    page = open_page(browser, sites[0])
    page.wait_for_selector("#mx td button", state="attached")
    assert page.locator("h1").inner_text() == "Pollination in BC"
    assert page.inner_text("#sent") == "What evidence is there for the pollination web?"
    assert [b.inner_text() for b in page.locator("#modes button").all()][1] == "X visits"
    assert not page.is_visible("#cards") and not page.is_visible("#classes")
    assert page.is_visible("#mx") and page.is_visible("#net")
    assert page.locator("#net line.e.before").count() == 1
    page.click("#modes [data-q=eaten]")
    page.wait_for_function("document.getElementById('sent').textContent.startsWith('What visits')")
    assert "—" not in page.inner_text("body") and page.errors == []


def test_the_toggle_swaps_between_the_two_pages(browser, sites):
    page = open_page(browser, sites[0])
    assert page.locator("#kind [aria-checked=true]").inner_text() == "Pollination"
    page.click("#kind [data-q='food-web.html']")
    page.wait_for_url("**/food-web.html")
    page.wait_for_function("window.__food")
    assert page.locator("h1").inner_text() == "Food web in BC"
    assert page.locator("#kind [aria-checked=true]").inner_text() == "Predation"
