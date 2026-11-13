"""Identify's photo-first cards in Chromium: the photo carousel (arrows, keys, dots), the
proposed species line, and the detail lent to the compare panel. iNaturalist is stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site


def test_the_carousel_flips_with_arrows_and_keys(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card .car .flip.nxt:visible")
    card = page.locator("#grid .card").first
    car = card.locator(".car")
    n = car.locator(".dots span").count()
    assert n >= 2 and car.get_attribute("data-at") == "0"
    assert card.locator(".flip.nxt").get_attribute("aria-label") == "Next photo"
    card.locator(".flip.nxt").click()
    assert car.get_attribute("data-at") == "1" and card.locator(".cap").inner_text()
    assert not page.locator("#cpanel").is_visible()  # an arrow flips, it does not open the panel
    card.focus()
    page.keyboard.press("ArrowLeft")
    assert car.get_attribute("data-at") == "0"
    page.keyboard.press("ArrowLeft")
    assert car.get_attribute("data-at") == str(n - 1)
    assert page.errors == []


def test_the_face_names_the_proposal_and_the_panel_borrows_the_detail(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card .look", state="attached")
    card = page.locator("#grid .card").first
    look = card.locator(".look i").inner_text()
    assert card.locator(".face .hl").inner_text() == f"{look}?"
    assert card.locator(".face .from").inner_text().startswith("from ")
    card.locator(".car").click()
    page.wait_for_selector("#cpanel #cpdet .det", state="attached")
    assert card.locator(".det").count() == 0
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#grid .card .det')")
    assert page.errors == []
