"""The map's User filter in Chromium, Only my genera, with the iNaturalist API answered by route
interception: the real map page over the stand-ins of test_map_groups_browser.py."""

import functools
import http.server
import threading
from urllib.parse import parse_qs, urlparse

import pytest

from what_to_id.map_points import encode_points
from what_to_id.page_map import render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_map_resolved_browser import LAYERS_STUB

browser = eb.browser
N = 300
# records cycle through taxa 1000-1006: species 1000-1002 sit in Genus A, 1003-1006 in Genus B
IN_GENUS_A = sum(1 for i in range(N) if i % 7 < 3)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("map-user")
    pool = pool_frame(range(1, N + 1))
    pool["user_id"] = [10 + i % 2 for i in range(N)]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/map.html?standalone=1"
    server.shutdown()


# Genus A (900): 30 + 25 = 55 IDs. Genus B (901): 49, one short of the threshold of 50; automatic
# keeps both, as Genus A alone holds 53% of 104. The ancestors include an order the pool lacks.
SPECIES_COUNTS = {
    "total_results": 3,
    "results": [
        {"count": 30, "taxon": {"id": 1000, "ancestor_ids": [1, 800, 900, 1000]}},
        {"count": 25, "taxon": {"id": 1001, "ancestor_ids": [1, 800, 900, 1001]}},
        {"count": 49, "taxon": {"id": 1003, "ancestor_ids": [1, 800, 901, 1003]}},
    ],
}

NONE = {
    "total_results": 1,
    "results": [{"count": 4, "taxon": SPECIES_COUNTS["results"][0]["taxon"]}],
}


def open_map(browser, url, hash_, counts=None):
    p = browser.new_page(viewport={"width": 1280, "height": 900})
    p.errors, p.calls = [], []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=LAYERS_STUB if r.request.url.endswith(".js") else "",
            content_type="text/javascript",
        ),
    )

    def api(route):
        u = urlparse(route.request.url)
        p.calls.append((u.path, parse_qs(u.query)))
        if u.path.endswith("/users/autocomplete"):  # a prefix match first, then the exact login
            body = {"results": [{"id": 5, "login": "jdoe2"}, {"id": 777, "login": "JDoe"}]}
        elif u.path.endswith("/identifications/species_counts"):
            body = counts or SPECIES_COUNTS
        elif u.path.endswith("/observations"):  # the user identified records 1 to 3 in the view
            body = {"total_results": 3, "results": [{"id": i} for i in (1, 2, 3)]}
        else:
            body = {"results": []}
        route.fulfill(json=body)

    p.route("https://api.inaturalist.org/**", api)
    p.goto(url + hash_)
    return p


def shown(page, n):
    page.wait_for_function(
        "n => (document.getElementById('count').textContent || '').startsWith(n + ' ')", arg=str(n)
    )


def test_my_taxa_keeps_the_users_genera_and_adds_the_user_to_the_identify_link(browser, site):
    page = open_map(browser, site, "#user=jdoe&umode=taxa&umin=50")
    shown(page, IN_GENUS_A)
    assert page.input_value("#usrname") == "jdoe" and checked(page) == ["taxa"]
    assert page.inner_text("#usrbox p") == "Genera where jdoe has at least 50 IDs in BC (1 genus)."
    # the login is looked up once, then the taxa are read for the user number that matched exactly
    paths = [c[0].rsplit("/v1/", 1)[1] for c in page.calls]
    assert paths == ["users/autocomplete", "identifications/species_counts"]
    q = page.calls[1][1]
    assert q["user_id"] == ["777"] and q["place_id"] == ["7085"] and q["per_page"] == ["500"]
    link = urlparse(page.get_attribute("#identify", "href"))
    assert parse_qs(link.query)["without_ident_user_id"] == ["777"]
    assert "skipped" in page.get_attribute("#identify", "title")
    # Identify gets the kept genera as taxon_id, so its count matches the map
    assert parse_qs(link.query)["taxon_id"] == ["900"]
    assert page.inner_text("#idnote") == "Genera where jdoe has at least 50 IDs in BC (1 genus)."
    # clearing the box brings every record back and takes the user out of the link and the hash
    page.fill("#usrname", "")
    page.press("#usrname", "Enter")
    shown(page, N)
    assert "without_ident_user_id" not in page.get_attribute("#identify", "href")
    page.wait_for_function("!location.hash.includes('user=')")
    assert page.errors == []
    page.close()


def test_a_user_number_skips_the_lookup_and_a_bad_name_asks_for_a_login(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa&umin=50")
    shown(page, IN_GENUS_A)
    assert [c[0].rsplit("/v1/", 1)[1] for c in page.calls] == ["identifications/species_counts"]
    assert page.calls[0][1]["user_id"] == ["42"]
    page.close()
    page = open_map(browser, site, "#user=bad%20name")
    page.wait_for_function("document.querySelector('#usrbox p').textContent.includes('Enter')")
    shown(page, N)
    assert page.calls == []
    page.close()


def test_a_throttled_reply_is_tried_again(browser, site):
    page = browser.new_page()
    page.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(body=LAYERS_STUB, content_type="text/javascript"),
    )
    hits = []

    def api(route):  # the first answer is iNaturalist's throttle, the second the taxa
        hits.append(route.request.url)
        if len(hits) == 1:
            route.fulfill(status=429, body="")
        else:
            route.fulfill(json=SPECIES_COUNTS)

    page.route("https://api.inaturalist.org/**", api)
    page.goto(site + "#user=42&umode=taxa&umin=50")
    page.wait_for_function("document.querySelector('#usrbox p').textContent.includes('busy')")
    shown(page, IN_GENUS_A)
    assert len(hits) == 2 and hits[0] == hits[1]
    page.close()


def test_an_area_listed_by_id_keeps_the_user_out_of_every_batch(browser, site):
    page = open_map(browser, site, "")
    shown(page, N)
    ring = [-124, 48, -122, 48, -122, 50, -124, 50]  # every record, so the area opens by id
    area = page.evaluate("r => MapArea.encode([r])", ring)
    page.close()
    page = open_map(browser, site, f"#user=42&umode=taxa&umin=50&area={area}")
    shown(page, IN_GENUS_A)
    link = urlparse(page.get_attribute("#identify", "href"))
    q = parse_qs(link.query)
    assert q["id"] and q["without_ident_user_id"] == ["42"]
    assert len(q["id"][0].split(",")) == IN_GENUS_A
    assert "taxon_id" not in q  # the ids already say which records
    assert page.errors == []
    page.close()


def test_observer_keeps_the_users_own_records(browser, site):
    page = open_map(browser, site, "#user=10&umode=observer")
    shown(page, N // 2)  # the fixture's observers alternate between users 10 and 11
    assert "observed by" in page.inner_text("#usrbox p")
    assert [c[0].rsplit("/v1/", 1)[1] for c in page.calls] == ["identifications/species_counts"]
    # Identify opens the user's records; without_ident_user_id would drop the ones they identified
    # themselves, which is nearly all of an observer's own records
    q = parse_qs(urlparse(page.get_attribute("#identify", "href")).query)
    assert q["user_id"] == ["10"] and "without_ident_user_id" not in q
    assert page.errors == []
    page.close()


def adjust(page, umin):
    """Picks a genus threshold under the Adjust disclosure."""
    page.evaluate("document.querySelector('#usrbox details').open = true")
    page.select_option("#usrbox select", umin)


def checked(page):
    return page.evaluate(
        "['taxa','unid','observer'].filter(f => document.getElementById('usr' + f).checked)"
    )


ALPHA = """() => { const d = L.find(l => l.id === 'pts').props.data,
  c = d.attributes.getFillColor.value;
  return Array.from({length: d.length}, (_, i) => c[4 * i + 3]); }"""


def test_an_old_link_with_a_login_alone_still_opens_on_observer(browser, site):
    page = open_map(browser, site, "#user=10")
    shown(page, N // 2)
    assert checked(page) == ["observer"]
    assert "umode" not in page.evaluate("location.hash")
    assert page.inner_text("#usrbox > summary") == "User: 10 · Only records @10 observed"
    # an observer's own ID counts as one, so Hide is off while Observed is ticked
    assert page.is_disabled("#usrunid") and page.get_attribute("#usrunid", "title")
    page.close()


def test_my_taxa_first_ranks_the_users_genera_and_dims_the_rest(browser, site):
    page = open_map(browser, site, "#user=42&umode=first&umin=50")
    page.wait_for_function("/^Genera/.test(document.querySelector('#usrbox p').textContent)")
    shown(page, N)  # nothing is hidden
    assert checked(page) == []
    # the dots in Genus A keep their colour, the rest drop to a fifth of its opacity
    alpha = page.evaluate(ALPHA)
    bright = max(alpha)
    assert alpha.count(bright) == IN_GENUS_A and alpha.count(bright // 5) == N - IN_GENUS_A
    # Identify gets every record the user has not identified, not only Genus A
    q = parse_qs(urlparse(page.get_attribute("#identify", "href")).query)
    assert q["without_ident_user_id"] == ["42"] and "taxon_id" not in q
    assert "dimmed" in page.inner_text("#idnote")
    page.check("#usrtaxa")  # everything left is theirs, so nothing is ranked
    page.wait_for_function("location.hash.includes('umode=taxa&')")
    shown(page, IN_GENUS_A)
    page.wait_for_function(f"(new Set(({ALPHA})())).size === 1")  # the colours come back
    assert "dimmed" not in page.inner_text("#idnote")
    page.close()


def test_not_yet_identified_hides_the_records_the_user_identified_in_the_view(browser, site):
    page = open_map(browser, site, "#user=42&umode=unid")
    shown(page, N - 3)
    assert checked(page) == ["unid"] and page.is_disabled("#usrobserver")
    q = page.calls[-1][1]
    assert page.calls[-1][0].endswith("/observations")
    assert q["ident_user_id"] == ["42"] and q["quality_grade"] == ["needs_id"]
    assert {"swlat", "swlng", "nelat", "nelng"} <= q.keys()
    assert page.is_visible("#usrbox button:has-text('Reload')")
    assert "approximate" in page.inner_text("#idnote")
    assert page.errors == []
    page.close()


def test_automatic_keeps_the_genera_holding_80_percent_and_says_so(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa")
    shown(page, N)  # Genus A holds 53% of the 104 IDs, so Genus B joins it
    assert page.input_value("#usrbox select") == "0"
    assert "umin" not in page.evaluate("location.hash")  # automatic is not written
    text = "Your top 2 genera, 100% of your 104 IDs in BC."
    assert page.inner_text("#usrbox p") == text and page.inner_text("#idnote") == text
    page.close()


def test_the_threshold_selector_filters_by_genus_sum_and_round_trips_in_the_hash(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa")
    shown(page, N)
    adjust(page, "50")  # Genus B has 49, one short
    shown(page, IN_GENUS_A)
    page.wait_for_function("location.hash.includes('umin=50')")  # no longer the default
    adjust(page, "20")
    shown(page, N)
    page.wait_for_function("location.hash.includes('umin=20')")
    assert parse_qs(urlparse(page.get_attribute("#identify", "href")).query)["taxon_id"] == [
        "900,901"
    ]
    assert page.inner_text("#idnote") == "Genera where 42 has at least 20 IDs in BC (2 genera)."
    assert [c[0].rsplit("/v1/", 1)[1] for c in page.calls] == ["identifications/species_counts"]
    page.close()
    page = open_map(browser, site, "#user=42&umode=taxa&umin=20")
    shown(page, N)
    assert page.input_value("#usrbox select") == "20"
    page.close()


def test_the_selector_sits_under_adjust_and_shows_only_with_a_user(browser, site):
    page = open_map(browser, site, "")
    assert page.is_hidden("#usrbox details")
    page.close()
    page = open_map(browser, site, "#user=42&umode=unid")
    shown(page, N - 3)
    assert page.is_hidden("#usrbox select")
    page.click("#usrbox details summary")
    assert page.is_visible("#usrbox select")
    assert page.inner_text("#usrbox details summary") == "Adjust"
    page.close()


def test_a_threshold_that_keeps_nothing_falls_back_and_says_so_without_writing_it(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa&umin=100")
    shown(page, IN_GENUS_A)  # Genus A has 55, so 50 is the highest lower threshold that keeps one
    assert page.input_value("#usrbox select") == "100"  # min(), not the fallback
    text = "Genera where 42 has at least 50 IDs in BC (1 genus); none reach 100 yet."
    assert page.inner_text("#usrbox p") == text and page.inner_text("#idnote") == text
    # the pick stays, the fallback is not written
    assert "umin=100" in page.evaluate("location.hash")
    page.close()


def test_a_user_with_no_genus_at_five_keeps_nothing_and_says_so(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa", counts=NONE)
    shown(page, 0)
    text = (
        "42 has fewer than 5 IDs in any BC genus yet. "
        "Try Only records @42 observed or Hide records @42 identified."
    )
    assert page.inner_text("#usrbox p") == text and page.inner_text("#idnote") == text
    assert page.errors == []
    page.close()


def test_too_many_genera_for_one_link_send_the_top_ones_and_say_so(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa&umin=20")
    shown(page, N)
    page.evaluate("META.max_url = 1504")  # room for one three-digit id
    adjust(page, "50")
    adjust(page, "20")
    page.wait_for_function("document.getElementById('idnote').textContent.includes('top genus')")
    # Genus B has more records to identify than Genus A
    assert parse_qs(urlparse(page.get_attribute("#identify", "href")).query)["taxon_id"] == ["901"]
    assert page.inner_text("#idnote") == (
        "Genera where 42 has at least 20 IDs in BC (2 genera). "
        "Identify gets only the top genus by records to identify."
    )
    assert page.errors == []
    page.close()


def test_a_user_with_no_genus_is_not_ranked_and_nothing_is_dimmed(browser, site):
    page = open_map(browser, site, "#user=42&umode=first", counts=NONE)
    page.wait_for_function("/fewer than 5/.test(document.querySelector('#usrbox p').textContent)")
    shown(page, N)
    assert len(set(page.evaluate(ALPHA))) == 1
    assert "dimmed" not in page.inner_text("#idnote") + page.inner_text("#usrbox p")
    assert page.errors == []
    page.close()


def test_the_box_names_the_user_and_ticks_and_the_dimming_when_collapsed(browser, site):
    page = open_map(browser, site, "")
    assert page.inner_text("#usrbox > summary") == "User" and page.is_hidden("#usrbox select")
    assert page.is_hidden("#usrbox button:has-text('Sign out')")
    page.close()
    page = open_map(browser, site, "#user=42&umode=first&umin=50")
    page.wait_for_function("/^Genera/.test(document.querySelector('#usrbox p').textContent)")
    assert page.inner_text("#usrbox > summary") == "User: 42 · Your genera first"
    assert page.eval_on_selector("#usrbox > summary", "e => e.offsetHeight") >= 24
    assert "dimmed on the map" in page.inner_text("#usrbox p")
    page.close()
    page = open_map(browser, site, "#user=42&umode=taxa,unid")
    shown(page, N - 3)
    assert page.inner_text("#usrbox > summary") == (
        "User: 42 · Only @42's genera, Hide records @42 identified"
    )
    page.close()


@pytest.mark.parametrize(
    ("typed", "user"),
    [
        ("https://www.inaturalist.org/people/JDoe", "JDoe"),
        ("https://www.inaturalist.ca/people/42?x=1", "42"),
        ("@JDoe", "JDoe"),
        ("inaturalist.org/people/JDoe/", "JDoe"),
    ],
)
def test_a_pasted_profile_link_or_at_login_is_taken_for_the_login(browser, site, typed, user):
    page = open_map(browser, site, "")
    page.click("#usrbox > summary")
    page.fill("#usrname", typed)
    page.press("#usrname", "Enter")
    page.wait_for_function(f"location.hash.includes('user={user}&')")
    assert page.input_value("#usrname") == user
    page.close()


def test_an_unparseable_entry_is_not_written_to_the_hash(browser, site):
    page = open_map(browser, site, "#user=42&umode=taxa&umin=50")
    shown(page, IN_GENUS_A)
    page.fill("#usrname", "not a login!")
    page.press("#usrname", "Enter")
    assert page.inner_text("#usrbox p") == "Enter an iNaturalist login or user number."
    assert "user=42" in page.evaluate("location.hash")
    page.close()


def test_the_same_login_can_be_tried_again_after_a_failed_lookup(browser, site):
    page = open_map(browser, site, "")
    page.unroute("https://api.inaturalist.org/**")
    page.route("https://api.inaturalist.org/**", lambda r: r.fulfill(status=400, body=""))
    page.click("#usrbox > summary")
    page.fill("#usrname", "JDoe")
    page.press("#usrname", "Enter")
    page.wait_for_function("document.querySelector('#usrbox p').textContent === 'HTTP 400'")
    page.unroute("https://api.inaturalist.org/**")
    page.route(
        "https://api.inaturalist.org/**",
        lambda r: r.fulfill(
            json={"results": [{"id": 9, "login": "JDoe"}]}
            if r.request.url.split("?")[0].endswith("/users/autocomplete")
            else SPECIES_COUNTS
        ),
    )
    page.press("#usrname", "Enter")
    page.wait_for_function("/^Your top/.test(document.querySelector('#usrbox p').textContent)")
    page.close()
