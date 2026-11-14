"""Identify's one-tap suggestions at the top of each search panel in Chromium: each applies the
address key the full filter writes, and Near me acts only on a tap. iNaturalist is stubbed."""

import numpy as np
import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame
from .test_identify_bar_browser import blank_map

browser = eb.browser
N = ib.N
WIDE = (1440, 900)
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
    assert "Up to" in park.inner_text()
    key = park.get_attribute("data-k")[2:]
    park.click()
    assert f"bcpark={key}" in hash_(page)


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
        body = {"results": [{"user": {"login": f"user{i}"}, "count": 50 - i} for i in range(5)]}
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
    return page, urls


def test_who_lists_the_top_identifiers_as_profile_links(browser, site):
    base, _ = site
    page, urls = open_who(browser, base)
    page.wait_for_selector("#sgwho a.sga")
    links = page.locator("#sgwho a.sga")
    assert links.count() == 5 and links.first.inner_text().startswith("user0 (50)")
    assert links.first.get_attribute("href") == "https://www.inaturalist.org/people/user0"
    assert links.first.get_attribute("target") == "_blank"
    assert "noopener" in links.first.get_attribute("rel")
    assert len(urls) == 1 and "per_page=5" in urls[0] and "taxon_id" not in urls[0]
    links.first.focus()
    assert "look=" not in hash_(page) and page.errors == []


def test_the_top_identifiers_are_asked_per_what_taxon_once(browser, site):
    base, _ = site
    page, urls = open_who(browser, base, "#taxa=900")
    page.wait_for_selector("#sgwho a.sga")
    assert len(urls) == 1 and "taxon_id=900" in urls[0]
    page.click("#bwho")
    page.click("#bwho")
    page.wait_for_selector("#sgwho a.sga")
    assert len(urls) == 1


def test_the_top_identifiers_hide_when_the_fetch_fails(browser, site):
    base, _ = site
    page, urls = open_who(browser, base, status=500)
    page.wait_for_timeout(300)
    assert len(urls) == 1 and page.locator("#sgwho a.sga").count() == 0
    assert page.locator("#sgwho .sgr").count() > 0
