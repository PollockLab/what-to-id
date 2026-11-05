"""Identify's routing in Chromium: a first visit opens on Easy confirms, Might be wrong's kind
control, My taxa first, the reference photos and the GoatCounter events. iNaturalist is stubbed."""

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

    def api(route):
        u = urlparse(route.request.url)
        path = u.path.rsplit("/v1/", 1)[1]
        if path == "observations":
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
                            "square_url": f"https://static.inaturalist.org/photos/{i}/square.jpg"
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


def test_a_return_visit_opens_on_might_be_wrong(browser, site):
    base, _ = site
    page = open_identify(browser, base)
    assert page.evaluate("__identify.level()") == 1
    page.goto(f"{base}/identify.html")
    page.wait_for_function("window.__identify")
    assert page.evaluate("__identify.level()") == 5
    assert (
        page.locator("#kind").is_visible()
        and kind(page, "All").get_attribute("aria-checked") == "true"
    )
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


def test_my_taxa_first_lists_the_users_genera_first_in_every_tab(browser, site):
    base, pts = site
    page = counted(browser, base, "#lvl=1")
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    page.fill("#melogin", "jdoe")
    page.click("#me button")
    page.wait_for_function("__identify.mine()")
    assert page.inner_text("#me .segnote") == (
        "Records in your 1 genus (at least 50 of your IDs each) come first."
    )
    # the login is looked up once, then the taxa are read for the user number that matched exactly
    assert [c[0] for c in page.api] == ["users/autocomplete", "identifications/species_counts"]
    assert page.api[1][1]["user_id"] == ["777"]
    for lv, *_ in page_identify.LEVELS:
        tab(page, lv).click()
        mine = [taxon[i] in GENUS_A for i in page.evaluate("__identify.view()")[lv]]
        assert any(mine) and mine == sorted(mine, reverse=True), lv  # all of the user's first
    assert page.locator("#grid .card").first.locator(".mine").count() == 1
    assert "me=jdoe" in page.evaluate("location.hash")
    page.reload()
    page.wait_for_function("window.__identify && __identify.mine()")  # kept in the hash
    assert page.input_value("#melogin") == "jdoe"
    page.fill("#melogin", "")
    page.click("#me button")
    page.wait_for_function("!__identify.mine()")
    assert "me=" not in page.evaluate("location.hash") and page.locator("#grid .mine").count() == 0
    assert not any("jdoe" in e or "777" in e for e in events(page))  # no login in the counts
    assert "identify/mine-on" in events(page) and page.errors == []


def test_an_unknown_login_says_so_and_keeps_the_order(browser, site):
    base, _ = site
    page = counted(browser, base, "#lvl=1&me=nobody")
    page.wait_for_function(
        "/No iNaturalist user/.test(document.querySelector('#me .segnote').textContent)"
    )
    assert page.inner_text("#me .segnote") == 'No iNaturalist user "nobody"'
    assert page.evaluate("__identify.mine()") is False and page.locator("#grid .mine").count() == 0
    assert page.errors == []


def test_a_card_with_a_look_alike_shows_both_reference_photos(browser, ranges_site):
    page = counted(browser, ranges_site, "#lvl=3")
    box = page.locator("#grid .card .cmp")
    box.wait_for()
    assert box.locator("figcaption").all_inner_texts() == ["Label", "Look-alike"]
    page.wait_for_function("document.querySelector('.cmp img').src")
    img = box.locator("img").first
    assert img.get_attribute("src") == "https://static.inaturalist.org/photos/1000/small.jpg"
    assert img.get_attribute("alt") == "Label Taxon 0, reference photo"
    assert [c[0] for c in page.api] == ["taxa/1000"]  # one request, each taxon once
    assert page.errors == []


def test_the_counted_events_name_the_choice_and_nothing_else(browser, site):
    base, _ = site
    page = counted(browser, base)
    page.evaluate("document.addEventListener('click', e => e.preventDefault())")  # no new tabs
    tab(page, 5).click()
    kind(page, "Odd shots").click()
    page.click("#go")
    page.get_by_label("Identify this record on iNaturalist").first.click()
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
