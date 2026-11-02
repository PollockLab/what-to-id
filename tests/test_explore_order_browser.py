"""Explore's pane order in Chromium: the pane switch's buttons set the order, by Alt+Arrow or a
drag, the frames keep their documents (CSS order, no reload), the link and this browser remember it.
Runs offline on the site and stand-ins of test_explore_home_browser.py."""

import os

from . import test_explore_home_browser as eh

browser, site, open_page, map_frame = eh.browser, eh.site, eh.open_page, eh.map_frame
SHOTS = os.environ.get("WTID_SHOTS")  # a folder: keep screenshots of the drag there
# the shown panes' names, left to right
LEFTS = (
    "['map', 'identify', 'space', 'tree'].map(n => [n, document.getElementById(n)])"
    ".filter(([n, f]) => f && !f.hidden).sort((a, b) => a[1].getBoundingClientRect().left"
    " - b[1].getBoundingClientRect().left).map(([n]) => n)"
)
BUTTONS = "[...document.querySelectorAll('.seg [data-p]')].map(b => b.dataset.p)"


def shot(page, name):
    if SHOTS:
        page.screenshot(
            path=f"{SHOTS}/{name}.png", clip={"x": 0, "y": 0, "width": 1280, "height": 300}
        )


def test_alt_arrow_reorders_the_panes_the_link_and_the_next_visit_without_reloading(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    map_frame(page)
    assert page.evaluate(LEFTS) == ["map", "identify"]
    page.evaluate("document.getElementById('identify').contentWindow.mark = 1")
    page.focus("[data-p=identify]")
    page.keyboard.press("Alt+ArrowLeft")
    assert page.evaluate(LEFTS) == ["identify", "map"]
    assert page.evaluate(BUTTONS)[:2] == ["identify", "map"]
    assert "view=identify-map" in page.url
    assert page.evaluate("document.getElementById('identify').contentWindow.mark") == 1  # no reload
    assert page.evaluate("document.activeElement.dataset.p") == "identify"
    page.focus("[data-p=map]")
    page.keyboard.press("Alt+ArrowRight")
    assert page.evaluate(BUTTONS)[:3] == [
        "identify",
        "space",
        "map",
    ]  # the hidden pane keeps a place
    page.click("[data-p=space]")
    assert page.evaluate(LEFTS) == ["identify", "space", "map"]
    assert "view=identify-space-map" in page.url
    assert "Panes, left to right" in page.text_content("[role=status]")
    page.goto(f"{site[0]}/explore.html")  # no view in the link: the order is kept
    map_frame(page)
    assert page.evaluate(LEFTS) == ["identify", "map"]
    assert page.evaluate(BUTTONS)[:3] == ["identify", "space", "map"]
    assert page.errors == []
    page.close()


def test_a_link_with_its_own_order_lays_the_panes_out_so_and_the_dividers_still_work(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html?view=space-identify-map")
    map_frame(page)
    assert page.evaluate(LEFTS) == ["space", "identify", "map"]
    assert page.evaluate(BUTTONS)[:3] == ["space", "identify", "map"]
    seps = page.locator(".sep")
    assert seps.count() == 2
    # by name: the dividers' DOM order differs from their order on screen
    left = page.locator(".sep[aria-label='Resize Photo space and Identify']")
    assert left.count() == 1
    wide = "document.getElementById('space').getBoundingClientRect().width"
    before = page.evaluate(wide)
    left.focus()
    page.keyboard.press("Shift+ArrowRight")
    assert page.evaluate(wide) > before  # the left pane of the divider grows
    page.close()
    # storage blocked: the order still moves, it just is not kept
    page = open_page(browser, "about:blank")
    page.add_init_script(eh.BLOCK)
    page.goto(f"{site[0]}/explore.html?view=identify-map")
    map_frame(page)
    page.focus("[data-p=map]")
    page.keyboard.press("Alt+ArrowLeft")
    assert page.evaluate(LEFTS) == ["map", "identify"]
    assert page.errors == []
    page.close()


def test_a_click_toggles_a_pane_and_a_drag_reorders_without_toggling(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    map_frame(page)
    page.click("[data-p=space]")
    assert page.evaluate(LEFTS) == ["map", "identify", "space"]
    page.click("[data-p=space]")
    assert page.evaluate(LEFTS) == ["map", "identify"]
    box, mbox = (
        page.locator("[data-p=identify]").bounding_box(),
        page.locator("[data-p=map]").bounding_box(),
    )
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] / 2, y)
    page.mouse.down()
    page.mouse.move(box["x"] + 2, y, steps=4)
    page.mouse.move(mbox["x"] + 4, y, steps=6)
    shot(page, "drag-mid")
    assert page.evaluate("document.querySelector('.seg .dr')?.dataset.p") == "identify"
    page.mouse.up()
    shot(page, "drag-after")
    assert page.evaluate(LEFTS) == ["identify", "map"]
    assert page.evaluate(BUTTONS)[:2] == ["identify", "map"]
    assert "view=identify-map" in page.url
    assert (
        page.evaluate("document.querySelectorAll('.seg [aria-pressed=true]').length") == 2
    )  # no toggle
    assert page.evaluate("localStorage.getItem('wtid-order')").startswith("identify-map")
    assert page.errors == []
    page.close()
