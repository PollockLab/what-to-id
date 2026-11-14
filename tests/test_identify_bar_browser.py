"""Identify's What | When | Where bar in Chromium: each segment opens its own panel, a group row
filters the cards, a preset writes the dates, Esc returns to the segment, Left and Right move
between segments, and a phone's sheet holds the three panels as accordion sections. iNaturalist
is stubbed."""

import re

import numpy as np
import pandas as pd
import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import GROUPS

browser = eb.browser
site = ib.site
PANELS = {"#bwhat": "#pwhat", "#bwhen": "#pwhen", "#bwhere": "#pwhere", "#bwho": "#pwho"}

# the canvas holds a pixel of the light layer's colour, --total in the light scheme
LIGHT_BAR = """() => {
  const c = document.getElementById('hist'), w = c.width, h = c.height;
  const d = c.getContext('2d').getImageData(0, 0, w, h).data;
  for (let i = 0; i < d.length; i += 4)
    if (d[i] === 213 && d[i + 1] === 227 && d[i + 2] === 245 && d[i + 3] === 255) return true;
  return false;
}"""


def blank_map(page):
    """Where's map frame is not under test here, and the CDN is stubbed: an empty page stands in."""
    page.route(
        "**/map.html?embed=1*",
        lambda r: r.fulfill(body="<!doctype html>", content_type="text/html"),
    )


def shown(page):
    return [p for p in PANELS.values() if page.locator(p).is_visible()]


def test_each_segment_opens_its_own_panel_and_a_click_outside_closes_it(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1", size=(1100, 800))
    blank_map(page)
    page.wait_for_function("__identify.ids().length > 0")
    assert shown(page) == []
    for seg, panel in PANELS.items():
        page.click(seg)
        assert shown(page) == [panel] and page.get_attribute(seg, "aria-expanded") == "true"
    page.click(seg)
    assert shown(page) == []
    page.click("#bwhat")
    page.mouse.click(5, 700)
    assert shown(page) == [] and page.errors == []


def test_a_group_row_filters_the_cards_and_the_segment_names_it(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=1", size=(1100, 800))
    page.wait_for_function("__identify.ids().length > 0")
    page.click("#bwhat")
    page.locator("#groups .gb", has_text="Birds").first.click()
    want = sorted(pts.loc[pts["iconic_taxon"] == "Aves", "id"].tolist())
    page.wait_for_function(f"__identify.ids().length === {len(want)}")
    assert ib.ids(page) == want and "groups=Aves" in page.evaluate("location.hash")
    assert page.inner_text("#bwhat b") == "Birds" and page.errors == []


def test_a_preset_writes_the_dates_into_the_hash(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1", size=(1100, 800))
    page.click("#bwhen")
    page.locator("#presets button", has_text="Last 30 days").click()
    since = page.input_value("#from")
    assert f"from={since}" in page.evaluate("location.hash") and page.input_value("#to")
    page.locator("#presets button", has_text="All dates").click()
    assert "from=" not in page.evaluate("location.hash") and page.errors == []


def test_escape_returns_to_the_segment_and_the_arrows_move_the_open_panel(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1", size=(1100, 800))
    blank_map(page)
    page.click("#bwhat")
    page.focus("#bwhat")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "bwhen" and shown(page) == ["#pwhen"]
    page.keyboard.press("ArrowRight")
    assert shown(page) == ["#pwhere"]
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "bwho" and shown(page) == ["#pwho"]
    page.keyboard.press("ArrowRight")  # the last segment stays
    assert page.evaluate("document.activeElement.id") == "bwho"
    page.keyboard.press("ArrowLeft")
    assert page.evaluate("document.activeElement.id") == "bwhere"
    page.keyboard.press("Tab")
    assert page.evaluate("!!document.activeElement.closest('#pwhere')")  # the map's frame
    page.focus("#wexp")  # a key in the frame goes to the map, which tells the page (where's tests)
    page.keyboard.press("Escape")
    assert shown(page) == [] and page.evaluate("document.activeElement.id") == "bwhere"
    assert page.errors == []


def test_a_phone_opens_one_sheet_with_accordion_sections_and_a_spaced_footer(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1", size=(390, 800), touch=True)
    page.wait_for_function("__identify.ids().length > 0")
    page.tap("#bwhen")
    assert page.locator("#bsheet").is_visible() and shown(page) == ["#pwhen"]
    page.tap("#ah0")
    assert shown(page) == ["#pwhat"] and page.get_attribute("#ah1", "aria-expanded") == "false"
    page.locator("#groups .gb").first.tap()
    page.wait_for_function("location.hash.includes('groups=')")
    n = page.inner_text("#bsheet .sdone .n")
    assert page.inner_text("#bsheet .sdone").replace("\n", " ") == f"Show {n} cards"
    page.tap("#bsheet .sdone")
    assert page.locator("#bsheet").is_hidden() and page.errors == []


@pytest.fixture(scope="module")
def totals_site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(1).choice(2**32 - 2, ib.N, replace=False) + 1
    score = np.random.default_rng(2).normal(size=ib.N).astype("float32")
    months = [f"{y}-{m:02d}" for y in range(2023, 2031) for m in range(1, 13)]
    every = {g: {ym: 10**4 for ym in months} for g in GROUPS}
    raw = {"on": "2026-01-01", "obs": every, "up": every}
    frame = ib.pool_frame(ids)
    # three years of dates, so the detail histogram draws one bar per month
    day = pd.Timestamp("2023-09-01") + pd.to_timedelta(np.arange(len(ids)) % 1100, unit="D")
    frame["observed_on"] = [d.date().isoformat() for d in day]
    frame["created_at"] = [d.isoformat() + "T00:00:00Z" for d in day]
    server, _ = ib.serve(tmp_path_factory.mktemp("totals-site"), frame, score, totals=raw)
    yield f"http://127.0.0.1:{server.server_port}", frame
    server.shutdown()


def test_the_when_histogram_has_the_maps_two_layers_and_its_tooltip(browser, totals_site):
    base, frame = totals_site
    page = ib.open_identify(browser, base, "#lvl=1", size=(1100, 800))
    page.wait_for_function("__identify.ids().length > 0")
    page.click("#bwhen")
    # the light layer is drawn behind the dark one: both of the map's colours land on the canvas
    page.wait_for_function(LIGHT_BAR)
    box = page.locator("#hist").bounding_box()
    tip = ""
    for x in range(2, int(box["width"]), 3):  # a bar with records: its tip names both counts
        page.mouse.move(box["x"] + x, box["y"] + box["height"] - 20)
        tip = page.inner_text("#htip")
        if " of " in tip:
            break
    m = re.fullmatch(
        r"([A-Z][a-z]+ \d{4}): ([\d,]+) of ([\d,]+) still need an ID \((<1|\d+)%\), "
        r"([\d,]+) in Easy confirms",
        tip,
    )
    assert m, tip
    n, t, tab = (int(g.replace(",", "")) for g in (m[2], m[3], m[5]))
    assert 0 < n <= t and tab <= n
    # the dark layer is the map's count: every pool record of the month, at every level
    month = pd.to_datetime(m[1], format="%B %Y").strftime("%Y-%m")
    assert n == frame["observed_on"].str.startswith(month).sum()
    assert page.errors == []
