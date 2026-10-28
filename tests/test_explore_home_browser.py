"""Explore as the home page in Chromium: the real map beside a stand-in Identify page, over the
stand-ins for MapLibre and deck.gl that test_map_groups_browser.py uses, so it runs offline. Beside
Identify the map's dots take the Identify levels' colours."""

import functools
import gzip
import http.server
import threading

import numpy as np
import pytest

from what_to_id import split_page
from what_to_id.page_identify import LEVELS
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from . import test_map_groups_browser as mg
from .embeddings_fixture import TREE, pool_frame

browser = eb.browser
N = 300
# the overlay keeps its layers, so a test can read the dots' colours
STUB = mg.STUB.replace(
    "MapboxOverlay: class { setProps() {} }",
    "MapboxOverlay: class { setProps(p) { window.__layers = p.layers; } }",
)
IDENTIFY = '<!doctype html><title>Identify</title><p id="status">300 to identify</p>'
GREEN, GREY = [0, 158, 115, 170], [150, 150, 150, 60]  # level 1 and no level, as in level_colour.js


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("explore-home")
    pool = pool_frame(range(1, N + 1))
    pool["iconic_taxon"] = [g for g, n in mg.SIZES.items() for _ in range(n)]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    # record i at level i % 6: none, the four levels, and 5 before the page names it
    (root / "pool-levels.bin").write_bytes(gzip.compress((np.arange(N) % 6).astype("u1").tobytes()))
    (root / "identify.html").write_text(IDENTIFY)
    split_page.build(root)
    served = []

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            served.append(self.path)

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", served
    server.shutdown()


def open_page(browser, url, width=1280):
    p = browser.new_page(viewport={"width": width, "height": 900})
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )
    p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    p.goto(url)
    return p


def map_frame(page):
    page.wait_for_function(
        "document.getElementById('map')?.contentDocument?.getElementById('count')?.textContent"
        ".startsWith('300 ')"
    )
    return next(f for f in page.frames if "map.html" in f.url)


# the fill colours of records 0, 1 and 5, and whether the legend shows
COLOURS = """() => { const c = window.__layers[0].props.data.attributes.getFillColor.value,
  at = i => Array.from(c.slice(4 * i, 4 * i + 4)), l = document.querySelector('.lvleg');
  return {c0: at(0), c1: at(1), c5: at(5), legend: !!l && !l.hidden,
    names: l ? [...l.querySelectorAll('span')].map(s => s.textContent) : []}; }"""


def test_beside_identify_the_dots_take_the_level_colours_and_go_back_without_it(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    frame.wait_for_function(f"({COLOURS})().legend")
    got = frame.evaluate(COLOURS)
    assert got["c0"] == GREY and got["c1"] == GREEN  # no level is faint grey, still drawn
    assert got["c5"] not in (GREY, GREEN) and got["c5"][3] > GREY[3]  # level 5 has its own colour
    assert got["names"] == [name for _, name, _ in LEVELS] + ["No level"]
    page.click("[data-p=identify]")  # the map alone: the group colours again
    frame.wait_for_function(f"!({COLOURS})().legend")
    got = frame.evaluate(COLOURS)
    assert got["c1"][3] == 110 and got["c1"] != GREEN
    page.click("[data-p=identify]")
    frame.wait_for_function(f"({COLOURS})().legend")
    assert page.errors == []
    page.close()


def test_the_standalone_map_keeps_the_group_colours_and_never_loads_the_levels(browser, site):
    base, served = site
    served.clear()
    page = open_page(browser, f"{base}/map.html?standalone=1")
    page.wait_for_function("document.getElementById('count').textContent.startsWith('300 ')")
    got = page.evaluate(COLOURS)
    assert got["c1"][3] == 110 and not got["legend"]
    assert not any("pool-levels.bin" in s for s in served)
    assert page.errors == []
    page.close()


# the top bar's groups button: its text, title, and per segment whether it is dimmed
GSUM = """() => { const g = document.getElementById('gsum');
  return {shown: !g.hidden, text: g.querySelector('.gt').textContent, title: g.title,
    dim: [...g.querySelectorAll('.gbar i')].map(i => i.classList.contains('dim'))}; }"""


def test_the_top_bar_shows_the_group_shares_and_opens_the_groups_filter(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    page.wait_for_function(f"({GSUM})().dim.length === 3")
    got = page.evaluate(GSUM)
    assert got["shown"] and got["text"] == "" and got["dim"] == [False] * 3
    assert (
        got["title"].startswith("All groups.") and "57%" in got["title"]
    )  # the largest group's share, as the map's own summary says it
    # the smallest group alone; the list sits in the shut filter drawer
    frame.evaluate("document.querySelectorAll('#groups > li')[2].querySelector('.gb').click()")
    page.wait_for_function(f"({GSUM})().text !== ''")
    got = page.evaluate(GSUM)
    assert got["dim"] == [True, True, False]
    assert got["text"] == frame.locator("#groups > li").nth(2).locator(".nm").text_content()
    assert not frame.evaluate("document.getElementById('side').classList.contains('open')")
    frame.evaluate("document.getElementById('grpsec').open = false")
    page.click("#gsum")
    frame.wait_for_function("document.getElementById('side').classList.contains('open')")
    assert frame.evaluate("document.getElementById('grpsec').open")
    page.click("[data-p=map]")  # without the map there are no shares to show
    page.wait_for_function("document.getElementById('gsum').hidden")
    assert page.errors == []
    page.close()


def test_the_header_keeps_one_line_at_1280(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    map_frame(page)
    page.wait_for_function("!document.getElementById('gsum').hidden")
    tops = page.evaluate(
        "[...document.querySelectorAll('.site-nav, #xbar > *:not([hidden]):not(.note)')]"
        ".map(e => { const r = e.getBoundingClientRect();"
        " return Math.round(r.top + r.height / 2); })"
    )
    assert max(tops) - min(tops) <= 2, tops
    assert page.evaluate("document.documentElement.scrollWidth") <= 1280
    page.close()


BLOCK = """Object.defineProperty(window, 'localStorage', {configurable: true,
  get() { throw new DOMException('blocked', 'SecurityError'); }});"""


def test_remembered_groups_apply_to_a_link_without_groups_and_show_all_clears_them(browser, site):
    base = site[0]
    page = open_page(browser, f"{base}/map.html?standalone=1")
    page.wait_for_function("document.getElementById('count').textContent.startsWith('300 ')")
    assert page.is_hidden("#gkeep") and page.is_hidden("#mine")  # nothing picked, nothing kept
    page.locator("#groups > li").nth(2).locator(".gb").click()
    page.click("#gkeep")
    assert page.evaluate("localStorage.getItem('wtid-my-groups')") == "Aves"
    assert page.text_content("#gkeep") == "Forget these groups"
    page.goto("about:blank")  # a new load, not a hash change
    page.goto(f"{base}/map.html?standalone=1#at=5/49/-123")  # a link that names no groups
    page.wait_for_function("document.getElementById('count').textContent.startsWith('30 ')")
    assert page.is_visible("#mine") and page.text_content("#mine").startswith("Your groups")
    page.click("#mine button")  # Show all
    page.wait_for_function("document.getElementById('count').textContent.startsWith('300 ')")
    assert page.is_hidden("#mine")
    page.goto("about:blank")
    page.goto(f"{base}/map.html?standalone=1#groups=Insecta")  # a link's own groups win
    page.wait_for_function("document.getElementById('count').textContent.startsWith('100 ')")
    assert page.is_hidden("#mine")
    assert page.errors == []
    page.close()
    # Explore hands them to every pane, so Identify and the map agree
    page = open_page(browser, f"{base}/explore.html")
    page.evaluate("localStorage.setItem('wtid-my-groups', 'Aves')")
    page.goto(f"{base}/explore.html")
    page.wait_for_function(
        "document.getElementById('map')?.contentDocument?.getElementById('count')?.textContent"
        ".startsWith('30 ')"
    )
    assert next(f for f in page.frames if "map.html" in f.url).is_visible("#mine")
    assert "groups=Aves" in next(f for f in page.frames if "identify.html" in f.url).url
    page.evaluate("localStorage.removeItem('wtid-my-groups')")
    assert page.errors == []
    page.close()


def test_with_storage_blocked_the_map_and_explore_still_work(browser, site):
    page = open_page(browser, "about:blank")
    page.add_init_script(BLOCK)
    page.goto(f"{site[0]}/map.html?standalone=1")
    page.wait_for_function("document.getElementById('count').textContent.startsWith('300 ')")
    page.locator("#groups > li").nth(2).locator(".gb").click()
    page.wait_for_function("document.getElementById('count').textContent.startsWith('30 ')")
    assert page.is_hidden("#gkeep")  # nothing can be kept, so nothing is offered
    page.goto(f"{site[0]}/explore.html")
    map_frame(page)
    page.wait_for_function("!document.getElementById('gsum').hidden")
    assert page.errors == []
    page.close()
