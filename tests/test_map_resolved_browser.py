"""The map's left-needs-ID control in Chromium: the real map page over the stand-ins of
test_map_groups_browser.py, with a pool-resolved.bin from a fake log of 40 records, 10 of which left
in the last 7 days and 5 of those are Aves."""

import functools
import http.server
import threading

import pytest

from what_to_id import site_files
from what_to_id.map_points import encode_points
from what_to_id.map_resolved import encode_left
from what_to_id.page_map import render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_map_groups_browser import STUB
from .test_map_resolved import NOW, log_frame

browser = eb.browser
# the stand-in overlay keeps the layers it was given
LAYERS_STUB = STUB.replace(
    "MapboxOverlay: class { setProps() {} }",
    "MapboxOverlay: class { setProps(p) { window.L = p.layers; } }",
)
LEFT = "(window.L || []).filter(l => l.id === 'left').map(l => l.props.data.length)"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("map-resolved")
    pool = pool_frame(range(1, 121))
    pool["observed_on"] = pool["created_at"] = ["2026-08-01"] * 119 + ["2026-11-03"]
    blobs, meta = encode_points(pool, TREE)
    ago = [0, 1, 2, 3, 4, 5, 6, 0, 1, 2] + [8 + i % 20 for i in range(30)]
    log = log_frame(range(1001, 1041), ago)
    log["iconic_taxon"] = ["Aves"] * 5 + ["Insecta"] * 5 + ["Plantae"] * 30
    log["reason"] = (
        [1] * 25 + [5] * 5 + [1] * 10
    )  # the 5 oldest are backfilled Research Grade, before the live log
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    site_files.publish(root, "resolved", "pool-resolved.bin", encode_left(log, pool, TREE, NOW))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/map.html?standalone=1"
    server.shutdown()


def open_map(browser, url, hash_="", missing=False):
    p = browser.new_page(viewport={"width": 1280, "height": 900})
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=LAYERS_STUB if r.request.url.endswith(".js") else "",
            content_type="text/javascript",
        ),
    )
    p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    if missing:
        p.route("**/pool-resolved.*", lambda r: r.fulfill(status=404))
    p.goto(url + hash_)
    return p


def says(page, text):
    page.wait_for_function(
        "t => document.getElementById('leftbox').textContent.includes(t)", arg=text
    )


def test_seven_days_counts_and_draws_the_records_that_left_under_the_filters(browser, site):
    page = open_map(browser, site, "#resolved=7")
    says(page, "10 in view left Needs ID in the last 7 days, 10 as Research Grade")
    main = page.locator("#leftbox > span:last-child > span").first
    assert main.get_attribute("title") == "28 Oct to 3 Nov 2026, UTC"
    assert page.locator("#leftbox .muted").last.inner_text() == ""  # the 7 days are all live
    page.wait_for_function(f"{LEFT}.join() === '10'")
    assert page.get_attribute("#leftbox button:text('7 days')", "aria-pressed") == "true"
    page.click("#scope button:text('All of BC')")
    says(page, "10 left Needs ID in the last 7 days")
    assert page.errors == []
    page.close()
    # a group chip narrows the count and the dots
    page = open_map(browser, site, "#resolved=7&groups=Aves")
    says(page, "5 in view left Needs ID")
    page.wait_for_function(f"{LEFT}.join() === '5'")
    assert page.errors == []
    page.close()


def test_thirty_days_and_off_change_the_hash_and_the_layer(browser, site):
    page = open_map(browser, site)
    assert page.locator("#leftbox button").all_inner_texts() == ["Off", "7 days", "30 days"]
    page.click("#leftbox button:text('30 days')")
    says(
        page, "40 in view left Needs ID since 7 Oct, 40 as Research Grade"
    )  # the log is 27 days old
    assert page.locator("#leftbox > span:last-child > span").first.get_attribute("title") == (
        "7 Oct to 3 Nov 2026, UTC"
    )
    note = "Before 12 Oct only Research Grade is counted."
    assert page.locator("#leftbox .muted").last.inner_text() == note
    page.wait_for_function("location.hash.includes('resolved=30')")
    page.wait_for_function(f"{LEFT}.join() === '40'")
    page.click("#leftbox button:text('Off')")
    page.wait_for_function(f"!location.hash.includes('resolved=') && {LEFT}.length === 0")
    assert page.inner_text("#leftbox > span:last-child") == ""
    assert page.errors == []
    page.close()


def test_a_missing_file_says_so_and_breaks_nothing(browser, site):
    page = open_map(browser, site, "#resolved=30", missing=True)
    says(page, "Could not load the records that left Needs ID (HTTP 404)")
    assert page.errors == []
    page.close()
