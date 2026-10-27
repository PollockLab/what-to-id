"""The Identify page in Chromium: a selection keeps what the map keeps, the cards follow the levels
file, and the photos come 200 ids to a request. iNaturalist is stubbed."""

import functools
import http.server
import threading

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_identify, pool_levels
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.page_map import decode_points, encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_page_nav import FORBIDDEN

browser = eb.browser
N = 2100
LOOKS = ["Bombus a", "Bombus b", "Apis c"]
LABELS = ["Clear matches", "Close calls", page_identify.NARROW_LABEL, "Odd shots"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("identify-site")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    blobs, meta = encode_points(pool_frame(ids), TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    pts = decode_points(blobs, meta)
    i = np.arange(N)
    scored = pd.DataFrame(
        {
            "id": pts["id"].to_numpy(np.int64),
            "taxon_id": pts["taxon_id"].to_numpy(np.int64),
            "level": np.where(i % 6 == 0, 0, 1 + (i * 7) % 4).astype("int8"),
            "score": np.random.default_rng(2).normal(size=N).astype("float32"),
            "score2": np.float32(0),
            "looks_like": pd.Series([LOOKS[k % 3] for k in i], dtype="category"),
        }
    )[list(IDENTIFY_COLUMNS)]
    scored.to_parquet(root / "identify.parquet")
    pool_levels.build(root, parquet=root / "identify.parquet")
    page_identify.build(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pts = pts.assign(level=scored["level"].to_numpy())
    yield f"http://127.0.0.1:{server.server_port}", pts
    server.shutdown()


def open_identify(browser, base, hash_=""):
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    # the header's links to the site's other pages are not in this fixture's site
    page.on(
        "response",
        lambda r: page.errors.append(r.url) if r.status >= 400 and ".html" not in r.url else None,
    )
    page.calls = eb.stub_inat(page, None)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify")
    return page


def ids(page):
    return sorted(page.evaluate("__identify.ids()"))


def day(pts):
    return pd.to_datetime(pts["observed_on"])


# (hash, the map's verdict per record in pandas): a picked group beside a taxon adds to it, a
# left-out one subtracts, and the dates cut what is left
CASES = [
    ("", lambda p: p["id"] > 0),
    ("#groups=Aves", lambda p: p["iconic_taxon"] == "Aves"),
    ("#groups=-Aves", lambda p: p["iconic_taxon"] != "Aves"),
    ("#taxa=900", lambda p: p["taxon_id"].isin([1000, 1001, 1002])),
    (
        "#groups=Aves&taxa=900",
        lambda p: p["taxon_id"].isin([1000, 1001, 1002]) | (p["iconic_taxon"] == "Aves"),
    ),
    (
        "#groups=-Aves&taxa=900",
        lambda p: p["taxon_id"].isin([1000, 1001, 1002]) & (p["iconic_taxon"] != "Aves"),
    ),
    ("#from=2026-08-10&to=2026-09-10", lambda p: day(p).between("2026-08-10", "2026-09-10")),
    ("#months=9", lambda p: day(p).dt.month == 9),
]


@pytest.mark.parametrize(("hash_", "verdict"), CASES, ids=[c[0] or "all" for c in CASES])
def test_a_selection_keeps_exactly_the_records_the_map_filter_keeps(browser, site, hash_, verdict):
    base, pts = site
    page = open_identify(browser, base, hash_)
    want = sorted(pts["id"][verdict(pts)].tolist())
    assert want and ids(page) == want
    assert page.errors == []


def test_the_area_and_the_lasso_narrow_the_same_ids_as_the_map_keeps(browser, site):
    base, pts = site
    page = open_identify(browser, base)
    west = float(np.median(pts["lon"]))
    ring = [west, 48, -122, 48, -122, 50, west, 50]  # the east half of the points
    area = page.evaluate("r => MapArea.encode([r])", ring)
    page.evaluate("a => postMessage({type: 'wtid-area', area: a}, location.origin)", area)
    page.wait_for_function("__identify.ids().length < 2100")
    inside = pts["lon"] > west
    assert ids(page) == sorted(pts["id"][inside].tolist())
    lasso = sorted(pts["id"][inside].tolist())[::3] + [1]  # one id the pool does not hold
    page.evaluate(
        "l => postMessage({type: 'wtid-keep', ids: new Uint32Array(l)}, location.origin)", lasso
    )
    page.wait_for_function(f"__identify.ids().length === {len(lasso) - 1}")
    assert ids(page) == sorted(set(lasso) - {1})
    page.evaluate("postMessage({type: 'wtid-keep', ids: null}, location.origin)")
    page.wait_for_function(f"__identify.ids().length === {int(inside.sum())}")
    assert page.errors == []


def test_cards_group_by_level_with_a_few_per_species_and_photos_in_batches(browser, site):
    base, pts = site
    page = open_identify(browser, base)
    page.wait_for_function("document.querySelectorAll('.card .ph img').length > 0")
    assert [h.inner_text() for h in page.locator("#sections h2").all()] == LABELS
    shown = page.evaluate("__identify.view()")
    level = dict(zip(pts["id"], pts["level"], strict=True))
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    for lv in (1, 2, 3, 4):
        assert shown[lv] and all(level[i] == lv for i in shown[lv])
        counts = pd.Series([taxon[i] for i in shown[lv]]).value_counts()
        assert counts.max() <= 3 and len(counts) == 7  # a few of each of the seven species
    assert page.locator("#lv1 .card").count() == 12
    assert all(len(c) <= 200 for c in page.calls) and page.calls
    before = len(page.calls)
    page.locator("#lv1 button.more").click()
    page.wait_for_function("document.querySelectorAll('#lv1 .card').length === 21")
    assert len(page.calls) == before + 1 and len(page.calls[-1]) == 9
    text = page.locator("#lv3 .card .name").first.inner_text()
    assert ", probably " in text and text.split(", probably ")[1].split()[0] in {"Bombus", "Apis"}
    assert "Often confused with" in page.locator("#lv2 .card .name").first.inner_text()
    assert page.locator("#sections").inner_text().count("Often confused with") >= 1
    body = page.inner_text("body").lower()
    assert not any(word in body for word in FORBIDDEN)
    assert "no level yet" in body
    assert page.errors == []


def test_the_selection_changes_what_the_cards_show(browser, site):
    base, pts = site
    page = open_identify(browser, base, "#groups=Aves")
    page.wait_for_function("document.querySelectorAll('.card').length > 0")
    shown = {i for lv in page.evaluate("__identify.view()") if lv for i in lv}
    assert shown <= set(pts["id"][pts["iconic_taxon"] == "Aves"])
    page.evaluate("location.hash = ''")
    page.wait_for_function("__identify.ids().length === 2100")
    assert page.errors == []


def test_the_page_names_the_narrowing_group_from_one_constant_and_has_the_header():
    html = page_identify.render()
    assert html.count(page_identify.NARROW_LABEL) == 1  # only in the config the constant fills
    assert "<nav" in html
    assert not [w for w in FORBIDDEN if w in html.lower()]
