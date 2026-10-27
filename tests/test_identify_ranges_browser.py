"""The Identify page's range maps in Chromium: the chip on each card, its popover map, the outside
its range chip and Clear matches starting with far records left out. iNaturalist is stubbed."""

import functools
import http.server
import threading

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

ONLY_LOOK = "Range: fits the look-alike, not the label"
# per record (taxon i % 7, "Taxon 3" and "Taxon 6" have no known range): level, km, note, look-alike
ROWS = [
    (1, 0, None, None),
    (1, 20, None, None),
    (1, 1234, None, None),
    (1, None, None, None),
    (2, 120, ONLY_LOOK, "Bombus a"),
    (2, 300, None, "Apis c"),  # a look-alike with no known range: the label's map alone
    (2, None, None, "Bombus a"),
    (3, 0, None, "Taxon 0"),
    (4, 80, None, None),
    (4, None, None, None),  # a known range, the record's distance unknown
]
N = len(ROWS)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """Two cells, west and east of 123 W; record 4 sits in the east one."""
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("identify-ranges-site")
    pool = pool_frame(np.arange(1, N + 1) * 1000)
    pool.loc[4, ["lat", "lon"]] = [49.0, -122.5]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    level, km, note, look = zip(*ROWS, strict=True)
    pd.DataFrame(
        {
            "id": pool["id"],
            "taxon_id": pool["taxon_id"],
            "level": np.int8(level),
            "score": np.float32(np.arange(N)),
            "score2": np.float32(0),
            "looks_like": pd.Series(look, dtype="category"),
        }
    )[list(IDENTIFY_COLUMNS)].to_parquet(root / "identify.parquet")
    rd = root / "ranges"
    rd.mkdir()
    pd.DataFrame(
        {
            "name": ["Taxon 0", "Taxon 1", "Taxon 2", "Taxon 4", "Taxon 5", "Bombus a"],
            "cells": [[0], [0, 1], [1], [0], [0, 1], [1]],
        }
    ).to_parquet(rd / "level-ranges.parquet")
    pd.DataFrame(
        {
            "lat": [np.float32([48, 48, 50, 50])] * 2,
            "lon": [np.float32([x, x + 1, x + 1, x]) for x in (-124, -123)],
        }
    ).to_parquet(rd / "level-range-cells.parquet")
    pd.DataFrame(
        {
            "id": pool["id"],
            "range_note": pd.Series(note, dtype=object),
            "lat": pool["lat"].astype("float32"),
            "lon": pool["lon"].astype("float32"),
            "out_km": pd.array(km, dtype="Int32"),
        }
    ).to_parquet(rd / "range-notes.parquet")
    pool_levels.build(root, parquet=root / "identify.parquet", ranges=rd)
    page_identify.build(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(ib.Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def opened(browser, base, hash_, size=(1000, 900), touch=False):
    page = ib.open_identify(browser, base, hash_, size, touch)
    page.wait_for_function("__identify.ranges()")
    page.wait_for_selector("#grid .card .links")
    return page


def shown(page, lv):
    return sorted(i // 1000 - 1 for i in page.evaluate("__identify.view()")[lv])


def chips(page):
    return sorted(page.locator("#grid .card .links > :not(a)").all_inner_texts())


def test_clear_matches_start_with_far_records_left_out_and_the_chip_cycles(browser, site):
    page = opened(browser, site, "#lvl=1")
    btn = page.locator("#out")
    assert btn.inner_text() == "Outside its range 1" and "not" in btn.get_attribute("class")
    assert shown(page, 1) == [0, 1, 3] and page.evaluate("__identify.total()")[1] == 3
    assert page.locator("#left").inner_text() == "Left out: 1 far outside their range."
    assert chips(page) == ["In range", "Just outside range", "No range map: range unknown"]
    assert "out=" not in page.url
    btn.click()
    assert shown(page, 1) == [0, 1, 2, 3] and "out=0" in page.url
    assert btn.get_attribute("aria-pressed") == "false" and page.locator("#left").inner_text() == ""
    assert chips(page) == [
        "About 1,200 km outside",
        "In range",
        "Just outside range",
        "No range map: range unknown",
    ]
    btn.click()
    assert shown(page, 1) == [2] and "out=1" in page.url
    assert btn.inner_text() == "Outside its range 1" and btn.get_attribute("aria-pressed") == "true"
    page.reload()
    page.wait_for_function("__identify.ranges()")
    assert shown(page, 1) == [2]  # kept in the hash
    btn.click()
    assert shown(page, 1) == [0, 1, 3] and "out=" not in page.url
    page.locator("#tab4").click()  # another level starts with nothing left out
    assert shown(page, 4) == [8, 9] and btn.inner_text() == "Outside its range 1"
    assert chips(page) == ["About 80 km outside", "Range map"]
    assert not [w for w in FORBIDDEN if w in page.inner_text("body").lower()]
    assert page.errors == []


def test_a_close_call_chip_gives_the_note_and_opens_the_map_by_click_and_keyboard(browser, site):
    page = opened(browser, site, "#lvl=2")
    assert chips(page) == [
        "About 300 km outside",
        "Fits the look-alike, not the label",
        "No range map: range unknown",
    ]
    assert page.locator("#out").inner_text() == "Outside its range 2"
    chip, pop = page.locator(".rchip", has_text="Fits the look-alike"), page.locator("#rpop")
    assert chip.get_attribute("aria-expanded") == "false" and "bad" in chip.get_attribute("class")
    chip.click()
    assert pop.is_visible() and pop.get_attribute("role") == "dialog"
    assert chip.get_attribute("aria-expanded") == "true"
    assert pop.locator("canvas").get_attribute("aria-label") == (
        "Range map: this record is outside the range of Taxon 4, inside the range of Bombus a. "
        "About 120 km outside the label's usual range. Inside the look-alike's."
    )
    assert pop.locator(".rleg").inner_text().split("\n") == [
        "Taxon 4",
        "Bombus a",
        "both",
        "this record",
    ]
    page.keyboard.press("Escape")
    assert pop.is_hidden() and chip.get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.className") == "rchip bad"
    page.keyboard.press("Enter")
    assert pop.is_visible() and page.evaluate("document.activeElement.id") == "rpop"
    pop.get_by_role("button", name="Close range map").click()
    assert pop.is_hidden()
    page.locator(".rchip", has_text="300 km").click()  # the look-alike's range is unknown
    assert pop.locator(".rleg").inner_text().split("\n") == ["Taxon 5", "this record"]
    assert pop.locator(".rcap").inner_text() == "About 300 km outside the label's usual range."
    assert page.errors == []


def test_a_phone_popover_is_a_bottom_sheet(browser, site):
    page = opened(browser, site, "#lvl=3", (390, 800), touch=True)
    page.locator(".rchip").tap()
    box = page.locator("#rpop").bounding_box()
    assert box["x"] == 0 and box["width"] == 390 and box["y"] + box["height"] == 800
    assert page.errors == []


def test_a_narrow_pane_opens_the_map_on_hover_beside_the_chip(browser, site):
    page = opened(browser, site, "#lvl=3", (400, 800))  # Identify's width inside Explore
    chip, pop = page.locator(".rchip").first, page.locator("#rpop")
    chip.hover()
    pop.wait_for(state="visible")
    c, box = chip.bounding_box(), pop.bounding_box()
    assert (
        box["width"] <= 400 - 16 and box["x"] >= 8 and abs(box["y"] - (c["y"] + c["height"])) < 20
    )
    page.mouse.move(0, 0)
    pop.wait_for(state="hidden")
    assert page.errors == []
