"""Identify's Your IDs list and its count of new replies in Chromium: the observations the viewer
identified that someone later disagreed with or commented on. iNaturalist is stubbed."""

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame
from .test_identify_bar_browser import blank_map
from .test_identify_suggest_browser import stub_identifiers

browser = eb.browser
N = ib.N
WIDE = (1440, 900)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    frame = pool_frame(ids)
    score = np.random.default_rng(2).normal(size=N).astype("float32")
    server, pts = ib.serve(tmp_path_factory.mktemp("yours-site"), frame, score)
    yield f"http://127.0.0.1:{server.server_port}", pts
    server.shutdown()


OBS = "https://api.inaturalist.org/v2/observations?*"
ME = {"id": 7, "login": "Me"}
OTHER = {"id": 8, "login": "them"}
ALICE, BOB = {"id": 9, "login": "alice"}, {"id": 10, "login": "bob"}
BIRD, WREN, GULL = ([1, 2, 10], [1, 2, 10, 12], [1, 3, 20])  # lineages, each ending in its own id
REPLY = "#myids [role=status]"


def ident(user, lineage, when, current=True, disagreement=None, name="Larus sp."):
    return {
        "user": user,
        "created_at": when,
        "current": current,
        "disagreement": disagreement,
        "taxon": {"id": lineage[-1], "name": name, "ancestor_ids": lineage[:-1]},  # as sent
    }


def record(oid, mine, others=(), comments=(), owner=OTHER, name="Corvus corax"):
    return {
        "id": oid,
        "user": owner,
        "taxon": {"id": 10, "name": name},
        "identifications": [mine, *others],
        "comments": [{"user": u, "created_at": t, "body": b} for u, t, b in comments],
    }


MINE = ident(ME, BIRD, "2026-05-01T10:00:00-07:00")  # 17:00 UTC
AFTER = "2026-05-02T00:00:00+00:00"
BEFORE_IN_UTC = "2026-05-01T12:00:00+00:00"  # later as a string than MINE, earlier as a time


def day(n):
    return f"2026-06-{n:02d}T00:00:00+00:00"


def stub_yours(page, data):
    urls = []

    def route(r):
        urls.append(r.request.url)
        r.fulfill(
            status=data.get("status", 200),
            json={"results": data["results"]},
            headers={"access-control-allow-origin": "*"},
        )

    page.route(OBS, route)
    return urls


def open_yours(browser, base, results, hash_="", signed_in=True, status=200, lang=None, fold=True):
    """Identify with the v2 observations stubbed before the page loads: the replies are fetched in
    the background. Returns the page, the asked addresses and the answer to change."""
    page = ib.open_identify(browser, base, size=WIDE)
    if signed_in:
        user = json.dumps({"jwt": "test-token", "user": ME})
        page.add_init_script(f"sessionStorage.setItem('wtid-inat', {json.dumps(user)})")
    if lang:
        page.add_init_script(f"localStorage.setItem('wtid-lang', '{lang}')")
    page.data = {"results": results, "status": status}
    urls = stub_yours(page, page.data)
    blank_map(page)
    page.goto(f"{base}/identify.html?again{hash_}")  # a new load, not a hash change
    page.wait_for_function("window.__identify")
    page.wait_for_function("__identify.ids().length > 0")
    if fold:
        page.click("#bwho")
        page.wait_for_selector("#sgwho .sgr")
        page.click("#myids summary")
        page.wait_for_function(
            f"document.querySelector('{REPLY}').textContent || document.querySelector('#myids li')"
        )
    return page, urls


def test_your_ids_lists_the_newest_unanswered_replies_with_who_and_what(browser, site):
    base, _ = site
    hostile = "<img src=x onerror=window.pwned=1> " + "long " * 30
    results = [
        record(101, MINE, [ident(ALICE, WREN[:2] + [11], day(3), True, True, "Nemophila")]),
        record(102, MINE, comments=[(BOB, day(9), hostile)]),
        record(103, MINE, [ident(OTHER, GULL, day(1))]),  # another branch, no flag
        record(201, MINE, [ident(OTHER, WREN, AFTER)]),  # refines
        record(202, MINE, [ident(OTHER, BIRD[:2], AFTER)]),  # a broader ID agrees
        record(
            203, MINE, comments=[(OTHER, BEFORE_IN_UTC, "x")]
        ),  # earlier, though "12:00" > "10:00"
        record(204, MINE, comments=[(ME, AFTER, "x")]),
        record(205, MINE, [ident(OTHER, GULL, AFTER, disagreement=True)], owner=ME),
        record(206, MINE, [ident(OTHER, GULL, AFTER, current=False, disagreement=True)]),
        record(207, MINE, [ident(OTHER, GULL, BEFORE_IN_UTC, disagreement=True)]),
        record(208, MINE, [ident(OTHER, BIRD, AFTER)]),  # the same taxon agrees
        record(
            209, MINE, [ident(OTHER, GULL, AFTER, disagreement=True)], [(ME, day(2), "ok")]
        ),  # answered
    ]
    page, urls = open_yours(browser, base, results)
    rows = page.locator("#myids li")
    assert rows.count() == 3
    texts = rows.all_inner_texts()
    assert (
        texts[0].split("\n")[1].startswith("bob commented: <img src=x onerror=window.pwned=1> long")
    )
    assert len(texts[0].split("\n")[1]) <= len("bob commented: ") + 80
    assert texts[1].split("\n")[1] == "alice suggests Nemophila" and "Corvus corax" in texts[1]
    assert texts[2].split("\n")[1] == "them suggests Larus sp."
    assert page.locator("#myids img").count() == 0 and page.evaluate("window.pwned") is None
    for oid in (102, 101, 103):
        link = page.get_by_role("link", name=f"Observation {oid} on iNaturalist")
        assert link.get_attribute("href") == f"https://www.inaturalist.org/observations/{oid}"
        assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")
    assert page.errors == []


def test_your_ids_shows_at_most_20_rows_newest_first(browser, site):
    base, _ = site
    results = [record(300 + n, MINE, comments=[(BOB, day(n), "c")]) for n in range(1, 26)]
    page, _ = open_yours(browser, base, results)
    hrefs = page.locator("#myids li a").evaluate_all("a => a.map(x => x.href.split('/').pop())")
    assert hrefs == [str(300 + n) for n in range(25, 5, -1)]


def test_your_ids_is_asked_once_per_person_in_v2_with_a_field_list(browser, site):
    base, _ = site
    page, urls = open_yours(browser, base, [record(102, MINE, comments=[(BOB, AFTER, "hi")])])
    page.click("#myids summary")
    page.click("#myids summary")
    page.reload()
    page.wait_for_function("window.__identify")
    page.wait_for_function("__identify.ids().length > 0")
    page.wait_for_timeout(300)
    assert len(urls) == 1
    url = urls[0]
    # the person's own observations would fill the 200 and are skipped anyway
    assert url.startswith(
        "https://api.inaturalist.org/v2/observations?ident_user_id=me&not_user_id=me&"
    )
    assert "per_page=200" in url and "order_by=updated_at" in url and "ancestor_ids" in url
    assert "fields=(id%3A!t" in url


def test_the_count_shows_unopened_opens_the_fold_and_clears_until_a_newer_reply(browser, site):
    base, _ = site
    results = [
        record(101, MINE, comments=[(BOB, AFTER, "one")]),
        record(102, MINE, comments=[(BOB, day(1), "two")]),
    ]
    page, urls = open_yours(browser, base, results, fold=False)
    page.wait_for_selector("#rep button")
    assert page.inner_text("#rep button") == "2 new replies to your IDs"
    assert page.locator("#pwho").is_hidden()
    page.click("#rep button")
    page.wait_for_selector("#myids li")
    assert page.locator("#pwho").is_visible() and page.locator("#myids").evaluate("e => e.open")
    assert page.locator("#myids li b").count() == 2  # first visit: every reply is new
    assert page.locator("#rep").is_hidden()
    page.reload()
    page.wait_for_function("window.__identify")
    page.wait_for_function("__identify.ids().length > 0")
    page.wait_for_timeout(300)
    assert page.locator("#rep").is_hidden() and len(urls) == 1
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    page.data["results"] = [record(103, MINE, comments=[(BOB, later, "newest")]), *results]
    page.evaluate("sessionStorage.removeItem('wtid-replies')")
    page.reload()
    page.wait_for_selector("#rep button")
    assert page.inner_text("#rep button") == "1 new reply to your IDs"
    page.click("#rep button")
    page.wait_for_selector("#myids li")
    assert page.locator("#myids li").count() == 3
    assert (
        page.locator("#myids li b").count() == 1
        and "New" in page.locator("#myids li").first.inner_text()
    )


def test_without_a_person_nothing_is_asked_and_no_count_shows(browser, site):
    base, _ = site
    hit = [record(102, MINE, comments=[(BOB, AFTER, "hi")])]
    # a name in the User box alone is not the viewer
    page, urls = open_yours(browser, base, hit, "#user=them", signed_in=False)
    page.wait_for_timeout(300)
    assert urls == [] and page.locator("#rep").is_hidden()
    assert page.inner_text(REPLY) == "Add your iNat login in About this page, or sign in."


def test_tapping_a_top_identifier_does_not_make_them_the_person(browser, site):
    base, _ = site
    page, urls = open_yours(browser, base, [], signed_in=False, fold=False)
    stub_identifiers(page)
    page.route("https://api.inaturalist.org/v1/users/autocomplete*", lambda r: r.abort())
    page.click("#bwho")
    page.click("#topids summary")
    page.locator("#topids button.sga").first.click()
    page.wait_for_function("document.getElementById('usrname').value === 'user0'")
    page.wait_for_timeout(300)
    assert urls == [] and page.locator("#rep").is_hidden()


def test_your_ids_says_so_when_nothing_qualifies_or_the_fetch_fails(browser, site):
    base, _ = site
    page, _ = open_yours(browser, base, [record(201, MINE)])
    assert (
        page.inner_text(REPLY) == "No replies to your IDs yet." and page.locator("#rep").is_hidden()
    )
    page, _ = open_yours(browser, base, [], status=500)
    assert page.inner_text(REPLY) == "Your IDs did not load."


def test_the_progress_login_names_the_person_and_a_change_follows_at_once(browser, site):
    base, _ = site
    hit = [
        record(101, ident(OTHER, BIRD, day(1)), [ident(ALICE, GULL, day(2), True, True)], owner=ME)
    ]
    page, urls = open_yours(browser, base, hit, "#me=them", signed_in=False)
    assert "ident_user_id=them" in urls[0] and page.locator("#myids li").count() == 1
    page.evaluate(
        "const i = document.querySelector('#prog input'); i.value = 'nobody';"
        "i.dispatchEvent(new Event('change'))"
    )
    page.wait_for_function("document.querySelector('#myids [role=status]').textContent !== ''")
    assert "ident_user_id=nobody" in urls[-1] and len(urls) == 2
    assert page.inner_text(REPLY) == "No replies to your IDs yet."


def test_replies_are_not_marked_seen_while_the_fold_is_out_of_sight(browser, site):
    base, _ = site
    page, _ = open_yours(browser, base, [record(102, MINE, comments=[(BOB, AFTER, "hi")])])
    assert page.locator("#rep").is_hidden()  # opened, so seen
    page.click("#bwho")  # the Who panel closes; the fold inside stays open
    assert page.locator("#myids").evaluate("e => e.open") and page.locator("#myids").is_hidden()
    page.evaluate("localStorage.setItem('wtid-yours-seen', JSON.stringify({me: 0}))")
    page.evaluate("location.hash = '#groups=Aves'")  # a filter change redraws the suggestions
    page.wait_for_selector("#rep button")
    assert page.inner_text("#rep button") == "1 new reply to your IDs"


def test_your_ids_and_the_count_read_in_french(browser, site):
    base, _ = site
    one = [record(102, MINE, comments=[(BOB, AFTER, "hi")])]
    page, _ = open_yours(browser, base, one, lang="fr", fold=False)
    page.wait_for_selector("#rep button")
    assert page.inner_text("#rep button") == "1 nouvelle réponse à vos identifications"
    page.click("#rep button")
    page.wait_for_selector("#myids li")
    assert page.inner_text("#myids summary") == "Vos identifications"
    text = page.inner_text("#myids li")
    assert "Nouveau" in text and "bob a commenté : hi" in text
    assert page.get_by_role("link", name="Observation 102 sur iNaturalist").count() == 1
    two = [*one, record(103, MINE, [ident(ALICE, GULL, day(1), True, True, "Larus")])]
    page, urls = open_yours(browser, base, two, lang="fr", fold=False)
    page.wait_for_selector("#rep button")
    assert page.inner_text("#rep button") == "2 nouvelles réponses à vos identifications"
    page.click("#rep button")
    page.wait_for_selector("#myids li")
    assert "alice suggère Larus" in page.inner_text("#myids")
    assert "locale=fr" in urls[0]


def test_one_tap_puts_the_known_login_in_an_empty_user_box(browser, site):
    base, _ = site
    page, _ = open_yours(browser, base, [], "#me=them", signed_in=False)
    assert page.input_value("#usrname") == "" and "user=" not in page.evaluate("location.hash")
    assert page.inner_text("#usrme") == "Use my login: them"
    page.click("#usrme")
    page.wait_for_function("document.querySelector('#usrme').hidden")
    assert page.input_value("#usrname") == "them"
    assert not page.is_checked("#usrtaxa")


def test_no_login_is_offered_when_none_is_known(browser, site):
    base, _ = site
    page, _ = open_yours(browser, base, [], signed_in=False)
    assert page.locator("#usrme").is_hidden()
