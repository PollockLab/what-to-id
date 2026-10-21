"""Photo-search page in Chromium on a Range-capable local server with a stubbed iNaturalist API."""

import base64
import functools
import http.server
import json
import os
import re
import threading
from urllib.parse import parse_qs, urlparse

import pytest

from what_to_id import atlas_taxa
from what_to_id.atlas_search_page import build

from .atlas_index_fixture import write_fixture

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with `Range: bytes=a-b` -> 206, as the real host must provide."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        header = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not header or not os.path.isfile(path):
            return super().do_GET()
        a, b = re.fullmatch(r"bytes=(\d+)-(\d+)", header).groups()
        with open(path, "rb") as f:
            data = f.read()
        part = data[int(a) : int(b) + 1]
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {a}-{int(a) + len(part) - 1}/{len(data)}")
        self.send_header("Content-Length", str(len(part)))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(part)


TAXA = [("Quercus garryana", "Garry oak"), ("Lobaria pulmonaria", "Lungwort"), ("Acer", "Maple")]


def write_taxa(atlas, ref):
    """Taxa whose vectors are fixture queries 1..3, so a taxon search has known hits."""
    import numpy as np
    import pandas as pd

    pool = atlas.parent / "pool.parquet"
    pd.DataFrame(
        {"taxon_name": [t for t, _ in TAXA] * 2, "common_name": [c for _, c in TAXA] * 2}
    ).to_parquet(pool)
    rows = dict(zip(sorted(t.lower() for t, _ in TAXA), range(1, 4), strict=True))
    queries = np.array(ref["queries"], dtype=np.float32)

    def embed(prompts):
        return queries[[rows[p.removeprefix("a photo of ").lower()] for p in prompts]]

    atlas_taxa.build(pool, atlas, embed)


SITE_ROOT = {}  # served base url -> directory, for tests that change files under a live page


@pytest.fixture(scope="module")
def browser():
    required = os.environ.get("WHAT_TO_ID_REQUIRE_BROWSER") == "1"
    if required:
        from playwright import sync_api as api
    else:
        api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as pw:
        try:
            instance = pw.chromium.launch()
        except Exception as error:
            if required:
                pytest.fail(f"Required Chromium unavailable: {error}")
            pytest.skip(f"Chromium unavailable: {error}")
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("faiss")
    root = tmp_path_factory.mktemp("atlas-search-site")
    ref = write_fixture(root / "atlas")
    write_taxa(root / "atlas", ref)
    build(root, data_url="atlas/")
    handler = functools.partial(RangeHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    SITE_ROOT[base] = root
    yield base, ref
    server.shutdown()


def stub_inat(page, ref):
    """Canned iNaturalist API: hit #3 left Needs ID, hit #5 is gone, Fungi on hit #4."""
    hits = ref["searches"][-1]["ids"][0]
    research, gone, fungi = hits[2], hits[4], hits[3]
    calls = []

    def observations(route):
        ids = [int(i) for i in parse_qs(urlparse(route.request.url).query)["id"][0].split(",")]
        calls.append(ids)
        results = [
            {
                "id": i,
                "quality_grade": "research" if i == research else "needs_id",
                "observed_on": "2026-05-01",
                "place_guess": "Vancouver, BC",
                "photos": [{"url": f"https://static.inaturalist.org/photos/{i}/square.jpg"}],
                "taxon": {
                    "name": f"Taxon {i}",
                    "preferred_common_name": f"Common {i}",
                    "ancestor_ids": [1, 47170] if i == fungi else [1, 2],
                },
            }
            for i in ids
            if i != gone
        ]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    def taxa(route):
        route.fulfill(
            json={"results": [{"id": 47170, "name": "Fungi", "preferred_common_name": "Fungi"}]},
            headers={"access-control-allow-origin": "*"},
        )

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.route("https://api.inaturalist.org/v1/taxa/autocomplete*", taxa)
    page.route(
        "https://static.inaturalist.org/**", lambda r: r.fulfill(body=PNG, content_type="image/png")
    )
    return {"research": research, "gone": gone, "fungi": fungi, "calls": calls}


@pytest.fixture
def open_page(browser, site):
    base, ref = site
    pages = []

    def opener(hash_="", width=1280, fake_encoder=True):
        page = browser.new_page(viewport={"width": width, "height": 900})
        pages.append(page)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: page.errors.append(f"failed {r.url}"))
        if fake_encoder:
            page.add_init_script(
                f"window.encoded = []; window.AtlasEncoderOverride = {{encode: async t => "
                f"(window.encoded.push(t), Float32Array.from({json.dumps(ref['queries'][0])}))}};"
            )
        page.stub = stub_inat(page, ref)
        page.goto(f"{base}/search.html{hash_}")
        return page

    yield opener
    for page in pages:
        page.close()


def card_ids(page):
    hrefs = page.locator(".card a.photo").evaluate_all("a => a.map(x => x.href)")
    return [int(h.rsplit("/", 1)[1]) for h in hrefs]


def test_text_search_renders_hits_drops_unneeded_and_hands_off(open_page, site):
    _, ref = site
    page = open_page("#q=a+bird+eating+a+frog")
    page.wait_for_selector(".card")
    hits = ref["searches"][-1]["ids"][0]
    gone = {page.stub["research"], page.stub["gone"]}
    assert card_ids(page)[:8] == [i for i in hits if i not in gone][:8]
    assert page.locator(".card").count() == 198
    assert "1 no longer need an ID" in page.locator("#dropped").inner_text()
    assert "1 no longer returned" in page.locator("#dropped").inner_text()
    assert "Similarity" in page.locator(".card").first.inner_text()
    assert page.locator(".card img").first.get_attribute("src").endswith("/small.jpg")
    assert [len(c) for c in page.stub["calls"]] == [200]
    identify = page.locator("#actions a").first.get_attribute("href")
    assert identify.startswith("https://www.inaturalist.org/observations/identify?")
    listed = identify.rsplit("id=", 1)[1].split(",")
    assert (
        len(listed) == 198 and str(hits[0]) in listed and str(page.stub["research"]) not in listed
    )
    mapped = (
        page.locator(".card").first.get_by_role("link", name="Show on map").get_attribute("href")
    )
    assert mapped.endswith(f"map.html#record={card_ids(page)[0]}")
    assert page.evaluate("document.activeElement.id") == "rh"
    assert page.errors == []


def test_more_like_this_and_id_deep_link(open_page, site):
    _, ref = site
    page = open_page("#q=a+bird")
    page.wait_for_selector(".card")
    source = ref["lookups"][0]
    assert source["id"] in card_ids(page)
    page.locator(".card").nth(card_ids(page).index(source["id"])).get_by_role(
        "button", name=re.compile("More photos like")
    ).click()
    page.wait_for_function(f"location.hash === '#id={source['id']}'")
    # the stubbed API drops two ids from every result, neighbours included
    gone = {page.stub["research"], page.stub["gone"]}
    want = [i for i in source["neighbors"][0] if i not in gone]
    page.wait_for_function(f"document.querySelectorAll('.card').length === {len(want)}")
    assert card_ids(page) == want
    deep = open_page(f"#id={source['id']}", fake_encoder=False)
    deep.wait_for_selector(".card")
    assert card_ids(deep) == want
    assert deep.errors == [] and page.errors == []


def test_stale_manifest_reloads_after_files_are_renamed(open_page, site):
    # the weekly compaction renames what it replaces; an open page must reload, not break
    base, ref = site
    atlas = SITE_ROOT[base] / "atlas"
    first, second = [r for r in ref["lookups"] if r["neighbors"] is not None][:2]
    page = open_page(f"#id={first['id']}", fake_encoder=False)
    page.wait_for_selector(".card")
    manifest_path = atlas / "manifest.json"
    saved = manifest_path.read_text()
    manifest = json.loads(saved)
    old = manifest["neighbors"][0]["name"]
    try:
        for suffix in (".bin", ".dir.u32"):
            (atlas / f"{old}{suffix}").rename(atlas / f"{old}-v2{suffix}")
        manifest["neighbors"][0]["name"] = f"{old}-v2"
        manifest_path.write_text(json.dumps(manifest))
        page.evaluate(f"location.hash = '#id={second['id']}'")
        page.wait_for_function(
            f"document.querySelector('.card a.photo[href$=\"/{second['neighbors'][0][0]}\"]')"
        )
        assert card_ids(page) == second["neighbors"][0]
    finally:
        for suffix in (".bin", ".dir.u32"):
            if (atlas / f"{old}-v2{suffix}").exists():
                (atlas / f"{old}-v2{suffix}").rename(atlas / f"{old}{suffix}")
        manifest_path.write_text(saved)


def test_pasted_url_absent_id_and_taxon_filter(open_page, site):
    _, ref = site
    page = open_page("", fake_encoder=False)
    page.fill("#q", f"https://www.inaturalist.org/observations/{ref['lookups'][1]['id']}/")
    page.press("#q", "Enter")
    page.wait_for_selector(".card")
    assert card_ids(page) == ref["lookups"][1]["neighbors"][0]
    page.fill("#q", "1")
    page.press("#q", "Enter")
    page.wait_for_function("document.querySelectorAll('.card').length === 0")
    assert "not in the index" in page.locator("#status").inner_text()
    # exclude Fungi from a text search: the one Fungi hit is reported as filtered
    text = open_page("#q=a+bird", fake_encoder=True)
    text.wait_for_selector(".card")
    # a bare query is wrapped in the caption template the model was tested with
    assert text.evaluate("window.encoded") == ["a photo of a bird"]
    text.locator("#filter summary").click()
    text.fill("#tq", "Fung")
    text.get_by_role("button", name="Leave out Fungi (Fungi)").click()
    text.wait_for_function("document.querySelectorAll('.card').length === 197")
    assert "1 outside the taxon filter" in text.locator("#dropped").inner_text()
    assert page.errors == [] and text.errors == []


def test_two_subject_query_searches_each_and_says_so(open_page):
    page = open_page("#q=a+bird+eating+a+frog")
    page.wait_for_selector(".card")
    # the whole sentence and each subject are encoded; the same fake vector keeps the hits identical
    assert page.evaluate("window.encoded") == [
        "a photo of a bird eating a frog",
        "a photo of a bird",
        "a photo of a frog",
    ]
    assert (
        page.locator("#how").inner_text().startswith("Each photo matches all of: a bird, a frog.")
    )
    page.fill("#q", "a bird")
    page.press("#q", "Enter")
    page.wait_for_function("document.getElementById('how').textContent === ''")
    assert page.errors == []


def test_text_search_without_encoder_asks_before_downloading(open_page):
    page = open_page("#q=a+bird", fake_encoder=False)
    page.wait_for_function("document.getElementById('status').textContent.includes('went wrong')")
    assert page.locator(".card").count() == 0
    # fixture manifest carries no text encoder: clear message, no download attempted
    assert "no text search model" in page.locator("#status").inner_text()


def test_layout_has_no_horizontal_scroll_at_375px(open_page):
    page = open_page("#q=a+bird", width=375)
    page.wait_for_selector(".card")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    columns = page.evaluate(
        "getComputedStyle(document.getElementById('grid')).gridTemplateColumns.split(' ').length"
    )
    assert columns == 2
    assert page.errors == []


@pytest.mark.parametrize(
    "query", ["Lobaria+pulmonaria", "LUNGWORT", "a+photo+of+lobaria++pulmonaria"]
)
def test_taxon_query_uses_precomputed_vector_not_the_encoder(open_page, site, query):
    _, ref = site
    page = open_page(f"#q={query}")
    page.wait_for_selector(".card")
    # sorted names: Acer=1, Lobaria pulmonaria=2, Quercus garryana=3 -> reference query 2
    want = ref["searches"][-1]["ids"][2]
    assert card_ids(page)[:5] == want[:5]
    assert page.evaluate("window.encoded") == []
    assert page.errors == []


def test_unknown_query_still_uses_the_encoder_when_taxa_exist(open_page):
    page = open_page("#q=a+bird")
    page.wait_for_selector(".card")
    assert page.evaluate("window.encoded") == ["a photo of a bird"]
    assert page.errors == []
