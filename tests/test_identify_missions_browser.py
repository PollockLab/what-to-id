"""Identify's Start here strip: up to six missions between the bar and the tabs. A click applies
one as hash filters and shows exactly its cards, the chip counts the marked ones and its x
restores the address. iNaturalist and where-to-blitz are stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .test_identify_gaps_browser import stub_checklist

browser = eb.browser
site = ib.site


def open_strip(browser, base, hash_="#lvl=1", size=(1280, 900)):
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    stub_checklist(page)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_selector("#missions .mcard")
    return page


def test_the_strip_sits_between_the_bar_and_the_tabs_and_scrolls_inside_itself(browser, site):
    base, _ = site
    page = open_strip(browser, base, size=(375, 800))
    assert 1 <= page.locator(".mcard").count() <= 6
    order = page.evaluate(
        "['bar','missions','qrow'].map(i => document.getElementById(i).getBoundingClientRect().top)"
    )
    assert order == sorted(order)
    assert page.evaluate("document.documentElement.scrollWidth <= 375")
    page.focus(".mcard")  # a button, so the keyboard reaches it
    assert page.evaluate("document.activeElement.classList.contains('mcard')")
    meta = page.inner_text(".mcard .mmeta")
    assert " cards · " in meta and " · gap " in meta and "/30" in meta
    assert page.errors == []


def test_the_strip_is_hidden_without_a_big_enough_part(browser, site):
    base, _ = site
    page = browser.new_page()  # level 3 holds too few cards of one group in a cell
    eb.stub_inat(page, None)
    stub_checklist(page)
    page.goto(f"{base}/identify.html#lvl=3")
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    page.wait_for_timeout(500)
    assert page.locator("#missions").is_hidden()


def test_a_mission_applies_its_filters_shows_exactly_its_cards_and_x_restores(browser, site):
    base, _ = site
    page = open_strip(browser, base)
    before = page.evaluate("location.hash")
    first = page.locator(".mcard").first
    n = int(first.get_attribute("data-n"))
    first.click()
    page.wait_for_selector("#mchip:not([hidden])")
    page.wait_for_function(f"__identify.view()[1].length === {n}")
    h = page.evaluate("location.hash")
    assert "groups=" in h and "area=" in h and "lvl=1" in h  # an ordinary, shareable link
    assert page.locator("#missions").is_hidden()
    assert page.inner_text("#mchip").startswith("Mission: ")
    assert f"0 of {n} marked" in page.inner_text("#mchip")
    assert page.inner_text("#count").startswith(f"{n} cards")
    ids = page.evaluate("__identify.view()[1]")
    page.reload()  # the link alone gives the same cards
    page.wait_for_function(f"window.__identify && __identify.view()[1].length === {n}")
    assert page.evaluate("__identify.view()[1]") == ids
    page.goto(f"{base}/identify.html{before}")
    page.wait_for_selector(".mcard")
    page.locator(".mcard").first.click()
    page.wait_for_selector("#mchip .mx")
    page.click("#mchip .mx")
    page.wait_for_selector("#missions .mcard")
    assert page.evaluate("location.hash") == before
    assert page.locator("#mchip").is_hidden()
    assert page.errors == []


def test_marking_cards_moves_the_chips_progress(browser, site):
    base, _ = site
    page = open_strip(browser, base)
    n = int(page.locator(".mcard").first.get_attribute("data-n"))
    page.locator(".mcard").first.click()
    page.wait_for_function(f"__identify.view()[1].length === {n}")
    page.wait_for_selector("#mchip:not([hidden])")
    page.evaluate("IdentifyFlow.mark(document.querySelector('#grid .card'), 'Skipped')")
    assert f"1 of {n} marked" in page.inner_text("#mchip")
    page.evaluate("IdentifyFlow.undo()")
    assert f"0 of {n} marked" in page.inner_text("#mchip")
