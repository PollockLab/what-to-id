"""Explore's state bar in Chromium: one bar over every pane with the map's count, its selection's
chips and the Legend and Filters buttons, which open the map frame's sheet; with the map pane hidden
the map's frame is the sheet. The site of test_clade_colour_browser.py, with a stand-in Identify."""

import os

import numpy as np
import pytest

from what_to_id import split_page, tree_page
from what_to_id.page_map import encode_points, render_map

from . import test_clade_colour_browser as cc
from . import test_explore_home_browser as eh
from .embeddings_fixture import pool_frame
from .test_tree_browser import serve

browser = cc.browser
SHOTS = os.environ.get("WTID_SHOTS")  # a folder: keep screenshots of the bar there
CHIPS = "[...document.querySelectorAll('#sbc li span')].map(s => s.textContent)"
COUNT = "document.getElementById('map')?.contentDocument?.getElementById('count')?.textContent"
HASH = "#groups=Plantae&from=2026-09-01"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("explore-bar")
    pool = pool_frame(np.arange(1, 301))
    pool["taxon_id"] = [t for t, n, _ in cc.SPLIT for _ in range(n)]
    pool["taxon_name"] = [cc.TREE[t][1] for t, n, _ in cc.SPLIT for _ in range(n)]
    pool["iconic_taxon"] = [g for _, n, g in cc.SPLIT for _ in range(n)]
    blobs, meta = encode_points(pool, cc.TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    (root / "identify.html").write_text(eh.IDENTIFY)
    tree_page.build(root)
    split_page.build(root)
    server, url = serve(root)
    yield url
    server.shutdown()


def open_page(browser, url, width=1280, dark=False, wait=True):
    p = browser.new_page(
        viewport={"width": width, "height": 800}, color_scheme="dark" if dark else "light"
    )
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=eh.STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )
    p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    p.goto(url)
    if not wait:  # a phone holds one pane: no map's frame until the bar asks for it
        return p, None
    p.wait_for_function(f"/^\\d/.test({COUNT} || '')")
    return p, next(f for f in p.frames if "map.html" in f.url)


def chips(page, n):
    page.wait_for_function(f"{CHIPS}.length === {n}")
    return page.evaluate(CHIPS)


def shot(page, name):
    if SHOTS:
        page.screenshot(path=f"{SHOTS}/{name}.png")


def test_the_bar_shows_the_same_chips_in_every_view(browser, site):
    seen = {}
    for view in ("map", "identify-tree", "map-identify-tree"):
        page, _ = open_page(browser, f"{site}/explore.html?view={view}{HASH}")
        seen[view] = chips(page, 2)
        assert page.text_content("#sbn")[0].isdigit()  # the map's count
        assert page.get_attribute("#sbl", "aria-expanded") == "false"
        assert page.is_hidden("#fb")  # the old Filters button is gone
        assert page.errors == []
        page.close()
    assert seen["map"] == seen["identify-tree"] == seen["map-identify-tree"]
    assert any("Plants" in c for c in seen["map"])
    assert any(c.startswith("Observed 2026-09-01") for c in seen["map"])


def test_picking_plants_on_the_map_adds_a_chip_and_its_x_removes_it(browser, site):
    page, frame = open_page(browser, f"{site}/explore.html?view=map")
    assert chips(page, 0) == [] and page.is_visible("#sbl") and page.is_visible("#sbf")
    cc.pick(frame, "Plants")
    assert "Plants" in chips(page, 1)[0]
    page.wait_for_function("location.hash.includes('groups=Plantae')")
    frame.wait_for_function("document.getElementById('count').textContent.startsWith('170 ')")
    page.click("#sbc button")
    chips(page, 0)
    page.wait_for_function("!location.hash.includes('groups=')")
    frame.wait_for_function("document.getElementById('count').textContent.startsWith('300 ')")
    assert frame.locator("#groups > li.on").count() == 0
    assert page.errors == []
    page.close()


def test_legend_opens_the_sheet_with_the_legend_rows_and_esc_closes_it(browser, site):
    page, frame = open_page(browser, f"{site}/explore.html?view=map{HASH}")
    frame.wait_for_function("!document.querySelector('.lvleg').hidden")
    assert frame.is_hidden(".lvleg")  # no legend in the map's corner
    page.click("#sbl")
    assert page.get_attribute("#sbl", "aria-expanded") == "true"
    frame.wait_for_selector("#xsheet .lvleg", state="visible")
    rows = frame.locator("#xsheet .lvleg .lrows > span:not(.lt)").all_text_contents()
    assert rows == ["Vascular Plants", "Mosses", "Liverworts"]
    assert frame.is_hidden("#xsheet #time")  # one of Legend and Filters at a time
    page.keyboard.press("Escape")
    frame.wait_for_selector("#xsheet", state="hidden")
    assert page.get_attribute("#sbl", "aria-expanded") == "false"
    page.click("#sbl")
    frame.wait_for_selector("#xsheet", state="visible")
    trail = "#xsheet .lvleg [aria-label='Legend trail']"
    frame.locator("#xsheet .lvleg .lrows button").first.focus()
    page.keyboard.press("Escape")  # focus in the legend, a pick shown: up a level, the sheet stays
    frame.wait_for_selector(trail, state="hidden")
    assert frame.is_visible("#xsheet") and page.get_attribute("#sbl", "aria-expanded") == "true"
    # no trail left, so Esc shuts the sheet and tells the bar wherever focus sits; pressed in the
    # frame because headless Linux grants no window focus to page.keyboard
    frame.locator("#xsheet").press("Escape")
    page.wait_for_function(
        "document.getElementById('sbl').getAttribute('aria-expanded') === 'false'"
    )
    assert frame.is_hidden("#xsheet")
    assert page.errors == []
    page.close()


def test_filters_opens_the_dates_and_the_area_and_closes_the_legend(browser, site):
    page, frame = open_page(browser, f"{site}/explore.html?view=map")
    page.click("#sbl")
    page.click("#sbf")
    assert page.get_attribute("#sbf", "aria-expanded") == "true"
    assert page.get_attribute("#sbl", "aria-expanded") == "false"
    frame.wait_for_selector("#xsheet #from", state="visible")  # the frame hears it a message later
    for sel in ("#from", "#to", "#byObs", "#byUp"):
        assert frame.is_visible(f"#xsheet {sel}")
    assert frame.get_by_role("button", name="Draw area", exact=True).is_visible()
    assert frame.is_hidden("#xsheet .lvleg")
    frame.fill("#from", "2026-09-01")
    frame.dispatch_event("#from", "change")
    assert any(c.startswith("Observed 2026-09-01") for c in chips(page, 1))
    page.click("#sbf")
    frame.wait_for_selector("#xsheet", state="hidden")
    assert page.errors == []
    page.close()


def test_with_the_map_pane_hidden_the_map_frame_is_the_sheet(browser, site):
    page, frame = open_page(browser, f"{site}/explore.html?view=identify-tree{HASH}")
    assert "sheet" not in page.get_attribute("#map", "class")
    page.click("#sbf")
    page.wait_for_function("document.getElementById('map').classList.contains('sheet')")
    frame.wait_for_selector("#xsheet #from", state="visible")
    box = page.locator("#map").bounding_box()
    assert box["width"] == 1280 and box["height"] <= 0.6 * 800 + 1
    assert frame.is_visible("#side") and frame.is_visible("#xsheet #from")
    page.click("#sbl")
    frame.wait_for_selector("#xsheet .lvleg", state="visible")
    assert frame.is_hidden("#side") and frame.is_hidden("#xsheet #from")
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('map').classList.contains('sheet')")
    frame.wait_for_selector("#xsheet", state="hidden")  # the frame hears it a message later
    assert page.evaluate("document.getElementById('map').getBoundingClientRect().width") == 280
    assert page.errors == []
    page.close()


@pytest.mark.parametrize("view", ["map", "map-identify-tree"])
def test_at_400_px_the_bar_fits_and_the_sheet_stays_within_60vh(browser, site, view):
    page, _ = open_page(browser, f"{site}/explore.html?view={view}{HASH}", 400, wait=view == "map")
    width = "document.documentElement.scrollWidth"
    if view == "map":
        chips(page, 2)
    else:  # Identify alone, so no map's frame and no chips yet
        page.wait_for_selector("#identify")
        assert chips(page, 0) == [] and page.locator("#map").count() == 0
    assert page.evaluate(width) <= 400
    bar = page.locator("#sbar").bounding_box()
    assert bar["x"] >= 0 and bar["x"] + bar["width"] <= 400
    page.click("#sbf")
    page.wait_for_function(f"/^\\d/.test({COUNT} || '')")
    frame = next(f for f in page.frames if "map.html" in f.url)
    frame.wait_for_selector("#xsheet #from", state="visible")
    if view == "map":
        assert frame.locator("#xsheet").bounding_box()["height"] <= 0.6 * 800 + 1
        assert frame.is_visible("#xsheet #grpsec")  # no room for the rail: it heads Filters
        page.click("#sbf")
        frame.wait_for_selector("#xsheet", state="hidden")
        assert frame.evaluate("document.documentElement.classList.contains('rail-off')")
        page.click("#sbf")
    else:  # the map's frame made for the sheet, its chips now in the bar
        assert page.locator("#map").bounding_box()["height"] <= 0.6 * 800 + 1
        chips(page, 2)
        page.click("#sbl")  # the sheet as tall as the legend's line or two
        frame.wait_for_selector("#xsheet .lvleg", state="visible")
        page.wait_for_function("document.getElementById('map').offsetHeight < 0.25 * innerHeight")
        page.click("#sbf")
    assert page.evaluate(width) <= 400
    shot(page, f"phone-{view}-filters")
    assert page.errors == []
    page.close()
