"""The tree of life page in Chromium, with iNaturalist stubbed: it draws, selects, opens by key and
fetches tip photos. Its split-view pane is covered in test_split_subsets_browser.py."""

import functools
import gzip
import http.server
import json
import threading
from urllib.parse import urlparse

import numpy as np
import pytest

from what_to_id import tree_page
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import pool_frame
from .test_atlas_search_browser import PNG
from .test_tree_page import write_site

browser = eb.browser


def stub_taxa(page):
    """iNaturalist's taxa endpoint, every asked id with a default photo. Returns the id lists."""
    calls = []

    def taxa(route):
        ids = [int(i) for i in urlparse(route.request.url).path.rsplit("/", 1)[1].split(",")]
        calls.append(ids)
        photo = {
            "square_url": "https://static.inaturalist.org/p/1/square.jpg",
            "attribution": "(c) x",
        }
        results = [{"id": i, "default_photo": photo} for i in ids]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/taxa/**", taxa)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=PNG, content_type="image/png")
    )
    return calls


def serve(root):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def built(tmp_path_factory, *tree):
    root = tmp_path_factory.mktemp("tree-site")
    write_site(root, *tree)
    tree_page.build(root)
    server, url = serve(root)
    yield url
    server.shutdown()


# Life > Animalia > Aves > a robin, and Life > Bacteria: 20 birds, then 20 Unknown records, 10 in
# Bacteria, 5 identified only to Life and 5 with no taxon
LIFE_TREE = {
    2000: [3, "Turdus migratorius", "American Robin", "species"],
    3: [1, "Aves", "Birds", "class"],
    1: [48460, "Animalia", "Animals", "kingdom"],
    48460: [None, "Life", "Life", "stateofmatter"],
    67333: [48460, "Bacteria", "", "kingdom"],
}


@pytest.fixture(scope="module")
def life_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("tree-life")
    pool = pool_frame(np.arange(1, 41))
    pool["taxon_id"] = [2000] * 20 + [67333] * 10 + [48460] * 5 + [None] * 5
    pool["taxon_name"] = ["x"] * 30 + ["Life"] * 5 + [None] * 5
    pool["iconic_taxon"] = ["Aves"] * 20 + [None] * 20
    blobs, meta = encode_points(pool, LIFE_TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    tree_page.build(root)
    server, url = serve(root)
    yield url
    server.shutdown()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    yield from built(tmp_path_factory)


# A chain that branches into a species at every rank, so the last species sit ten levels down.
RANKS = ["kingdom", "phylum", "class", "order", "family", "subfamily", "tribe", "subtribe", "genus"]
DEEP = {
    **{
        700 + i: [699 + i if i else None, f"Brachytheciaceae {i}", "", r]
        for i, r in enumerate(RANKS)
    },
    **{1000 + k: [700 + min(k, 8), f"Taxon {k}", "", "species"] for k in range(10)},
    1007: [707, "Taxon 7", "Feather mosses with a long common name", "species"],  # a long name too
}


@pytest.fixture(scope="module")
def deep_site(tmp_path_factory):
    pool = pool_frame(np.arange(1, 301))
    pool["taxon_id"] = 1000 + np.arange(300) % 10
    pool["taxon_name"] = [DEEP[t][1] for t in pool["taxon_id"]]
    yield from built(tmp_path_factory, DEEP, pool)


# One genus of many species with long names, so their tip labels crowd the full circle.
WIDE = {
    800: [None, "Sphagnum", "", "genus"],
    **{1100 + k: [800, f"Sphagnum magellanicum subsp. {k}", "", "species"] for k in range(40)},
}


@pytest.fixture(scope="module")
def wide_site(tmp_path_factory):
    pool = pool_frame(np.arange(1, 401))
    pool["taxon_id"] = 1100 + np.arange(400) % 40
    pool["taxon_name"] = [WIDE[t][1] for t in pool["taxon_id"]]
    yield from built(tmp_path_factory, WIDE, pool)


def open_tree(browser, site, w=1280, h=800, hash_=""):
    page = browser.new_page(viewport={"width": w, "height": h})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.calls = stub_taxa(page)
    page.goto(f"{site}/tree.html{hash_}")
    page.wait_for_selector("#outline [role=treeitem]")
    return page


def test_draws_the_tree_and_the_outline(browser, site):
    page = open_tree(browser, site)
    items = page.locator("#outline [role=treeitem] .nm").all_inner_texts()
    assert any("Genus A" in t for t in items) and any("Genus B" in t for t in items)
    assert page.locator("#svg .nd").count() >= 3 and page.locator("#svg .lk").count() >= 2
    assert page.inner_text("#status") == ""
    page.wait_for_selector("#svg image")  # a tip with room shows its photo once it has loaded
    assert page.errors == []
    page.close()


def test_a_click_selects_and_the_card_links_out(browser, site):
    page = open_tree(browser, site)
    page.locator("#outline .nm", has_text="Genus A").click()
    page.wait_for_selector("#card:not([hidden])")
    assert "Genus A" in page.inner_text("#card h2")
    assert "Share of all needing ID" in page.inner_text("#card")
    root = page.locator("#outline .tc").first
    assert root.inner_text().endswith("· 100%")
    assert "of all needing ID" in root.get_attribute("title")
    assert page.get_attribute("#card a:has-text('Show on map')", "href") == "map.html#taxa=900"
    ident = page.get_attribute("#card a:has-text('Help identify')", "href")
    assert "taxon_id=900" in ident and "place_id=" in ident
    assert "sel=900" in page.evaluate("location.hash")
    page.wait_for_selector("#card .kids .th img")  # the tips' photos, from the stubbed taxa API
    assert all(len(ids) <= 30 for ids in page.calls)
    page.go_back()  # back to the opening view, which selects the root
    page.wait_for_function("!document.querySelector('#card h2').textContent.includes('Genus A')")
    assert page.errors == []
    page.close()


def test_the_page_opens_on_the_root_selected(browser, site):
    page = open_tree(browser, site)
    page.wait_for_selector("#card:not([hidden])")
    assert "Biggest below" in page.inner_text("#card")
    assert " · " not in page.inner_text("#card p.muted")  # the root has no rank
    assert "picked" not in (page.get_attribute("#svg", "class") or "")  # nothing dims
    assert page.errors == []
    page.close()


def test_every_way_to_the_root_opens_its_card(browser, site):
    page = open_tree(browser, site, hash_="#sel=900")
    root = page.locator("#svg .nd").first.get_attribute("data-k")  # nodes draw from the root down
    for click in (
        lambda: page.locator(f'#svg .nd[data-k="{root}"]').click(),
        lambda: page.locator(f'#svg text.lb.in[data-k="{root}"]').click(),
        lambda: page.locator("#outline [role=treeitem] .nm").first.click(),
        lambda: page.click("#reset"),
    ):
        page.locator("#card .x").click()
        page.wait_for_selector("#card", state="hidden")
        click()
        page.wait_for_function("document.querySelector('#card h2')?.textContent === 'Family F'")
    page.set_viewport_size({"width": 390, "height": 800})  # on a phone it sits above the outline
    box, out = page.locator("#card").bounding_box(), page.locator("#side").bounding_box()
    assert box["y"] + box["height"] <= out["y"] + 1
    assert page.errors == []
    page.close()


def test_a_click_on_the_circle_selects_without_moving_it_and_esc_clears(browser, site):
    page = open_tree(browser, site)
    where = (
        "[...document.querySelectorAll('#svg .nd > circle:first-of-type')]"
        ".map(c => [c.getAttribute('cx'), c.getAttribute('cy')])"
    )
    page.evaluate(
        "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )  # resize redraw
    before = page.evaluate(where)
    k = page.evaluate(
        "[...document.querySelectorAll('#outline .nm')]"
        ".find(e => e.textContent.includes('Genus A')).closest('[data-k]').dataset.k"
    )
    page.locator(f'#svg .nd[data-k="{k}"]').click()
    page.wait_for_function("document.querySelector('#card h2').textContent.includes('Genus A')")
    assert "sel=900" in page.evaluate("location.hash")
    assert page.evaluate(where) == before
    assert "picked" in page.get_attribute("#svg", "class")
    assert page.locator(f'#svg .nd.hp[data-k="{k}"]').count() == 1
    page.keyboard.press("Escape")
    page.wait_for_selector("#card", state="hidden")
    assert "sel=" not in page.evaluate("location.hash")
    assert page.errors == []
    page.close()


def test_the_outline_works_by_keyboard(browser, site):
    page = open_tree(browser, site)
    first = page.locator("#outline [role=treeitem]").first
    assert first.get_attribute("tabindex") == "0"
    first.focus()
    page.keyboard.press("ArrowDown")
    key = page.evaluate("document.activeElement.dataset.k")
    assert key and key != first.get_attribute("data-k")
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.getAttribute('aria-selected')") == "true"
    assert page.errors == []
    page.close()


def test_a_hash_reopens_the_selection(browser, site):
    page = open_tree(browser, site, hash_="#sel=1003")
    page.wait_for_selector("#card:not([hidden])")
    assert "Taxon 3" in page.inner_text("#card h2")
    sel = page.locator("#outline [aria-selected=true] .nm").inner_text()
    assert "Taxon 3" in sel
    page.close()


def test_focusing_a_tip_shows_it_among_its_siblings(browser, site):
    page = open_tree(browser, site, hash_="#focus=1003")
    page.wait_for_selector("#card:not([hidden])")
    assert "Taxon 3" in page.inner_text("#card h2")
    assert "Genus B" in page.inner_text("#crumbs [aria-current]")
    assert page.locator("#svg .nd").count() >= 3
    assert page.errors == []
    page.close()


def test_a_phone_shows_the_outline_and_switches_to_the_radial_tree(browser, site):
    page = open_tree(browser, site, 390, 800)
    assert page.locator("#side").is_visible() and page.locator("#radial").is_hidden()
    page.click("#mode")
    page.wait_for_selector("#svg .nd")
    assert page.locator("#radial").is_visible() and page.locator("#side").is_hidden()
    assert page.errors == []
    page.close()


def test_the_page_names_the_missing_tree(browser, site):
    page = browser.new_page()
    old = gzip.compress(json.dumps([["x", "", 1, 0, -1]]).encode())  # no counts
    page.route("**/pool-taxa.bin*", lambda r: r.fulfill(body=old))
    page.goto(f"{site}/tree.html")
    page.wait_for_function("document.getElementById('status').textContent.includes('without')")
    page.close()


DRAWN = """() => { const b = [...document.querySelectorAll(
    '#svg .nd, #svg .br, #svg .lk, #svg .lb, #svg image')]
    .map(e => e.getBoundingClientRect()).filter(r => r.width || r.height);
  return b.length ? [Math.min(...b.map(r => r.left)), Math.min(...b.map(r => r.top)),
    Math.max(...b.map(r => r.right)), Math.max(...b.map(r => r.bottom))] : null; }"""
SPLIT_WORDS = """() => [...document.querySelectorAll('#outline .nm')].flatMap(e => {
  const out = [], rg = document.createRange();
  const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
  for (let n; (n = tw.nextNode());) for (const m of n.data.matchAll(/[^\\s-]+/g)) {
    rg.setStart(n, m.index); rg.setEnd(n, m.index + m[0].length);
    if (new Set([...rg.getClientRects()].map(r => Math.round(r.top))).size > 1) out.push(m[0]); }
  return out; })"""


@pytest.mark.parametrize(
    "w,query", [(1400, ""), (1150, ""), (1000, ""), (900, ""), (800, ""), (693, "?embed=1")]
)
def test_the_card_never_covers_the_circle_and_names_wrap_between_words(browser, site, w, query):
    page = open_tree(browser, site, w=w, hash_=query)
    assert page.locator("#radial").is_visible()  # Explore's 693px pane gets the circle
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    tree, card = page.evaluate(DRAWN), page.locator("#card").bounding_box()
    assert tree and card and card["height"] > 0
    x0, y0, x1, y1 = tree
    apart = (
        x1 <= card["x"]
        or x0 >= card["x"] + card["width"]
        or y1 <= card["y"]
        or y0 >= card["y"] + card["height"]
    )
    assert apart, (tree, card)
    assert page.evaluate(SPLIT_WORDS) == []
    assert page.errors == []
    page.close()


@pytest.mark.parametrize("col", [240, 340])
def test_a_deep_outline_keeps_one_line_per_row_at_any_width(browser, deep_site, col):
    page = open_tree(browser, deep_site, hash_="#sel=1009")
    page.add_style_tag(content=f"body{{grid-template-columns:{col}px minmax(0,1fr)!important}}")
    page.wait_for_selector('#outline [aria-level="10"][aria-selected="true"]')
    assert abs(page.locator("#side").bounding_box()["width"] - col) <= 2
    rows = page.eval_on_selector_all("#outline .row", "r => r.map(e => e.offsetHeight)")
    assert max(rows) <= 44, rows
    assert page.evaluate(SPLIT_WORDS) == []
    names = page.eval_on_selector_all("#outline .nm", "r => r.map(e => e.offsetWidth)")
    assert min(names) >= 40, names  # depth never squeezes a name to nothing
    assert page.errors == []
    page.close()


PINNED = """() => { const s = document.getElementById('side').getBoundingClientRect();
  return [0, 1, 2, 3, 4].map(k => document.elementFromPoint(s.right - 30, s.top + 28 * k + 14)
    ?.closest('[role=treeitem]')?.getAttribute('aria-level')); }"""


def test_a_deep_outline_pins_only_four_levels_and_follows_the_selection(browser, deep_site):
    page = open_tree(browser, deep_site, h=420, hash_="#sel=1009")
    page.wait_for_selector('#outline [aria-level="10"][aria-selected="true"]')
    page.eval_on_selector("#side", "s => s.scrollTop = 140")  # five levels scrolled past
    pinned = page.evaluate(PINNED)
    assert pinned[:4] == ["1", "2", "3", "4"] and pinned[4] != "5", pinned
    # a pick from the card brings its row out from under the four pinned rows
    page.eval_on_selector("#side", "s => s.scrollTop = s.scrollHeight")
    page.click("#card .kids.up button")
    page.wait_for_function("document.querySelector('#card h2').textContent.endsWith('ceae 8')")
    page.evaluate("new Promise(r => requestAnimationFrame(r))")
    side = page.locator("#side").bounding_box()
    row = page.locator('#outline [aria-selected="true"]>.row').bounding_box()
    top, bottom = side["y"] + 4 * 28 - 1, side["y"] + side["height"] - row["height"]
    assert top <= row["y"] <= bottom, (side, row)
    assert page.errors == []
    page.close()


def test_the_card_climbs_to_its_parent_or_any_taxon_above(browser, deep_site):
    page = open_tree(browser, deep_site, hash_="#sel=1009")
    page.wait_for_function("document.querySelector('#card h2')?.textContent === 'Taxon 9'")

    def shows(name):
        page.wait_for_function(f"document.querySelector('#card h2').textContent === '{name}'")

    assert page.inner_text("#card .path").endswith("Brachytheciaceae 7")  # Part of names the parent
    page.click("#card .kids.up button")
    shows("Brachytheciaceae 8")
    assert "Brachytheciaceae 3" not in page.inner_text("#card .path")  # the middle is folded
    page.click("#card .path button[aria-label='Show all taxa above']")
    page.locator("#card .path button", has_text="Brachytheciaceae 3").click()
    shows("Brachytheciaceae 3")
    assert "sel=703" in page.evaluate("location.hash")
    page.locator("#card .path button").first.click()
    shows("Brachytheciaceae 0")
    assert page.locator("#card .path, #card .kids.up").count() == 0  # the root has nothing above
    assert page.errors == []
    page.close()


RIM = """() => [...document.querySelectorAll('#svg text.lb:not(.in)')].map(e => [
  [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.data).join(''),
  e.querySelector('title').textContent, parseFloat(getComputedStyle(e).fontSize)])"""


@pytest.mark.parametrize("w", [693, 900, 1400])
def test_a_crowded_circle_shows_tip_names_whole_or_not_at_all(browser, wide_site, w):
    page = open_tree(browser, wide_site, w=w, h=700)
    page.wait_for_selector("#svg text.lb:not(.in)")
    rim = page.evaluate(RIM)
    assert rim
    for shown, title, size in rim:
        assert title.startswith(shown) and not shown.endswith("…"), (shown, title)
        assert size >= 9, (shown, size)
    assert page.errors == []
    page.close()


def test_the_root_is_life_and_the_group_cards_link_to_their_records(browser, life_site):
    page = open_tree(browser, life_site, hash_="#sel=0")
    page.wait_for_selector("#card:not([hidden])")
    assert page.inner_text("#card h2") == "Life" and "40" in page.inner_text("#card dl")
    assert page.locator("#card .body > p.muted").first.inner_text() != "Life"  # no repeat subtitle
    # each circle label's own text, less its hover title
    own = "[...e.childNodes].filter(n => n.nodeType === 3).map(n => n.data).join('')"
    names = page.eval_on_selector_all("#svg text.lb", f"es => es.map(e => {own})")
    assert "Unknown" in names and "Life" not in names  # the group's tip, named as its card and chip
    titles = page.eval_on_selector_all(
        "#svg text.lb", "es => es.map(e => e.querySelector('title').textContent)"
    )
    assert titles[names.index("Unknown")].startswith(
        "Unknown: 20 records need ID"
    )  # the hover title too
    page.close()
    page = open_tree(browser, life_site, hash_="#sel=48460")
    page.wait_for_selector("#card:not([hidden])")
    assert page.inner_text("#card h2") == "Unknown"
    assert page.inner_text("#card .body > p.muted") == (
        "Records not identified past Life, or with no taxon."
    )
    dl = page.locator("#card dd").all_inner_texts()
    assert dl[:4] == ["20", "50%", "5 (25%)", "5"]  # need an ID, share, only to Life, no taxon
    assert "No taxon" in page.inner_text("#card dl")
    ident = page.get_attribute("#card a:has-text('Help identify')", "href")
    assert "iconic_taxa=unknown" in ident and "taxon_id" not in ident  # not all of Life
    on_map = page.get_attribute("#card a:has-text('Show on map')", "href")
    assert on_map == "map.html#groups=Unknown"
    page.close()
    page = open_tree(browser, life_site, hash_="#sel=3")
    page.wait_for_selector("#card:not([hidden])")
    ident = page.get_attribute("#card a:has-text('Help identify')", "href")
    assert "iconic_taxa=Aves" in ident and "taxon_id" not in ident
    assert "No taxon" not in page.inner_text("#card dl")
    assert page.errors == []
    page.close()
