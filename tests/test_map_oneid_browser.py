"""The map's One ID from Research Grade choice in Chromium: the real map page over the stand-ins of
test_map_groups_browser.py."""

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
# (IDs by others, agreements, taxon): the boundary cases of the rule, five of eight qualify
CASES = [
    (0, 0, 1000),
    (1, 1, 1001),
    (2, 1, 1002),
    (3, 2, 1003),
    (2, 2, 1004),
    (1, 0, 1005),
    (3, 1, 1006),
    (0, 0, 900),  # a genus
]
N = 80
WANT = sum(1 for i in range(N) if i % 8 < 5)


def serve(root, n, value=None):
    pool = pool_frame(range(1, n + 1))
    pool["ident_count"] = [CASES[i % 8][0] for i in range(n)]
    pool["agree"] = [CASES[i % 8][1] for i in range(n)]
    pool["taxon_id"] = [CASES[i % 8][2] for i in range(n)]
    pool["taxon_name"] = [f"Taxon {c % 1000}" if c >= 1000 else "Genus A" for c in pool["taxon_id"]]
    pool["rank"] = ["species" if c >= 1000 else "genus" for c in pool["taxon_id"]]
    blobs, meta = encode_points(pool, TREE)
    assert meta["flags"] == ["oneid"]
    if value is not None:
        meta["value"] = value
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
    return server, f"http://127.0.0.1:{server.server_port}/map.html?standalone=1"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    server, url = serve(tmp_path_factory.mktemp("map-oneid"), N)
    yield url
    server.shutdown()


def open_map(browser, url, hash_):
    p = browser.new_page(viewport={"width": 1280, "height": 900})
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )
    p.goto(url + hash_)
    return p


def shown(page, n):
    page.wait_for_function(
        "n => (document.getElementById('count').textContent || '').startsWith(n + ' ')", arg=str(n)
    )


def test_the_hash_keeps_the_records_one_id_from_research_grade(browser, site):
    page = open_map(browser, site, "")
    shown(page, N)
    page.click("#flags button:has-text('One ID from Research Grade')")
    shown(page, WANT)
    page.wait_for_function("location.hash.includes('only=oneid')")
    page.close()
    page = open_map(browser, site, "#only=oneid")
    shown(page, WANT)
    page.close()
    page = open_map(browser, site, "#only=-oneid")
    shown(page, N - WANT)
    assert page.errors == []
    page.close()


def test_identify_cannot_filter_it_and_says_so(browser, site):
    page = open_map(browser, site, "#only=oneid")
    shown(page, WANT)
    page.wait_for_function("document.getElementById('idnote').textContent.includes('Identify')")
    assert "cannot filter records one ID from Research Grade" in page.inner_text("#idnote")
    q = parse_qs(urlparse(page.get_attribute("#identify", "href")).query)
    assert "rank" not in q and "introduced" not in q
    page.close()


BIG = 16100  # 10,063 one ID from Research Grade, past the 10,000 listed by id


@pytest.fixture(scope="module")
def big_site(tmp_path_factory):
    server, url = serve(tmp_path_factory.mktemp("map-oneid-big"), BIG)
    yield url
    server.shutdown()


def test_past_the_limit_the_note_offers_every_record_and_back(browser, big_site):
    want = sum(1 for i in range(BIG) if i % 8 < 5)
    page = open_map(browser, big_site, "#only=oneid")
    page.wait_for_function(
        "document.getElementById('idnote').textContent.includes('the first 10,000')"
    )
    assert f"the first 10,000 of these {want:,} records" in page.inner_text("#idnote")
    assert "batch 1 of 50" in page.inner_text("#identify")
    # Identify hides records the viewer reviewed, which the map cannot know, so the note says so
    assert "already reviewed by you" in page.inner_text("#idnote")
    page.click("#idnote button:has-text('Open all')")
    page.wait_for_function("document.getElementById('identify').textContent.includes('of 51')")
    assert "opens these records by id" in page.inner_text("#idnote")
    # the new button keeps keyboard focus, so a keyboard user can switch back
    assert page.evaluate("document.activeElement.textContent") == "Open only the first 10,000"
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('identify').textContent.includes('of 50')")
    assert page.errors == []
    page.close()


# taxon 1003 listed in Canada, 1001 BC S1-S2 with Research Grade records, the rest no status
VALUE = [[1001, 2, 50], [1003, 1, 0]]
VN = 400  # two batches, so the order decides which records the first one holds


@pytest.fixture(scope="module")
def value_site(tmp_path_factory):
    server, url = serve(tmp_path_factory.mktemp("map-value"), VN, VALUE)
    yield url
    server.shutdown()


def test_conservation_status_sort_lists_at_risk_records_first_and_back(browser, value_site):
    page = open_map(browser, value_site, "")
    shown(page, VN)
    order = page.locator("#idorder")
    order.wait_for(state="visible")
    assert "id" not in parse_qs(urlparse(page.get_attribute("#identify", "href")).query)
    order.click()
    page.wait_for_function("(document.getElementById('identify').href || '').includes('&id=')")
    ids = parse_qs(urlparse(page.get_attribute("#identify", "href")).query)["id"][0].split(",")
    taxa = [CASES[(int(i) - 1) % 8][2] for i in ids]
    # every record of each at-risk taxon in batch 1, against 25 in the newest 200 unordered
    assert len(ids) == 200 and taxa.count(1003) == 50 and taxa.count(1001) == 50
    assert "batch 1 of 2" in page.inner_text("#identify")
    assert order.get_attribute("aria-pressed") == "true"
    note = page.inner_text("#idnote")
    assert note.startswith("Sorted by conservation status: listed by SARA or COSEWIC, then BC S1")
    assert ", so it opens these records" in note
    order.click()
    page.wait_for_function("!(document.getElementById('identify').href || '').includes('&id=')")
    assert page.errors == []
    page.close()
