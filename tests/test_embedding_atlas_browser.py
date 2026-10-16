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


def test_back_restores_missing_request_notice_and_cross_model_intent(open_atlas):
    page, errors = open_atlas(fragment="#group=Aves&id=99999")
    initial_url = page.url
    page.locator("#record").select_option("7")
    assert page.locator("#missing-selection").is_hidden()
    page.go_back()
    page.wait_for_function("location.hash.includes('requested=99999')")
    assert page.url == initial_url
    assert page.locator("#missing-selection").is_visible()
    page.locator("#advanced summary").first.click()
    assert (
        page.get_by_role("link", name="Other", exact=True)
        .get_attribute("href")
        .endswith("#group=Aves&id=99999")
    )
    assert errors == []


def test_promoting_a_match_outside_search_preserves_specialist_scope(open_atlas):
    page, errors = open_atlas()
    search = page.get_by_role("searchbox")
    search.fill("107")
    search.press("Enter")
    page.locator('[data-focal-id="107"]').wait_for()
    trigger = page.locator(".neighbors button").first
    candidate = trigger.get_attribute("data-observation-id")
    trigger.click()
    page.get_by_role("button", name="Use as focal photo", exact=True).click()
    assert page.locator(f'[data-focal-id="{candidate}"]').count() == 1
    assert search.input_value() == "107"
    assert "1 match" in page.locator("#search-status").inner_text()
    assert "outside these results" in page.locator("#record option").first.inner_text()
    assert errors == []


def test_back_closes_comparison_before_restoring_the_previous_focal(open_atlas):
    page, errors = open_atlas()
    page.locator("#record").select_option("7")
    page.locator(".neighbors button").first.click()
    assert "Observation 107" in page.locator("#focal-figure").inner_text()
    page.go_back()
    page.locator('[data-focal-id="100"]').wait_for()
    assert page.locator("#photo-comparison").is_hidden()
    assert page.locator("#location-chooser").is_hidden()
    page.locator(".neighbors button").first.click()
    assert "Observation 100" in page.locator("#focal-figure").inner_text()
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


@pytest.mark.parametrize("width", [390, 1440])
def test_layout_switch_preserves_focal_rankings_filters_and_brushed_observation_ids(
    open_atlas, atlas_site, width
):
    import json

    from what_to_id.atlas_projection import projection_fidelity

    page, errors = open_atlas(width)
    payload = json.loads((atlas_site / "embeddings-data/Aves.json").read_text())
    records = payload["records"]
    neighbors = np.array([[index for index, _ in record["neighbors"]] for record in records])
    focal_neighbors = neighbors[0].tolist()
    non_neighbors = [index for index in range(1, len(records)) if index not in focal_neighbors]
    primary_order = focal_neighbors + non_neighbors
    pca_order = non_neighbors + focal_neighbors
    for index, record in enumerate(records):
        record["xy"] = [0, 0] if index == 0 else [primary_order.index(index) + 1, index % 3]
        record["pca_xy"] = [0, 0] if index == 0 else [index % 3, pca_order.index(index) + 1]
    payload["projection"] = "t-SNE"
    payload["projection_metadata"] = {"method": "t-SNE", "requested_method": "t-SNE"}
    for coordinate_key, quality_key, count_key in [
        ("xy", "projection_quality", "projection_match_count"),
        ("pca_xy", "pca_projection_quality", "pca_projection_match_count"),
    ]:
        quality, counts = projection_fidelity(
            np.array([record[coordinate_key] for record in records], dtype=float), neighbors
        )
        payload[quality_key] = quality
        for record, count in zip(records, counts, strict=True):
            record[count_key] = int(count)
    assert records[0]["projection_match_count"] != records[0]["pca_projection_match_count"]
    page.route(
        "**/embeddings-data/Aves.json",
        lambda route: route.fulfill(json=payload),
    )
    page.reload()
    page.locator('[data-focal-id="100"]').wait_for()
    page.get_by_role("button", name="Photo space", exact=True).click()
    layout = page.get_by_label("Layout", exact=True)
    assert layout.is_visible() and layout.input_value() == "primary"
    assert layout.locator("option").all_text_contents() == [
        "Local neighborhoods (t-SNE)",
        "Linear overview (PCA)",
    ]
    page.get_by_role("searchbox").fill("Recorded taxon")
    page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#only-brushed").check()
    initial_hash = page.evaluate("location.hash")
    initial_ids = page.locator(".neighbors button").evaluate_all(
        "buttons => buttons.map(button => button.dataset.observationId)"
    )
    initial_points = page.locator("#plot circle").evaluate_all(
        "circles => circles.map(circle => [circle.dataset.observationId,"
        "circle.getAttribute('cx'),circle.getAttribute('cy')])"
    )
    assert (
        f"contain {records[0]['projection_match_count']}"
        in page.locator("#projection").inner_text()
    )
    page.locator("#plot-mode").select_option("brush")
    box = page.locator("#plot").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 3, box["y"] + box["height"] / 3)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 3 + 25, box["y"] + box["height"] / 3 + 20)
    page.locator("#brush-rectangle").wait_for()
    layout.select_option("pca")
    page.mouse.up()
    assert page.locator("#brush-rectangle").count() == 0
    assert page.locator("#only-brushed").is_checked()
    matching_options = page.locator("#record option").filter(has_text="Recorded taxon")
    assert matching_options.count() == 1
    assert matching_options.inner_text().endswith("100")
    assert page.evaluate("location.hash") == initial_hash
    assert (
        page.locator(".neighbors button").evaluate_all(
            "buttons => buttons.map(button => button.dataset.observationId)"
        )
        == initial_ids
    )
    pca_points = page.locator("#plot circle").evaluate_all(
        "circles => circles.map(circle => [circle.dataset.observationId,"
        "circle.getAttribute('cx'),circle.getAttribute('cy')])"
    )
    assert pca_points != initial_points
    assert (
        f"contain {records[0]['pca_projection_match_count']}"
        in page.locator("#projection").inner_text()
    )
    assert "PCA retains" in page.locator("#projection").inner_text()
    layout.select_option("primary")
    assert "Local t-SNE layout" in page.locator("#projection").inner_text()
    assert (
        page.locator("#plot circle").evaluate_all(
            "circles => circles.map(circle => [circle.dataset.observationId,"
            "circle.getAttribute('cx'),circle.getAttribute('cy')])"
        )
        == initial_points
    )
    assert errors == []


def test_pca_only_sample_has_no_layout_choice(open_atlas):
    page, errors = open_atlas()
    page.get_by_role("button", name="Photo space", exact=True).click()
    assert page.locator("#layout-control").is_hidden()
    assert "PCA retains" in page.locator("#projection").inner_text()
    assert errors == []


def identify_batch_ids(page):
    from urllib.parse import parse_qs

    result = []
    for href in page.locator("#identify-batches a").evaluate_all(
        "links => links.map(link => link.href)"
    ):
        url = urlparse(href)
        assert url.scheme == "https" and url.netloc == "www.inaturalist.org"
        assert url.path == "/observations/identify"
        params = parse_qs(url.query)
        result.extend(int(ident) for ident in params.pop("id")[0].split(","))
        assert params == {
            "quality_grade": ["needs_id"],
            "reviewed": ["false"],
            "place_id": ["any"],
            "per_page": ["200"],
        }
    return result


@pytest.mark.parametrize("width", [390, 1440])
def test_identify_handoff_uses_exact_search_ids_and_empty_results_recover(open_atlas, width):
    page, errors = open_atlas(width)
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    action = page.get_by_role("button", name="Identify these results", exact=False)
    page.get_by_role("searchbox").fill("107")
    assert action.inner_text() == "Identify these results (1)"
    initial_hash = page.evaluate("location.hash")
    initial_tabs = len(page.context.pages)
    action.click()
    dialog = page.get_by_role("dialog", name="Identify these results", exact=True)
    assert dialog.is_visible()
    assert identify_batch_ids(page) == [107]
    assert "2026-09-11" in page.locator("#identify-note").inner_text()
    assert "live count may be smaller" in dialog.inner_text()
    assert page.evaluate("location.hash") == initial_hash
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert len(page.context.pages) == initial_tabs
    page.keyboard.press("Escape")
    assert dialog.is_hidden()
    assert action.evaluate("button => document.activeElement === button")
    assert page.get_by_role("searchbox").input_value() == "107"
    page.get_by_role("searchbox").fill("no-such-sampled-observation")
    assert action.is_disabled() and action.inner_text() == "Identify these results (0)"
    page.get_by_role("button", name="Clear search and filters", exact=True).click()
    assert action.is_enabled() and action.inner_text() == "Identify these results (18)"
    assert not [url for url in requests if "api.inaturalist.org" in url]
    assert errors == []


def test_identify_handoff_intersects_brush_search_and_map_without_changing_state(open_atlas):
    page, errors = open_atlas(390)
    page.get_by_role("button", name="Photo space", exact=True).click()
    page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#record").select_option("7")
    page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#only-brushed").check()
    page.get_by_role("searchbox").fill("Recorded taxon")
    action = page.get_by_role("button", name="Identify these results", exact=False)
    assert action.inner_text() == "Identify these results (2)"
    initial_hash = page.evaluate("location.hash")
    original_rank_ids = page.locator(".neighbors button").evaluate_all(
        "buttons => buttons.map(button => button.dataset.observationId)"
    )
    action.click()
    assert identify_batch_ids(page) == [107, 100]
    assert page.evaluate("location.hash") == initial_hash
    assert page.locator('[data-focal-id="107"]').count() == 1
    page.get_by_role("button", name="Close", exact=True).click()
    assert page.locator("#only-brushed").is_checked()
    assert page.get_by_role("searchbox").input_value() == "Recorded taxon"
    assert page.locator("#group").input_value() == "Aves"
    assert page.locator(".workspace").get_attribute("data-view") == "photo"
    assert (
        page.locator(".neighbors button").evaluate_all(
            "buttons => buttons.map(button => button.dataset.observationId)"
        )
        == original_rank_ids
    )
    page.locator("#advanced summary").first.click()
    page.evaluate("""testMap.getBounds=()=>({getWest:()=>10,getSouth:()=>10,
        getEast:()=>11,getNorth:()=>11})""")
    page.locator("#only-view").check()
    assert action.is_disabled() and action.inner_text() == "Identify these results (0)"
    page.locator("#only-view").uncheck()
    assert action.is_enabled() and action.inner_text() == "Identify these results (2)"
    assert page.evaluate("location.hash") == initial_hash
    assert errors == []


def test_identify_handoff_is_disabled_after_failed_group_load_then_recovers(open_atlas):
    page, errors = open_atlas()
    action = page.get_by_role("button", name="Identify these results", exact=False)
    assert action.is_enabled()
    page.route("**/embeddings-data/Plantae.json", lambda route: route.fulfill(status=503))
    page.locator("#group").select_option("Plantae")
    page.get_by_role("alert").wait_for()
    assert action.is_disabled()
    page.locator("#group").select_option("Aves")
    page.wait_for_function("document.getElementById('error').hidden")
    assert action.is_enabled()
    assert errors == []


@pytest.fixture(scope="module")
def taxonomy_site(tmp_path_factory):
    import json

    directory = tmp_path_factory.mktemp("atlas-taxonomy-browser")
    # A misleading recorded name is unrelated; ordinary species names descend
    # through the fixture tree. The hornwort branch deliberately ends above a known preset root.
    plants = [
        (100, 20, "Mosses", -123),
        (101, 11, "Atrichum undulatum", -123),
        (102, 12, "Pellia epiphylla", -123),
        (103, 13, "Different recorded label", -123),
        (104, 99, "Mosses", -123),
        (105, 21, "Another unrelated plant", -123),
        (106, 14, "Out-of-map moss", -100),
        (107, 15, "Extra moss", -123),
    ]
    fungi = [
        (200, 31, "A lichen species", -123),
        (201, 32, "Another fungus", -123),
        (202, 98, "Unplaced fungus", -123),
    ]
    rows = []
    for group, observations in [("Plantae", plants), ("Fungi", fungi)]:
        vectors = (
            np.random.default_rng(len(observations))
            .normal(size=(len(observations), 8))
            .astype("f4")
        )
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        np.savez(
            directory / f"{group}.npz",
            ids=np.array([r[0] for r in observations]),
            E=vectors,
            backbone="fixture",
        )
        for ident, taxon_id, name, longitude in observations:
            rows.append(
                dict(
                    id=ident,
                    taxon_id=taxon_id,
                    iconic_taxon=group,
                    lon=longitude,
                    lat=49,
                    taxon_name=name,
                    photo_url="",
                    observed_on="2026-09-11",
                )
            )
    pool = directory / "pool.parquet"
    pd.DataFrame(rows).to_parquet(pool)
    parents = {
        1: None,
        20: 1,
        21: 1,
        11: 311249,
        12: 64615,
        13: 56327,
        14: 311249,
        15: 311249,
        311249: 1,
        64615: 1,
        56327: 999,
        31: 54743,
        32: 1,
        54743: 1,
    }
    taxonomy = directory / "taxonomy.json"
    taxonomy.write_text(
        json.dumps(
            {
                "taxa": {
                    str(k): [parent, "Cached taxon", "", "taxon"] for k, parent in parents.items()
                }
            }
        )
    )
    output = directory / "site"
    build(
        pool,
        str(directory / "{group}.npz"),
        output,
        snapshot_date="2026-09-11",
        taxonomy_path=taxonomy,
    )
    return output


@pytest.fixture
def open_taxonomy_atlas(browser, taxonomy_site):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def route(request):
        path = urlparse(request.request.url).path
        if "maplibre-gl.js" in path:
            request.fulfill(body=MAP_ADAPTER, content_type="text/javascript")
        elif "maplibre-gl.css" in path:
            request.fulfill(body="", content_type="text/css")
        else:
            file = taxonomy_site / path.lstrip("/")
            if file.is_file():
                request.fulfill(path=str(file))
            else:
                request.fulfill(status=404, body="Not found")

    page.route("**/*", route)
    page.goto("https://taxonomy-atlas.test/embeddings.html#group=Plantae&id=100")
    page.locator('[data-focal-id="100"]').wait_for()
    page.wait_for_function("window.testMap && testMap.sources.observations")
    assert errors == []
    yield page, errors
    page.close()


def _scope_result_ids(page):
    return page.locator("#record option").evaluate_all(
        "options=>options.filter(o=>o.value!=='').map(o=>Number(o.textContent.split(' · ').pop()))"
    )


def test_verified_taxon_scope_excludes_name_lookalikes_and_retains_focal_and_rankings(
    open_taxonomy_atlas,
):
    page, errors = open_taxonomy_atlas
    scope = page.get_by_role("combobox", name="Taxon scope", exact=True)
    assert scope.input_value() == ""
    assert "Bryophytes · 5 ancestry matches" in scope.inner_text()
    assert "Lichen-forming groups (approximate) · 0 ancestry matches" in scope.inner_text()
    before = page.locator(".neighbors button").evaluate_all(
        "buttons=>buttons.map(b=>b.dataset.observationId)"
    )
    scope.select_option("0")
    assert _scope_result_ids(page) == [101, 102, 103, 106, 107]
    assert page.locator('[data-focal-id="100"]').count() == 1
    message = page.locator("#taxon-scope-message").inner_text()
    assert "1 observation has unknown scope membership from incomplete ancestry" in message
    assert "focal photo stays selected outside" in message
    assert "full life-group sample" in message
    assert (
        page.locator(".neighbors button").evaluate_all(
            "buttons=>buttons.map(b=>b.dataset.observationId)"
        )
        == before
    )
    page.get_by_role("searchbox").fill("Mosses")
    assert page.locator("#record").is_disabled()
    page.get_by_role("searchbox").fill("Atrichum")
    assert _scope_result_ids(page) == [101]
    page.get_by_role("searchbox").fill("")
    page.get_by_role("button", name="Photo space", exact=True).click()
    assert (
        page.locator('#plot circle[data-observation-id="105"]').get_attribute("opacity") == "0.12"
    )
    assert (
        page.locator('#plot circle[data-observation-id="104"]').get_attribute("opacity") == "0.12"
    )
    assert page.locator('#plot circle[data-observation-id="100"]').get_attribute("opacity") == "1"
    opacities = page.evaluate(
        "Object.fromEntries(testMap.sources.observations.data.features.map(f=>[data.records[f.properties.index].id,f.properties.opacity]))"
    )
    assert opacities["105"] == 0.12 and opacities["104"] == 0.12 and opacities["100"] == 1
    assert "Dimmed: outside the selected ancestry scope" in page.locator("#legend").inner_text()
    assert errors == []


def test_taxon_scope_intersects_search_brush_and_map_and_reset_recovers(open_taxonomy_atlas):
    page, errors = open_taxonomy_atlas
    page.get_by_role("button", name="Photo space", exact=True).click()
    for index in [2, 6]:
        page.locator("#record").select_option(str(index))
        page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#record").select_option("0")
    page.get_by_role("combobox", name="Taxon scope", exact=True).select_option("0")
    page.locator("#only-brushed").check()
    assert _scope_result_ids(page) == [102, 106]
    page.locator("#advanced summary").first.click()
    page.locator("#only-view").check()
    assert _scope_result_ids(page) == [102]
    page.get_by_role("searchbox").fill("Pellia")
    assert _scope_result_ids(page) == [102]
    assert page.locator('[data-focal-id="100"]').count() == 1
    page.get_by_role("button", name="Clear taxon scope", exact=True).click()
    assert page.get_by_role("combobox", name="Taxon scope", exact=True).input_value() == ""
    assert page.locator("#only-brushed").is_checked() and page.locator("#only-view").is_checked()
    assert page.get_by_role("searchbox").input_value() == "Pellia"
    assert _scope_result_ids(page) == [102]
    page.get_by_role("button", name="Clear search and filters", exact=True).click()
    assert _scope_result_ids(page) == list(range(100, 108))
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert errors == []


def test_empty_taxon_scope_recovers_and_group_changes_clear_stale_scope(open_taxonomy_atlas):
    page, errors = open_taxonomy_atlas
    page.get_by_role("combobox", name="Taxon scope", exact=True).select_option("1")
    assert page.locator("#record").is_disabled()
    assert "0 matches" in page.locator("#search-status").inner_text()
    assert (
        "2 observations have unknown scope membership from incomplete ancestry"
        in page.locator("#taxon-scope-message").inner_text()
    )
    page.get_by_role("button", name="Clear taxon scope", exact=True).click()
    assert _scope_result_ids(page) == list(range(100, 108))
    assert page.locator('[data-focal-id="100"]').count() == 1
    page.get_by_role("combobox", name="Taxon scope", exact=True).select_option("0")
    page.locator("#group").select_option("Fungi")
    page.locator('[data-focal-id="200"]').wait_for()
    assert page.get_by_role("combobox", name="Taxon scope", exact=True).input_value() == ""
    assert _scope_result_ids(page) == [200, 201, 202]
    page.get_by_role("combobox", name="Taxon scope", exact=True).select_option("1")
    assert _scope_result_ids(page) == [200]
    assert "approximate" in page.locator("#taxon-scope-message").inner_text()
    assert errors == []


def test_build_without_taxonomy_has_no_expert_scope_controls_or_inference(open_atlas):
    page, errors = open_atlas()
    assert page.locator("#taxon-scope-control").is_hidden()
    assert page.locator("#taxon-scope-status").is_hidden()
    assert page.locator("#taxon-scope").is_disabled()
    assert _scope_result_ids(page) == list(range(100, 118))
    assert errors == []


def test_mobile_taxon_scope_is_accessible_and_clear_action_retains_focal(open_taxonomy_atlas):
    page, errors = open_taxonomy_atlas
    page.set_viewport_size({"width": 390, "height": 900})
    scope = page.get_by_role("combobox", name="Taxon scope", exact=True)
    scope.select_option("0")
    assert scope.is_visible()
    assert page.get_by_role("button", name="Clear taxon scope", exact=True).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Clear taxon scope", exact=True).click()
    assert scope.input_value() == ""
    assert scope.evaluate("element=>document.activeElement===element")
    assert page.locator('[data-focal-id="100"]').count() == 1
    assert errors == []


def test_identify_intersects_ancestry_with_search_brush_and_map(open_taxonomy_atlas):
    page, errors = open_taxonomy_atlas
    page.get_by_role("combobox", name="Taxon scope", exact=True).select_option("0")
    page.get_by_role("button", name="Identify these results (5)", exact=True).click()
    assert set(identify_batch_ids(page)) == {101, 102, 103, 106, 107}
    assert "taxon scope" in page.locator("#identify-dialog").inner_text()
    page.locator("#close-identify").click()
    page.get_by_role("button", name="Photo space", exact=True).click()
    for index in [2, 6]:
        page.locator("#record").select_option(str(index))
        page.get_by_role("button", name="Add selected photo", exact=True).click()
    page.locator("#only-brushed").check()
    page.get_by_role("button", name="Identify these results (2)", exact=True).click()
    assert set(identify_batch_ids(page)) == {102, 106}
    page.locator("#close-identify").click()
    page.locator("#advanced summary").first.click()
    page.locator("#only-view").check()
    page.get_by_role("searchbox").fill("Pellia")
    page.get_by_role("button", name="Identify these results (1)", exact=True).click()
    assert identify_batch_ids(page) == [102]
    assert page.locator('[data-focal-id="106"]').count() == 1
    page.locator("#close-identify").click()
    page.get_by_role("searchbox").fill("Mosses")
    assert page.locator("#identify-results").is_disabled()
    assert errors == []


def test_outside_listed_lichen_scope_is_approximate_and_recovers_without_unknown_ids(
    open_taxonomy_atlas,
):
    page, errors = open_taxonomy_atlas
    page.locator("#group").select_option("Fungi")
    page.locator('[data-focal-id="200"]').wait_for()
    scope = page.get_by_role("combobox", name="Taxon scope", exact=True)
    assert (
        "Outside listed lichen-forming groups (approximate) · 1 ancestry matches"
        in scope.inner_text()
    )
    before = page.locator(".neighbors button").evaluate_all(
        "buttons=>buttons.map(b=>b.dataset.observationId)"
    )
    scope.select_option("2")
    assert _scope_result_ids(page) == [201]
    assert page.evaluate("activeTaxonScope().exclude") is True
    assert page.locator('[data-focal-id="200"]').count() == 1
    assert (
        "1 observation has unknown scope membership"
        in page.locator("#taxon-scope-message").inner_text()
    )
    page.get_by_role("button", name="Identify these results (1)", exact=True).click()
    assert identify_batch_ids(page) == [201]
    page.locator("#close-identify").click()
    page.get_by_role("searchbox").fill("Unplaced")
    assert page.locator("#record").is_disabled()
    assert page.locator("#identify-results").is_disabled()
    page.get_by_role("button", name="Clear search and filters", exact=True).click()
    assert scope.input_value() == ""
    assert _scope_result_ids(page) == [200, 201, 202]
    assert (
        page.locator(".neighbors button").evaluate_all(
            "buttons=>buttons.map(b=>b.dataset.observationId)"
        )
        == before
    )
    scope.select_option("2")
    page.locator("#group").select_option("Plantae")
    page.locator('[data-focal-id="100"]').wait_for()
    assert scope.input_value() == ""
    assert scope.locator("option[value='2']").count() == 0
    assert errors == []


@pytest.fixture(scope="module")
def fungal_partition_payload(tmp_path_factory):
    import json

    from what_to_id.atlas_taxonomy import AtlasTaxonomy
    from what_to_id.embedding_atlas import group_payload

    directory = tmp_path_factory.mktemp("fungal-scope-partition")
    ids = np.arange(10000, 11000)
    vectors = np.random.default_rng(29).normal(size=(1000, 8)).astype("f4")
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    embeddings = directory / "Fungi.npz"
    np.savez(embeddings, ids=ids, E=vectors, backbone="fixture")
    # 254 complete positives plus one partial path through another listed root.
    # Exactly 742 complete negatives and three unknowns are distinct source IDs.
    taxa = [31] * 254 + [33] + [32] * 742 + [98] * 3
    pool = pd.DataFrame(
        dict(
            id=ids,
            taxon_id=taxa,
            iconic_taxon="Fungi",
            lon=-123,
            lat=49,
            taxon_name="Recorded fungus",
            photo_url="",
            observed_on="2026-09-11",
        )
    )
    path = directory / "taxonomy.json"
    path.write_text(
        json.dumps(
            {
                "taxa": {
                    str(k): [parent, "Cached taxon", "", "taxon"]
                    for k, parent in {
                        1: None,
                        31: 54743,
                        54743: 1,
                        32: 1,
                        33: 118252,
                        118252: 999,
                    }.items()
                }
            }
        )
    )
    payload = group_payload(pool, embeddings, "Fungi", taxonomy=AtlasTaxonomy(path))
    return payload


def test_identify_fungal_partition_contains_exactly_742_known_outside_ids(
    open_taxonomy_atlas, fungal_partition_payload
):
    page, errors = open_taxonomy_atlas
    page.route(
        "**/embeddings-data/Fungi.json", lambda route: route.fulfill(json=fungal_partition_payload)
    )
    page.locator("#group").select_option("Fungi")
    page.locator('[data-focal-id="10000"]').wait_for()
    scope = page.get_by_role("combobox", name="Taxon scope", exact=True)
    scope.select_option("1")
    page.get_by_role("button", name="Identify these results (255)", exact=True).click()
    included = set(identify_batch_ids(page))
    assert included == set(range(10000, 10255))
    page.locator("#close-identify").click()
    scope.select_option("2")
    page.get_by_role("button", name="Identify these results (742)", exact=True).click()
    outside = set(identify_batch_ids(page))
    assert outside == set(range(10255, 10997))
    assert included.isdisjoint(outside)
    assert len(included | outside) == 997
    assert (included | outside).isdisjoint(range(10997, 11000))
    assert page.locator('[data-focal-id="10000"]').count() == 1
    assert (
        "3 observations have unknown scope membership"
        in page.locator("#taxon-scope-message").inner_text()
    )
    assert errors == []
