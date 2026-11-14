"""The Identify page's range maps in Chromium: the chip on each card, its popover map, the far
outside segments and Clear matches starting with far records hidden. iNaturalist is stubbed."""

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
from .identify_sheets import close, reveal
from .test_identify_first_browser import first_lists
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


def write_site(root, introduced=()):
    """Two cells, west and east of 123 W; record 4 is in the east one, record 7 (Narrow it down) in
    the west one, its suggestion's range; ``introduced`` marks rows."""
    pytest.importorskip("pyarrow")
    pool = pool_frame(np.arange(1, N + 1) * 1000)
    pool.loc[4, ["lat", "lon"]] = [49.0, -122.5]
    pool.loc[7, ["lat", "lon"]] = [49.0, -123.5]
    if introduced:
        pool["introduced"] = pool.index.isin(introduced)
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


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("identify-ranges-site")
    write_site(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(ib.Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def opened(browser, base, hash_, size=(1000, 900), touch=False):
    page = ib.open_identify(browser, base, hash_, size, touch)
    page.wait_for_function("window.__identify && __identify.ranges()")
    page.wait_for_selector(".links", state="attached")
    return page


def shown(page, lv):
    return sorted(i // 1000 - 1 for i in page.evaluate("__identify.view()")[lv])


def chips(page):
    return sorted(page.locator("#grid .card .links > :not(a)").all_inner_texts())


def seg(page):
    return page.locator("#rout .segb")


def picked(page):
    return page.locator("#rout .segb[aria-checked=true]").inner_text()


def test_clear_matches_start_with_far_records_hidden_and_the_segments_filter(browser, site):
    page = opened(browser, site, "#lvl=1")
    assert page.locator("#rout").get_attribute("hidden") is None
    assert page.locator("#rout [role=radiogroup]").count() == 1
    assert seg(page).all_inner_texts() == ["All 4", "Hide far outside 3", "Only far outside 1"]
    assert picked(page) == "Hide far outside 3"
    assert page.locator("#hintbody .segnote").text_content() == (
        "Far outside: 50 km or more from the labelled species' known range in BC. "
        "Records with no range map count as in range."
    )
    assert shown(page, 1) == [0, 1, 3] and page.evaluate("__identify.total()")[1] == 3
    assert chips(page) == ["In range", "Just outside range", "No range map: range unknown"]
    assert "out=" not in page.url
    reveal(page, "#rout .segb")
    seg(page).nth(0).click()
    assert shown(page, 1) == [0, 1, 2, 3] and "out=0" in page.url and picked(page) == "All 4"
    assert chips(page) == [
        "About 1,200 km outside",
        "In range",
        "Just outside range",
        "No range map: range unknown",
    ]
    seg(page).nth(2).click()
    assert shown(page, 1) == [2] and "out=1" in page.url and picked(page) == "Only far outside 1"
    page.reload()
    page.wait_for_function("window.__identify && __identify.ranges()")
    assert shown(page, 1) == [2] and picked(page) == "Only far outside 1"  # kept in the hash
    reveal(page, "#rout .segb")
    seg(page).nth(1).click()
    assert shown(page, 1) == [0, 1, 3] and "out=" not in page.url
    close(page)
    page.locator("#tab5").click()  # another level starts at All
    page.locator("#kind .segb", has_text="Odd shots").click()  # the counts follow the kind
    assert shown(page, 5) == [8, 9] and picked(page) == "All 2"
    assert seg(page).all_inner_texts() == ["All 2", "Hide far outside 1", "Only far outside 1"]
    assert chips(page) == ["About 80 km outside", "Range map"]
    assert not [w for w in FORBIDDEN if w in page.inner_text("body").lower()]
    assert page.errors == []


def test_the_first_lists_leave_out_far_clear_matches_as_the_page_does(browser, site):
    first = first_lists(site)[""]
    page = opened(browser, site, "#lvl=1&conf=all&sort=conf")  # level 3 as the first list holds it
    page.click("#tab3")  # its rank and look-alikes load when it is first shown
    page.wait_for_load_state("networkidle")
    page.click("#tab1")
    view = page.evaluate("__identify.view()")
    assert [r[0] // 1000 - 1 for r in first["rows"][1]] == [3, 1, 0]  # no 2: 1,234 km outside
    total = page.evaluate("__identify.total()")
    for lv in (1, 3):
        assert [r[0] for r in first["rows"][lv]] == view[lv] and first["total"][lv] == total[lv]
    kinds = [k for k, _ in page_identify.KINDS]
    assert [r[0] for k in kinds for r in first["rows"][k]] == view[5]
    assert sum(first["total"][k] for k in kinds) == total[5]


def test_the_segments_move_with_the_arrow_keys(browser, site):
    page = opened(browser, site, "#lvl=1")
    reveal(page, "#rout .segb")
    page.locator("#rout .segb[aria-checked=true]").focus()
    page.keyboard.press("ArrowRight")
    assert picked(page) == "Only far outside 1" and "out=1" in page.url and shown(page, 1) == [2]
    assert page.evaluate("document.activeElement.textContent") == "Only far outside 1"
    page.keyboard.press("ArrowRight")  # wraps
    assert picked(page) == "All 4" and "out=0" in page.url
    page.keyboard.press("ArrowLeft")
    assert picked(page) == "Only far outside 1"
    page.keyboard.press("Home")
    assert picked(page) == "All 4"
    page.keyboard.press("End")
    assert picked(page) == "Only far outside 1"
    assert page.errors == []


def test_narrow_it_down_starts_with_records_in_the_suggestions_range(browser, site):
    page = opened(browser, site, "#lvl=3&conf=all")
    texts = seg(page).all_inner_texts()
    assert texts == ["All 1", "Suggestion in range 1", "Suggestion not in range 0"]
    assert seg(page).nth(2).is_disabled() and picked(page) == "Suggestion in range 1"
    assert shown(page, 3) == [7] and "out=" not in page.url
    assert page.locator("#grid .card .links .range").inner_text() == "Range: fits the suggestion"
    assert page.errors == []


def test_a_close_call_chip_gives_the_note_and_opens_the_map_by_click_and_keyboard(browser, site):
    page = opened(browser, site, "#lvl=5&kind=2")
    assert chips(page) == [
        "About 300 km outside",
        "Fits the look-alike, not the label",
        "No range map: range unknown",
    ]
    assert picked(page).startswith("All ") and seg(page).nth(2).inner_text() == "Only far outside 2"
    chip, pop = page.locator(".rchip", has_text="Fits the look-alike"), page.locator("#rpop")
    assert chip.get_attribute("aria-expanded") == "false" and "bad" in chip.get_attribute("class")
    ib.panel(page, page.locator(".card", has=chip))
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
    far = page.locator(".rchip", has_text="300 km")
    ib.panel(page, page.locator(".card", has=far))
    far.click()  # the look-alike's range is unknown
    assert pop.locator(".rleg").inner_text().split("\n") == ["Taxon 5", "this record"]
    assert pop.locator(".rcap").inner_text() == "About 300 km outside the label's usual range."
    assert page.errors == []


def test_the_hash_record_opens_its_range_popover_under_only_far_outside(browser, site):
    page = opened(browser, site, "#lvl=1&out=1&record=3000")
    page.wait_for_selector("#rpop:not([hidden])")
    assert shown(page, 1) == [2] and picked(page) == "Only far outside 1"
    assert page.locator("#cpdet .rchip").get_attribute("aria-expanded") == "true"
    assert page.errors == []


def test_the_hash_record_picks_its_level_and_leads_it(browser, site):
    last = opened(browser, site, "#lvl=5&out=0").evaluate("__identify.view()")[1][-1]
    page = opened(browser, site, f"#lvl=5&out=0&record={last}")
    page.wait_for_selector("#rpop:not([hidden])")
    assert page.evaluate("__identify.level()") == 1
    assert page.evaluate("__identify.view()")[1][0] == last
    assert page.locator("#cpdet .rchip").get_attribute("aria-expanded") == "true"
    assert page.errors == []


def test_a_hash_record_not_on_the_list_opens_nothing(browser, site):
    page = opened(browser, site, "#lvl=1&out=1&record=1000")
    assert page.locator("#rpop").count() == 0 or page.locator("#rpop").is_hidden()
    assert page.errors == []


def test_a_phone_popover_is_a_bottom_sheet(browser, site):
    page = opened(browser, site, "#lvl=1", (390, 800), touch=True)
    ib.panel(page, page.locator(".card", has=page.locator(".rchip")).first)
    page.locator("#cpdet .rchip").tap()
    box = page.locator("#rpop").bounding_box()
    assert box["x"] == 0 and box["width"] == 390 and box["y"] + box["height"] == 800
    assert page.errors == []


def test_a_narrow_pane_opens_the_map_on_hover_beside_the_chip(browser, site):
    page = opened(
        browser, site, "#lvl=1", (400, 2000)
    )  # Identify's width inside Explore; room below the reference photos
    ib.panel(page, page.locator(".card", has=page.locator(".rchip")).first)
    chip, pop = page.locator("#cpdet .rchip"), page.locator("#rpop")
    chip.hover()
    pop.wait_for(state="visible")
    c, box = chip.bounding_box(), pop.bounding_box()
    assert (
        box["width"] <= 400 - 16
        and box["x"] >= 8
        # below the chip, or above it when the panel's sheet puts the chip low
        and min(abs(box["y"] - (c["y"] + c["height"])), abs(box["y"] + box["height"] - c["y"])) < 20
    )
    page.mouse.move(0, 0)
    pop.wait_for(state="hidden")
    assert page.errors == []
