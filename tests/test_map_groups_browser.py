"""The map's groups list in Chromium: the real map page over stand-ins for MapLibre and deck.gl
(the CDN builds need WebGL), so it runs offline. The stand-in map shows the whole world."""

import functools
import http.server
import threading

import pytest

from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame

browser = eb.browser
SIZES = {"Plantae": 170, "Insecta": 100, "Aves": 30}
STUB = """
window.maplibregl = {
  Map: class { constructor(o) { this.c = document.getElementById(o.container);
      this.doubleClickZoom = this.dragPan = { enable() {}, disable() {} }; }
    on() {} once() {} off() {} resize() {} fitBounds() {} easeTo() {} flyTo() {}
    addSource() {} addLayer() {} getSource() { return null; } getLayer() { return null; }
    addControl(c) { const e = c && c.onAdd && c.onAdd(this); if (e) this.c.appendChild(e); }
    getBounds() { return { getWest: () => -180, getEast: () => 180, getSouth: () => -85,
      getNorth: () => 85, contains: () => true }; }
    getCenter() { return { lat: 49, lng: -123 }; } getZoom() { return 5; }
    getContainer() { return this.c; } getCanvas() { return document.createElement('canvas'); }
    project() { return { x: 0, y: 0 }; } },
  NavigationControl: class {},
};
window.deck = {
  MapboxOverlay: class { setProps() {} },
  DataFilterExtension: class { initializeState() {} },
  ScatterplotLayer: class { constructor(p) { this.props = p; this.id = p.id; } },
  TextLayer: class { constructor(p) { this.props = p; this.id = p.id; } },
};"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("map-groups")
    pool = pool_frame(range(1, 301))
    pool["iconic_taxon"] = [g for g, n in SIZES.items() for _ in range(n)]
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


@pytest.fixture
def page(browser, site):
    p = browser.new_page(viewport={"width": 1280, "height": 900})
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )
    p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    p.goto(site)
    p.wait_for_function("document.querySelector('#groups .gc').textContent !== ''")
    p.wait_for_selector("#groups .gt")  # the carets come with the taxa
    yield p
    assert p.errors == []
    p.close()


ROWS = """() => [...document.querySelectorAll('#groups > li')].map(li => [
  li.querySelector('.nm').textContent, li.querySelector('.gc').textContent,
  li.querySelector('.gp').textContent, li.querySelector('.gb').getAttribute('aria-pressed')])"""


def hash_groups(page):
    return page.evaluate("new URLSearchParams(location.hash.slice(1)).get('groups')")


def test_groups_come_first_and_open_with_rows_by_count(page):
    assert page.evaluate("document.querySelector('#side details.sec').id") == "grpsec"
    assert page.evaluate("document.getElementById('grpsec').open")
    rows = page.evaluate(ROWS)
    assert [r[1] for r in rows] == ["170", "100", "30"]
    assert [r[2] for r in rows] == ["57%", "33%", "10%"]
    label = page.get_attribute("#gbar", "aria-label")
    assert rows[0][0] + " 57%" in label and rows[2][0] + " 10%" in label
    assert page.locator("#gbar i").count() == 3


def test_picking_a_group_keeps_every_share_and_writes_the_old_hash(page):
    before = page.evaluate(ROWS)
    page.locator("#groups > li").nth(2).locator(".gb").click()
    page.wait_for_function("(document.getElementById('count').textContent || '').startsWith('30 ')")
    after = page.evaluate(ROWS)
    assert [r[:3] for r in after] == [r[:3] for r in before]
    assert [r[3] for r in after] == ["false", "false", "true"]
    page.wait_for_function("location.hash.includes('groups=Aves')")
    page.locator("#groups > li").nth(2).locator(".gb").click()  # again clears it
    page.wait_for_function("!location.hash.includes('groups=')")


def test_leave_out_sets_the_minus_term_and_marks_the_row(page):
    row = page.locator("#groups > li").nth(0)
    row.locator(".gx").click()
    page.wait_for_function("location.hash.includes('groups=-')")
    assert hash_groups(page) == "-Plantae"
    assert row.locator(".nm").text_content().startswith("not ")
    assert row.locator(".gx").get_attribute("aria-pressed") == "true"
    page.wait_for_function(
        "(document.getElementById('count').textContent || '').startsWith('130 ')"
    )
    assert [r[1] for r in page.evaluate(ROWS)] == ["170", "100", "30"]


def test_the_caret_opens_the_ranks_with_counts(page):
    row = page.locator("#groups > li").nth(0)
    row.locator(".gt").click()
    assert row.locator(".gt").get_attribute("aria-expanded") == "true"
    counts = row.locator(".gs .tn .tc").all_text_contents()
    assert counts and all(c.replace(",", "").isdigit() for c in counts)
    assert sum(int(c) for c in counts) == 170  # Genus A and Genus B under Family F


def test_a_date_preset_shows_as_a_chip_and_clear_all_clears_it(page):
    page.get_by_role("button", name="Last 30 days").click()  # the records span 60 days
    chip = page.locator("#selbar li").filter(has_text="Observed")
    assert chip.count() == 1 and "to now" in chip.inner_text()
    page.locator("#selbar .lbl button").click()
    page.wait_for_selector("#selbar", state="hidden")
    assert page.get_by_role("button", name="All dates").get_attribute("aria-pressed") == "true"
