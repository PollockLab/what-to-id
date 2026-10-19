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


def test_available_drops_pages_that_were_not_built():
    html = nav("map.html", {"index.html", "map.html"})
    hrefs = [h for h, _ in _links(html)]
    assert hrefs == ["index.html", "map.html"]
    assert BLITZ in html
    # the page you are on stays even when the set forgets it
    assert 'href="search.html" aria-current="page"' in nav("search.html", {"index.html"})


def test_unknown_availability_is_probed_by_the_page():
    assert '"Views" data-probe' in nav("index.html")
    assert '"Views" data-probe' not in nav("index.html", {"index.html"})


def test_external_link_opens_a_new_tab_and_says_so():
    link = re.search(rf'<a [^>]*href="{re.escape(BLITZ)}"[^>]*>.*?</a>', nav("map.html")).group()
    assert 'target="_blank"' in link and 'rel="noopener"' in link
    assert "Where to Blitz" in link and "↗" in link and "opens in a new tab" in link


def test_skip_link_keeps_the_hash():
    link = re.search(r'<a class="site-skip"[^>]*>', nav("map.html")).group()
    assert "event.preventDefault()" in link and ".focus()" in link


def test_base_and_extra_page():
    html = nav("embeddings-sample.html", base="https://x.test/app/", carry=False)
    assert 'href="https://x.test/app/map.html"' in html
    assert 'href="embeddings-sample.html" aria-current="page"' in html
    assert html.count('aria-current="page"') == 1 and "data-fixed" in html


def test_no_forbidden_words():
    low = (CSS + nav("map.html") + nav("embeddings-sample.html", carry=False)).lower()
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


def test_switcher_on_the_map_page_carries_the_record_and_the_centre(browser):
    pg = _open(browser, "map.html", "#record=42&at=9.5/49.123456/-123.987654")
    assert pg.get_attribute(".site-nav [aria-current=page]", "href") == "map.html"
    assert pg.locator(".site-nav a").first.bounding_box()["height"] >= 44
    assert _href(pg, "space") == "embeddings.html#id=42"
    assert _href(pg, "blitz") == BLITZ + "?at=49.123,-123.988"
    # replaceState fires no event: the next hover reads the new hash
    pg.evaluate("history.replaceState(null,'','#at=9.5/50.5/-120.25')")
    assert _href(pg, "space") == "embeddings.html"
    assert _href(pg, "blitz") == BLITZ + "?at=50.500,-120.250"


def test_switcher_carries_groups_between_map_and_photo_space(browser):
    pg = _open(browser, "map.html", "#groups=Insecta,-Aves&record=42")
    assert _href(pg, "space") == "embeddings.html#id=42&groups=Insecta,-Aves"
    pg = _open(browser, "embeddings.html", "#groups=-Aves")
    assert _href(pg, "map") == "map.html#groups=-Aves"


def test_photo_search_switcher_points_the_map_at_the_chosen_record(browser):
    pg = _open(browser, "search.html", "#id=7")
    assert _href(pg, "map") == "map.html#record=7"
    pg.focus(".site-skip")
    pg.keyboard.press("Enter")
    assert pg.evaluate("location.hash") == "#id=7"
    assert pg.evaluate("document.activeElement.id") == "main-content"


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
