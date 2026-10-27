"""The panes of the split page in Chromium: a divider between each two shown panes, the phone
header, and the viewport reaching Identify. Fixtures come from test_split_identify_browser.py."""

import pytest

from . import test_split_identify_browser as si

browser, site, pts = si.browser, si.site, si.pts
explore, frame_of = si.explore, si.frame_of

VIEW = "?view=identify-map-tree"
PANES = "[...document.querySelectorAll('#main-content iframe')]"
WIDTHS = PANES + ".map(f => f.getBoundingClientRect().width)"


def _page(browser, site, query=VIEW, width=1500):
    base, *_ = site
    page = explore(browser, base, query, width)
    page.wait_for_function(f"{WIDTHS}.length === {len(query.split('=')[1].split('-'))}")
    return page


def _drag(page, i, dx, off=0):
    box = page.locator(".sep").nth(i).bounding_box()
    x, y = box["x"] + box["width"] / 2 + off, box["y"] + 100
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=8)
    page.mouse.up()


def test_n_panes_have_n_minus_one_dividers_with_good_defaults(browser, pts, site):
    page = _page(browser, site)
    seps = page.locator(".sep")
    assert seps.count() == 2
    assert [seps.nth(i).get_attribute("role") for i in range(2)] == ["separator"] * 2
    assert all(seps.nth(i).get_attribute("aria-valuenow") for i in range(2))
    identify, map_, tree = page.evaluate(WIDTHS)
    assert 320 <= identify <= 440 and tree == pytest.approx(0.3 * 1500, rel=0.08) and map_ > 300
    page.click("[data-p=tree]")
    assert page.locator(".sep").count() == 1
    page.click("[data-p=map]")
    assert page.locator(".sep").count() == 0
    page.close()


def test_dragging_a_divider_moves_only_its_two_panes_and_is_remembered(browser, pts, site):
    page = _page(browser, site)
    before = page.evaluate(WIDTHS)
    _drag(page, 0, 60)
    after = page.evaluate(WIDTHS)
    assert after[0] == pytest.approx(before[0] + 60, abs=3)
    assert after[1] == pytest.approx(before[1] - 60, abs=3)
    assert after[2] == pytest.approx(before[2], abs=1)
    assert page.evaluate("document.getElementById('main-content').className") == ""
    page.reload()
    page.wait_for_function(f"{WIDTHS}.length === 3")
    assert page.evaluate(WIDTHS) == pytest.approx(after, abs=3)
    page.close()


def test_a_divider_can_be_grabbed_beside_its_line(browser, pts, site):
    page = _page(browser, site)
    before = page.evaluate(WIDTHS)
    _drag(page, 0, 40, off=-10)  # over the pane on the left, inside the 23 px target
    assert page.evaluate(WIDTHS)[0] == pytest.approx(before[0] + 40, abs=3)
    page.close()


def test_the_minimum_widths_hold(browser, pts, site):
    page = _page(browser, site)
    _drag(page, 0, -2000)
    identify, map_, tree = page.evaluate(WIDTHS)
    assert identify == pytest.approx(280, abs=1) and tree > 250
    _drag(page, 1, 2000)  # the tree shrinks to its floor
    assert page.evaluate(WIDTHS)[2] == pytest.approx(260, abs=1)
    _drag(page, 0, 2000)  # the map shrinks to its floor
    assert page.evaluate(WIDTHS)[1] == pytest.approx(320, abs=1)
    page.close()


def test_arrow_keys_move_a_divider_and_a_double_click_resets_it(browser, pts, site):
    page = _page(browser, site)
    before = page.evaluate(WIDTHS)
    sep = page.locator(".sep").first
    sep.focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate(WIDTHS)[0] == pytest.approx(before[0] + 16, abs=2)
    page.keyboard.press("Shift+ArrowLeft")
    assert page.evaluate(WIDTHS)[0] == pytest.approx(before[0] - 48, abs=2)
    page.keyboard.press("Enter")
    assert page.evaluate(WIDTHS) == pytest.approx(before, abs=2)
    _drag(page, 1, -80)
    assert page.evaluate(WIDTHS)[2] == pytest.approx(before[2] + 80, abs=3)
    page.locator(".sep").nth(1).dblclick()
    assert page.evaluate(WIDTHS) == pytest.approx(before, abs=2)
    page.close()


def test_a_broken_store_falls_back_to_the_defaults(browser, pts, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.add_init_script("localStorage.setItem('wtid-panes', '{nope')")
    page.goto(f"{base}/explore.html{VIEW}")
    page.wait_for_function(f"{WIDTHS}.length === 3")
    assert page.locator(".sep").count() == 2
    page.close()


@pytest.mark.parametrize("width", [390, 800])
def test_the_header_fits_the_viewport_with_tappable_toggles(browser, pts, site, width):
    base, *_ = site
    page = explore(browser, base, "", width)
    page.wait_for_selector("#xbar [data-p=tree]")
    boxes = page.evaluate(
        "[...document.querySelectorAll('#xbar [data-p], #sq, #counts')].map(e => {"
        " const r = e.getBoundingClientRect();"
        " return [e.id || e.dataset.p, r.left, r.right, r.height]; })"
    )
    assert [b[0] for b in boxes if b[0] != "sq" and b[0] != "counts"] == [
        "identify",
        "map",
        "space",
        "tree",
    ]
    for name, left, right, height in boxes:
        assert left >= 0 and right <= width, name
        if name not in ("sq", "counts"):
            assert height >= 32 and page.is_visible(f"[data-p={name}]")
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    page.close()


def test_hiding_the_map_clears_the_viewport_in_identify_and_showing_it_replays_it(
    browser, pts, site
):
    page = _page(browser, site, "?view=identify-map")
    page.evaluate(
        "window.got = []; document.getElementById('identify').contentWindow.addEventListener("
        "'message', e => e.data.type === 'wtid-view' && got.push(e.data.area))"
    )
    frame_of(page, "map").evaluate(
        "parent.postMessage({type: 'wtid-view', area: 'abc'}, location.origin)"
    )
    page.wait_for_function("got.length === 1")
    page.wait_for_function(
        "/to identify · .*on map, both in view/.test(document.getElementById('counts').textContent)"
    )
    page.click("[data-p=map]")
    page.wait_for_function("got.length === 2")
    assert page.evaluate("got") == ["abc", ""]
    page.click("[data-p=map]")
    page.wait_for_function("got.length === 3")
    assert page.evaluate("got[2]") == "abc"
    page.close()


def test_a_more_link_in_identify_sends_its_species_to_the_map(browser, pts, site):
    page = _page(browser, site, "?view=identify-map")
    frame = frame_of(page, "identify")
    page.evaluate(
        "window.got = []; document.getElementById('map').contentWindow.addEventListener("
        "'message', e => e.data.type === 'wtid-selection' && got.push(e.data.sel))"
    )
    frame.wait_for_selector("#grid .card .sp")
    frame.locator("#grid .card .sp").first.click()
    page.wait_for_function("got.some(s => /(^|&)taxa=/.test(s))")
    page.close()
