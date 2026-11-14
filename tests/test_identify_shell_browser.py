"""Identify's chrome in Chromium: the search pill and Filters button open modal sheets (focus held,
Esc closes), a filter away from its default shows as a removable chip, the sheets' footers count the
cards, and the batch links sit in a popover. iNaturalist is stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .identify_sheets import close

browser = eb.browser
site = ib.site


def test_the_modes_sit_on_the_bar_row_with_their_counts(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base)
    assert page.locator("#fbtn, #fsheet, #chips").count() == 0  # no Filters sheet any more
    tabs = page.get_by_role("tab")
    assert (
        tabs.first.is_visible() and page.evaluate("__identify.level()") == 1
    )  # Easy confirms by default
    total = page.evaluate("__identify.total()")
    assert " ".join(tabs.first.inner_text().split()) == f"Easy confirms {total[1]:,}"
    top = page.locator(".top")
    assert top.locator("#bar").is_visible() and top.locator("#tabs").is_visible()
    assert top.locator("#qchips label").count() == 2  # At risk and Invasive
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.errors == []


def test_no_filter_heading_is_ever_visible_without_its_control(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base)
    for lv in (1, 5, 3):
        ib.tab(page, lv).click()
        page.wait_for_selector("#grid .card")
        empty = page.evaluate(
            """() => [...document.querySelectorAll('.top .qseg')].filter(e => e.offsetParent
            && !e.querySelector('button,input,select')).map(e => e.id)"""
        )
        assert empty == [], (lv, empty)
        assert page.locator("#fsh, .ssec, .ssec h3").count() == 0
    assert page.errors == []


def test_the_who_segment_holds_the_login_threshold_and_the_three_ticks(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1&user=12345&umin=20")
    assert page.inner_text("#bwho small") == "Who"
    page.wait_for_function("document.querySelector('#bwho b').textContent === '@12345'")
    page.click("#bwho")
    page.wait_for_selector("#usrbox", state="visible")
    assert page.locator("#uload").is_hidden()
    assert page.locator("#usrname").is_visible()
    assert page.locator("#usrbox select[aria-label='Fewest IDs in a genus']").is_visible()
    labels = page.locator("#usrbox form > label:has(input[type=checkbox])").all_inner_texts()
    assert [t.strip() for t in labels] == [
        "Only @12345's genera",
        "Hide records @12345 identified",
        "Only records @12345 observed",
    ]
    page.locator("#usrbox label", has_text="Only @12345's genera").click()
    page.wait_for_function("location.hash.includes('umode=')")
    page.wait_for_function(
        "document.querySelector('#bwho b').textContent.startsWith('@12345 \u00b7 ')"
    )
    assert page.locator("#ubtn, #upop").count() == 0
    assert page.errors == []


def test_who_says_anyone_without_a_user_and_the_bar_wraps_on_a_phone(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1")
    assert page.inner_text("#bwho b") == "Anyone"
    page.set_viewport_size({"width": 375, "height": 800})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    tops = page.evaluate(
        "[...document.querySelectorAll('#bar .seg1')].map(e => e.getBoundingClientRect().top)"
    )
    assert len(tops) == 4 and len(set(tops)) == 2  # a 2x2 grid
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


def test_the_who_ticks_wait_for_a_user_name_and_say_so(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=1")
    page.click("#bwho")
    page.wait_for_selector("#usrbox", state="visible")
    assert page.inner_text("#usrhint") == "Enter a user name first"
    for box in ("taxa", "unid", "observer"):
        assert page.is_disabled(f"#usr{box}")
    assert "user" in page.inner_text("#usrbox form")  # the labels name the user, not "I" or "my"
    assert "my genera" not in page.inner_text("#usrbox form").lower()
    page.fill("#usrname", "JDoe")
    page.press("#usrname", "Enter")
    page.wait_for_function("document.getElementById('usrhint').hidden")
    assert page.inner_text("#usrbox form > label:has(#usrtaxa)").strip() == "Only @JDoe's genera"
    assert page.is_enabled("#usrtaxa") and page.errors == []
