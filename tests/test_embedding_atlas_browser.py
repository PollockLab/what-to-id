"""Browser task gates using real generated pages and a deterministic map boundary.

The map adapter isolates tile/WebGL availability, while clicks execute the production
map handler. These tests do not establish live basemap rendering or human usability.
"""

import os
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import pytest

from what_to_id.embedding_atlas import build

MAP_ADAPTER = """
class Bounds {
  extend(){return this;}
  getWest(){return -130;}getSouth(){return 45;}
  getEast(){return -110;}getNorth(){return 60;}
}
class TestMap {
  constructor(){this.handlers={};this.sources={};window.testMap=this;
    const canvas=document.createElement('canvas');canvas.tabIndex=0;
    document.getElementById('map').append(canvas);this.canvas=canvas;
    setTimeout(()=>this.handlers.load?.(),0);}
  addControl(){}on(name,layer,fn){if(typeof layer==='function')this.handlers[name]=layer;}
  addSource(name,source){this.sources[name]={...source,setData:data=>this.sources[name].data=data};}
  addLayer(){}getSource(name){return this.sources[name];}
  getCanvas(){return this.canvas;}getBounds(){return new Bounds();}getZoom(){return 4;}
  fitBounds(){}flyTo(){}resize(){}project(){return {x:100,y:100};}
  queryRenderedFeatures(){return this.hits||[];}
  clickIds(indices){this.hits=indices.map(index=>({properties:{index}}));
    this.handlers.click({point:{x:100,y:100},lngLat:{lng:-123,lat:49}});}
}
window.maplibregl={Map:TestMap,LngLatBounds:Bounds,NavigationControl:class {}};
"""


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
def atlas_site(tmp_path_factory):
    directory = tmp_path_factory.mktemp("atlas-browser")
    rows = []
    for group, count, offset in [("Aves", 18, 100), ("Plantae", 4, 200)]:
        ids = np.arange(offset, offset + count)
        rng = np.random.default_rng(offset)
        vectors = rng.normal(size=(count, 6)).astype("f4")
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        np.savez(directory / f"{group}.npz", ids=ids, E=vectors, backbone="test-encoder")
        for ident in ids:
            rows.append(
                dict(
                    id=int(ident),
                    iconic_taxon=group,
                    lon=-123.0,
                    lat=49.0,
                    taxon_name=f"Recorded taxon {ident}",
                    photo_url=f"https://static.inaturalist.org/photos/{ident}/medium.jpg",
                    observed_on="2026-09-11",
                )
            )
    pool = directory / "pool.parquet"
    pd.DataFrame(rows).to_parquet(pool)
    output = directory / "site"
    build(
        pool,
        str(directory / "{group}.npz"),
        output,
        snapshot_date="2026-09-11",
        model_view_specs=["Test=embeddings.html", "Other=other/embeddings.html"],
        current_label="Test",
        reference_embedding_pattern=str(directory / "{group}.npz"),
        reference_pool_path=pool,
    )
    return output


@pytest.fixture
def open_atlas(browser, atlas_site):
    pages = []

    def open_page(width=1440, fragment="#group=Aves&id=100"):
        page = browser.new_page(viewport={"width": width, "height": 900})
        pages.append(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request):
            url = request.request.url
            path = urlparse(url).path
            if "maplibre-gl.js" in path:
                request.fulfill(body=MAP_ADAPTER, content_type="text/javascript")
            elif "maplibre-gl.css" in path:
                request.fulfill(body="", content_type="text/css")
            elif "/photos/" in path:
                request.fulfill(
                    body='<svg xmlns="http://www.w3.org/2000/svg" width="300" '
                    'height="240"><rect width="300" height="240" '
                    'fill="#78a777"/></svg>',
                    content_type="image/svg+xml",
                )
            else:
                file = atlas_site / path.lstrip("/")
                if file.is_file():
                    request.fulfill(path=str(file))
                else:
                    request.fulfill(status=404, body="Not found")

        page.route("**/*", route)
        page.goto("https://atlas.test/embeddings.html" + fragment)
        page.locator('[data-focal-id="100"]').wait_for()
        page.wait_for_function("window.testMap && testMap.sources.observations")
        assert errors == []
        return page, errors

    yield open_page
    for page in pages:
        page.close()


@pytest.mark.parametrize("width", [390, 820, 1440])
def test_photo_space_is_visible_before_inspector_and_can_return_to_map(open_atlas, width):
    page, errors = open_atlas(width)
    assert page.locator("#projection-pane").is_hidden()
    page.get_by_role("button", name="Photo space", exact=True).click()
    page.wait_for_function("document.activeElement.id === 'projection-pane'")
    heading = page.locator("#projection-pane h2").bounding_box()
    inspector = page.locator(".inspector").bounding_box()
    assert heading and 0 <= heading["y"] < 300
    assert page.locator("#plot").is_visible()
    assert page.locator("#geography-pane").is_hidden()
    assert page.evaluate("document.activeElement.id") == "projection-pane"
    if width == 390:
        assert heading["y"] < inspector["y"]
    page.get_by_role("button", name="Map", exact=True).click()
    assert page.locator("#geography-pane").is_visible()
    assert page.locator("#projection-pane").is_hidden()
    page.get_by_role("button", name="Split", exact=True).click()
    assert page.locator("#geography-pane").is_visible()
    assert page.locator("#projection-pane").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []


@pytest.mark.parametrize("width", [390, 1440])
def test_compare_preserves_focal_then_promotes_with_back(open_atlas, width):
    page, errors = open_atlas(width)
    trigger = page.locator(".neighbors button").first
    first_candidate = trigger.get_attribute("data-observation-id")
    initial_hash = page.evaluate("location.hash")
    trigger.click()
    dialog = page.get_by_role("dialog", name="Compare photos", exact=True)
    assert dialog.is_visible()
    assert page.locator("#focal-figure").get_by_text("Observation 100", exact=False).is_visible()
    assert page.locator("#candidate-figure a").get_attribute("href").endswith(first_candidate)
    page.get_by_role("button", name="Next match", exact=True).click()
    next_candidate = page.locator("#candidate-figure a").get_attribute("href").rsplit("/", 1)[1]
    assert next_candidate != first_candidate
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert page.evaluate("location.hash") == initial_hash
    page.keyboard.press("Escape")
    assert dialog.is_hidden()
    assert trigger.evaluate("element => document.activeElement === element")
    trigger.click()
    page.get_by_role("button", name="Use as focal photo", exact=True).click()
    assert page.locator(f'[data-focal-id="{first_candidate}"]').count() == 1
    assert page.evaluate("location.hash").endswith("id=" + first_candidate)
    page.go_back()
    page.locator('[data-focal-id="100"]').wait_for()
    assert errors == []


def test_map_location_chooser_exposes_all_ids_without_duplicate_world_copies(open_atlas):
    page, errors = open_atlas()
    page.evaluate("testMap.clickIds([...Array(18).keys(),0,1,2])")
    dialog = page.get_by_role("dialog", name="18 observations near this point")
    assert dialog.is_visible()
    buttons = page.locator("#location-photos button")
    assert buttons.count() == 18
    ids = buttons.evaluate_all("elements => elements.map(e => e.dataset.observationId)")
    assert ids == [str(i) for i in range(100, 118)]
    for ident in ids:
        if not dialog.is_visible():
            page.evaluate("testMap.clickIds([...Array(18).keys(),0,1,2])")
        page.locator(f'#location-photos button[data-observation-id="{ident}"]').click()
        assert page.locator(f'[data-focal-id="{ident}"]').count() == 1
    assert errors == []


def test_filtered_empty_search_recovers_without_changing_focal_or_rankings(open_atlas):
    page, errors = open_atlas(390)
    initial_ids = page.locator(".neighbors button").evaluate_all(
        "elements => elements.map(e => e.dataset.observationId)"
    )
    page.get_by_role("searchbox").fill("nonexistent-name")
    assert page.locator("#record").is_disabled()
    assert "0 matches" in page.locator("#search-status").inner_text()
    page.get_by_role("button", name="Clear search and filters", exact=True).click()
    assert page.locator("#record").is_enabled()
    assert page.locator("#record option").count() == 18
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert (
        page.locator(".neighbors button").evaluate_all(
            "elements => elements.map(e => e.dataset.observationId)"
        )
        == initial_ids
    )
    assert errors == []


def test_unfamiliar_first_preserves_specialist_search_and_empty_scope(open_atlas):
    page, errors = open_atlas()
    page.get_by_role("searchbox").fill("107")
    page.locator("#advanced summary").first.click()
    page.locator("#unfamiliar").click()
    assert page.get_by_role("searchbox").input_value() == "107"
    assert page.locator('[data-focal-id="107"]').count() == 1
    assert "1 match" in page.locator("#search-status").inner_text()
    page.get_by_role("searchbox").fill("nonexistent-name")
    assert page.locator("#unfamiliar").is_disabled()
    assert page.locator('[data-focal-id="107"]').count() == 1
    assert errors == []


def test_deep_link_and_cross_encoder_links_keep_focal_id_and_brush_filters_work(open_atlas):
    page, errors = open_atlas()
    page.locator("#record").select_option("7")
    assert page.evaluate("location.hash") == "#group=Aves&id=107"
    page.reload()
    page.locator('[data-focal-id="107"]').wait_for()
    page.locator("#advanced summary").first.click()
    assert (
        page.get_by_role("link", name="Other", exact=True)
        .get_attribute("href")
        .endswith("other/embeddings.html#group=Aves&id=107")
    )
    page.get_by_role("button", name="Photo space", exact=True).click()
    page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#only-brushed").check()
    assert page.locator("#record option").count() == 1
    assert page.locator("#record option").inner_text().endswith("107")
    page.get_by_role("button", name="Clear selection", exact=True).click()
    assert page.locator("#record option").count() == 18
    assert errors == []


def test_group_change_resets_brush_and_keeps_photo_space_and_representation_controls(open_atlas):
    page, errors = open_atlas(820)
    page.get_by_role("button", name="Photo space", exact=True).click()
    page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#only-brushed").check()
    page.locator("#group").select_option("Plantae")
    page.locator('[data-focal-id="200"]').wait_for()
    assert page.locator("#missing-selection").is_hidden()
    assert "requested=" not in page.url
    assert not page.locator("#only-brushed").is_checked()
    assert page.locator("#record option").count() == 4
    assert page.locator("#projection-pane").is_visible()
    page.locator("#advanced summary").first.click()
    page.locator("#color-mode").select_option("representation")
    assert "RGB" in page.locator("#legend").inner_text()
    page.locator("#plot").focus()
    assert page.locator("#plot-preview").is_visible()
    page.keyboard.press("ArrowRight")
    assert page.locator("#plot-preview").is_visible()
    assert errors == []


def test_explicit_missing_observation_link_keeps_the_requested_id(open_atlas):
    page, errors = open_atlas(fragment="#group=Aves&id=99999")
    assert page.locator("#missing-selection").is_visible()
    assert "99999" in page.locator("#missing-selection").inner_text()
    assert "requested=99999" in page.url
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert errors == []


def test_failed_group_load_has_explicit_error_and_can_recover(open_atlas):
    page, errors = open_atlas()
    page.route("**/embeddings-data/Plantae.json", lambda route: route.fulfill(status=503))
    page.locator("#group").select_option("Plantae")
    page.get_by_role("alert").wait_for()
    assert "Could not load this life group" in page.get_by_role("alert").inner_text()
    page.locator("#group").select_option("Aves")
    page.wait_for_function("document.getElementById('error').hidden")
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert errors == []


@pytest.mark.parametrize("side", ["focal", "candidate"])
def test_mobile_photo_inspection_uses_full_width_and_returns_to_same_comparison(open_atlas, side):
    page, errors = open_atlas(390)

    def photo_route(route):
        landscape = "/photos/100/" in route.request.url
        width, height = (600, 384) if landscape else (400, 600)
        route.fulfill(
            body=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}"><rect width="{width}" height="{height}" '
            'fill="#78a777"/></svg>',
            content_type="image/svg+xml",
        )

    page.route("**/photos/**", photo_route)
    page.reload()
    page.locator('[data-focal-id="100"]').wait_for()
    trigger = page.locator(".neighbors button").first
    trigger.click()
    page.get_by_role("button", name="Next match", exact=True).click()
    candidate_href = page.locator("#candidate-figure a").get_attribute("href")
    match_status = page.locator("#comparison-status").inner_text()
    focal_hash = page.evaluate("location.hash")
    figure = page.locator(f"#{side}-figure")
    photo_button = figure.get_by_role("button", name="Inspect", exact=False)
    image = figure.locator("img")
    image.evaluate("image => image.decode()")
    before_width = image.bounding_box()["width"]
    frozen_src = image.get_attribute("src")
    photo_button.click()
    assert page.get_by_role("dialog", name="Inspect", exact=False).is_visible()
    after = image.bounding_box()
    assert after["width"] >= 320 and after["width"] >= 1.9 * before_width
    natural_width, natural_height = image.evaluate(
        "image => [image.naturalWidth,image.naturalHeight]"
    )
    assert after["width"] / after["height"] == pytest.approx(
        natural_width / natural_height, rel=0.01
    )
    assert after["height"] <= 900 * 0.62 + 1
    assert image.get_attribute("src") == frozen_src
    assert figure.get_by_role("link", name="Complete observation on iNaturalist").is_visible()
    assert page.evaluate("location.hash") == focal_hash
    assert page.locator("#candidate-figure a").get_attribute("href") == candidate_href
    assert page.locator("#comparison-status").inner_text() == match_status
    page.keyboard.press("ArrowRight")
    assert page.locator("#candidate-figure a").get_attribute("href") == candidate_href
    page.keyboard.press("Escape")
    assert page.get_by_role("dialog", name="Compare photos", exact=True).is_visible()
    assert photo_button.evaluate("button => document.activeElement === button")
    assert page.locator("#comparison-status").inner_text() == match_status
    assert page.locator("#candidate-figure a").get_attribute("href") == candidate_href
    photo_button.click()
    page.get_by_role("button", name="Back to comparison", exact=True).click()
    assert photo_button.evaluate("button => document.activeElement === button")
    page.keyboard.press("Escape")
    assert page.locator("#photo-comparison").is_hidden()
    assert trigger.evaluate("button => document.activeElement === button")
    assert page.evaluate("location.hash") == focal_hash
    assert errors == []
