"""Identify's Where panel is the real map, loaded bare the first time it opens: the canvas and the
area tools, the filters of Identify, an area that comes back into the address and the cards, and an
Expand map that fills the window. MapLibre and deck.gl come from the CDN, so this runs with
-m network; the basemap is a blank style."""

import json
import sys

import pytest

from . import test_identify_browser as ib

pytestmark = pytest.mark.network
site = ib.site
BLANK = '{"version":8,"sources":{},"layers":[]}'


@pytest.fixture(scope="module")
def browser():
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as pw:
        args = ["--use-angle=metal"] if sys.platform == "darwin" else []  # WebGL in headless macOS
        try:
            instance = pw.chromium.launch(args=args)
        except Exception as error:
            pytest.skip(f"Chromium unavailable: {error}")
        yield instance


def real_map(page):
    """The fixture stubs the CDN's deck.gl; the map needs the real libraries and a blank basemap."""
    page.unroute("https://unpkg.com/**")
    page.route("https://basemaps.cartocdn.com/**", lambda r: r.fulfill(body=BLANK))


def open_where(browser, base, hash_="#lvl=1", size=(1100, 800), touch=False):
    """Identify with Where open (a phone: its sheet's section) and the map's canvas drawn."""
    page = ib.open_identify(browser, base, hash_, size=size, touch=touch)
    real_map(page)
    page.wait_for_function("__identify.ids().length > 0")
    page.tap("#bwhere") if touch else page.click("#bwhere")  # a phone's opens the sheet on Where
    frame = page.frame_locator("#pwhere iframe")
    frame.locator("#map canvas").first.wait_for()
    return page, frame


def geojson(west, east=-122.0):
    ring = [[west, 48], [east, 48], [east, 50], [west, 50], [west, 48]]
    body = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
    return {
        "name": "area.geojson",
        "mimeType": "application/json",
        "buffer": json.dumps(body).encode(),
    }


def test_the_map_is_not_loaded_until_where_opens_and_then_it_is_bare(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1", size=(1100, 800))
    real_map(page)
    page.wait_for_function("__identify.ids().length > 0")
    page.click("#bwhat")
    assert page.locator("iframe").count() == 0
    page.click("#bwhere")
    assert page.locator("#pwhere iframe").count() == 1
    src = page.get_attribute("#pwhere iframe", "src")
    assert "embed=1" in src and "bare=1" in src
    frame = page.frame_locator("#pwhere iframe")
    frame.locator("#map canvas").first.wait_for()
    for gone in ("header", "#side", "#time", ".site-shell"):
        assert frame.locator(gone).first.is_hidden(), gone
    assert frame.get_by_role("button", name="Draw area", exact=True).is_visible()
    assert frame.get_by_label("BC parks and protected areas").is_visible()
    assert frame.locator(".area input[type=file]").count() == 1
    page.click("#bwhat")
    page.click("#bwhere")
    assert page.locator("#pwhere iframe").count() == 1  # opened once
    assert page.errors == []


def test_the_map_holds_identifys_filters_live(browser, site):
    base, pts = site
    page, frame = open_where(browser, base, "#lvl=1&groups=Aves")
    n = int((pts["iconic_taxon"] == "Aves").sum())
    frame.locator("#count").wait_for(state="attached")
    page.wait_for_function(
        "n => document.querySelector('#pwhere iframe').contentDocument.getElementById('count')"
        ".textContent.includes(n)",
        arg=f"{n:,}",
    )
    page.click("#bwhat")
    page.locator("#groups .gb", has_text="Birds").first.click()  # Birds off: no filter left
    page.wait_for_function("!location.hash.includes('groups=')")
    page.click("#bwhere")
    page.wait_for_function(
        "n => document.querySelector('#pwhere iframe').contentDocument.getElementById('count')"
        ".textContent.includes(n)",
        arg=f"{len(pts):,}",
    )
    assert page.errors == []


def test_an_area_set_in_the_map_writes_area_and_narrows_the_cards(browser, site):
    base, pts = site
    page, frame = open_where(browser, base)
    west = float(pts["lon"].median())
    frame.locator(".area input[type=file]").set_input_files(geojson(west))
    page.wait_for_function("location.hash.includes('area=')")
    page.wait_for_function("__identify.ids().length < 2100")
    got = set(ib.ids(page))
    assert (
        set(pts["id"][pts["lon"] > west + 1e-3]) <= got <= set(pts["id"][pts["lon"] > west - 1e-3])
    )
    assert page.inner_text("#bwhere b") == "Drawn area"
    frame.get_by_role("button", name="Clear area").click()
    page.wait_for_function("__identify.ids().length === 2100")
    assert (
        "area=" not in page.evaluate("location.hash") and page.inner_text("#bwhere b") == "Anywhere"
    )
    assert page.errors == []


def test_a_drawn_area_is_written_to_the_address(browser, site):
    base, _ = site
    page, frame = open_where(browser, base)
    frame.get_by_role("button", name="Draw area", exact=True).click()
    box = frame.locator("#map canvas").first.bounding_box()
    for fx, fy in ((0.3, 0.4), (0.7, 0.4), (0.7, 0.8)):
        page.mouse.click(box["x"] + fx * box["width"], box["y"] + fy * box["height"])
    frame.get_by_role("button", name="Finish").click()
    page.wait_for_function("location.hash.includes('area=')")
    assert page.inner_text("#bwhere b") == "Drawn area" and page.errors == []


def test_expand_fills_the_window_and_escape_or_show_cards_returns(browser, site):
    base, _ = site
    page, _ = open_where(browser, base, size=(1100, 800))
    page.click("#wexp")
    box = page.locator("#wbox").bounding_box()
    assert (box["x"], box["y"], box["width"], box["height"]) == (0, 0, 1100, 800)
    assert page.inner_text("#wexp") == f"Show {page.inner_text('.sdone .n')} cards"
    page.keyboard.press("Escape")
    assert page.locator("#wbox.big").count() == 0 and page.locator("#pwhere").is_visible()
    page.click("#wexp")
    page.frame_locator("#pwhere iframe").locator("#map canvas").first.click(
        position={"x": 5, "y": 300}
    )
    page.keyboard.press("Escape")  # the key goes to the map's frame
    page.wait_for_function("!document.querySelector('#wbox.big')")
    page.click("#wexp")
    page.click("#wexp")  # Show N cards
    assert page.locator("#wbox.big").count() == 0 and page.locator("#pwhere").is_hidden()
    assert page.errors == []


def test_a_phone_fills_the_section_and_expands_full_screen(browser, site):
    base, _ = site
    page, frame = open_where(browser, base, size=(390, 800), touch=True)
    assert page.locator("#ab2").is_visible()
    inner = page.locator("#pwhere iframe").bounding_box()
    assert inner["height"] >= 260 and inner["width"] >= 300
    page.tap("#wexp")
    box = page.locator("#wbox").bounding_box()
    assert (box["width"], box["height"]) == (390, 800)
    page.tap("#wexp")
    assert page.locator("#bsheet").is_hidden() and page.errors == []


def test_escape_in_the_small_maps_frame_closes_the_panel(browser, site):
    base, _ = site
    page, frame = open_where(browser, base)
    frame.locator("#map canvas").first.click(position={"x": 5, "y": 300})
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#pwhere').hidden")
    assert page.evaluate("document.activeElement.id") == "bwhere" and page.errors == []
