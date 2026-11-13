"""Identify's level 3 flow in Chromium: one reused iNaturalist tab, the name copied on Identify,
the Opened mark and the next card's focus, and the j, k, i, Enter and c keys. window.open and the
clipboard are stubbed; iNaturalist is stubbed."""

from urllib.parse import parse_qs, urlparse

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
    assert [o[2] for o in opened] == [None, None]  # a tab: no window features
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
    page.click("#hint summary")  # the keys sit in the notes line
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


def stub_taxa(page):
    """Each taxon has two photos; each species' similar species are taxa 901 and 902; a name
    search finds taxon 950 under that name."""

    def api(route):
        path = route.request.url.split("/v1/", 1)[1]
        if path.startswith("taxa?"):
            name = parse_qs(urlparse(route.request.url).query)["q"][0]
            body = {"results": [{"id": 950, "name": name, "taxon_photos": []}]}
        elif path.startswith("identifications/similar_species"):
            body = {
                "results": [
                    {"count": 5, "taxon": {"id": t, "name": f"Sim {t}"}} for t in (901, 902, 903)
                ]
            }
        else:
            ids = [int(i) for i in path.split("?")[0].split("/")[1].split(",")]
            photo = {
                "url": "https://static.inaturalist.org/photos/1/square.jpg",
                "attribution": "(c) x",
            }
            body = {
                "results": [
                    {
                        "id": i,
                        "name": f"Taxon {i}",
                        "wikipedia_summary": f"<b>Taxon {i}</b> is a bee. It flies."
                        if i != 902
                        else "A " + "very " * 40 + "long one. More.",
                        "default_photo": {"square_url": photo["url"]},
                        "taxon_photos": [{"photo": photo}, {"photo": photo}],
                    }
                    for i in ids
                ]
            }
        route.fulfill(json=body, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/taxa/**", api)
    page.route("https://api.inaturalist.org/v1/taxa?*", api)
    page.route("https://api.inaturalist.org/v1/identifications/similar_species*", api)


def test_the_compare_panel_shows_photos_and_works_from_the_keys(browser, site):
    base, _ = site
    page = level_3(browser, base)
    stub_taxa(page)
    cards = page.locator("#grid .card")
    ids = page.evaluate("[...document.querySelectorAll('#grid .card')].map(c => c.dataset.id)")
    name = cards.nth(0).locator(".look i").inner_text()
    cards.nth(0).locator(".title").click()
    panel = page.locator("#cpanel")
    assert panel.is_visible() and panel.get_attribute("role") == "dialog"
    assert page.evaluate("document.activeElement.id") == "cpanel"
    assert name in panel.locator("#cphead").inner_text()
    assert "/large." in panel.locator(".cpbig").get_attribute("src")
    page.wait_for_selector(
        "#cprefs .cpref"
    )  # the suggestion is not in the taxa table: its name, no photos
    assert name in panel.locator(".cpref h3").first.inner_text()
    why = cards.nth(0).locator(".why").inner_text()
    assert why.startswith("vs ") and panel.locator("#cpwhy").inner_text() == why
    rival = why[3:].split(",")[0]
    h = panel.locator(".cpref h3").all_inner_texts()
    assert h[1:] == [f"Runner-up {rival}"]  # a name with no taxon id has no similar species
    page.keyboard.press("c")
    assert page.evaluate("COPIED")[-1] == name
    page.keyboard.press("s")  # skipped, on to the next
    assert cards.nth(0).locator(".opened").inner_text() == "Skipped"
    assert panel.locator("#cpat").inner_text().startswith("2 of")
    page.keyboard.press("u")  # undone: back on the first, unmarked
    assert cards.nth(0).locator(".opened").count() == 0
    assert panel.locator("#cpat").inner_text().startswith("1 of")
    page.keyboard.press("u")  # one step only
    assert panel.locator("#cpat").inner_text().startswith("1 of")
    page.keyboard.press("s")
    second = cards.nth(1).locator(".look i").inner_text()
    before = panel.locator("#cpo").bounding_box()
    page.keyboard.press("Enter")  # copies, opens in the one tab, marked, on to the next
    assert page.evaluate("OPENED")[-1][1] == "wtid-inat" and page.evaluate("COPIED")[-1] == second
    page.wait_for_function("document.getElementById('cpt').textContent.length > 0")
    assert panel.locator("#cpt").inner_text() == f"Copied {second}, paste in iNat"
    assert panel.locator("#cpo").bounding_box() == before  # the toast does not move Identify
    assert cards.nth(1).locator(".opened").inner_text() == "Opened"
    assert panel.locator("#cpat").inner_text().startswith("3 of")
    page.keyboard.press("k")
    assert panel.locator("#cpat").inner_text().startswith("2 of")
    page.keyboard.press("Escape")
    assert not panel.is_visible() and page.evaluate("document.activeElement.dataset.id") == ids[1]
    assert page.errors == []


def test_the_compare_panel_fits_a_phone_with_the_species_and_two_similar(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 360, "height": 740})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script(STUBS)
    eb.stub_inat(page, None)
    stub_taxa(page)
    page.goto(f"{base}/identify.html#lvl=1")
    page.locator("#grid .card .title").first.click()
    page.wait_for_function("document.querySelectorAll('#cprefs .cpref').length === 3")
    h = page.locator("#cprefs .cpref h3").all_inner_texts()
    assert h[0].startswith("Label") and h[1:] == [
        "Similar Taxon 901",
        "Similar Taxon 902",
    ]  # the whole record
    assert page.locator("#cprefs .cpref").first.locator("img").count() == 2
    sums = page.locator("#cprefs .cpref .cpsum")
    assert sums.nth(1).inner_text() == "Taxon 901 is a bee."  # HTML stripped, first sentence
    assert len(sums.nth(2).inner_text()) == 140 and sums.nth(2).inner_text().endswith("…")
    assert sums.nth(2).get_attribute("title").endswith("long one. More.")
    assert "/medium." in page.locator("#cprefs img").first.get_attribute("src")
    box = page.locator("#cpanel").bounding_box()
    assert box["x"] == 0 and box["width"] == 360
    assert page.evaluate("document.querySelector('#cpanel').scrollWidth <= 360")
    assert page.errors == []


def test_the_panel_asks_for_its_observation_when_the_cards_have_not_got_it(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script(STUBS)
    eb.stub_inat(page, None)
    stub_taxa(page)
    held = []

    def hold(route):  # the cards' request, many ids, hangs; the panel's own one id goes through
        if "%2C" in route.request.url or "," in route.request.url:
            held.append(route)
        else:
            route.fallback()

    page.route("https://api.inaturalist.org/v1/observations*", hold)
    page.goto(f"{base}/identify.html#lvl=3")
    page.wait_for_selector("#grid .card .copy")
    assert page.locator("#grid .card .ph img").count() == 0 and held
    page.locator("#grid .card .title").first.click()
    page.wait_for_selector("#cpobs .cpbig")
    assert "Vancouver" in page.inner_text("#cpobs .cpwhen")
    assert page.errors == []


def test_the_why_line_names_the_runner_up_and_the_margin_in_words(browser, site):
    base, _ = site
    page = level_3(browser, base)
    page.wait_for_selector("#grid .card .why")
    lines = page.locator("#grid .card .why")
    words = {t.split(", ")[-1] for t in lines.all_inner_texts()}
    assert words <= {"close call", "fair margin", "clear margin"} and len(words) > 1
    assert "Margin 0.0" in lines.first.get_attribute("title")
    assert page.locator("#grid .card .why").count() == page.locator("#grid .card .copy").count()
    page.click("#tab1")
    page.wait_for_function("__identify.level() === 1")
    assert page.locator("#grid .card .why").count() == 0
    assert page.errors == []


def test_a_photo_that_fails_leaves_a_blank_box_not_its_alt_text(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    page.route("https://static.inaturalist.org/**", lambda r: r.fulfill(status=404))
    page.goto(f"{base}/identify.html#lvl=3")
    page.wait_for_function(
        "(l => l.length && l.every(i => !i.hasAttribute('src')))"
        "([...document.querySelectorAll('#grid .card .ph img')].slice(0, 2))"
    )
    img = page.locator("#grid .card .ph img").first
    assert img.evaluate("i => getComputedStyle(i).visibility") == "hidden"
    assert page.errors == []


def test_a_first_visit_shows_the_key_tip_until_dismissed(browser, site):
    base, _ = site
    page = level_3(browser, base)
    tip = page.locator("#tip")
    assert tip.is_visible() and "u undo" in tip.inner_text()
    tip.locator("button").click()
    assert not tip.is_visible()
    page.reload()
    page.wait_for_selector("#grid .card")
    assert not page.locator("#tip").is_visible()


def test_a_touch_device_tip_has_no_keys(browser, site):
    base, _ = site
    ctx = browser.new_context(has_touch=True, is_mobile=True, viewport={"width": 400, "height": 800})
    page = ctx.new_page()
    eb.stub_inat(page, None)
    page.goto(f"{base}/identify.html#lvl=3")
    page.wait_for_selector("#grid .card")
    assert page.inner_text("#tip").startswith("Tap a card to compare. Identify opens iNat")
    assert "undo" not in page.inner_text("#tip")
    ctx.close()


def test_the_panel_keeps_focus_and_announces_each_card(browser, site):
    base, _ = site
    page = level_3(browser, base)
    stub_taxa(page)
    cards = page.locator("#grid .card")
    label = cards.nth(0).locator(".title i").first.inner_text()
    look = cards.nth(0).locator(".look i").inner_text()
    cards.nth(0).locator(".title").click()
    live = page.locator("#cplive")
    assert live.get_attribute("aria-live") == "polite"
    assert live.text_content().endswith(f", {label} to {look}") and live.text_content().startswith("1 of ")
    inside = "document.getElementById('cpanel').contains(document.activeElement)"
    for key in ["Tab"] * 12 + ["Shift+Tab"] * 12:
        page.keyboard.press(key)
        assert page.evaluate(inside), key
    page.keyboard.press("Escape")
    page.keyboard.press("j")  # Esc closed it: j moves on the grid, the panel stays shut
    assert not page.locator("#cpanel").is_visible()
    cards.nth(0).locator(".title").click()
    page.locator("#cpj").click()
    assert live.text_content().startswith("2 of ")
    assert page.errors == []
