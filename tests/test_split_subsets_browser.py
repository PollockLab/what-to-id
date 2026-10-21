"""The split page's relays in Chromium: the map's area into the photo space, the photo space's
lasso into the map, and the tree's taxon into the map. The fixture loads the photo space in both
frames, so these pin the relay and the photo space's ends; map.js's is in test_map_projects.py."""

import pytest

from . import test_embeddings_browser as eb
from .test_embeddings_browser import POOL_N, ready, shown, stub_inat
from .test_tree_browser import stub_taxa

browser, site, open_page = eb.browser, eb.site, eb.open_page

RING = "[[-123.6,48,-123,48,-123,50,-123.6,50]]"


@pytest.fixture
def split(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html?view=side")
    page.wait_for_function(
        "[...document.querySelectorAll('iframe')].every(f =>"
        " f.contentDocument.getElementById('status').textContent === '')"
    )
    frames = [f for f in page.frames if "embed=1" in f.url]
    assert len(frames) == 2
    yield page, frames
    page.close()


def test_the_maps_area_subsets_the_photo_space_which_cannot_clear_it(split, open_page):
    page, (left, right) = split
    h = left.evaluate(f"MapArea.encode({RING})")
    west = open_page(f"#area={h}")
    ready(west)
    left.evaluate("h => parent.postMessage({type: 'wtid-area', area: h}, location.origin)", h)
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert shown(right) == shown(west) < POOL_N
    assert shown(left) == POOL_N  # the sender keeps its own area
    chip = right.locator("#selbar li", has_text="Map area")
    assert chip.count() == 1 and chip.locator("button.x").count() == 0
    left.evaluate("parent.postMessage({type: 'wtid-area', area: ''}, location.origin)")
    right.wait_for_function(
        f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert right.locator("#selbar li").count() == 0
    assert page.errors == []


def test_the_maps_view_subsets_the_photo_space_which_cannot_clear_it(split, open_page):
    page, (left, right) = split
    h = left.evaluate(f"MapArea.encode({RING})")
    west = open_page(f"#area={h}")
    ready(west)
    left.evaluate("h => parent.postMessage({type: 'wtid-view', area: h}, location.origin)", h)
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert shown(right) == shown(west) < POOL_N
    chip = right.locator("#selbar li", has_text="Map view")
    assert chip.count() == 1 and chip.locator("button.x").count() == 0
    left.evaluate("parent.postMessage({type: 'wtid-view', area: ''}, location.origin)")
    right.wait_for_function(
        f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert right.locator("#selbar li").count() == 0
    assert page.errors == []


def test_the_maps_view_and_area_intersect(split, open_page):
    page, (left, right) = split
    small = "[[-123.4,48.5,-123.1,48.5,-123.1,49.5,-123.4,49.5]]"
    h, v = left.evaluate(f"[MapArea.encode({RING}), MapArea.encode({small})]")
    west = open_page(f"#area={v}")
    ready(west)
    left.evaluate(
        "([h, v]) => {parent.postMessage({type: 'wtid-area', area: h}, location.origin);"
        "parent.postMessage({type: 'wtid-view', area: v}, location.origin);}",
        [h, v],
    )
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert shown(right) == shown(west) < POOL_N
    assert page.errors == []


def _view(left, area):
    left.evaluate("a => parent.postMessage({type: 'wtid-view', area: a}, location.origin)", area)


def test_the_view_chip_and_bar_wording_follow_a_visible_map(split):
    page, (left, right) = split
    _view(left, left.evaluate(f"MapArea.encode({RING})"))
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    page.wait_for_function(
        "document.getElementById('counts').textContent.includes('in photo space, in map view')"
    )
    page.click("[data-v='space']")  # the hidden map's view masks nothing
    right.wait_for_function(
        f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert right.locator("#selbar li").count() == 0
    assert "map view" not in page.inner_text("#counts")
    page.click("[data-v='side']")
    right.wait_for_function("document.querySelectorAll('#selbar li').length === 1")
    assert right.locator("#selbar li", has_text="Map view").count() == 1
    page.wait_for_function("document.getElementById('counts').textContent.includes('in map view')")
    assert page.errors == []


def test_a_view_holding_all_the_data_masks_nothing_and_has_no_chip(split):
    page, (left, right) = split
    _view(left, left.evaluate("MapArea.encode([[-180,-85,180,-85,180,85,-180,85]])"))
    page.wait_for_timeout(500)
    assert shown(right) == POOL_N and right.locator("#selbar li").count() == 0
    assert page.errors == []


def test_a_removed_space_takes_its_lasso_off_the_map(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    # the stub map is a photo space that ignores ids, so record what each frame is sent
    page.add_init_script(
        "window.__keep = []; addEventListener('message', e => { if (e.data && e.data.type ==="
        " 'wtid-keep') __keep.push(e.data.ids && Array.from(e.data.ids)); })"
    )
    page.goto(f"{base}/split.html?view=space")
    ok = (
        "document.querySelector('#%s')?.contentDocument?.getElementById('status')?.textContent===''"
    )
    page.wait_for_function(ok % "space")
    space = next(f for f in page.frames if "embed=1" in f.url)
    space.evaluate(
        "parent.postMessage({type: 'wtid-keep', ids: new Uint32Array([0, 1, 2])}, location.origin)"
    )
    page.click("[data-v='map']")
    page.wait_for_function(ok % "map")
    page.click("[data-v='space']")
    page.wait_for_function(ok % "space")
    page.click("[data-v='map']")  # a new map must not inherit the lasso of the removed space
    page.wait_for_function(ok % "map")
    frame = next(f for f in page.frames if "embed=1" in f.url)
    assert all(k is None for k in frame.evaluate("__keep"))
    assert page.errors == []
    page.close()


def test_an_area_sent_before_the_frame_loads_still_arrives(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html?view=map")
    joined = (
        "(f => f && f.contentDocument && f.contentDocument.getElementById('status') &&"
        " f.contentDocument.getElementById('status').textContent === '')"
        "(document.querySelector('%s'))"
    )
    page.wait_for_function(joined % "#map")
    left = next(f for f in page.frames if "embed=1" in f.url)
    h = left.evaluate(f"MapArea.encode({RING})")
    left.evaluate("h => parent.postMessage({type: 'wtid-area', area: h}, location.origin)", h)
    page.click("[data-v='side']")  # the second frame is created now, after the message
    page.wait_for_function(joined % "#space")
    right = next(f for f in page.frames if "embed=1" in f.url and f is not left)
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert 0 < shown(right) < POOL_N
    assert page.errors == []
    page.close()


LASSO = [(10, 10), (50, 10), (50, 30), (10, 30)]  # plot pixels; the deck stub unprojects 1:1
INSIDE = """() => {
  const l = __deck.props.layers.find(x => x.id === 'pts'), a = l.props.data.attributes,
    pos = a.getPosition.value, c = a.getFilterCategory.value;
  let inside = 0, bad = 0;
  for (let i = 0; i < l.props.data.length; i++) {
    const ok = pos[2*i] > 10 && pos[2*i] < 50 && pos[2*i+1] > 10 && pos[2*i+1] < 30;
    inside += ok; if (ok !== !!c[3*i+2]) bad++; }
  return {inside, bad, ring: !!__deck.props.layers.find(x => x.id === 'lasso')}; }"""


def test_a_shift_drag_lasso_keeps_the_dots_inside_and_sends_their_ids_to_the_map(split):
    page, (left, right) = split
    page.evaluate(
        "window.__keep = []; addEventListener('message', e => { if (e.data && e.data.type ==="
        " 'wtid-keep') __keep.push(e.data.ids && Array.from(e.data.ids)); })"
    )
    box = left.locator("#plot").bounding_box()
    page.keyboard.down("Shift")
    page.mouse.move(box["x"] + LASSO[0][0], box["y"] + LASSO[0][1])
    page.mouse.down()
    for x, y in LASSO[1:]:
        page.mouse.move(box["x"] + x, box["y"] + y)
    page.mouse.up()
    page.keyboard.up("Shift")
    page.wait_for_function("__keep.length === 1")
    got = left.evaluate(INSIDE)
    assert got["bad"] == 0 and got["ring"] and 0 < got["inside"] < POOL_N
    assert shown(left) == got["inside"] == len(page.evaluate("__keep[0]"))
    assert shown(right) == POOL_N  # a photo space ignores the ids; only the map applies them
    chips = "[...document.querySelectorAll('#selbar li')].map(l => l.textContent)"
    assert left.evaluate(chips) == ["Lasso×"]
    assert left.locator("#lclear").is_visible()
    left.click("#lclear")
    page.wait_for_function("__keep.length === 2")
    assert page.evaluate("__keep[1]") is None
    assert shown(left) == POOL_N and not left.evaluate(INSIDE)["ring"]
    assert left.locator("#lclear").is_hidden()
    assert page.errors == []


def test_the_maps_projects_subset_the_photo_space_which_cannot_clear_them(split, site):
    page, (left, right) = split
    _, _, pool, _ = site
    ids = sorted(pool)[:7]
    left.evaluate(
        "ids => parent.postMessage({type: 'wtid-projects', ids: Uint32Array.from(ids)},"
        " location.origin)",
        ids,
    )
    right.wait_for_function("document.getElementById('count').textContent.startsWith('7 ')")
    assert shown(left) == POOL_N  # the sender is the map's stand-in here
    chip = right.locator("#selbar li", has_text="Map projects")
    assert chip.count() == 1 and chip.locator("button.x").count() == 0
    assert "map only" in chip.inner_text()
    left.evaluate("parent.postMessage({type: 'wtid-projects', ids: null}, location.origin)")
    right.wait_for_function(
        f"document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert right.locator("#selbar li").count() == 0
    assert page.errors == []


KEEP = (
    "window.__keep = []; addEventListener('message', e => { if (e.data && e.data.type ==="
    " 'wtid-keep') __keep.push({ids: e.data.ids && Array.from(e.data.ids), view: e.data.view}); })"
)
IN_VIEW = """() => {
  const vs = __deck.props.viewState, k = 2 ** vs.zoom, box = document.getElementById('plot'),
    hw = box.clientWidth / 2 / k, hh = box.clientHeight / 2 / k,
    pos = __deck.props.layers.find(x => x.id === 'pts').props.data.attributes.getPosition.value;
  let n = 0;
  for (let i = 0; i < pos.length / 2; i++)
    n += Math.abs(pos[2*i] - vs.target[0]) <= hw && Math.abs(pos[2*i+1] - vs.target[1]) <= hh;
  return n; }"""


def test_the_photo_views_region_narrows_the_map_and_the_maps_reset_shows_it_all(split):
    page, (left, right) = split
    page.evaluate(KEEP)
    right.evaluate(
        "() => { const vs = __deck.props.viewState;"
        " __deck.props.onViewStateChange({viewState: {...vs, zoom: vs.zoom + 2}}); }"
    )
    page.wait_for_function("__keep.length === 1")
    got = page.evaluate("__keep[0]")
    assert got["view"] and 0 < len(got["ids"]) == right.evaluate(IN_VIEW) < POOL_N
    assert shown(right) == POOL_N  # its own view narrows only the map
    page.wait_for_function(
        "document.getElementById('counts').textContent.includes('on map, in photo view')"
    )
    left.evaluate("parent.postMessage({type: 'wtid-reset'}, location.origin)")
    page.wait_for_function("__keep.length === 2")
    assert page.evaluate("__keep[1]") == {"ids": None, "view": False}
    page.wait_for_function("!document.getElementById('counts').textContent.includes('photo view')")
    assert page.errors == []


def test_a_hidden_photo_space_takes_its_views_cut_off_the_map(split):
    page, (left, right) = split
    page.evaluate(KEEP)
    right.evaluate(
        "() => { const vs = __deck.props.viewState;"
        " __deck.props.onViewStateChange({viewState: {...vs, zoom: vs.zoom + 2}}); }"
    )
    page.wait_for_function("__keep.length === 1")
    page.click("[data-v='map']")
    page.wait_for_function("__keep.length === 2")
    assert page.evaluate("__keep[1]") == {"ids": None, "view": False}
    assert page.errors == []


def test_the_split_opens_on_the_tree_whose_selection_is_the_maps_and_back(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    stub_taxa(page)
    page.goto(f"{base}/split.html")
    tree, left = page.frame_locator("#tree"), page.frame_locator("#map")
    tree.locator("#outline .nm", has_text="Genus A").click()
    page.wait_for_function("location.hash.includes('taxa=900')")
    left.locator("#selbar li").first.wait_for()
    on = tree.locator("#outline [aria-selected=true] > .row .nm", has_text="Genus A")
    page.evaluate("location.hash = ''")
    on.wait_for(state="detached")
    page.evaluate("location.hash = '#taxa=900'")  # as when the map picks it
    on.wait_for()
    assert page.errors == []
    page.close()


def test_going_back_in_the_tree_keeps_its_selection_the_maps(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    stub_taxa(page)
    page.goto(f"{base}/split.html")
    tree = page.frame_locator("#tree")
    tree.locator("#outline .nm", has_text="Genus A").click()
    page.wait_for_function("location.hash.includes('taxa=900')")
    tree.locator("#outline .nm", has_text="Genus B").dispatch_event("click")  # under the card
    page.wait_for_function("location.hash.includes('taxa=901')")
    frame = next(f for f in page.frames if "tree.html" in f.url)
    frame.evaluate("history.back()")  # its own hash holds no filter, which must not clear the pick
    page.wait_for_function("location.hash.includes('taxa=900')")
    page.wait_for_timeout(500)
    on = tree.locator("#outline [aria-selected=true] > .row .nm")
    assert on.inner_text() == "Genus A" and "taxa=900" in page.evaluate("location.hash")
    assert page.errors == []
    page.close()


def test_a_group_the_map_leaves_out_leaves_the_tree_and_its_counts(browser, site):
    # the fixture's taxa hang from no life group, so every record counts as Unknown
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    stub_taxa(page)
    page.goto(f"{base}/split.html")
    tree = page.frame_locator("#tree")
    root = tree.locator("#outline .tc").first
    root.wait_for()
    before = root.inner_text()
    assert not before.startswith("0 ")
    for sel, want in (("groups=-Unknown", "0 "), ("groups=-Aves", before), ("", before)):
        page.evaluate(
            "s => document.querySelector('#tree').contentWindow.postMessage("
            "{type: 'wtid-selection', sel: s}, location.origin)",
            sel,
        )
        page.wait_for_timeout(200)
        assert root.inner_text().startswith(want), (sel, root.inner_text())
    assert page.errors == []
    page.close()


def _tree_page(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    stub_taxa(page)
    page.goto(f"{base}/split.html")
    return page, page.frame_locator("#tree")


def test_a_taxon_the_map_leaves_out_leaves_the_tree_with_everything_below_it(browser, site):
    page, tree = _tree_page(browser, site)
    root = tree.locator("#outline .tc").first
    root.wait_for()
    before = root.inner_text().split()[0]
    page.evaluate(
        "s => document.querySelector('#tree').contentWindow.postMessage("
        "{type: 'wtid-selection', sel: s}, location.origin)",
        "taxa=-900",
    )
    page.wait_for_function(
        "b => document.querySelector('#tree').contentDocument.querySelector('#outline .tc')"
        ".textContent.split(' ')[0] !== b",
        arg=before,
    )
    assert tree.locator("#outline .nm", has_text="Genus A").count() == 0
    assert page.errors == []
    page.close()


def test_a_card_leaves_its_taxon_out_of_the_tree_and_the_map(browser, site):
    page, tree = _tree_page(browser, site)
    tree.locator("#outline .nm", has_text="Genus A").click()
    page.wait_for_function("location.hash.includes('taxa=900')")
    tree.locator("#card button", has_text="Leave out").click()
    page.wait_for_function("/taxa=-900/.test(location.hash) && !/taxa=900/.test(location.hash)")
    tree.locator("#outline .nm", has_text="Genus A").wait_for(state="detached")
    assert tree.locator("#outline .nm", has_text="Genus B").count() == 1
    assert tree.locator("#card h2").count() == 1  # the card moves up instead of vanishing
    assert page.errors == []
    page.close()


def test_the_maps_counts_reach_the_tree_and_replace_its_own(browser, site):
    page, tree = _tree_page(browser, site)
    root = tree.locator("#outline .tc").first
    root.wait_for()
    before = root.inner_text().split()[0]
    left = next(f for f in page.frames if "embeddings.html" in f.url)
    left.evaluate("parent.postMessage({type: 'wtid-counts', own: [], total: 7}, location.origin)")
    tree.locator("#outline .tc", has_text="7 ·").first.wait_for()
    assert root.inner_text().split()[0] == "7" != before
    assert page.errors == []
    page.close()
