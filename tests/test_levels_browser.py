"""The levels page in Chromium, photo hosts stubbed: each level reaches a first photo, the group
tabs filter, the hash keeps the choice, the Identify links carry the ids."""

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_levels

from . import test_embeddings_browser as eb
from .test_atlas_search_browser import PNG
from .test_page_levels import levels_frame
from .test_tree_browser import serve

browser = eb.browser
OBS = "https://www.inaturalist.org/observations/"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("levels-site")
    levels_frame().to_parquet(root / "levels.parquet")
    page_levels.build(root, None, root / "levels.parquet")
    server, url = serve(root)
    yield url
    server.shutdown()


@pytest.fixture(scope="module")
def map_site(tmp_path_factory):
    """Record 201 sits at 48.5 N, 123 W: inside cell 0 (Aus bus) but outside cell 1 (Cus dus)."""
    root = tmp_path_factory.mktemp("levels-map-site")
    sq = lambda x: np.float32([x, x + 1, x + 1, x])  # noqa: E731
    pd.DataFrame({"name": ["Aus bus", "Cus dus"], "cells": [[0], [1]]}).to_parquet(
        root / "level-ranges.parquet"
    )
    pd.DataFrame(
        {"lat": [np.float32([48, 48, 49, 49])] * 2, "lon": [sq(-124), sq(-122)]}
    ).to_parquet(root / "level-range-cells.parquet")
    levels_frame().assign(lat=48.5, lon=-123.5).to_parquet(root / "levels.parquet")
    page_levels.build(root, None, root / "levels.parquet")
    server, url = serve(root)
    yield url
    server.shutdown()


def open_page(browser, url, hash_="", w=1280):
    page = browser.new_page(viewport={"width": w, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    for host in (
        "https://inaturalist-open-data.s3.amazonaws.com/**",
        "https://static.inaturalist.org/**",
    ):
        page.route(host, lambda r: r.fulfill(body=PNG, content_type="image/png"))
    page.goto(f"{url}/levels.html{hash_}")
    page.wait_for_selector("#cards .card")
    return page


def obs_links(page):
    return page.locator("#cards a.obs").evaluate_all("as => as.map(a => a.href)")


def first_photo_loaded(page):
    img = page.locator("#cards .card img").first
    img.wait_for()
    return page.wait_for_function("i => i.complete && i.naturalWidth > 0", arg=img.element_handle())


@pytest.mark.parametrize(
    "level,ids",
    [("easy", [101, 102]), ("taxonomist", [201]), ("weird", [301, 302])],
)
def test_each_level_reaches_a_first_photo(browser, site, level, ids):
    page = open_page(browser, site)
    page.locator(f'#levels button[data-level="{level}"]').click()
    assert first_photo_loaded(page)
    assert obs_links(page) == [OBS + str(i) for i in ids]
    assert page.locator(f'#levels button[data-level="{level}"]').get_attribute("aria-pressed") == (
        "true"
    )
    assert f"level={level}" in page.url and page.errors == []


def test_look_alikes_name_both_species(browser, site):
    page = open_page(browser, site, "#level=taxonomist")
    assert page.locator("#cards .card div i").all_inner_texts() == ["Aus bus", "Cus dus"]
    page = open_page(browser, site, "#level=easy")
    assert page.locator("#cards .card div i").all_inner_texts() == ["Aus bus", "Eus fus"]


def test_group_tabs_filter_and_identify_carries_the_ids(browser, site):
    page = open_page(browser, site, "#level=weird")
    assert page.locator("#tabs button").all_inner_texts() == ["All 2", "Fungi 1"]
    assert page.locator("#cards .card").nth(1).inner_text().startswith("No photo")
    page.get_by_role("button", name="Fungi, 1 record").click()
    assert obs_links(page) == [OBS + "301"]
    assert "g=Fungi" in page.url
    assert page.locator("#act a").get_attribute("href").endswith("&id=301")
    assert page.locator("#cards a.identify").get_attribute("href").endswith("&id=301")


def test_phone_width_has_no_side_scroll(browser, site):
    page = open_page(browser, site, w=375)
    assert page.evaluate("document.documentElement.scrollWidth") <= 375


def test_close_call_wording(browser, site):
    page = open_page(browser, site, "#level=taxonomist")
    assert page.locator("#cards .card div").first.inner_text() == (
        "Labelled Aus bus. Often confused with Cus dus."
    )


def test_close_call_with_ranges_draws_a_labelled_map(browser, map_site):
    page = open_page(browser, map_site, "#level=taxonomist")
    cv = page.locator("#cards .card canvas")
    assert cv.get_attribute("role") == "img"
    assert cv.get_attribute("aria-label") == (
        "Range map: this record is inside the range of Aus bus, outside the range of Cus dus"
    )
    page.wait_for_function("c => c.width > 0", arg=cv.element_handle())
    page.locator(".rbtn").click()
    assert page.locator(".card.wide").count() == 1 and page.errors == []
    page = open_page(browser, map_site, "#level=easy")
    assert page.locator("#cards canvas").count() == 0


def test_cards_without_ranges_have_no_map(browser, site):
    page = open_page(browser, site, "#level=taxonomist")
    assert page.locator("#cards canvas").count() == 0
