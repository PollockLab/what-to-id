"""site_assets/fetch_once.js in Chromium: two frames share one download of a content-hashed file."""

import collections
import functools
import http.server
import threading
from pathlib import Path

import pytest

from . import test_identify_browser as ib

browser = ib.browser
JS = (Path(__file__).parents[1] / "src/what_to_id/site_assets/fetch_once.js").read_text()
OLD, NEW, PLAIN = "pool-1.aaaaaaaaaaaa.bin", "pool-1.0123456789ab.bin", "pool-1.bin"


@pytest.fixture
def site(tmp_path):
    for name in (OLD, NEW, PLAIN):
        (tmp_path / name).write_bytes(name.encode())
    asks = f"[fetchOnce('{NEW}'),fetchOnce('{NEW}'),fetchOnce('{PLAIN}')]"
    child = (
        f"<script>{JS}</script><script>window.got=Promise.all({asks}).then(function(a)"
        "{return a.map(function(b){return new TextDecoder().decode(b);});});</script>"
    )
    (tmp_path / "child.html").write_text(child)
    (tmp_path / "old.html").write_text(
        f"<script>{JS}</script><script>window.got=fetchOnce('{OLD}');</script>"
    )
    (tmp_path / "two.html").write_text(
        '<iframe src="child.html"></iframe><iframe src="child.html"></iframe>'
    )
    hits = collections.Counter()

    class Count(ib.Quiet):
        def do_GET(self):
            hits[self.path.lstrip("/")] += 1
            super().do_GET()

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Count, directory=str(tmp_path))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/", hits
    server.shutdown()


def keys(page):
    return page.evaluate(
        "caches.open('wtid-data').then(c=>c.keys()).then(k=>k.map(r=>r.url.split('/').pop()))"
    )


def test_two_frames_download_a_hashed_file_once_and_evict_its_old_version(browser, site):
    base, hits = site
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(base + "old.html")
    page.evaluate("window.got")
    assert keys(page) == [OLD]
    page.goto(base + "two.html")
    for f in page.frames[1:]:
        f.wait_for_load_state()
        assert f.evaluate("window.got") == [NEW, NEW, PLAIN]
    assert hits[NEW] == 1  # one network request across both frames and both asks
    assert keys(page) == [NEW]  # the old version of pool-1 is gone
    ctx.close()
