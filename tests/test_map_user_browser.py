"""The map's User filter in Chromium, My taxa mode, with the iNaturalist API answered by route
interception: the real map page over the stand-ins of test_map_groups_browser.py."""

import functools
import http.server
import threading
from urllib.parse import parse_qs, urlparse

import pytest

from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_map_groups_browser import STUB

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


def open_map(browser, url, hash_):
    p = browser.new_page(viewport={"width": 1280, "height": 900})
    p.errors, p.calls = [], []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )

    def api(route):
        u = urlparse(route.request.url)
        p.calls.append((u.path, parse_qs(u.query)))
        if u.path.endswith("/users/autocomplete"):  # a prefix match first, then the exact login
            body = {"results": [{"id": 5, "login": "jdoe2"}, {"id": 777, "login": "JDoe"}]}
        elif u.path.endswith("/identifications/species_counts"):
            # one species of Genus A; its ancestors are the genus and an order the pool lacks
            body = {
                "total_results": 1,
                "results": [{"count": 3, "taxon": {"id": 1000, "ancestor_ids": [1, 900, 1000]}}],
            }
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
    page = open_map(browser, site, "#user=jdoe")
    shown(page, IN_GENUS_A)
    assert page.input_value("#usrname") == "jdoe" and page.input_value("#usrbox select") == "taxa"
    assert "has identified" in page.inner_text("#usrbox p")
    # the login is looked up once, then the taxa are read for the user number that matched exactly
    paths = [c[0].rsplit("/v1/", 1)[1] for c in page.calls]
    assert paths == ["users/autocomplete", "identifications/species_counts"]
    q = page.calls[1][1]
    assert q["user_id"] == ["777"] and q["place_id"] == ["7085"] and q["per_page"] == ["500"]
    link = urlparse(page.get_attribute("#identify", "href"))
    assert parse_qs(link.query)["without_ident_user_id"] == ["777"]
    assert "skipped" in page.get_attribute("#identify", "title")
    assert "differs" in page.inner_text("#idnote")  # the count is approximate under My taxa
    # clearing the box brings every record back and takes the user out of the link and the hash
    page.fill("#usrname", "")
    page.press("#usrname", "Enter")
    shown(page, N)
    assert "without_ident_user_id" not in page.get_attribute("#identify", "href")
    page.wait_for_function("!location.hash.includes('user=')")
    assert page.errors == []
    page.close()


def test_a_user_number_skips_the_lookup_and_a_bad_name_asks_for_a_login(browser, site):
    page = open_map(browser, site, "#user=42")
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
        "https://unpkg.com/**", lambda r: r.fulfill(body=STUB, content_type="text/javascript")
    )
    hits = []

    def api(route):  # the first answer is iNaturalist's throttle, the second the taxa
        hits.append(route.request.url)
        if len(hits) == 1:
            route.fulfill(status=429, body="")
        else:
            body = {
                "total_results": 1,
                "results": [{"count": 1, "taxon": {"id": 1000, "ancestor_ids": [1, 900, 1000]}}],
            }
            route.fulfill(json=body)

    page.route("https://api.inaturalist.org/**", api)
    page.goto(site + "#user=42")
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
    page = open_map(browser, site, f"#user=42&area={area}")
    shown(page, IN_GENUS_A)
    link = urlparse(page.get_attribute("#identify", "href"))
    q = parse_qs(link.query)
    assert q["id"] and q["without_ident_user_id"] == ["42"]
    assert len(q["id"][0].split(",")) == IN_GENUS_A
    assert page.errors == []
    page.close()


def test_observer_keeps_the_users_own_records(browser, site):
    page = open_map(browser, site, "#user=10&umode=observer")
    shown(page, N // 2)  # the fixture's observers alternate between users 10 and 11
    assert page.calls == [] and "observed by" in page.inner_text("#usrbox p")
    # Identify opens the user's records; without_ident_user_id would drop the ones they identified
    # themselves, which is nearly all of an observer's own records
    q = parse_qs(urlparse(page.get_attribute("#identify", "href")).query)
    assert q["user_id"] == ["10"] and "without_ident_user_id" not in q
    assert page.errors == []
    page.close()


def test_not_yet_identified_hides_the_records_the_user_identified_in_the_view(browser, site):
    page = open_map(browser, site, "#user=42&umode=unid")
    shown(page, N - 3)
    q = page.calls[-1][1]
    assert page.calls[-1][0].endswith("/observations")
    assert q["ident_user_id"] == ["42"] and q["quality_grade"] == ["needs_id"]
    assert {"swlat", "swlng", "nelat", "nelng"} <= q.keys()
    assert page.is_visible("#usrbox button") and "approximate" in page.inner_text("#idnote")
    assert page.errors == []
    page.close()
