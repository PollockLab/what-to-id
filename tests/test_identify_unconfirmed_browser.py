"""Identify's "Research Grade here" control in Chromium: hidden without an area, None yet keeps the
species with no Research Grade record in the area's box, records above species do not pass, and
the choice is kept in the hash. iNaturalist is stubbed."""

import functools
import http.server
import threading
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_identify, pool_levels
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.page_map import encode_points, render_map

from . import test_identify_browser as ib
from .embeddings_fixture import TREE, pool_frame
from .test_page_nav import FORBIDDEN

browser = ib.browser

N = 8  # records 0-6 are species 1000-1006, record 7 is labelled at genus 900
RING = [-124, 48, -122, 48, -122, 50, -124, 50]
# species_counts: 1000 as a species, 1001 through a subspecies, a genus row that marks nothing
COUNTS = {
    "total_results": 3,
    "results": [
        {"count": 3, "taxon": {"id": 1000, "rank": "species", "ancestor_ids": [800, 900]}},
        {
            "count": 1,
            "taxon": {"id": 99999, "rank": "subspecies", "ancestor_ids": [800, 901, 1001]},
        },
        {"count": 9, "taxon": {"id": 901, "rank": "genus", "ancestor_ids": [800]}},
    ],
}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("identify-unconfirmed-site")
    pool = pool_frame(np.arange(1, N + 1) * 1000)
    pool.loc[7, ["taxon_id", "taxon_name", "rank"]] = [900, "Genus A", "genus"]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    pd.DataFrame(
        {
            "id": pool["id"],
            "taxon_id": pool["taxon_id"],
            "level": np.int8(1),
            "score": np.float32(np.arange(N)),
            "score2": np.float32(0),
            "looks_like": pd.Series([None] * N, dtype="category"),
        }
    )[list(IDENTIFY_COLUMNS)].to_parquet(root / "identify.parquet")
    pool_levels.build(root, parquet=root / "identify.parquet")
    page_identify.build(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(ib.Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def opened(browser, base, hash_=""):
    page = ib.open_identify(browser, base, hash_, (1000, 900))
    page.counts = []

    def species_counts(route):
        u = urlparse(route.request.url)
        page.counts.append(parse_qs(u.query))
        route.fulfill(json=COUNTS, headers={"access-control-allow-origin": "*"})

    page.route("https://api.inaturalist.org/v1/observations/species_counts*", species_counts)
    page.wait_for_selector("#grid .card")
    return page


def shown(page):
    return sorted(i // 1000 - 1 for i in page.evaluate("__identify.view()")[1])


def seg(page):
    return page.locator("#rg .segb")


def picked(page):
    return page.locator("#rg .segb[aria-checked=true]").inner_text()


def set_area(page):
    area = page.evaluate("r => MapArea.encode([r])", RING)
    page.evaluate("a => postMessage({type: 'wtid-area', area: a}, location.origin)", area)
    return area


def test_the_control_is_hidden_without_an_area(browser, site):
    page = opened(browser, site, "#lvl=1")
    assert page.locator("#rg").is_hidden() and shown(page) == list(range(N))
    set_area(page)
    page.locator("#rg").wait_for(state="visible")
    assert seg(page).all_inner_texts() == ["All 8", "None yet"] and page.counts == []
    page.evaluate("postMessage({type: 'wtid-area', area: ''}, location.origin)")
    page.locator("#rg").wait_for(state="hidden")
    assert page.errors == []


def test_none_yet_keeps_the_species_without_a_research_grade_record_and_leaves_out_genus(
    browser, site
):
    page = opened(browser, site, "#lvl=1")
    set_area(page)
    seg(page).nth(1).click()
    page.wait_for_function("__identify.view()[1].length === 5")
    assert shown(page) == [2, 3, 4, 5, 6]  # no 0 (species) or 1 (subspecies), no 7 (genus)
    assert picked(page) == "None yet 5" and seg(page).nth(0).inner_text() == "All 8"
    assert "rg=none" in page.url
    q = page.counts[0]
    assert len(page.counts) == 1 and q["quality_grade"] == ["research"] and q["per_page"] == ["500"]
    assert [q[k] for k in ("swlat", "swlng", "nelat", "nelng")] == [
        ["48.0000"],
        ["-124.0000"],
        ["50.0000"],
        ["-122.0000"],
    ]
    assert page.locator("#rg .segnote").inner_text() == (
        "Species with no Research Grade record in this area yet. Your ID could be its first."
    )
    seg(page).nth(0).click()
    assert shown(page) == list(range(N)) and "rg=" not in page.url
    assert not [w for w in FORBIDDEN if w in page.inner_text("body").lower()]
    assert page.errors == []


def test_the_choice_is_kept_in_the_hash(browser, site):
    page = opened(browser, site, "#lvl=1")
    area = set_area(page)
    page.evaluate("h => { location.hash = h; }", f"lvl=1&area={area}&rg=none")
    page.reload()  # the route is set, a fresh goto would race it
    page.wait_for_function("window.__identify && __identify.view()[1].length === 5")
    assert shown(page) == [2, 3, 4, 5, 6] and picked(page) == "None yet 5"
    assert f"area={area}" in page.url and "rg=none" in page.url
    assert page.errors == []
