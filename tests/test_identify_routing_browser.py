"""Identify's routing in Chromium: a first visit opens on Easy confirms, Might be wrong's kind
control, the User filter, the reference photos and the GoatCounter events. iNaturalist is
stubbed."""

from urllib.parse import parse_qs, urlparse

import pytest

from what_to_id import page_identify

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from . import test_identify_ranges_browser as rb

browser = eb.browser
site = ib.site
ranges_site = rb.site
open_identify, kind, tab, ORDER = ib.open_identify, ib.kind, ib.tab, ib.ORDER
GENUS_A = {1000, 1001, 1002}  # Taxon 0 to 2
# 55 IDs in Genus A, 49 in Genus B: only Genus A reaches 50
SPECIES_COUNTS = {
    "total_results": 3,
    "results": [
        {"count": 30, "taxon": {"id": 1000, "ancestor_ids": [1, 800, 900, 1000]}},
        {"count": 25, "taxon": {"id": 1001, "ancestor_ids": [1, 800, 900, 1001]}},
        {"count": 49, "taxon": {"id": 1003, "ancestor_ids": [1, 800, 901, 1003]}},
    ],
}


def counted(browser, base, hash_=""):
    """identify.html with GoatCounter stubbed (its events in EV) and the iNaturalist calls its
    helpers make: the user lookup, the user's taxa and the reference photos."""
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors, page.api = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script("window.EV = []; window.goatcounter = {count: o => EV.push(o)};")
    eb.stub_inat(page, None)
    page.route(ib.WTB, lambda r: r.abort())  # no live checklist

    def api(route):
        u = urlparse(route.request.url)
        path = u.path.rsplit("/v1/", 1)[1]
        if path == "observations" and "ident_user_id" not in u.query:
            return route.fallback()
        page.api.append((path, parse_qs(u.query)))
        if path == "users/autocomplete":  # a prefix match first, then the exact login
            body = {"results": [{"id": 5, "login": "jdoe2"}, {"id": 777, "login": "JDoe"}]}
        elif path == "identifications/species_counts":
            body = SPECIES_COUNTS
        elif path.startswith("taxa/"):  # Taxon 0 has a photo, the rest none
            body = {
                "results": [
                    {
                        "id": int(i),
                        "default_photo": {
                            "square_url": f"https://static.inaturalist.org/photos/{i}/square.jpg",
                            "attribution": "(c) A. Photographer, some rights reserved (CC BY-NC)",
                        },
                    }
                    if i == "1000"
                    else {"id": int(i), "default_photo": None}
                    for i in path[5:].split(",")
                ]
            }
        else:
            body = {"results": []}
        route.fulfill(json=body, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/**", api)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify")
    return page


def events(page):
    return [e["path"] for e in page.evaluate("EV")]


def test_a_return_visit_opens_on_easy_confirms(browser, site):
    base, _ = site
    page = open_identify(browser, base)
    assert page.evaluate("__identify.level()") == 1
    page.goto(f"{base}/identify.html")
    page.wait_for_function("window.__identify")
    assert page.evaluate("__identify.level()") == 1
    assert page.errors == []


def test_the_kind_control_filters_might_be_wrong_and_keeps_the_kind_in_the_hash(browser, site):
    base, pts = site
    page = open_identify(browser, base, "#lvl=5")
    level = dict(zip(pts["id"], pts["level"], strict=True))
    n = {k: int((pts["level"] == k).sum()) for k in ORDER}
    for k, name in page_identify.KINDS:
        assert kind(page, name).inner_text() == f"{name} {n[k]:,}"
    kind(page, "Odd shots").click()
    assert "kind=4" in page.evaluate("location.hash") and page.evaluate("__identify.kind()") == 4
    assert {level[i] for i in page.evaluate("__identify.view()")[5]} == {4}
    assert page.locator("#go").inner_text().startswith("Identify ")
    page.reload()
    page.wait_for_function("window.__identify && __identify.view()[5].length")
    assert kind(page, "Odd shots").get_attribute("aria-checked") == "true"
    assert {level[i] for i in page.evaluate("__identify.view()")[5]} == {4}
    kind(page, "Odd shots").focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("__identify.kind()") == 2
    assert page.evaluate("document.activeElement.textContent").startswith("Close calls")
    kind(page, "All").click()
    assert "kind=" not in page.evaluate("location.hash")
    tab(page, 1).click()
    assert page.locator("#kind").is_hidden()
    assert page.errors == []


def test_the_user_filter_keeps_only_the_users_genera_as_the_map_does(browser, site):
    base, pts = site
    # Only my genera, the default here: the test map has no observer file
    page = counted(browser, base, "#lvl=1&user=JDoe&umode=taxa&umin=50")
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    page.wait_for_function("__identify.user()")
    # the login is looked up once, then the taxa are read for the user number that matched exactly
    assert [c[0] for c in page.api] == ["users/autocomplete", "identifications/species_counts"]
    assert page.api[1][1]["user_id"] == ["777"]
    ids = page.evaluate("__identify.ids()")
    assert ids and {taxon[i] for i in ids} <= GENUS_A
    assert page.locator("#usrbox").get_attribute("open") is not None
    assert page.input_value("#usrname") == "JDoe" and page.is_checked("#usrtaxa")
    assert page.is_disabled("#usrobserver")
    assert page.get_attribute("#usrobserver", "title") == "This map has no observer file."
    assert "identify/user-taxa" in events(page)
    # no login in the counts
    assert not any("jdoe" in e.lower() or "777" in e for e in events(page))
    assert page.errors == []


def test_my_taxa_first_lists_the_users_genera_first_then_a_divider_then_the_rest(browser, site):
    base, pts = site
    page = counted(browser, base, "#lvl=1")
    before = page.evaluate("__identify.view()[1]")
    page.close()
    page = counted(browser, base, "#lvl=1&user=JDoe&umode=first&umin=50")
    page.wait_for_function("__identify.user()")
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    rows, m = page.evaluate("__identify.view()[1]"), page.evaluate("__identify.mine()")
    assert sorted(rows) == sorted(before) and 0 < m < len(rows)  # nothing hidden, only ranked
    assert {taxon[i] for i in rows[:m]} <= GENUS_A and not {taxon[i] for i in rows[m:]} & GENUS_A
    assert not page.is_checked("#usrtaxa") and not page.is_checked("#usrunid")
    while page.locator("#grid .sep").count() == 0:
        page.click("#more")
    sep = page.locator("#grid .sep:not(.top)")
    assert sep.inner_text() == f"End of your genera · {m} card{'s' if m > 1 else ''}"
    assert sep.evaluate("e => [...e.parentNode.children].indexOf(e)") == m + 1  # the top line leads
    assert "identify/user-first" in events(page) and page.errors == []


def test_a_login_typed_on_identify_goes_to_the_hash(browser, site):
    base, _ = site
    page = counted(browser, base, "#lvl=1")
    n = len(page.evaluate("__identify.ids()"))
    page.click("#bwho")
    page.fill("#usrname", "JDoe")
    page.press("#usrname", "Enter")
    page.wait_for_function("__identify.user()")
    assert "user=JDoe&umode=first" in page.evaluate("location.hash")  # a typed login starts there
    assert len(page.evaluate("__identify.ids()")) == n  # My taxa first hides nothing
    page.check("#usrtaxa")
    # Only my genera, the default without an observer file
    page.wait_for_function("!location.hash.includes('umode')")
    page.wait_for_function("__identify.mine() === -1")  # all left is theirs: nothing is ranked
    page.fill("#usrname", "")
    page.press("#usrname", "Enter")
    page.wait_for_function("!__identify.user()")
    assert "user=" not in page.evaluate("location.hash")
    assert len(page.evaluate("__identify.ids()")) == n and page.errors == []


def test_combined_ticks_count_as_one_event_and_the_login_is_kept_for_the_map(browser, site):
    base, _ = site
    page = counted(browser, base, "#lvl=1&user=JDoe&umode=taxa,unid")
    # counted once both loads are in, after the genera alone already filter
    page.wait_for_function("EV.some(e => e.path === 'identify/user-taxa-unid')")
    page.close()
    page = counted(browser, base, "#lvl=1")
    page.click("#bwho")
    page.fill("#usrname", "JDoe")
    page.press("#usrname", "Enter")
    page.wait_for_function("__identify.user()")
    # the map on the same origin reads the same key
    assert page.evaluate("JSON.parse(localStorage.getItem('wtid.user')).user") == "JDoe"
    assert page.errors == []
    page.close()


def test_an_unknown_login_says_so_and_filters_nothing(browser, site):
    base, _ = site
    page = counted(browser, base, "#lvl=1")
    n = len(page.evaluate("__identify.ids()"))
    page.goto(f"{base}/identify.html#lvl=1&user=nobody")
    page.wait_for_function("window.__identify")
    page.wait_for_function(
        "/No iNaturalist user/.test(document.querySelector('#usrbox p').textContent)"
    )
    assert page.text_content("#usrbox p") == 'No iNaturalist user "nobody"'
    assert page.evaluate("__identify.user()") is False
    assert len(page.evaluate("__identify.ids()")) == n and page.errors == []


def test_a_card_with_a_look_alike_shows_both_reference_photos(browser, ranges_site):
    page = counted(browser, ranges_site, "#lvl=3&conf=all")  # one tiny fixture level
    box = page.locator("#grid .card .cmp")
    box.wait_for(state="attached")  # its photos are frames of the card's carousel
    assert box.locator("figcaption").all_inner_texts() == ["Label", "Suggested"]  # level 3
    page.wait_for_function("document.querySelector('.cmp img').src")
    img = box.locator("img").first
    assert img.get_attribute("src") == "https://static.inaturalist.org/photos/1000/small.jpg"
    assert img.get_attribute("alt") == "Label Taxon 0, reference photo"
    assert box.locator("img").nth(1).get_attribute("alt") == "Suggested Taxon 0, reference photo"
    figs = box.locator("figure")
    assert figs.first.get_attribute("title") == (
        "Taxon 0. Photo (c) A. Photographer, some rights reserved (CC BY-NC)"
    )
    link = box.locator("a").first
    assert link.get_attribute("href") == "https://www.inaturalist.org/taxa/1000"
    assert link.get_attribute("target") == "wtid-inat" and link.get_attribute("rel") == "noopener"
    assert [c[0] for c in page.api] == ["taxa/1000"]  # one request, each taxon once
    assert page.errors == []


def test_the_counted_events_name_the_choice_and_nothing_else(browser, site):
    base, _ = site
    page = counted(browser, base)
    no_tabs = "e => e.target.closest('a') && e.preventDefault()"
    page.evaluate(f"document.addEventListener('click', {no_tabs})")  # no new tabs
    tab(page, 5).click()
    kind(page, "Odd shots").click()
    page.click("#go")
    ib.panel(page, page.locator("#grid .card").first)
    page.locator("#cpo").click()
    assert events(page) == [
        "identify/tab-5",
        "identify/kind-4",
        "identify/batch-5-4",
        "identify/card-4",
    ]
    assert all(e["event"] is True for e in page.evaluate("EV")) and page.errors == []


def test_goatcounter_is_off_unless_a_site_code_is_given():
    assert page_identify.analytics(None) == "" and page_identify.analytics("") == ""
    assert page_identify.GOATCOUNTER_JS not in page_identify.render()
    tag = page_identify.analytics("wtid")
    assert 'data-goatcounter="https://wtid.goatcounter.com/count"' in tag
    assert f'integrity="{page_identify.GOATCOUNTER_SRI}"' in tag and "async" in tag
    assert tag in page_identify.render(goatcounter="wtid")
    for bad in ("Wtid", "a b", "x.evil.com/", "-a", "a" * 51):
        with pytest.raises(ValueError, match="GoatCounter"):
            page_identify.analytics(bad)
