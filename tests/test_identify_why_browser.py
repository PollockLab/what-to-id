"""The compare panel's "Why this card?": the level's rule, the place in the level, the look-alike,
the range verdict and the weights that raised the card, from data the page already holds, in
English and French, with no probability words and no POST. iNaturalist is stubbed."""

import re

from . import test_identify_browser as ib
from . import test_identify_fit_browser as fb
from . import test_identify_www_browser as wb

browser = fb.browser
site = fb.site
RULE_1 = "Labelled at species, and the photo matches its label best among the pool's species."
RULE_3 = (
    "Labelled above species, and the photo points to one species of it, unless it is an odd shot."
)
BANNED = re.compile(r"probabl|likel|certain", re.I)


def guarded(browser, fr=False):
    """A stand-in for `browser` whose pages share a context that refuses and records POSTs."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    ctx.posts = []
    if fr:
        ctx.add_init_script("localStorage.setItem('wtid-lang','fr')")

    def no_post(route):
        if route.request.method == "POST":
            ctx.posts.append(route.request.url)
            return route.abort()
        return route.fallback()

    ctx.route("**/*", no_post)
    return type("B", (), {"new_page": lambda self, **k: ctx.new_page(), "ctx": ctx})()


def opened(browser, base, hash_, fr=False):
    b = guarded(browser, fr)
    page = ib.open_identify(b, base, hash_)
    page.ctx = b.ctx
    return page


def why(page, card):
    """The explanation of a card, its details opened the way a user does."""
    ib.panel(page, card)
    d = page.locator("#cpexp")
    if not d.evaluate("e => e.open"):
        d.locator("summary").click()
    return d


def level_3(page, name="Apis c"):
    page.wait_for_function("document.querySelectorAll('#grid .card .look i').length > 0")
    page.wait_for_function(
        "window.__identify && __identify.ranges()"
    )  # open_row waits for a card only
    card = page.locator("#grid .card", has=page.locator(".look i", has_text=name)).first
    card.wait_for()
    return card


def test_level_1_names_its_rule_and_links_to_how_it_works(browser, site):
    base, _, _ = site
    page = opened(browser, base, "#lvl=1")
    page.wait_for_selector("#grid .card")
    d = why(page, page.locator("#grid .card").first)
    text = d.inner_text()
    assert page.locator("#tab1 span").first.inner_text() in text and RULE_1 in text
    assert d.locator("a.cwl").first.get_attribute("href").endswith("terms.html#level-clear-matches")
    assert not BANNED.search(text) and "Looks" not in text and "Ranks in" not in text
    assert page.ctx.posts == [] and page.errors == []


def test_level_3_names_the_rank_the_look_alike_the_range_verdict_and_the_weights(browser, site):
    base, _, _ = site
    b = guarded(browser)
    page = wb.open_row(b, base, "#lvl=3&conf=all&run=1&pri=conf:40,risk:60")
    page.ctx = b.ctx
    level_3(page, "Apis c")
    # look-alikes and ranges land after the first cards: wait for the card redrawn with its verdict
    page.wait_for_function(
        "[...document.querySelectorAll('#grid .card .range')]"
        ".some(e => /^Range: /.test(e.textContent))"
    )
    card = (
        page.locator("#grid .card", has=page.locator(".look i", has_text="Apis c"))
        .filter(has=page.locator(".range", has_text="Range: "))
        .first
    )
    verdict = card.locator(".range").inner_text()  # the card's own words for the range
    d = why(page, card)
    page.wait_for_function(
        "(() => { const t = document.querySelector('#cpexp ul').innerText;"
        " return ['Ranks in', 'Looks most like', 'Range: '].every(s => t.includes(s)); })()"
    )
    text = d.inner_text()
    assert RULE_3 in text, text
    assert "Looks most like Apis c" in text, text
    assert verdict in text, (verdict, text)
    assert re.search(
        r"Ranks in the best \d+% of this level .* A rank, not a measured accuracy\.", text
    )
    assert "Raised by Level order" in text
    assert d.locator("a.cwl[href$='terms.html#best-match']").count() == 1
    assert not BANNED.search(text)
    # At risk on: Apis c is at risk, so its card says so and links to the entry
    page.locator("#cpx").click()
    page.get_by_role("checkbox", name="At risk").check()
    page.wait_for_function(
        "[...document.querySelectorAll('#grid .card .look i')]"
        ".every(e => e.textContent === 'Apis c')"
    )
    text = why(page, level_3(page, "Apis c")).inner_text()
    assert "Raised by At risk: A species at risk, listed in Canada or BC S1-S3." in text
    assert page.locator("#cpexp a.cwl[href$='terms.html#threatened']").count() == 1
    # the weight off (Quick wins): the card stays, the line goes
    page.locator("#cpx").click()
    page.evaluate("document.querySelector('[data-preset=quick]').click()")
    page.wait_for_function("location.hash.includes('pri=conf:100')")
    text = why(page, level_3(page, "Apis c")).inner_text()
    assert "Raised by Level order" in text and "At risk" not in text
    assert page.ctx.posts == [] and page.errors == []


def test_the_best_cut_and_a_look_alike_without_a_range_say_so(browser, site):
    base, _, _ = site
    page = opened(browser, base, "#lvl=3&conf=5&run=1")
    text = why(page, level_3(page, "Bombus b")).inner_text()
    assert "Kept by Best 5%" in text and re.search(r"Range: |No range map", text)
    assert page.ctx.posts == []


def test_the_explanation_is_in_french(browser, site):
    base, _, _ = site
    page = opened(browser, base, "#lvl=3&conf=all&run=1", fr=True)
    text = why(page, level_3(page)).inner_text()
    page.wait_for_function("document.querySelector('#cpexp ul').innerText.includes('Se classe')")
    text = page.locator("#cpexp").inner_text()
    assert (
        "Pourquoi cette carte" in text and "Remontée par" in text and "Ressemble surtout à" in text
    )
    assert (
        "Se classe parmi les meilleurs" in text and "Un rang, pas une exactitude mesurée." in text
    )
    assert "Raised by" not in text and "Looks most like" not in text and "Ranks in" not in text
    assert (
        page.locator("#cpexp a.cwl")
        .first.get_attribute("aria-label")
        .startswith("Comment ça marche")
    )
    assert page.ctx.posts == []


def test_opening_the_details_shifts_no_card_and_they_keep_their_state(browser, site):
    base, _, _ = site
    page = opened(browser, base, "#lvl=1")
    page.wait_for_selector("#grid .card")
    cards = page.locator("#grid .card")
    ib.panel(page, cards.first)
    before = [cards.nth(k).bounding_box() for k in range(3)]
    d = page.locator("#cpexp")
    d.locator("summary").click()
    assert [cards.nth(k).bounding_box() for k in range(3)] == before
    page.keyboard.press("j")  # the next card: the details stay open
    assert d.evaluate("e => e.open") and d.is_visible()
