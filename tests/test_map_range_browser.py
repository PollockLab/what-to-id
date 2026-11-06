"""The map's Outside usual range choice in Chromium, over the Identify range fixture's records."""

import functools
import http.server
import threading

import pytest

from what_to_id import pool_levels, site_files

from . import test_identify_ranges_browser as rb
from .test_map_oneid_browser import open_map, shown

browser = rb.browser


def serve(root):
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(rb.ib.Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/map.html?standalone=1"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("map-range")
    rb.write_site(root)
    km = pool_levels.unpack_range(site_files.path(root, "range").read_bytes(), rb.N)[1]
    server, url = serve(root)
    yield url, int((km >= 50).sum())
    server.shutdown()


def test_the_chip_keeps_the_records_far_outside_their_range_and_off_restores_all(browser, site):
    url, far = site
    assert 0 < far < rb.N
    page = open_map(browser, url, "#only=range")
    shown(page, far)
    chip = page.locator("#flags button:has-text('Outside usual range')")
    chip.click()  # on, left out, off
    shown(page, rb.N - far)
    page.wait_for_function("location.hash.includes('only=-range')")
    chip.click()
    shown(page, rb.N)
    page.wait_for_function("!location.hash.includes('only=')")
    assert page.errors == []
    page.close()


def test_identify_cannot_filter_it_and_says_so(browser, site):
    page = open_map(browser, site[0], "#only=range")
    shown(page, site[1])
    page.wait_for_function("document.getElementById('idnote').textContent.includes('Identify')")
    assert "cannot filter records outside their range" in page.inner_text("#idnote")
    page.close()


def test_without_the_range_file_there_is_no_chip_and_the_hash_keeps_all(browser, tmp_path):
    rb.write_site(tmp_path)
    # a build without ranges drops the file and the flag
    pool_levels.build(tmp_path, parquet=tmp_path / "identify.parquet")
    server, url = serve(tmp_path)
    page = open_map(browser, url, "#only=range")
    shown(page, rb.N)
    assert page.locator("#flags button:has-text('Outside usual range')").count() == 0
    assert page.errors == []
    page.close()
    server.shutdown()
