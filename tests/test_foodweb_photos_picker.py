"""The Food web cards in Chromium: any prey via iNaturalist's taxon search, photos, zoom."""

import base64
import json
from pathlib import Path

import pytest

from . import test_embeddings_browser as eb
from .foodweb_page import answer, build_site, open_page

browser = eb.browser
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
PICS = "https://static.inaturalist.org/photos/{}/square.jpg"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    yield from build_site(tmp_path_factory.mktemp("foodweb-photos"))


def stub_inat(page, calls):
    """iNaturalist's API and photos, offline; `calls` collects the API paths asked for."""

    def api(route):
        url = route.request.url
        calls.append(url.split("/v1/")[1])
        if "/taxa/autocomplete" in url:
            body = {
                "results": [
                    {
                        "id": 145310,
                        "name": "Spinus tristis",
                        "preferred_common_name": "American Goldfinch",
                    }
                ]
            }
        else:
            body = {"results": [{"photos": [{"url": PICS.format(1)}, {"url": PICS.format(2)}]}]}
        route.fulfill(json=body)

    page.route("https://api.inaturalist.org/v1/**", api)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=GIF, content_type="image/gif")
    )


def test_a_prey_the_metaweb_lacks_is_found_on_inaturalist_and_exported(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    calls = []
    stub_inat(page, calls)
    page.click("#draw")
    card = page.locator("#cards li", has_text="Description mentions “myodes”")
    answer(card, "Eating")
    box = card.locator(".which input")
    box.fill("goldfinch")
    opt = card.get_by_role("option", name="American Goldfinch")
    assert "Spinus tristis · iNaturalist" in opt.inner_text()
    opt.click()
    assert card.locator(".which .ev").inner_text() == "Eating = American Goldfinch"
    card.locator(".which button", has_text="Confirm").click()
    assert card.locator(".res").inner_text() == "Shows it: Barred Owl eating American Goldfinch"
    stored = json.loads(page.evaluate("localStorage.getItem('wtid-loop')"))
    assert stored["ann"]["502"]["prey"] == "Spinus tristis"
    assert page.evaluate("EatingCore.taxonId('Spinus tristis')") == 145310
    with page.expect_download() as d:
        page.click("#export")
    assert (
        '"502","https://www.inaturalist.org/observations/502","Strix varia","Spinus tristis","yes"'
        in Path(d.value.path()).read_text()
    )
    assert [c for c in calls if c.startswith("taxa/")] == [
        "taxa/autocomplete?per_page=10&q=goldfinch"
    ]
    box = page.locator("#cards li", has_text="Description mentions “mouse”")
    answer(box, "Eating")
    box.locator(".which input").fill("mouse")  # a metaweb match lists first
    assert box.get_by_role("option").first.inner_text().startswith("House Mouse")
    assert page.errors == []


def test_cards_flip_through_the_observation_photos_fetched_on_demand(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    calls = []
    stub_inat(page, calls)
    page.click("#draw")
    card = page.locator("#cards li", has_text="Description mentions “myodes”")  # np=2
    assert card.locator(".pn").inner_text() == "1 / 2" and calls == []
    assert page.locator("#cards li").first.locator(".pv").count() == 0  # one photo, no arrows
    card.get_by_role("button", name="Next photo").click()
    page.wait_for_function(
        "document.querySelector('#cards li:has(.pv) .ph img').src.endsWith('/2/medium.jpg')"
    )
    assert card.locator(".pn").inner_text() == "2 / 2" and calls == ["observations/502"]
    card.get_by_role("button", name="Next photo").click()  # wraps, no second request
    page.wait_for_function(
        "document.querySelector('#cards li:has(.pv) .ph img').src.endsWith('/1/medium.jpg')"
    )
    assert calls == ["observations/502"] and page.errors == []


def test_the_zoom_view_shows_a_large_photo_and_keeps_the_keys(browser, base):
    for width in (1280, 390):
        page = open_page(browser, base + "#q=eats&x=Strix varia")
        page.set_viewport_size({"width": width, "height": 800})
        stub_inat(page, [])
        page.click("#draw")
        card = page.locator("#cards li", has_text="Description mentions “myodes”")
        card.get_by_role("button", name="Zoom photo").click()
        img = page.locator("dialog.zoom img")
        page.wait_for_function(
            "document.querySelector('dialog.zoom img').src.endsWith('/1/large.jpg')"
        )
        assert page.locator("dialog.zoom").is_visible() and img.evaluate(
            "e=>e===document.activeElement"
        )
        page.keyboard.press("ArrowRight")
        page.wait_for_function(
            "document.querySelector('dialog.zoom img').src.endsWith('/2/large.jpg')"
        )
        assert card.locator(".pn").inner_text() == "2 / 2"
        page.keyboard.press("4")  # the answer keys wait for the zoom view to close
        assert card.locator(".res").inner_text() == ""
        img.click()
        assert "full" in page.locator("dialog.zoom").get_attribute("class")
        page.keyboard.press("Escape")
        assert not page.locator("dialog.zoom").is_visible()
        assert card.locator(".zb").evaluate("e=>e===document.activeElement")
        page.keyboard.press("j")
        assert page.errors == []
