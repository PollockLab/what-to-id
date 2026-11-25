"""The map's Life groups setting in Chromium: iNaturalist (one Plantae chip), or Split plants."""

import functools
import http.server
import threading

import pytest

from what_to_id.map_points import encode_points
from what_to_id.page_map import render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_map_groups_browser import ROWS, STUB

browser = eb.browser
SIZES = {
    "Tracheophyta": 100,
    "Bryophytes": 30,
    "Algae": 10,
    "Plantae": 20,
    "Insecta": 100,
    "Aves": 40,
}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("map-plants")
    pool = pool_frame(range(1, 301))
    pool["iconic_taxon"] = [g for g, n in SIZES.items() for _ in range(n)]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/map.html?standalone=1"
    server.shutdown()


@pytest.fixture
def open_page(browser, site):
    pages = []

    def opener(extra="", width=1280):
        p = browser.new_page(viewport={"width": width, "height": 900})
        p.errors = []
        p.on("pageerror", lambda e: p.errors.append(str(e)))
        p.route(
            "https://unpkg.com/**",
            lambda r: r.fulfill(
                body=STUB if r.request.url.endswith(".js") else "",
                content_type="text/javascript",
            ),
        )
        p.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
        p.goto(site + extra)
        p.wait_for_function("document.querySelector('#groups .gc').textContent !== ''")
        pages.append(p)
        return p

    yield opener
    for p in pages:
        assert p.errors == []
        p.close()


def rows(page):
    return {r[0]: r[1] for r in page.evaluate(ROWS)}


def test_inaturalist_mode_is_the_default_and_merges_the_plants(open_page):
    page = open_page()
    assert rows(page) == {"Plants": "160", "Insects": "100", "Birds": "40"}
    assert page.locator("#gmode button[aria-pressed=true]").text_content() == "iNaturalist"
    assert page.evaluate("META.group_ids.Plantae") == 47126


def test_split_mode_keeps_the_four_plant_groups(open_page):
    page = open_page("&plants=split")
    assert rows(page) == {
        "Vascular plants": "100", "Insects": "100", "Birds": "40",
        "Mosses, liverworts and hornworts": "30", "Other plants": "20", "Green and red algae": "10",
    }  # fmt: skip
    assert page.locator("#gmode button[aria-pressed=true]").text_content() == "Split plants"


def test_the_button_switches_keeps_the_choice_and_old_links_read(open_page):
    page = open_page()
    page.get_by_role("button", name="Split plants").click()
    page.wait_for_function("location.search.includes('plants=split')")
    page.wait_for_function("document.querySelectorAll('#groups > li').length === 6")
    assert page.evaluate("localStorage.getItem('wtid-plants')") == "split"
    page.goto(
        page.url.replace("plants=split", "") + "#groups=Tracheophyta"
    )  # kept without the param
    page.wait_for_function("document.querySelectorAll('#groups > li').length === 6")
    page.goto(page.url.split("?")[0] + "?standalone=1&plants=inat#groups=Tracheophyta,-Algae")
    page.wait_for_function("document.querySelectorAll('#groups > li').length === 3")
    assert page.locator("#groups > li .gb[aria-pressed=true] .nm").text_content() == "Plants"
    page.wait_for_function(
        "(document.getElementById('count').textContent || '').startsWith('160 ')"
    )
    page.evaluate("localStorage.removeItem('wtid-plants')")


def test_the_iNaturalist_link_names_plantae(open_page):
    page = open_page("&plants=inat#groups=Plantae")
    page.wait_for_function(
        "(document.getElementById('count').textContent || '').startsWith('160 ')"
    )
    page.wait_for_function("document.getElementById('identify').href.includes('Plantae')")
