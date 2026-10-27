"""The photo space's Map of life in Chromium: view switch, hash, semantic zoom, look-alike file.

deck.gl is replaced by a recorder, as in test_embeddings_browser.py; the map's pixels are read
back from the canvas the page hands the bitmap layer.
"""

import functools
import gzip
import http.server
import json
import threading

import numpy as np
import pytest

from what_to_id.embeddings_page import build
from what_to_id.page_map import _decode_shard, encode_points, render_map
from what_to_id.split_page import build as build_split

from . import test_embeddings_browser as eb
from .atlas_index_fixture import write_fixture
from .embeddings_fixture import BBOX, pool_frame, write_layout

POOL_N, TOTAL, stub_inat = eb.POOL_N, eb.TOTAL, eb.stub_inat
browser = eb.browser  # the shared Chromium fixture

DECK_STUB = """
class Layer { constructor(p) { this.props = p; this.id = p.id; } }
window.deck = {
  Deck: class { constructor(p) { this.props = p; window.__deck = this; }
    setProps(p) { Object.assign(this.props, p); } },
  OrthographicView: Layer, ScatterplotLayer: Layer, PathLayer: Layer, BitmapLayer: Layer,
  TextLayer: Layer, LinearInterpolator: Layer,
  DataFilterExtension: class { initializeState() {} },
};"""
# taxon id -> [parent, latin, common, rank]
TREE = {
    1: [None, "Animalia", "Animals", "kingdom"],
    47126: [None, "Plantae", "Plants", "kingdom"],
    47120: [1, "Arthropoda", "", "phylum"],
    2: [1, "Chordata", "", "phylum"],
    47158: [47120, "Insecta", "Insects", "class"],
    3: [2, "Aves", "Birds", "class"],
    211194: [47126, "Tracheophyta", "", "phylum"],
    47124: [211194, "Magnoliopsida", "", "class"],
    47157: [47158, "Lepidoptera", "", "order"],
    47208: [47158, "Coleoptera", "", "order"],
    7251: [3, "Passeriformes", "", "order"],
    1000: [47157, "Vanessa cardui", "", "species"],
    1001: [47208, "Carabus nemoralis", "", "species"],
    1002: [7251, "Turdus migratorius", "", "species"],
    1003: [47124, "Achillea millefolium", "", "species"],
}
# blob: (centre, taxon, group, look-alike level, class agreement in twelfths)
BLOBS = [
    ((-25.0, -5.0), 1000, "Insecta", 0, 12),
    ((-8.0, -5.0), 1001, "Insecta", 3, 12),
    ((30.0, -5.0), 1002, "Aves", 2, 6),
    ((10.0, 22.0), 1003, "Plantae", 1, 12),
]
LEVEL = {"same family": 0, "same phylum": 3}
IDS = np.random.default_rng(1).choice(2**32 - 2, TOTAL, replace=False) + 1  # as the fixture
BLOB = np.arange(TOTAL) % len(BLOBS)
PLACED = np.arange(TOTAL) % 9 != 4  # unplaced records shift each later point's row in the file
BIRDS = IDS[:POOL_N][(BLOB == 2)[:POOL_N] & PLACED[:POOL_N]].tolist()


def lookalike_file(root, blobs, meta, value):
    """pool-lookalike.bin per its contract, rows in the shards' order, `value(id)` -> 4 nibbles."""
    a, b = [], []
    for s in meta["shards"]:
        name = s["file"].split("?")[0]
        for i in _decode_shard(gzip.decompress(blobs[name]), s["n"])["id"]:
            cls, order, fam, lev = value(int(i))
            a.append(cls | order << 4)
            b.append(fam | (lev + 2) << 4)
    (root / "pool-lookalike.bin").write_bytes(gzip.compress(bytes(a + b)))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("faiss")
    root = tmp_path_factory.mktemp("life-map-site")
    atlas = root / "atlas"
    write_fixture(atlas)
    ids, blob, placed = IDS, BLOB, PLACED
    rng = np.random.default_rng(6)
    centre = np.array([BLOBS[k][0] for k in blob])
    xy = centre + rng.normal(0, 2.5, (TOTAL, 2))
    assert (xy.min(0) > BBOX[:2]).all() and (xy.max(0) < BBOX[2:]).all()
    manifest = json.loads((atlas / "manifest.json").read_text())
    write_layout(atlas, {"layout-base-20261025": (ids[placed], xy[placed])}, manifest)
    pool = pool_frame(ids[:POOL_N])
    pool["taxon_id"] = [BLOBS[k][1] for k in blob[:POOL_N]]
    pool["iconic_taxon"] = [BLOBS[k][2] for k in blob[:POOL_N]]
    pool.loc[::2, "observed_on"] = "2025-01-15"  # older than the recent shard: two shards
    pool.loc[::2, "created_at"] = "2025-01-15T00:00:00Z"
    blobs, meta = encode_points(pool, TREE)
    assert len(meta["shards"]) == 2
    for name, data in blobs.items():
        (root / name).write_bytes(data)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    of = dict(zip(ids.tolist(), blob.tolist(), strict=True))
    lookalike_file(root, blobs, meta, lambda i: (BLOBS[of[i]][4], 12, 12, BLOBS[of[i]][3]))
    build(root, data_url="atlas/")
    build_split(root, map_url="embeddings.html")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def open_page(browser, site):
    pages = []

    def opener(hash_="", missing=False, path="embeddings.html?standalone=1"):
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        pages.append(page)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        stub_inat(page, None)
        page.route(
            "https://unpkg.com/**",
            lambda r: r.fulfill(body=DECK_STUB, content_type="text/javascript"),
        )
        if missing:
            page.route("**/pool-lookalike.bin*", lambda r: r.fulfill(status=404, body="no"))
        page.goto(f"{site}/{path}{hash_}")
        if path.startswith("embeddings"):
            page.wait_for_function("document.getElementById('lifebar').hidden === false")
        return page

    yield opener
    for page in pages:
        page.close()


def ids(page):
    return page.evaluate("__deck.props.layers.map(l => l.id)")


def drawn(page, look=False):
    """Wait for the map's bitmap, and return the hash's tokens."""
    page.wait_for_function("__deck.props.layers.some(l => l.id === 'life-img')")
    page.wait_for_function("document.getElementById('status').textContent === ''")
    if look:
        page.wait_for_function(
            "document.getElementById('vlook').getAttribute('aria-pressed') === 'true'"
        )
    return set(page.evaluate("location.hash.slice(1).split('&')"))


def pixel(page, x, y):
    """The bitmap's colour under layout point (x, y)."""
    return page.evaluate(
        """([x, y]) => { const l = __deck.props.layers.find(l => l.id === 'life-img'),
          c = l.props.image,
          b = l.props.bounds, i = Math.floor((x - b[0]) / (b[2] - b[0]) * c.width),
          j = Math.floor((b[3] - y) / (b[3] - b[1]) * c.height);
          return Array.from(c.getContext('2d').getImageData(i, j, 1, 1).data); }""",
        [x, y],
    )


def hover(page, x, y):
    page.evaluate(
        "([x, y]) => __deck.props.onHover({coordinate: [x, y], x: 50, y: 50, index: -1})", [x, y]
    )
    return page.locator(".ptip").evaluate("e => e.hidden ? '' : e.textContent")


def tokens(page):
    return set(page.evaluate("location.hash.slice(1).split('&')"))


def layer(page, id_):
    return page.evaluate(
        "id => { const l = __deck.props.layers.find(l => l.id === id);"
        " return {radius: l.props.getRadius, opacity: l.props.opacity}; }",
        id_,
    )


def test_the_map_of_life_is_the_view_and_look_alikes_survives_a_reload(open_page):
    page = open_page()
    drawn(page)
    assert not any(t.startswith("life=") for t in tokens(page))  # the default writes nothing
    assert page.locator("#vpts").count() == 0  # no Points view to switch to
    # far out with nothing held back the points draw as a faint texture over the full-strength map
    assert layer(page, "pts")["radius"] == 1 and layer(page, "life-img")["opacity"] == 1
    assert {"life-lbl", "life-lbl-k"} <= set(ids(page))
    labels = page.evaluate(
        "__deck.props.layers.find(l => l.id === 'life-lbl').props.data.map(d => d.text)"
    )
    assert {"Insecta", "Aves", "Magnoliopsida"} <= set(labels)
    clades = pixel(page, 30, -5)
    page.click("#vlook")
    assert "life=look" in drawn(page, look=True)
    blue = pixel(page, 30, -5)
    assert blue != clades and blue[2] > blue[0] + 60  # the look-alike ramp is blue
    legend = page.locator("#llegend").inner_text()
    assert "same class" in legend and "often photographed together (GloBI)" in legend
    page.reload()
    page.wait_for_function("document.getElementById('lifebar').hidden === false")
    assert "life=look" in drawn(page, look=True)
    assert pixel(page, 30, -5) == blue
    page.click("#vclade")
    page.wait_for_function("!location.hash.includes('life=')")
    assert pixel(page, 30, -5) == clades
    assert page.errors == []


def test_hover_reads_agreement_and_levels_from_the_file_in_both_shards(open_page):
    page = open_page("#life=look")
    drawn(page, look=True)
    birds = hover(page, 30, -5)
    assert birds.startswith("Aves (Birds)") and "50% of its photo neighbours are also Aves" in birds
    assert "100% same class" in birds
    beetles = hover(page, -8, -5)
    assert "Insecta (Insects)" in beetles and "100% same phylum" in beetles
    assert hover(page, 55, 30) == ""  # empty space says nothing


def zoom_by(page, dz):
    """Scroll-zoom as the controller does: a new view state, about the same centre."""
    page.evaluate(
        "dz => __deck.props.onViewStateChange({viewState: Object.assign({}, __deck.props.viewState,"
        " {zoom: __deck.props.viewState.zoom + dz})})",
        dz,
    )


def test_click_flies_to_a_clade_whose_map_draws_over_life_and_zooming_out_returns(open_page):
    page = open_page()
    drawn(page)
    count = page.locator("#count").inner_text()
    home = page.evaluate("__deck.props.viewState.zoom")
    page.evaluate("__deck.props.onClick({coordinate: [-25, -5], index: -1})")  # the Insecta region
    page.wait_for_function("location.hash.includes('clade=47158')")
    drawn(page)
    assert page.evaluate("__deck.props.viewState.zoom") > home  # the camera flew in
    assert page.evaluate("__deck.props.viewState.transitionDuration") > 0
    assert ids(page)[:2] == ["life-img", "life-zoom"]  # the world stays drawn around the clade
    labels = page.evaluate(
        "__deck.props.layers.filter(l => l.id === 'life-lbl')"
        ".flatMap(l => l.props.data.map(d => d.text))"
    )
    assert {"Lepidoptera", "Coleoptera"} <= set(labels)  # the labels follow the rank in view
    assert page.locator("#lup").count() == 0  # zooming out is the way back
    assert page.locator("#count").inner_text() == count  # zooming filters nothing
    opacity = "id => __deck.props.layers.find(l => l.id === id).props.opacity"
    assert page.evaluate(opacity, "life-zoom") == 1
    zoom_by(page, 8)  # far past 12 px a zoom cell: its blocks give way to the points and life map
    assert page.evaluate(opacity, "life-zoom") == 0 and page.evaluate(opacity, "life-img") > 0
    zoom_by(page, -8)
    zoom_by(page, -3)
    page.wait_for_function("!location.hash.includes('clade=')")
    assert page.locator("#lwhere").inner_text() == "All life" and "life-zoom" not in ids(page)


def test_a_clade_in_the_address_is_where_the_view_starts_and_show_only_picks_it(open_page):
    page = open_page("#clade=47158")
    drawn(page)
    page.wait_for_function("document.getElementById('lwhere').textContent.startsWith('Insecta')")
    count = page.locator("#count").inner_text()
    assert not any(t.startswith("taxa=") for t in tokens(page))  # a camera target, not a filter
    page.click("#lonly")
    page.wait_for_function("location.hash.includes('taxa=')")
    assert page.locator("#count").inner_text() != count
    assert "Insecta" in page.locator("#selbar").inner_text()


def test_without_the_file_the_map_still_draws_and_look_alikes_is_off(open_page):
    page = open_page("#life=look", missing=True)
    assert "life=look" not in drawn(page)
    assert page.locator("#vlook").is_disabled()
    assert "No nearest-photos file" in page.locator("#lnote").inner_text()
    text = hover(page, 30, -5)
    assert text.startswith("Aves (Birds)") and "photo neighbours" not in text


def test_split_view_hands_the_map_tokens_to_the_photo_frame(open_page):
    page = open_page("#life=look&clade=47158", path="explore.html?view=space")
    page.wait_for_function("document.querySelector('iframe#space')")
    src = page.evaluate("document.querySelector('iframe#space').src")
    assert "life=look" in src and "clade=47158" in src


def space_frame(page):
    page.wait_for_function(
        "document.querySelector('iframe#space')?.contentDocument?.getElementById('lifebar')"
        "?.hidden === false"
    )
    space = next(f for f in page.frames if "embed=1" in f.url)
    drawn(space)
    return space


def test_split_view_keeps_the_map_tokens_in_its_address_for_a_reload(open_page):
    page = open_page(path="explore.html?view=space")
    space = space_frame(page)
    space.click("#vlook")
    page.wait_for_function("location.hash.includes('life=look')")
    space.evaluate("__deck.props.onClick({coordinate: [-25, -5], index: -1})")
    page.wait_for_function("location.hash.includes('clade=47158')")
    page.reload()
    space = space_frame(page)
    drawn(space, look=True)
    assert space.locator("#lwhere").inner_text() == "Insecta (Insects)"
    assert {"life=look", "clade=47158"} <= tokens(page)
    space.click("#vclade")
    page.wait_for_function("!location.hash.includes('life=')")
    assert "clade=47158" in tokens(page)


def test_reset_undoes_a_clade_zoom_and_a_resize_refits_the_view(open_page):
    page = open_page()
    drawn(page)
    home = page.evaluate("__deck.props.viewState.zoom")
    page.evaluate("__deck.props.onClick({coordinate: [-25, -5], index: -1})")
    page.wait_for_function("location.hash.includes('clade=47158')")
    drawn(page)
    zoomed = page.evaluate("__deck.props.viewState.zoom")
    assert zoomed > home
    page.set_viewport_size({"width": 900, "height": 700})
    page.wait_for_function(f"__deck.props.viewState.zoom < {zoomed}")  # the clade is framed again
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_function(f"Math.abs(__deck.props.viewState.zoom - {zoomed}) < 1e-6")
    page.evaluate("postMessage({type: 'wtid-reset'}, location.origin)")  # the map's Reset all
    page.wait_for_function("!location.hash.includes('clade=')")
    page.wait_for_function(f"Math.abs(__deck.props.viewState.zoom - {home}) < 1e-6")
    assert page.locator("#lwhere").inner_text() == "All life"


def test_a_subset_from_the_tree_draws_over_the_dimmed_map_and_its_points_open_records(open_page):
    page = open_page(path="explore.html?view=space")
    space = space_frame(page)
    page.evaluate(
        "window.__records = []; addEventListener('message', e => {"
        " if (e.data && e.data.type === 'wtid-record') __records.push(e.data.id); })"
    )
    # the split view hands the frame the tree's pick as it does: the ids under the taxon
    page.evaluate(
        "ids => document.querySelector('iframe#space').contentWindow.postMessage("
        "{type: 'wtid-subset', ids, label: 'Aves'}, location.origin)",
        BIRDS,
    )
    space.wait_for_function("__deck.props.layers.find(l => l.id === 'pts').props.getRadius === 1.5")
    assert layer(space, "life-img")["opacity"] < 1  # the map dims under the subset
    assert len(set(pixel(space, 30, -5)[:3])) == 1  # and turns grey, so the points are the colour
    assert "few" not in ids(space)
    assert (
        space.locator("#count").inner_text() == f"{len(BIRDS):,} shown of {PLACED[:POOL_N].sum():,}"
    )
    row = space.evaluate(
        """() => { const D = __deck.props.layers.find(l => l.id === 'pts').props.data,
          p = D.attributes.getPosition.value, k = D.attributes.getFilterCategory.value;
          for (let i = 0; i < D.length; i++) if (k[3 * i + 2] && p[2 * i] > 22) return i;
          return -1; }"""
    )
    assert row >= 0
    space.evaluate("i => __deck.props.onClick({index: i, layer: {id: 'pts'}})", row)
    space.wait_for_selector("#card:not([hidden])")
    page.wait_for_function("__records.length > 0")
    assert page.evaluate("__records[0]") in BIRDS
    # a click on the map away from any point still zooms into the clade under it
    space.evaluate("__deck.props.onClick({coordinate: [-25, -5], index: -1})")
    space.wait_for_function("location.hash.includes('clade=47158')")
    # a subset of two is ringed, so it is found on the map
    page.evaluate(
        "ids => document.querySelector('iframe#space').contentWindow.postMessage("
        "{type: 'wtid-subset', ids, label: 'two'}, location.origin)",
        BIRDS[:2],
    )
    space.wait_for_function(
        "__deck.props.layers.find(l => l.id === 'few')?.props.data.length === 2"
    )


def label_texts(page):
    """Label texts by layer id, for the map's label layers (those ending -f are the faded ones)."""
    return page.evaluate(
        """() => Object.fromEntries(__deck.props.layers.filter(l => l.id.startsWith('life-lbl'))
          .map(l => [l.id, {t: l.props.data.map(d => d.text), a: l.props.getColor[3],
            o: l.props.outlineColor[3]}]))"""
    )


def test_labels_outside_the_selection_fade_and_those_around_it_stay(open_page):
    page = open_page(path="explore.html?view=space")
    space = space_frame(page)
    space.wait_for_function("__deck.props.layers.some(l => l.id === 'life-lbl')")
    assert not [i for i in label_texts(space) if i.endswith("-f")]  # no filter: nothing fades
    page.evaluate(
        "ids => document.querySelector('iframe#space').contentWindow.postMessage("
        "{type: 'wtid-subset', ids, label: 'Aves'}, location.origin)",
        BIRDS,
    )
    space.wait_for_function("__deck.props.layers.some(l => l.id === 'life-lbl-f')")
    got = label_texts(space)
    faded = {t for i, v in got.items() if i.endswith("-f") for t in v["t"]}
    kept = {t for i, v in got.items() if not i.endswith("-f") for t in v["t"]}
    assert "Insecta" in faded and "Insecta" not in kept
    assert "Aves" in kept and "Aves" not in faded
    assert got["life-lbl-f"]["a"] < 100 and got["life-lbl-f"]["o"] < 100
    assert got["life-lbl"]["a"] > 200 and got["life-lbl"]["o"] > 200
