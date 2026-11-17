"""Identify's one-tap suggestions at the top of each search panel in Chromium: each applies the
address key the full filter writes, and Near me acts only on a tap. iNaturalist is stubbed."""

import json
import os
import re

import numpy as np
import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame
from .test_identify_bar_browser import blank_map

browser = eb.browser
N = ib.N
WIDE = (1440, 900)
SHOT = os.environ.get("WTID_SHOT")
GEO = """(code) => {
  navigator.geolocation.getCurrentPosition = (ok, err) => {
    if (code) err({code}); else ok({coords: {longitude: -123, latitude: 49}});
  };
}"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    i = np.arange(N)
    # IDs by others cycle 0..3; with one of them, half agree; every fifth record is threatened
    frame = pool_frame(ids).assign(
        ident_count=i % 4, agree=np.where(i % 4 == 1, (i // 4) % 2, 0), threatened=i % 5 == 0
    )
    score = np.random.default_rng(2).normal(size=N).astype("float32")
    server, pts = ib.serve(tmp_path_factory.mktemp("suggest-site"), frame, score)
    yield f"http://127.0.0.1:{server.server_port}", pts
    server.shutdown()


def opened(browser, base, seg, hash_="", geo=None):
    page = ib.open_identify(browser, base, hash_, size=WIDE)
    if geo is not None:
        page.add_init_script(f"({GEO})({geo})")
        page.reload()
        page.wait_for_function("window.__identify")
    blank_map(page)
    page.wait_for_function("__identify.ids().length > 0")
    page.click(f"#b{seg}")
    page.wait_for_selector(f"#sg{seg} .sgr")
    return page


def hash_(page):
    return page.evaluate("location.hash")


def row(page, seg, text):
    return page.locator(f"#sg{seg} .sgr", has_text=text).first


def test_a_backlog_row_sets_the_groups_key_and_a_second_tap_clears_it(browser, site):
    base, pts = site
    page = opened(browser, base, "what")
    first = page.locator("#sgwhat .sgr[data-k^='b:']").first
    g = first.get_attribute("data-k")[2:]
    n = int((pts["iconic_taxon"] == g).sum())  # the top bar's denominator: every record to identify
    assert f"{n:,} of the records to identify" in first.inner_text()
    first.click()
    assert f"groups={g}" in hash_(page)
    assert ib.ids(page) == sorted(pts["id"][pts["iconic_taxon"] == g].tolist())
    assert page.locator(f"#sgwhat .sgr[data-k='b:{g}']").get_attribute("aria-pressed") == "true"
    page.locator(f"#sgwhat .sgr[data-k='b:{g}']").click()
    assert "groups=" not in hash_(page) and len(ib.ids(page)) == N
    assert page.errors == []


def test_blitz_targets_count_threatened_records_and_a_group_pick_is_remembered(browser, site):
    base, pts = site
    page = opened(browser, base, "what")
    blitz = page.locator("#sgwhat .sgr[data-k^='z:']")
    assert blitz.count() == 3 and "threatened or introduced" in blitz.first.inner_text()
    g = blitz.first.get_attribute("data-k")[2:]
    blitz.first.click()
    page.reload()
    page.wait_for_function("window.__identify")
    page.click("#bwhat")
    page.wait_for_selector("#sgwhat .sgr[data-k^='r:']")
    assert page.locator("#sgwhat .sgr[data-k^='r:']").first.get_attribute("data-k") == f"r:g{g}"


def test_the_when_cards_set_the_dates_the_presets_set(browser, site):
    base, pts = site
    page = opened(browser, base, "when")
    row(page, "when", "Last 7 days").click()
    assert "from=" in hash_(page)
    last = ib.day(pts).max()
    assert ib.ids(page) == sorted(pts["id"][ib.day(pts) >= last - np.timedelta64(6, "D")].tolist())
    row(page, "when", "All dates").click()
    assert "from=" not in hash_(page) and len(ib.ids(page)) == N


def test_since_your_last_visit_uses_the_date_kept_on_this_device(browser, site):
    base, pts = site
    since = (ib.day(pts).max() - np.timedelta64(9, "D")).date().isoformat()
    page = ib.open_identify(browser, base, "", size=WIDE)
    page.evaluate(f"sessionStorage.setItem('wtid-prevvisit', JSON.stringify('{since}'))")
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    page.click("#bwhen")
    card = row(page, "when", "Since your last visit")
    assert since in card.inner_text()
    card.click()
    assert f"from={since}" in hash_(page)


def test_near_me_does_nothing_until_tapped_then_draws_a_removable_circle(browser, site):
    base, pts = site
    page = opened(browser, base, "where", geo=0)
    assert "area=" not in hash_(page)
    row(page, "where", "Near me").click()
    page.wait_for_function("location.hash.includes('area=')")
    ring = page.evaluate(
        "MapArea.decode(new URLSearchParams(location.hash.slice(1)).get('area'))[0]"
    )
    assert len(ring) == 128  # 64 points
    dl = 50 / 111.195  # the 64-gon sits just inside the ellipse of 50 km
    r = np.hypot((pts["lon"] + 123) * np.cos(np.radians(49)) / dl, (pts["lat"] - 49) / dl)
    got = set(ib.ids(page))
    assert set(pts["id"][r <= 0.99]) <= got <= set(pts["id"][r <= 1.001]) and got
    assert page.errors == []


def test_a_blocked_location_shows_why_and_changes_nothing(browser, site):
    base, pts = site
    page = opened(browser, base, "where", geo=1)
    before = hash_(page)
    row(page, "where", "Near me").click()
    page.wait_for_selector("#sgwhere .sgm:has-text('blocked')")
    assert hash_(page) == before and len(ib.ids(page)) == N


def test_a_suggested_park_sets_bcpark(browser, site):
    base, pts = site
    page = opened(browser, base, "where")
    page.wait_for_selector("#sgwhere .sgr[data-k^='p:']")
    park = page.locator("#sgwhere .sgr[data-k^='p:']").first
    assert re.search(r"Up to [\d,]+ to identify", park.inner_text())
    key = park.get_attribute("data-k")[2:]
    park.click()
    assert f"bcpark={key}" in hash_(page)


def test_where_puts_the_map_first_with_three_suggestions_and_an_explore_link(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "", size=WIDE)
    page.route(  # the fixture's site has no Explore page: a blank one stands in
        "**/explore.html*", lambda r: r.fulfill(body="<!doctype html>", content_type="text/html")
    )
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    blank_map(page)
    page.click("#bwhere")
    page.wait_for_selector("#sgwhere .sgr[data-k^='p:']")
    assert page.evaluate(  # the map, then the suggestions
        "!!(document.getElementById('wbox').compareDocumentPosition("
        "document.getElementById('sgwhere')) & Node.DOCUMENT_POSITION_FOLLOWING)"
    )
    assert page.locator("#sgwhere .sgr").count() == 3  # Near me and two parks
    park = page.locator("#sgwhere .sgr[data-k^='p:']").first
    key = park.get_attribute("data-k")[2:]
    park.click()
    page.wait_for_function(f"location.hash.includes('bcpark={key}')")
    link = page.get_by_role("link", name="Open in Explore")
    page.wait_for_function(
        f"document.getElementById('xmap').href.includes('bcpark={key}')"
    )  # follows the area once the panel redraws
    href = link.get_attribute("href")
    assert href.startswith("explore.html?view=map#") and f"bcpark={key}" in href
    page.click("#wexp")  # the expanded map keeps the link in reach
    assert link.is_visible() and page.get_attribute("#wexp", "aria-expanded") == "true"
    assert page.errors == []


def test_the_who_chips_keep_the_records_with_that_many_outside_ids(browser, site):
    base, pts = site
    page = opened(browser, base, "who")
    row(page, "who", "Nobody has looked").click()
    assert "look=nobody" in hash_(page)
    assert ib.ids(page) == sorted(pts["id"][pts["ident_count"] == 0].tolist())
    row(page, "who", "Needs a second opinion").click()
    assert "look=second" in hash_(page) and "look=nobody" not in hash_(page)
    want = (pts["ident_count"] == 1) & (pts["agree"] == 0)
    assert ib.ids(page) == sorted(pts["id"][want].tolist())
    row(page, "who", "Needs a second opinion").click()
    assert "look=" not in hash_(page) and len(ib.ids(page)) == N


def test_not_yet_by_me_is_inert_until_a_login_is_set(browser, site):
    base, pts = site
    page = opened(browser, base, "who")
    chip = row(page, "who", "Not yet by me")
    assert chip.get_attribute("aria-disabled") == "true"
    chip.dispatch_event("click")  # aria-disabled stays focusable, so Playwright will not click it
    assert "Type your iNaturalist login" in page.inner_text("#sgwho .sgm")
    assert "umode" not in hash_(page)


def test_a_suggestion_leaves_the_served_order_alone(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=1", size=WIDE)
    page.wait_for_function("__identify.ids().length > 0")
    page.wait_for_load_state("networkidle")  # the rank and look files re-cut level 3
    full = page.evaluate("__identify.view()")
    page.click("#bwho")
    page.wait_for_selector("#sgwho .sgr")
    row(page, "who", "Nobody has looked").click()
    kept = set(ib.ids(page))
    after = page.evaluate("__identify.view()")
    flat = lambda v: [i for r in v if r for i in r]  # noqa: E731
    seen = set(flat(full))
    assert [i for i in flat(after) if i in seen] == [i for i in flat(full) if i in kept]


IDENT = "https://api.inaturalist.org/v1/observations/identifiers*"


def stub_identifiers(page, status=200):
    urls = []

    def route(r):
        urls.append(r.request.url)
        n = int(r.request.url.split("per_page=")[1])
        body = {"results": [{"user": {"login": f"user{i}"}, "count": 50 - i} for i in range(n)]}
        r.fulfill(status=status, json=body, headers={"access-control-allow-origin": "*"})

    page.route(IDENT, route)
    return urls


def open_who(browser, base, hash_="", status=200):
    page = ib.open_identify(browser, base, hash_, size=WIDE)
    urls = stub_identifiers(page, status)
    blank_map(page)
    page.wait_for_function("__identify.ids().length > 0")
    page.click("#bwho")
    page.wait_for_selector("#sgwho .sgr")
    assert (
        urls == [] and not page.locator("#topids button.sga").count()
    )  # folded: nothing asked yet
    # the fold sits under the login box
    assert page.evaluate(
        "usrbox.compareDocumentPosition(topids) & Node.DOCUMENT_POSITION_FOLLOWING"
    )
    page.click("#topids summary")
    return page, urls


def test_who_lists_the_top_identifiers_as_buttons_with_profile_links(browser, site):
    base, _ = site
    page, urls = open_who(browser, base)
    page.wait_for_selector("#topids button.sga")
    names = page.locator("#topids button.sga")
    assert names.count() == 5 and names.first.inner_text().startswith("user0 (50)")
    link = page.get_by_role("link", name="user0 on iNaturalist")
    assert link.get_attribute("href") == "https://www.inaturalist.org/people/user0"
    assert link.get_attribute("target") == "_blank"
    assert "noopener" in link.get_attribute("rel")
    assert len(urls) == 1 and "per_page=5" in urls[0] and "taxon_id" not in urls[0]
    assert page.get_by_text("Top identifiers for these filters").count() == 1
    names.first.focus()
    assert "look=" not in hash_(page) and page.errors == []


def test_tapping_an_identifier_fills_the_login_and_ticks_only_their_genera(browser, site):
    base, _ = site
    page, _ = open_who(browser, base)
    page.wait_for_selector("#topids button.sga")
    page.route("https://api.inaturalist.org/v1/users/autocomplete*", lambda r: r.abort())
    page.locator("#topids button.sga").first.click()
    page.wait_for_function("document.getElementById('usrname').value === 'user0'")
    page.wait_for_function("document.getElementById('usrtaxa').checked")
    # Only the genera is the default tick, so the address carries no umode
    page.wait_for_function("location.hash.includes('user=user0')")
    assert "user=user0" in hash_(page) and page.locator("#usrtaxa").is_checked()
    assert page.get_by_role("link", name="user0 on iNaturalist").count() == 1
    page.screenshot(path=SHOT, clip=page.locator("#pwho").bounding_box()) if SHOT else None
    assert page.errors == []


def test_the_top_identifiers_are_asked_per_what_taxon_once(browser, site):
    base, _ = site
    page, urls = open_who(browser, base, "#taxa=900")
    page.wait_for_selector("#topids button.sga")
    assert len(urls) == 1 and "taxon_id=900" in urls[0]
    page.click("#bwho")
    page.click("#bwho")
    page.wait_for_selector("#topids button.sga")
    assert len(urls) == 1


def test_the_top_identifiers_follow_the_filters_and_the_chosen_number(browser, site):
    base, _ = site
    page, urls = open_who(browser, base, "#groups=Aves&taxa=900")
    page.wait_for_selector("#topids button.sga")
    assert "iconic_taxa=Aves" in urls[0] and "taxon_id=900" in urls[0] and "d1=" not in urls[0]
    page.select_option("#topn", "10")
    page.wait_for_function("document.querySelectorAll('#topids button.sga').length === 10")
    assert "per_page=10" in urls[-1]
    page.evaluate(
        "location.hash = '#taxa=900'"
    )  # a filter change asks again while the fold is open
    page.wait_for_function("document.querySelectorAll('#topids button.sga').length === 10")
    page.wait_for_timeout(300)
    assert "iconic_taxa" not in urls[-1] and "per_page=10" in urls[-1] and len(urls) == 3


def test_the_top_identifiers_hide_when_the_fetch_fails(browser, site):
    base, _ = site
    page, urls = open_who(browser, base, status=500)
    page.wait_for_timeout(300)
    assert len(urls) == 1 and page.locator("#topids button.sga").count() == 0
    assert page.inner_text("#topids [role=status]") == "None found for these filters."
    assert page.locator("#sgwho .sgr").count() > 0


OBS = "https://api.inaturalist.org/v1/observations?*"
ME = {"id": 7, "login": "Me"}
OTHER = {"id": 8, "login": "them"}
BIRD, WREN, GULL = ([1, 2, 10], [1, 2, 10, 12], [1, 3, 20])  # lineages, each ending in its own id


def ident(user, lineage, when, current=True, disagreement=None):
    return {
        "user": user,
        "created_at": when,
        "current": current,
        "disagreement": disagreement,
        "taxon": {"id": lineage[-1], "ancestor_ids": lineage[:-1]},  # as iNaturalist sends it
    }


def record(oid, mine, others=(), comments=(), owner=OTHER, name="Corvus corax"):
    return {
        "id": oid,
        "user": owner,
        "taxon": {"id": 10, "name": name},
        "identifications": [mine, *others],
        "comments": [{"user": u, "created_at": t, "body": "hi"} for u, t in comments],
    }


MINE = ident(ME, BIRD, "2026-05-01T10:00:00-07:00")  # 17:00 UTC
AFTER = "2026-05-02T00:00:00+00:00"
BEFORE_IN_UTC = "2026-05-01T12:00:00+00:00"  # later as a string than MINE, earlier as a time


def stub_yours(page, results, status=200):
    urls = []

    def route(r):
        if "ident_user_id" not in r.request.url:  # the cards' own photo lookups
            return r.fallback()
        urls.append(r.request.url)
        r.fulfill(
            status=status, json={"results": results}, headers={"access-control-allow-origin": "*"}
        )

    page.route(OBS, route)
    return urls


def open_yours(browser, base, results, hash_="", signed_in=True, status=200, lang=None):
    page = ib.open_identify(browser, base, hash_, size=WIDE)
    if signed_in:
        user = json.dumps({"jwt": "test-token", "user": ME})
        page.add_init_script(f"sessionStorage.setItem('wtid-inat', {json.dumps(user)})")
    if lang:
        page.add_init_script(f"localStorage.setItem('wtid-lang', '{lang}')")
    if signed_in or lang:
        page.reload()
        page.wait_for_function("window.__identify")
    urls = stub_yours(page, results, status)
    blank_map(page)
    page.wait_for_function("__identify.ids().length > 0")
    page.click("#bwho")
    page.wait_for_selector("#sgwho .sgr")
    assert urls == []  # folded: nothing asked yet
    page.click("#myids summary")
    return page, urls


def test_your_ids_lists_the_records_others_disagreed_with_or_commented_on(browser, site):
    base, _ = site
    results = [
        record(101, MINE, [ident(OTHER, WREN[:2] + [11], AFTER, disagreement=True)]),
        record(102, MINE, comments=[(OTHER, AFTER)]),
        record(103, MINE, [ident(OTHER, GULL, AFTER)]),  # another branch, no flag
        record(104, MINE, [ident(OTHER, GULL, AFTER, disagreement=True)], [(OTHER, AFTER)]),
        record(201, MINE, [ident(OTHER, WREN, AFTER)]),  # refines
        record(202, MINE, [ident(OTHER, BIRD[:2], AFTER)]),  # a broader ID agrees
        record(203, MINE, comments=[(OTHER, BEFORE_IN_UTC)]),  # earlier, though "12:00" > "10:00"
        record(204, MINE, comments=[(ME, AFTER)]),
        record(205, MINE, [ident(OTHER, GULL, AFTER, disagreement=True)], owner=ME),
        record(206, MINE, [ident(OTHER, GULL, AFTER, current=False, disagreement=True)]),
        record(207, MINE, [ident(OTHER, GULL, BEFORE_IN_UTC, disagreement=True)]),
        record(208, MINE, [ident(OTHER, BIRD, AFTER)]),  # the same taxon agrees
    ]
    page, urls = open_yours(browser, base, results)
    page.wait_for_selector("#myids li")
    rows = page.locator("#myids li")
    assert rows.count() == 4
    assert [rows.nth(i).inner_text().split("\n")[1] for i in range(4)] == [
        "Someone disagreed",
        "New comment",
        "Someone disagreed",
        "Someone disagreed · New comment",
    ]
    assert "Corvus corax" in rows.first.inner_text()
    for oid in (101, 102, 103, 104):
        link = page.get_by_role("link", name=f"Observation {oid} on iNaturalist")
        assert link.get_attribute("href") == f"https://www.inaturalist.org/observations/{oid}"
        assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")
    assert len(urls) == 1 and "ident_user_id=me" in urls[0] and "per_page=50" in urls[0]
    assert page.errors == []


def test_your_ids_says_so_when_nothing_qualifies_or_nobody_is_named_or_the_fetch_fails(
    browser, site
):
    base, _ = site
    status = "#myids [role=status]"
    page, urls = open_yours(browser, base, [record(201, MINE)])
    page.wait_for_function(f"document.querySelector('{status}').textContent !== ''")
    assert page.inner_text(status) == "No replies to your IDs yet."
    page, urls = open_yours(browser, base, [], signed_in=False)
    page.wait_for_function(f"document.querySelector('{status}').textContent !== ''")
    assert page.inner_text(status) == "Type your iNaturalist login above, or sign in."
    assert urls == []
    page, urls = open_yours(browser, base, [], status=500)
    page.wait_for_function(f"document.querySelector('{status}').textContent !== ''")
    assert page.inner_text(status) == "Your IDs did not load."
    # the User box names the person when nobody is signed in
    page, urls = open_yours(
        browser,
        base,
        [
            record(
                101, ident(OTHER, BIRD, "2026-05-01T00:00:00Z"), [ident(ME, GULL, AFTER)], owner=ME
            )
        ],
        "#user=them",
        signed_in=False,
    )
    page.wait_for_selector("#myids li")
    assert "ident_user_id=them" in urls[0] and page.locator("#myids li").count() == 1


def test_your_ids_reads_in_french(browser, site):
    base, _ = site
    page, _ = open_yours(browser, base, [record(102, MINE, comments=[(OTHER, AFTER)])], lang="fr")
    page.wait_for_selector("#myids li")
    assert page.inner_text("#myids summary") == "Vos identifications"
    assert "Nouveau commentaire" in page.inner_text("#myids li")
    assert page.get_by_role("link", name="Observation 102 sur iNaturalist").count() == 1
    assert "locale=fr" in page.evaluate(
        "performance.getEntriesByType('resource').map(e=>e.name).join()"
    )
