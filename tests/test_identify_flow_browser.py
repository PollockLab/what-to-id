"""Identify's level 3 flow in Chromium: one reused iNaturalist popup, the name copied on Identify,
the Opened mark and the next card's focus, and the j, k, i, Enter and c keys. window.open and the
clipboard are stubbed; iNaturalist is stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site

STUBS = """
window.OPENED = []; window.COPIED = [];
window.open = (u, n, f) => (OPENED.push([u, n, f]), {focus() {}});
Object.defineProperty(navigator, 'clipboard',
  {value: {writeText: t => (COPIED.push(t), Promise.resolve())}});
"""


def level_3(browser, base, hash_="#lvl=3"):
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script(STUBS)
    eb.stub_inat(page, None)
    page.route("https://pollocklab.github.io/**", lambda r: r.abort())  # no gap data needed here
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_selector("#grid .card .copy")
    return page


def test_identify_copies_the_name_and_opens_the_one_named_popup(browser, site):
    base, _ = site
    page = level_3(browser, base)
    first, second = page.locator("#grid .card").nth(0), page.locator("#grid .card").nth(1)
    name = first.locator(".look i").inner_text()
    href = first.locator("a.btn").get_attribute("href")
    assert first.locator("a.btn").get_attribute("target") == "wtid-inat"
    first.locator("a.btn").click()
    second.locator("a.btn").click()
    opened = page.evaluate("OPENED")
    assert [o[1] for o in opened] == ["wtid-inat", "wtid-inat"] and opened[0][0].endswith(
        href[-20:]
    )
    assert "popup" in opened[0][2] and "width=" in opened[0][2] and "left=" in opened[0][2]
    assert page.evaluate("COPIED")[0] == name
    first.locator(".when").click()  # the observation link shares the window
    assert page.evaluate("OPENED")[-1][1] == "wtid-inat"
    assert page.errors == []


def test_identify_marks_the_card_opened_and_focuses_the_next(browser, site):
    base, _ = site
    page = level_3(browser, base)
    cards = page.locator("#grid .card")
    assert cards.nth(0).locator(".opened").count() == 0
    cards.nth(0).locator("a.btn").click()
    assert cards.nth(0).locator(".opened").inner_text() == "Opened"
    assert page.evaluate("document.activeElement.dataset.id") == cards.nth(1).get_attribute(
        "data-id"
    )
    cards.nth(0).locator("a.btn").click()
    assert cards.nth(0).locator(".opened").count() == 1  # marked once
    assert page.errors == []


def test_the_keys_move_open_and_copy_and_the_hint_shows_on_level_3_only(browser, site):
    base, _ = site
    page = level_3(browser, base)
    ids = page.evaluate("[...document.querySelectorAll('#grid .card')].map(c => c.dataset.id)")
    focused = "document.activeElement.dataset.id"
    assert page.locator("#keys").is_visible()
    page.keyboard.press("j")
    assert page.evaluate(focused) == ids[0]
    page.keyboard.press("j")
    assert page.evaluate(focused) == ids[1]
    page.keyboard.press("k")
    assert page.evaluate(focused) == ids[0]
    page.keyboard.press("c")
    assert len(page.evaluate("COPIED")) == 1 and page.evaluate("OPENED") == []
    page.keyboard.press("i")
    assert len(page.evaluate("OPENED")) == 1 and page.evaluate(focused) == ids[1]
    page.keyboard.press("Enter")
    assert len(page.evaluate("OPENED")) == 2 and page.evaluate(focused) == ids[2]
    page.focus("#grpsel")  # a form field keeps its keys
    page.keyboard.press("j")
    assert page.evaluate("document.activeElement.id") == "grpsel"
    page.click("#tab1")
    assert page.locator("#keys").is_hidden()
    assert page.errors == []
