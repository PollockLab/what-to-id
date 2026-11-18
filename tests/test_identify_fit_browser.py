"""Level 3's range filter without the look-alike file: pool-levels-fit.bin holds, per level-3
record, what fits() answers, so the default tab never downloads pool-levels-looks.bin.
iNaturalist is stubbed."""

import gzip
import json
import urllib.request

import numpy as np
import pandas as pd
import pytest

from what_to_id import pool_levels, site_files

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame

browser = eb.browser
N = ib.N


def write_ranges(root, pts):
    """A big triangle first (it takes the cells it overlaps), then 0.1 degree squares over most of
    the pool; level 3's suggestions are Bombus b and Apis c, holding other halves."""
    d = root / "ranges"
    d.mkdir()
    sq = [(x, y) for x in np.arange(-123.6, -122.85, 0.1) for y in np.arange(48.4, 49.25, 0.1)]
    ring = [np.float32([[-123.6, 48.4], [-123.0, 48.4], [-123.6, 49.0]])]
    ring += [np.float32([[x, y], [x + 0.1, y], [x + 0.1, y + 0.1], [x, y + 0.1]]) for x, y in sq]
    rng = np.random.default_rng(5)

    def pick(first):  # cell 0 is the triangle: in one range, not the other
        return [0] * first + (1 + np.flatnonzero(rng.random(len(ring) - 1) < 0.5)).tolist()

    pd.DataFrame(
        {"name": ["Bombus a", "Bombus b", "Apis c"], "cells": [pick(0), pick(1), pick(0)]}
    ).to_parquet(d / "level-ranges.parquet")
    pd.DataFrame({"lat": [r[:, 1] for r in ring], "lon": [r[:, 0] for r in ring]}).to_parquet(
        d / "level-range-cells.parquet"
    )
    pd.DataFrame(
        {
            "id": pts["id"].to_numpy(np.int64),
            "range_note": pd.Series([None] * len(pts), dtype=object),
            "lat": pts["lat"].astype("float32"),
            "lon": pts["lon"].astype("float32"),
            "out_km": pd.array(np.arange(len(pts)) * 37 % 120, dtype="Int32"),
        }
    ).to_parquet(d / "range-notes.parquet")
    return d


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    score = np.random.default_rng(2).normal(size=N).astype("float32")
    root = tmp_path_factory.mktemp("identify-fit-site")
    server, pts = ib.serve(root, pool_frame(ids), score, ranges=write_ranges)
    yield f"http://127.0.0.1:{server.server_port}", pts, root
    server.shutdown()


def fetch(base, name):
    with urllib.request.urlopen(f"{base}/{name}") as r:
        return r.read()


def files(base):
    return site_files.read_meta(fetch(base, site_files.MAP_NAME).decode())["files"]


def fit_ids(base, pts):
    """The ids of the level-3 records the fit file marks as fitting, and all level-3 ids."""
    f = files(base)
    level, _ = pool_levels.unpack(fetch(base, f["levels"]))
    bits = np.unpackbits(
        np.frombuffer(gzip.decompress(fetch(base, f["fit"])), np.uint8), bitorder="little"
    )
    ids = pts["id"].to_numpy()[level == 3]
    return set(ids[bits[: len(ids)] == 1].tolist()), set(ids.tolist())


def settled(page):
    page.wait_for_function("__identify.ranges()")
    page.wait_for_load_state("networkidle")


def test_the_fit_bits_are_what_the_page_answers_with_the_look_alikes_loaded(browser, site):
    base, pts, _ = site
    fit, level3 = fit_ids(base, pts)
    assert 0 < len(fit) < len(level3)  # both answers occur
    for out, want in (("-1", fit), ("1", level3 - fit)):
        page = ib.open_identify(browser, base, f"#lvl=3&conf=all&run=1&out={out}")
        settled(page)
        assert set(page.evaluate("__identify.view()")[3]) == want
        page.close()


def test_the_default_tab_reads_no_look_alikes_and_counts_level_3_as_the_level_3_page_does(
    browser, site
):
    base, _, _ = site
    f = files(base)
    page = browser.new_page()
    eb.stub_inat(page, None)
    asked = []
    page.on("request", lambda r: asked.append(r.url))
    page.goto(f"{base}/identify.html#lvl=1")
    page.wait_for_function("window.__identify")
    settled(page)
    assert [u for u in asked if f["fit"] in u] and not [u for u in asked if f["looks"] in u]
    count = page.locator('#tabs [data-lv="3"] b').inner_text()
    total = page.evaluate("__identify.total()[3]")
    page.locator('#tabs [data-lv="3"]').click()
    page.wait_for_function(
        f"performance.getEntriesByType('resource').some(e => e.name.includes('{f['looks']}'))"
    )
    page.wait_for_load_state("networkidle")
    assert page.locator('#tabs [data-lv="3"] b').inner_text() == count
    assert page.evaluate("__identify.total()[3]") == total
    direct = ib.open_identify(browser, base, "#lvl=3")
    settled(direct)
    assert direct.evaluate("__identify.total()[3]") == total


def test_a_map_without_the_fit_file_or_with_it_failing_reads_the_look_alikes_as_before(
    browser, site
):
    base, _, _ = site
    f = files(base)
    page = ib.open_identify(browser, base, "#lvl=3")
    settled(page)
    total = page.evaluate("__identify.total()[3]")
    page.close()
    meta = json.loads(fetch(base, "map-meta.json"))
    del meta["files"]["fit"]
    for fail in (False, True):
        page = browser.new_page()
        eb.stub_inat(page, None)
        asked = []
        page.on("request", lambda r, a=asked: a.append(r.url))
        if fail:
            page.route(f"**/{f['fit']}*", lambda r: r.abort())
        else:
            page.route("**/map-meta.json*", lambda r: r.fulfill(json=meta))
        page.goto(f"{base}/identify.html#lvl=1")
        page.wait_for_function("window.__identify")
        settled(page)
        page.wait_for_function(
            f"performance.getEntriesByType('resource').some(e => e.name.includes('{f['looks']}'))"
        )
        assert page.evaluate("__identify.total()[3]") == total
        assert [u for u in asked if f["looks"] in u]
        page.close()
