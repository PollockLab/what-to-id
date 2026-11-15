"""One filter state across every view, in Chromium: each link to another page carries the filters
in the hash, a view applies the ones it can and names the rest as held, and the way back to
Identify brings them all home."""

import re
import shutil
from urllib.parse import urljoin

import pytest

from what_to_id import atlas_search_page, page_confusion, terms_page

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from . import test_page_confusion as tc
from . import test_split_identify_browser as sb
from .test_identify_unconfirmed_browser import RING

browser, site = eb.browser, eb.site
F = ["groups=Aves", "months=6", "lvl=3", "conf=all", "risk=1"]


@pytest.fixture(scope="module")
def views(site, pts, tmp_path_factory):
    """The split site plus the confused pairs, How it works and search pages."""
    root = max(
        tmp_path_factory.getbasetemp().glob("embeddings-site*"), key=lambda p: p.stat().st_mtime
    )
    pq, rq = root / "pairs.parquet", root / "records.parquet"
    tc.pairs_frame().to_parquet(pq)
    tc.records_frame().to_parquet(rq)
    page_confusion.build(root, None, pq, rq)
    terms_page.build(root)
    atlas_search_page.build(root)
    shutil.copy(root / "identify.html", root / "index.html")  # the deploy's landing page
    return site[0]


pts = sb.pts


def opened(browser, url):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    page.route(ib.WTB, lambda r: r.abort())
    page.goto(url)
    return page


def identify(browser, base):
    page = opened(browser, f"{base}/identify.html#" + "&".join(F))
    page.wait_for_function("window.__identify")
    area = page.evaluate("r => MapArea.encode([r])", RING)
    want = [*F, f"area={area}"]
    page.evaluate("h => { location.hash = h; }", "&".join(want))
    page.wait_for_function("document.getElementById('xmap').getAttribute('href').includes('area=')")
    return page, want


def tokens(href):
    return href.split("#", 1)[1].split("&") if "#" in href else []


def carries(href, want):
    got = {t.split("=")[0]: t for t in tokens(href)}
    return all(got.get(t.split("=")[0]) == t for t in want)


def note(page):
    n = page.locator("#site-held")
    return n.inner_text() if n.count() and n.is_visible() else ""


# each link off Identify, the page it opens, and the filters it holds (named in its note): the
# Explore map stays as the rail beside the photo space and the taxonomy, so the area applies there
LINKS = [
    ("#xmap", "explore.html", "Identify tab, Best x%, At risk"),
    ("#xspace", "explore.html", "Identify tab, Best x%, At risk"),
    ("#xtree", "explore.html", "Identify tab, Best x%, At risk"),
    (".hm a[href^='explore.html']", "explore.html", ""),
    (
        ".hm a[href^='confusion.html']",
        "confusion.html",
        "What, When, Identify tab, Best x%, At risk, Where",
    ),
    (".hm a[href^='terms.html']", "terms.html", ""),
]


@pytest.mark.parametrize("link,path,held", LINKS, ids=[x[0] for x in LINKS])
def test_a_view_opened_from_identify_has_its_filters_and_brings_them_back(
    browser, views, link, path, held
):
    page, want = identify(browser, views)
    href = page.get_attribute(link, "href")
    assert href.split("#")[0].split("?")[0] == path and carries(href, want), href
    page.goto(urljoin(page.url, href))
    page.wait_for_load_state("networkidle")
    if path != "terms.html":  # How it works keeps its anchors: the filters ride in the tab
        assert carries(page.url, want), page.url
        text = f"Kept for the other views, not applied here: {held}." if held else ""
        page.wait_for_function(
            "t => document.getElementById('site-held').textContent === t", arg=text
        )
    if path == "explore.html":  # the panes open with the filters they apply
        srcs = page.eval_on_selector_all("iframe", "l => l.map(f => f.src)")
        assert srcs and all(carries(u, ["groups=Aves", "months=6"]) for u in srcs), srcs
    # the way back: Explore's Show cards, elsewhere the wordmark
    sel = ".site-shell a[href^='identify.html']" if path == "explore.html" else ".site-brand"
    page.wait_for_function(
        "([s, w]) => w.every(t => document.querySelector(s).getAttribute('href').includes(t))",
        arg=[sel, want],
    )
    page.locator(sel).click()
    page.wait_for_function("window.__identify")
    assert page.evaluate("__identify.level()") == 3 and carries(page.url, want), page.url
    assert page.errors == []


PAGES = [
    "identify.html",
    "explore.html",
    "confusion.html",
    "search.html",
    "tree.html",
    "terms.html",
]


@pytest.mark.parametrize("path", PAGES)
def test_every_link_to_another_view_carries_the_filters(browser, views, path):
    want = ["groups=Aves", "months=6", "risk=1"]
    if path == "terms.html":  # an anchor page: it passes on the filters last seen in this tab
        page = opened(browser, f"{views}/confusion.html#" + "&".join(want))
        page.wait_for_load_state("networkidle")
        page.goto(f"{views}/terms.html")
    else:
        page = opened(browser, f"{views}/{path}#" + "&".join(want))
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(100)  # the sweep after the last write
    hrefs = page.evaluate(
        "[...document.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.href])"
        ".filter(([h, u]) => h[0] !== '#' && new URL(u).origin === location.origin"
        " && /\\.html$/.test(new URL(u).pathname)).map(([h]) => h)"
    )
    # a link to a section of How it works keeps its anchor: that page reads the filters from the tab
    hrefs = [h for h in hrefs if not re.search(r"#[^=&]+$", h)]
    assert hrefs and all(carries(h, want) for h in hrefs), hrefs
    assert page.errors == []


def test_clear_filters_on_explore_drops_them_from_the_address_and_every_pane(browser, views):
    area = "area=" + identify(browser, views)[1][-1].split("=", 1)[1]
    page = opened(browser, f"{views}/explore.html#" + "&".join([*F, area]))  # Identify and the map
    page.wait_for_load_state("networkidle")
    button = page.locator("#sbx")
    button.wait_for(state="visible")
    assert button.get_attribute("aria-label").startswith("Clear filters")
    button.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("!/groups=|months=|risk=|conf=|area=/.test(location.hash)")
    button.wait_for(state="hidden")
    assert "lvl=3" in page.url and page.evaluate("document.activeElement.id") == "sbf"
    srcs = page.eval_on_selector_all("iframe", "l => l.map(f => f.src)")
    assert srcs and not [u for u in srcs if re.search(r"groups=|months=|risk=|area=", u)], srcs
    pane = "document.getElementById('identify').contentWindow"
    page.wait_for_function(f"{pane}.__identify && {pane}.__identify.level() === 3")
    assert note(page) == ""
    assert page.errors == []
