"""The levels page in Chromium, photo hosts stubbed: each level reaches a first photo, the group
tabs filter, the hash keeps the choice, the Identify links carry the ids."""

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
