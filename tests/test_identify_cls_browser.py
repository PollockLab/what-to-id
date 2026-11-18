"""Identify's rows hold the height they fill, so a phone that runs the page's script late does not
see the rows below them drop when the tabs and chips arrive. iNaturalist is stubbed."""

import http.server
import struct
import threading
import time
import zlib
from urllib.parse import parse_qs, urlparse

import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site

HEIGHTS = "['tabs','qchips'].map(i=>document.getElementById(i).getBoundingClientRect().height)"


@pytest.mark.parametrize("size", [(390, 844), (1280, 800)])
def test_the_empty_tabs_and_chips_are_as_tall_as_the_filled_ones(browser, site, size):
    page = ib.open_identify(browser, site[0], "#lvl=3&sort=conf", size=size, touch=size[0] < 600)
    page.wait_for_selector("#tabs .tab .cut", state="attached")
    page.wait_for_selector("#qchips .qchip", state="attached")
    filled = page.evaluate(HEIGHTS)
    assert min(filled) > 20  # a real tab row and a real chip row
    page.evaluate(
        "tabs.replaceChildren();qchips.replaceChildren()"
    )  # the page before its script ran
    empty = page.evaluate(HEIGHTS)
    assert empty == pytest.approx(filled, abs=1)
    page.close()


LATE = """(()=>{sortb.hidden=false;showall.hidden=false;showall.textContent='Show all';
count.textContent='5,417 cards · 3 per species of 73,367 records, the best 5%';
go.textContent='Identify these 200 on iNaturalist';prev.hidden=next.hidden=false;
bn.textContent='Batch 1 of 28'})()"""


def test_level_3_bar_holds_the_lines_that_arrive_late_on_a_phone(browser, site):
    """The Prioritize chip and Show all (the survey layer) and Batch n of m (the whole pool) wrap
    a second line in the count row and the batch row: the cards below must not move for them."""
    page = ib.open_identify(browser, site[0], "#lvl=3&sort=conf", size=(390, 844), touch=True)
    page.wait_for_selector("#grid .card")
    top = "grid.getBoundingClientRect().top"
    before = page.evaluate(top)
    page.evaluate(LATE)
    assert page.evaluate(top) == pytest.approx(before, abs=1)
    page.close()


def png(w, h):
    """A grey PNG of this size."""
    raw = b"".join(b"\0" + b"\x80" * w for _ in range(h))

    def chunk(kind, body):
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


SIZES = [png(500, 375), png(375, 500), png(500, 500)]  # landscape, portrait, square photos


class Slow(http.server.BaseHTTPRequestHandler):
    """Photos of varied shapes, each 300 to 800 ms late."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        n = int(self.path.split("/")[2])
        time.sleep(0.3 + n % 6 / 10)
        body = SIZES[n % 3]
        self.send_response(200)
        self.send_header("content-type", "image/png")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def photos():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def gone(i):
    return i % 10 < 3  # about 30% of the records left Needs ID since the pool was built


def open_slow(browser, base, photos_url, hash_, size):
    """Identify whose gone records are Research Grade and whose photos are late and varied."""
    touch = size[0] < 600
    view = {"width": size[0], "height": size[1]}
    page = (
        browser.new_context(viewport=view, has_touch=True, is_mobile=True).new_page()
        if touch
        else browser.new_page(viewport=view)
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route(ib.WTB, lambda r: r.abort())
    page.route(
        "https://api.inaturalist.org/v1/**",
        lambda r: r.fulfill(json={"results": []}, headers={"access-control-allow-origin": "*"}),
    )

    def observations(route):
        ids = [int(i) for i in parse_qs(urlparse(route.request.url).query)["id"][0].split(",")]
        results = [
            {
                "id": i,
                "quality_grade": "research" if gone(i) else "needs_id",
                "observed_on": "2026-05-01",
                "place_guess": "Vancouver, BC",
                "photos": [{"url": f"https://static.inaturalist.org/photos/{i}/square.jpg"}],
                "taxon": {"name": f"Taxon {i}", "preferred_common_name": f"Common {i}"},
            }
            for i in ids
        ]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.route(
        "https://static.inaturalist.org/**",
        lambda r: r.fulfill(
            response=r.fetch(url=photos_url + urlparse(r.request.url).path),
            headers={"access-control-allow-origin": "*"},
        ),
    )
    page.add_init_script(
        "window.IntersectionObserver = undefined"
    )  # only the first page, not scroll's
    page.add_init_script(
        """window.__cls=0;new PerformanceObserver(l=>{for(const e of l.getEntries())
        if(!e.hadRecentInput&&(e.sources||[]).some(s=>s.node&&s.node.closest&&s.node.closest('#grid')))window.__cls+=e.value;
        }).observe({type:'layout-shift',buffered:true});"""
    )
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify")
    return page


@pytest.mark.parametrize("size", [(390, 844), (1280, 800)])
@pytest.mark.parametrize("hash_", ["#lvl=1", "#lvl=3&sort=conf"])
def test_cards_whose_records_are_gone_are_refilled_where_they_stand(
    browser, site, photos, size, hash_
):
    page = open_slow(browser, site[0], photos, hash_, size)
    level = int(hash_.split("lvl=")[1][0])
    page.wait_for_function(
        f"document.querySelectorAll('#grid .card .ph img').length>="
        f"Math.min(12,__identify.view()[{level}].length)&&"
        "[...document.querySelectorAll('#grid .card .ph img')].every(i=>i.complete&&i.naturalWidth)"
    )
    page.wait_for_timeout(1500)  # a late refill or a second round of answers
    shown = page.evaluate("[...document.querySelectorAll('#grid .card')].map(c=>+c.dataset.id)")
    first = page.evaluate(f"__identify.view()[{level}].slice(0, 12)")
    assert len(shown) == len(first) > 0 and not [i for i in shown if gone(i)]
    assert sorted(shown) == sorted(
        first
    )  # the first (up to twelve) records still needing an ID, however they are ordered
    assert page.evaluate("window.__cls") < 0.05
    assert page.errors == []
    page.close()
