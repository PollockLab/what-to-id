"""Identify's chrome in Chromium: the search pill and Filters button open modal sheets (focus held,
Esc closes), a filter away from its default shows as a removable chip, the sheets' footers count the
cards, and the batch links sit in a popover. iNaturalist is stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .identify_sheets import close, reveal

browser = eb.browser
site = ib.site


def test_the_filters_sheet_holds_focus_closes_on_escape_and_counts_cards(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card")
    n = page.inner_text("#count").split(" ")[0]
    assert page.inner_text("#count").endswith(" cards to ID")
    page.click("#fbtn")
    sheet = page.locator("#fsheet")
    assert sheet.is_visible()
    inside = "document.activeElement.closest('#fsheet') !== null"
    assert page.evaluate(inside), page.evaluate("document.activeElement.outerHTML.slice(0, 200)")
    for _ in range(30):  # Tab cycles inside the modal
        page.keyboard.press("Tab")
        assert page.evaluate(inside)
    assert page.text_content("#fsheet .sdone") == f"Show {n} cards"
    close(page)
    assert sheet.is_hidden()
    assert page.evaluate("document.activeElement.id") == "fbtn"  # focus returns to the opener
    assert page.errors == []


def test_a_filter_off_its_default_shows_a_chip_that_removes_it(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card")
    assert page.locator("#chips .chip").count() == 0 and page.locator("#fcount").is_hidden()
    reveal(page, "#sort .seg")
    page.click("#sort button:has-text('All')")
    page.wait_for_function("location.hash.includes('conf=')")
    close(page)
    chip = page.locator("#chips .chip")
    assert chip.count() == 1 and page.inner_text("#fcount") == "1"
    assert page.get_attribute("#fbtn", "aria-label") == "Filters, 1 on"
    x = chip.locator(".chipx")
    assert x.get_attribute("aria-label").startswith("Remove Confidence")
    x.click()
    page.wait_for_function("!location.hash.includes('conf=')")
    assert page.locator("#chips .chip").count() == 0
    reveal(page, "#sort .seg")  # Clear all does the same for every filter
    page.click("#sort button:has-text('All')")
    page.wait_for_function("location.hash.includes('conf=')")
    page.click("#fclear")
    page.wait_for_function("!location.hash.includes('conf=')")
    assert page.errors == []


def test_the_pill_names_the_search_and_opens_its_sheet(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1")
    page.wait_for_function("__identify.ids().length > 0")
    assert page.get_attribute("#pill", "aria-label").startswith("Search: All groups, ")
    page.click("#pill")
    page.select_option("#grpsel", "Aves")
    page.wait_for_function("location.hash.includes('groups=Aves')")
    page.click("#ssheet .sdone")
    assert page.locator("#ssheet").is_hidden() and page.inner_text("#pwhat") == "Aves"
    assert page.errors == []


def test_the_batch_links_open_in_a_popover(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card")
    assert page.locator("#go").is_hidden() and page.locator("#inatb").is_visible()
    page.click("#inatb")
    assert page.locator("#go").is_visible() and page.inner_text("#cap").endswith(")")
    page.keyboard.press("Escape")
    assert page.locator("#go").is_hidden()
    assert page.errors == []
