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


def test_the_what_segment_names_the_search_and_opens_its_panel(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1")
    page.wait_for_function("__identify.ids().length > 0")
    assert page.inner_text("#bwhat b") == "All groups"
    page.click("#bwhat")
    page.locator("#groups .gb", has_text="Birds").first.click()
    page.wait_for_function("location.hash.includes('groups=Aves')")
    assert page.inner_text("#bwhat b") == "Birds"
    assert page.errors == []


def test_the_batch_button_is_in_view_and_keyboard_reachable(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card")
    go = page.locator("#go")
    assert (
        go.is_visible()
        and go.inner_text().startswith("Identify ")
        and go.inner_text().endswith(" on iNaturalist")
    )
    assert "/observations/identify?" in go.get_attribute("href")
    assert page.inner_text("#cap").endswith(")")
    go.focus()
    assert page.evaluate("document.activeElement.id") == "go"
    assert page.errors == []


def test_the_help_button_holds_the_notes_totals_and_keys(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card")
    assert page.locator("#status").is_hidden() and page.locator("#about").is_hidden()
    page.click("#helpb")
    for sel in ("#status", "#prog", "#desc", "#hint summary", "#about summary"):
        assert page.locator(sel).is_visible(), sel
    assert page.locator("#help .sub").is_visible()
    close(page)
    assert page.evaluate("document.activeElement.id") == "helpb"
    assert page.errors == []


def test_the_batch_button_opens_the_next_batch_by_keyboard(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card")
    page.evaluate(  # two records per batch, so the list spans several
        "() => { const f = IdentifyLinks.batches; IdentifyLinks.batches = ids => "
        "Array.from({length: Math.ceil(ids.length / 2)}, "
        "(_, i) => f(ids.slice(2 * i, 2 * i + 2))[0]); }"
    )
    ib.tab(page, 1).click()
    ib.tab(page, 3).click()
    go = page.locator("#go")

    def ids():
        return [int(i) for i in go.get_attribute("href").split("&id=")[1].split(",")]

    n = len(page.evaluate("__identify.view()")[3])
    assert go.inner_text() == "Identify these 2 on iNaturalist"
    assert (
        page.inner_text("#bn") == f"Batch 1 of {-(-n // 2)}" and page.locator("#prev").is_disabled()
    )
    first = ids()
    page.focus("#next")
    page.keyboard.press("Enter")
    assert page.inner_text("#bn").startswith("Batch 2 of ") and ids() != first
    page.focus("#go")  # Tab order: button, then the arrows, all keyboard reachable
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "prev"
    assert page.errors == []
