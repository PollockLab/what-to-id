"""The Identify pane of the split page in Chromium: open by default beside the map, first on a
phone, and following the map's group chips, area and lasso and the photo search. The map is a
photo space here (the real one needs a CDN), as in the other split tests."""

import numpy as np
import pandas as pd
import pytest

from what_to_id import pool_levels, split_page
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.page_identify import build as build_identify
from what_to_id.page_map import decode_points, encode_points

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_embeddings_browser import POOL_N, TOTAL, stub_inat

browser, site = eb.browser, eb.site


@pytest.fixture(scope="module")
def pts(site, tmp_path_factory):
    """The photo-space site gains an Identify page over its pool; the pool's points come back."""
    # the newest embeddings-site dir is the one `site` just made for this module
    root = max(
        tmp_path_factory.getbasetemp().glob("embeddings-site*"), key=lambda p: p.stat().st_mtime
    )
    ids = np.random.default_rng(1).choice(2**32 - 2, TOTAL, replace=False) + 1
    blobs, meta = encode_points(pool_frame(ids[:POOL_N]), TREE)
    pts = decode_points(blobs, meta)
    pd.DataFrame(
        {
            "id": pts["id"].to_numpy(np.int64),
            "taxon_id": pts["taxon_id"].to_numpy(np.int64),
            "level": (1 + np.arange(POOL_N) % 4).astype("int8"),
            "score": np.random.default_rng(2).normal(size=POOL_N).astype("float32"),
            "score2": np.float32(0),
            "looks_like": pd.Series(["Bombus a"] * POOL_N, dtype="category"),
        }
    )[list(IDENTIFY_COLUMNS)].to_parquet(root / "identify.parquet")
    pool_levels.build(root, parquet=root / "identify.parquet")
    build_identify(root)
    split_page.build(root, map_url="embeddings.html")  # offers Identify now it exists
    return pts


def test_the_split_page_offers_identify_only_once_it_is_built(tmp_path):
    html = split_page.build(tmp_path).read_text()
    assert 'data-p="identify"' not in html and "identify:null" in html
    assert "['identify','map']" in html  # the default only applies when FILES keeps identify
    (tmp_path / "identify.html").write_text("")
    html = split_page.build(tmp_path).read_text()
    assert 'data-p="identify"' in html and 'identify:"identify.html"' in html


def explore(browser, base, query="", width=1280):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/explore.html{query}")
    return page


def frame_of(page, name):
    page.wait_for_function(
        f"document.getElementById('{name}')?.contentDocument?.readyState === 'complete'"
    )
    return next(f for f in page.frames if f.url.split("?")[0].endswith(f"/{name_file[name]}"))


name_file = {"identify": "identify.html", "map": "embeddings.html"}


def ids(frame):
    frame.wait_for_function("window.__identify")
    return sorted(frame.evaluate("__identify.ids()"))


def test_the_default_view_is_identify_beside_the_map_and_the_switch_lists_four_panes(
    browser, site, pts
):
    page = explore(browser, site[0])
    frame_of(page, "identify")
    frame_of(page, "map")
    shown = page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.id)")
    assert shown == ["identify", "map"]
    assert page.locator("#xbar .seg button").all_inner_texts() == [
        "Identify",
        "Map",
        "Photo space",
        "Taxonomy",
    ]
    assert page.locator("[data-p=identify]").get_attribute("aria-pressed") == "true"
    assert page.locator("[data-p=space]").get_attribute("aria-pressed") == "false"
    page.wait_for_function("/to identify/.test(document.getElementById('counts').textContent)")
    assert page.errors == []
    page.close()


def test_old_views_still_open_their_panes_and_each_pane_toggles(browser, site, pts):
    page = explore(browser, site[0], "?view=map-space")
    frame_of(page, "map")
    assert page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.id)") == [
        "map",
        "space",
    ]
    page.click("[data-p=identify]")
    frame_of(page, "identify")
    assert page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.id)") == [
        "identify",
        "map",
        "space",
    ]
    page.click("[data-p=identify]")
    page.wait_for_function("document.getElementById('identify').hidden")
    assert page.errors == []
    page.close()


def test_a_group_picked_on_the_map_narrows_identify_to_the_map_filters_ids(browser, site, pts):
    page = explore(browser, site[0])
    ident = frame_of(page, "identify")
    assert len(ids(ident)) == POOL_N
    page.frame_locator("#map").locator("#groups button[data-g='0']").click()  # Aves
    ident.wait_for_function(f"__identify.ids().length < {POOL_N}")
    assert ids(ident) == sorted(pts["id"][pts["iconic_taxon"] == "Aves"].tolist())
    assert "groups=Aves" in page.evaluate("location.hash")
    assert page.errors == []
    page.close()


def test_the_hash_selection_reaches_identify_on_load(browser, site, pts):
    page = explore(browser, site[0], "#groups=Aves")
    ident = frame_of(page, "identify")
    assert ids(ident) == sorted(pts["id"][pts["iconic_taxon"] == "Aves"].tolist())
    page.close()


def test_the_maps_area_and_a_lasso_reach_identify(browser, site, pts):
    page = explore(browser, site[0])
    ident, left = frame_of(page, "identify"), frame_of(page, "map")
    west = float(np.median(pts["lon"]))
    inside = pts["lon"] > west
    ring = [west, 48, -122, 48, -122, 50, west, 50]
    area = left.evaluate("r => MapArea.encode([r])", ring)
    left.evaluate("a => parent.postMessage({type: 'wtid-area', area: a}, location.origin)", area)
    ident.wait_for_function(f"__identify.ids().length < {POOL_N}")
    assert ids(ident) == sorted(pts["id"][inside].tolist())
    lasso = sorted(pts["id"][inside].tolist())[::3]
    left.evaluate(
        "l => parent.postMessage({type: 'wtid-keep', ids: new Uint32Array(l)}, location.origin)",
        lasso,
    )
    ident.wait_for_function(f"__identify.ids().length === {len(lasso)}")
    assert ids(ident) == lasso
    left.evaluate("parent.postMessage({type: 'wtid-keep', ids: null}, location.origin)")
    ident.wait_for_function(f"__identify.ids().length === {int(inside.sum())}")
    assert page.errors == []
    page.close()


def test_the_photo_search_subset_reaches_identify_and_clears_with_its_chip(browser, site, pts):
    page = explore(browser, site[0])
    ident = frame_of(page, "identify")
    assert len(ids(ident)) == POOL_N
    page.fill("#sq", f"https://www.inaturalist.org/observations/{int(pts['id'].iloc[0])}")
    page.press("#sq", "Enter")
    ident.wait_for_function(f"__identify.ids().length < {POOL_N}")
    chip = page.frame_locator("#map").locator("#selbar li:has-text('Photo search')")
    chip.wait_for(state="attached")
    n = int(
        page.frame_locator("#map").locator("#count").inner_text().split(" ")[0].replace(",", "")
    )
    assert len(ids(ident)) == n
    chip.locator("button").click()
    ident.wait_for_function(f"__identify.ids().length === {POOL_N}")
    assert page.errors == []
    page.close()


def test_a_phone_shows_identify_first(browser, site, pts):
    page = explore(browser, site[0], width=390)
    frame_of(page, "identify")
    assert page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.id)") == ["identify"]
    page.click("[data-p=map]")  # a toggle picks the pane on a phone
    frame_of(page, "map")
    assert page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.id)") == ["map"]
    assert page.errors == []
    page.close()


def test_the_old_levels_page_forwards_its_group_to_identify_and_the_map(browser, site, pts):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    stub_inat(page, None)
    page.goto(f"{site[0]}/levels.html#level=weird&g=Aves&out=1")
    page.wait_for_url("**/explore.html**")
    assert page.evaluate("new URLSearchParams(location.search).get('view')") == "identify-map"
    assert page.evaluate("location.hash") == "#groups=Aves"
    assert ids(frame_of(page, "identify")) == sorted(
        pts["id"][pts["iconic_taxon"] == "Aves"].tolist()
    )
    page.close()


def test_the_levels_forward_is_written_beside_explore(tmp_path):
    split_page.build(tmp_path)
    html = (tmp_path / "levels.html").read_text()
    assert "explore.html?view=identify-map" in html and "groups=" in html
