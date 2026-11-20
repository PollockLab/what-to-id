"""The Food web "Search photos" control, with a stubbed encoder, index and iNaturalist API."""

import pytest

from what_to_id import page_eating

from . import test_embeddings_browser as eb
from .foodweb_page import build_site, open_page

browser = eb.browser
CORS = {"access-control-allow-origin": "*"}
GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)
# the encoder and index the page would load: a fake encoder, an index of five hits (ids 11 to 15)
STUB = """
window.QUERIES = [];
window.AtlasEncoderOverride = {encode: async t => { QUERIES.push(t); return new Float32Array(4); }};
"""
INDEX = """() => { AtlasSearchIndex.open = async () => ({
  manifest: {text_encoder: {bytes: 1e6}},
  taxonVector: async () => null,
  search: async () => [11, 12, 13, 14, 15].map((id, i) => ({id, score: 1 - i / 10, tag: i})),
}); }
"""


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    yield from build_site(tmp_path_factory.mktemp("search-site"), data_url="atlas/")


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    yield from build_site(tmp_path_factory.mktemp("plain-site"))


def stub_inat(page, calls=None):
    def observations(route):
        ids = route.request.url.split("id=")[1].split("&")[0].split(",")
        if calls is not None:
            calls.append(ids)
        results = [
            {
                "id": int(i),
                "quality_grade": "research" if i == "13" else "needs_id",
                "observed_on": "2026-05-01",
                "photos": [{"url": f"https://static.inaturalist.org/photos/{i}/square.jpg"}],
                "taxon": {"name": f"Taxon {i}", "preferred_common_name": f"Common {i}"},
            }
            for i in ids
        ]
        route.fulfill(json={"results": results}, headers=CORS)

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=GIF, content_type="image/gif")
    )


def test_render_ships_the_search_code_only_with_a_data_url():
    plain_html, html = page_eating.render(), page_eating.render("atlas/")
    assert "var FoodSearch" not in plain_html and "AtlasEncoder" not in plain_html
    assert '"search"' not in plain_html
    assert '"search": {"dataUrl": "atlas/"}' in html and "var FoodSearch" in html


def test_the_control_is_hidden_when_search_is_not_configured(browser, plain):
    page = open_page(browser, plain + "#q=eats&x=Strix varia")
    assert page.locator("#fsearch").is_hidden() and page.locator("#fsearch button").count() == 0
    assert page.errors == []


def test_the_control_shows_for_a_predator_question_only(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    assert page.locator("#fsearch").is_visible()
    assert "a photo of a Barred Owl eating" in page.inner_text("#fsearch")
    page.evaluate("location.hash = '#q=eaten&y=Mus musculus'")
    page.wait_for_function("document.getElementById('fsearch').hidden")
    page.evaluate("location.hash = '#q=does&x=Strix varia&y=Mus musculus'")
    page.wait_for_function("!document.getElementById('fsearch').hidden")
    assert "a photo of a Barred Owl eating a House Mouse" in page.inner_text("#fsearch")
    assert page.errors == []


def test_nothing_downloads_until_the_click_then_results_link_out(browser, base):
    page = browser.new_page()
    page.errors, seen, calls = [], [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("request", lambda r: seen.append(r.url))
    stub_inat(page, calls)
    page.add_init_script(STUB)
    page.goto(base + "#q=does&x=Strix varia&y=Mus musculus")
    page.wait_for_function("window.__food && window.__text")
    page.evaluate(INDEX)
    assert not [u for u in seen if "atlas" in u or "inaturalist" in u or "jsdelivr" in u]
    page.click("#fsearch button")
    page.wait_for_selector("#fsearch li a")
    links = page.locator("#fsearch li a").evaluate_all("l => l.map(a => a.href)")
    # id 13 left Needs ID, so four of the five hits show; each links to its observation
    assert links == [f"https://www.inaturalist.org/observations/{i}" for i in (11, 12, 14, 15)]
    assert page.locator("#fsearch img").first.get_attribute("alt") == "Common 11"
    queries = page.evaluate("QUERIES")
    assert "a photo of a Barred Owl eating a House Mouse" in queries
    assert "a photo of a Barred Owl" in queries and "a photo of a House Mouse" in queries
    assert page.inner_text("#fsearch p").startswith("4 photos")
    assert len(calls) == 1 and page.errors == []


def test_a_failed_search_shows_an_error_and_can_be_retried(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia", STUB)
    page.evaluate(
        "() => { AtlasSearchIndex.open = () => Promise.reject(new Error('index is down')); }"
    )
    page.click("#fsearch button")
    page.wait_for_selector("#fsearch .err")
    assert "index is down" in page.inner_text("#fsearch .err")
    assert page.locator("#fsearch button").is_enabled()
    stub_inat(page)
    page.evaluate(INDEX)
    page.click("#fsearch button")
    page.wait_for_selector("#fsearch li a")
    assert page.locator("#fsearch .err").count() == 0 and page.errors == []
