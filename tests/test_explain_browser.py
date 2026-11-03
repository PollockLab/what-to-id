"""The toggletips in Chromium: nothing shows at rest, hover opens after a delay on a desktop, a tap
opens a bottom sheet on a phone, and rows drawn later work without wiring."""

import time

from what_to_id import glossary, page_nav

from . import test_embeddings_browser as eb

browser = eb.browser
BODY = (
    '<main id="main-content"><p>Records that <span id="t" data-explain="needs-id">need an ID</span>'
    ' and a <button type="button" id="b" data-explain="needs-id" onclick="this.dataset.hit=1">'
    "button</button>.</p><p id=far>Elsewhere</p></main>"
)
POP = "#explain-pop"


def _page(browser, phone=False):
    html = (
        '<!doctype html><meta name=viewport content="width=device-width">'
        f"<style>{page_nav.CSS}</style><body>{page_nav.nav('map.html')}{BODY}"
    )
    ctx = (
        browser.new_context(viewport={"width": 390, "height": 800}, has_touch=True, is_mobile=True)
        if phone
        else browser.new_context(viewport={"width": 1000, "height": 700})
    )
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.set_content(html)
    page.wait_for_function("document.getElementById('t').getAttribute('role')==='button'")
    return page


def _lines(page):
    return [x for x in page.inner_text(POP).split("\n") if x]


def _shown(page):
    return page.is_visible(POP)


def test_at_rest_nothing_new_shows_and_controls_stay_controls(browser):
    page = _page(browser)
    assert not _shown(page)
    assert page.inner_text("main") == "Records that need an ID and a button.\n\nElsewhere"
    t = page.locator("#t")
    assert [t.get_attribute(a) for a in ("role", "tabindex", "aria-expanded")] == [
        "button",
        "0",
        "false",
    ]
    assert "dotted" in t.evaluate("e => getComputedStyle(e).textDecorationStyle")
    # a tagged button keeps its own click and never opens the toggletip
    assert page.get_attribute("#b", "role") is None
    page.click("#b")
    assert page.get_attribute("#b", "data-hit") == "1" and not _shown(page)
    assert page.errors == []


def test_desktop_hover_opens_after_a_delay_and_esc_closes(browser):
    page = _page(browser)
    start = time.monotonic()
    page.hover("#t")
    assert not _shown(page)
    page.wait_for_selector(POP, state="visible")
    assert time.monotonic() - start >= 0.25
    assert _lines(page)[1:] == [glossary.GLOSSARY["needs-id"][0]]
    assert page.get_attribute("#t", "aria-expanded") == "true"
    box, t = page.locator(POP).bounding_box(), page.locator("#t").bounding_box()
    assert box["y"] >= t["y"] + t["height"] and box["x"] + box["width"] <= 1000
    page.keyboard.press("Escape")
    assert not _shown(page) and page.get_attribute("#t", "aria-expanded") == "false"
    # unpinned, it closes when the pointer leaves
    page.mouse.move(900, 650)
    page.hover("#t")
    page.wait_for_selector(POP, state="visible")
    page.mouse.move(900, 650)
    page.wait_for_selector(POP, state="hidden")


def test_keyboard_pins_it_and_esc_returns_focus(browser):
    page = _page(browser)
    page.focus("#t")
    page.keyboard.press("Enter")
    assert _shown(page) and page.evaluate("document.activeElement.id") == "explain-pop"
    page.keyboard.press("Escape")
    assert not _shown(page) and page.evaluate("document.activeElement.id") == "t"
    page.keyboard.press(" ")
    assert _shown(page)
    page.click("#far")
    assert not _shown(page)


def test_phone_tap_opens_a_bottom_sheet(browser):
    page = _page(browser, phone=True)
    page.tap("#t")
    assert _shown(page)
    box = page.locator(POP).bounding_box()
    assert box["x"] == 0 and box["width"] == 390 and box["y"] + box["height"] == 800
    page.tap("#t")
    assert not _shown(page)
    page.tap("#t")
    page.tap(".xx")
    assert not _shown(page)


def test_rows_drawn_later_work_without_wiring(browser):
    page = _page(browser)
    page.evaluate(
        "var s=document.createElement('span');s.id='late';s.textContent='Research Grade';"
        "s.dataset.explain='research-grade';document.querySelector('main').append(s)"
    )
    page.wait_for_function("document.getElementById('late').tabIndex===0")
    page.click("#late")
    assert _lines(page)[1:] == [glossary.GLOSSARY["research-grade"][0]]
    # an unknown key is left alone
    page.evaluate("document.getElementById('late').dataset.explain='no-such-key'")
    page.click("#far")
    page.click("#late")
    assert not _shown(page)


def test_use_line_and_more_link_show_when_given(browser, monkeypatch):
    monkeypatch.setitem(
        glossary.GLOSSARY, "needs-id", ("A term.", "Use it when testing.", "about.html#x")
    )
    page = _page(browser)
    page.click("#t")
    assert _lines(page) == ["×", "A term.", "Use it when testing.", "More →"]
    assert page.get_attribute(f"{POP} a", "href") == "about.html#x"
