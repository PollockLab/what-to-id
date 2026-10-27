"""The shared site header: one current page, only built pages, a skip link that keeps the hash."""

import re
from pathlib import Path

import pytest

from what_to_id import page_nav
from what_to_id.page_nav import BLITZ, CSS, PAGES, nav

FORBIDDEN = ("similarity", "novelty", "surprise", "recency", "gap first", "gap_first")


def _links(html):
    return re.findall(r"<a href=\"([^\"]+)\"([^>]*)>", html.split("<nav", 1)[1])


@pytest.mark.parametrize("current", [page for page, _ in PAGES])
def test_exactly_one_current_page(current):
    html = nav(current)
    assert html.count('aria-current="page"') == 1
    assert re.search(rf'href="{current}" aria-current="page"', html)


@pytest.mark.parametrize("current", ["map.html", "embeddings.html", "tree.html", "search.html"])
def test_the_pages_inside_explore_mark_explore(current):
    html = nav(current)
    assert html.count('aria-current="page"') == 1
    assert re.search(r'href="explore.html" aria-current="page"', html)
    assert "Photo space<" not in html and ">Map<" not in html and ">Taxonomy<" not in html


def test_the_tabs_are_explore_look_alikes_study_and_blitz():
    assert [label for _, label in PAGES] == ["Explore", "Confused pairs", "Study"]
    assert "levels.html" not in nav("study.html") and ">Where to Blitz" in nav("study.html")


def test_available_drops_pages_that_were_not_built():
    # without the split page the Explore tab opens the map
    html = nav("map.html", {"study.html", "map.html"})
    hrefs = [h for h, _ in _links(html)]
    assert hrefs == ["map.html", "study.html"]
    assert BLITZ in html
    # the page you are on stays even when the set forgets it
    assert 'href="confusion.html" aria-current="page"' in nav("confusion.html", {"study.html"})


def test_unknown_availability_is_probed_by_the_page():
    assert '"Views" data-probe' in nav("study.html")
    assert '"Views" data-probe' not in nav("study.html", {"study.html"})


def test_external_link_opens_a_new_tab_and_says_so():
    link = re.search(rf'<a [^>]*href="{re.escape(BLITZ)}"[^>]*>.*?</a>', nav("map.html")).group()
    assert 'target="_blank"' in link and 'rel="noopener"' in link
    assert "Where to Blitz" in link and "↗" in link and "opens in a new tab" in link


def test_skip_link_keeps_the_hash():
    link = re.search(r'<a class="site-skip"[^>]*>', nav("map.html")).group()
    assert "event.preventDefault()" in link and ".focus()" in link


def test_base_prefixes_the_links():
    html = nav("study.html", base="https://x.test/app/")
    assert 'href="https://x.test/app/explore.html"' in html
    assert 'href="https://x.test/app/study.html" aria-current="page"' in html


def test_no_forbidden_words():
    low = (CSS + nav("map.html")).lower()
    assert not [w for w in FORBIDDEN if w in low]


def test_module_is_stdlib_only():
    src = Path(page_nav.__file__).read_text()
    assert not re.search(r"^\s*(import|from)\s+(numpy|pandas|what_to_id)", src, re.M)


# --- in a browser ---

PAGE = "<!doctype html><style>%s</style><body>%s<main id=main-content>x</main>"


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            instance = pw.chromium.launch()
        except Exception as error:
            pytest.skip(f"Chromium unavailable: {error}")
        yield instance
        instance.close()


def _open(browser, current, fragment=""):
    pg = browser.new_page()
    html = PAGE % (CSS, nav(current))
    pg.route("http://site.test/**", lambda r: r.fulfill(body=html, content_type="text/html"))
    pg.goto(f"http://site.test/{current}{fragment}")
    return pg


def _href(pg, view):
    pg.hover(f".site-nav [data-view={view}]")
    return pg.get_attribute(f".site-nav [data-view={view}]", "href")


def test_explore_tab_on_the_map_page_carries_the_record_and_the_selection(browser):
    pg = _open(
        browser, "map.html", "#record=42&groups=Insecta,-Aves&acc=100&at=9.5/49.123456/-123.987654"
    )
    assert pg.get_attribute(".site-nav [aria-current=page]", "href").startswith("explore.html")
    assert pg.locator(".site-nav a").first.bounding_box()["height"] >= 44
    assert _href(pg, "explore") == "explore.html#id=42&groups=Insecta,-Aves&acc=100"
    assert _href(pg, "blitz") == BLITZ + "?at=49.123,-123.988"
    # replaceState fires no event: the next hover reads the new hash
    pg.evaluate("history.replaceState(null,'','#at=9.5/50.5/-120.25')")
    assert _href(pg, "explore") == "explore.html"
    assert _href(pg, "blitz") == BLITZ + "?at=50.500,-120.250"


def test_explore_tab_carries_taxa_and_leaves_the_camera(browser):
    pg = _open(browser, "map.html", "#taxa=311249,-64615&months=6&area=abc&at=9/49/-123")
    assert _href(pg, "explore") == "explore.html#taxa=311249,-64615&months=6&area=abc"
    pg = _open(browser, "embeddings.html", "#groups=-Aves")
    assert _href(pg, "explore") == "explore.html#groups=-Aves"


def test_photo_search_explore_tab_opens_the_chosen_record(browser):
    pg = _open(browser, "search.html", "#id=7")
    assert _href(pg, "explore") == "explore.html#id=7"
    pg.focus(".site-skip")
    pg.keyboard.press("Enter")
    assert pg.evaluate("location.hash") == "#id=7"
    assert pg.evaluate("document.activeElement.id") == "main-content"


def test_explore_tab_falls_back_to_the_map_when_the_split_page_is_missing(browser):
    pg = browser.new_page()
    html = PAGE % (CSS, nav("map.html"))
    pg.route("http://site.test/map.html", lambda r: r.fulfill(body=html, content_type="text/html"))
    pg.route("http://site.test/explore.html", lambda r: r.fulfill(status=404, body=""))
    pg.route("http://site.test/search.html", lambda r: r.fulfill(status=404, body=""))
    pg.goto("http://site.test/map.html#groups=-Aves")
    pg.wait_for_selector('.site-nav a[href="map.html"]')
    assert _href(pg, "blitz").startswith(BLITZ)
    assert pg.get_attribute(".site-nav [aria-current=page]", "href") == "map.html"


def test_shell_is_one_short_row_on_a_phone(browser):
    pg = _open(browser, "map.html")
    pg.set_viewport_size({"width": 390, "height": 800})
    assert pg.locator(".site-shell").bounding_box()["height"] <= 56
    assert all(
        b["height"] >= 44
        for b in pg.locator(".site-nav a").evaluate_all(
            "els => els.map(e => e.getBoundingClientRect().toJSON())"
        )
    )
    assert pg.evaluate("document.documentElement.scrollWidth") <= 390
