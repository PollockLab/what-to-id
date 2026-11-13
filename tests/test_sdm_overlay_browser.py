"""The map's modelled range overlay in Chromium: one picked taxon with an ECCC habitat model offers
the toggle, which adds the tiler's raster and the iNaturalist range outline to the map (the
MapLibre stand-in records its sources) with a legend, and takes them off again."""

import pytest

from . import test_sdm_browser as sb
from .test_map_groups_browser import STUB
from .test_map_oneid_browser import open_map

browser = sb.browser
site = sb.site
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
# the stand-in map keeps its sources and layers where the test reads them
PLAIN = "addSource() {} addLayer() {} getSource() { return null; } getLayer() { return null; }"
TRACK = """addSource(id, s) { (window.__src ??= {})[id] = s; }
    removeSource(id) { delete __src[id]; }
    addLayer(l, at) { (window.__lyr ??= {})[l.id] = [l, at]; } removeLayer(id) { delete __lyr[id]; }
    getSource(id) { return (window.__src || {})[id] || null; }
    getLayer(id) { return (window.__lyr || {})[id] || null; } isStyleLoaded() { return true; }"""
assert PLAIN in STUB
LEGEND = "Habitat model (ECCC 1 km, 1980-2010 climate): low to high"


def opened(browser, site, hash_, range_file=True):
    page = open_map(browser, f"{site}/map.html?standalone=1", hash_)
    page.unroute("https://unpkg.com/**")
    page.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB.replace(PLAIN, TRACK) if r.request.url.endswith(".js") else "",
            content_type="text/javascript",
        ),
    )
    page.route("**/cog/tiles/**", lambda r: r.fulfill(body=PNG, content_type="image/png"))
    if not range_file:
        page.route("**/pool-levels-range.*", lambda r: r.fulfill(status=404))
    page.reload()
    page.wait_for_function("/^\\d/.test(document.getElementById('count').textContent)")
    return page


def sources(page):
    return page.evaluate("Object.keys(window.__src || {}).sort()")


@pytest.mark.parametrize("hash_", ["", "#taxa=1000,1001", "#taxa=1004", "#taxa=-1000"])
def test_no_toggle_unless_one_included_pick_has_a_model(browser, site, hash_):
    page = opened(browser, site, hash_)
    page.wait_for_timeout(200)
    assert page.locator("#sdmbtn").is_hidden() and sources(page) == []
    assert page.locator(".sdmleg").is_hidden() and page.errors == []
    page.close()


def test_the_toggle_adds_the_model_and_the_range_outline_and_takes_them_off(browser, site):
    page = opened(browser, site, "#taxa=1001")
    btn = page.locator("#sdmbtn")
    btn.wait_for()
    assert (
        btn.inner_text() == "Show modelled range" and btn.get_attribute("aria-pressed") == "false"
    )
    btn.click()
    page.wait_for_function("window.__src && window.__src['sdm-range'] && window.__src['sdm-mask']")
    assert btn.get_attribute("aria-pressed") == "true"
    assert sources(page) == ["sdm", "sdm-mask", "sdm-range"]
    raster = page.evaluate("__src.sdm")
    assert raster["type"] == "raster" and raster["tileSize"] == 256
    assert raster["attribution"] == "ECCC SDM via Biodiversité Québec"
    assert raster["tiles"] == [
        "https://tiler2.biodiversite-quebec.ca/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png"
        "?url=https%3A%2F%2Fexample.org%2Fsdm%2Ftaxon-1.tif"
        "&colormap_name=viridis&rescale=0,99&nodata=255"
    ]
    # Taxon 1's two cells share one edge, so the outline is the six outer edges, in degrees
    geom = page.evaluate("__src['sdm-range'].data.geometry")
    assert geom["type"] == "MultiLineString" and len(geom["coordinates"]) == 6
    assert {p[0] for e in geom["coordinates"] for p in e} == {-124, -123, -122}
    assert not [e for e in geom["coordinates"] if e[0][0] == e[1][0] == -123]  # the shared edge
    lyr = page.evaluate("Object.values(__lyr).map(x => [x[0].id, x[0].type])")
    assert sorted(lyr) == [["sdm", "raster"], ["sdm-mask", "fill"], ["sdm-range", "line"]]
    mask = page.evaluate("__src['sdm-mask'].data.features.map(f => f.properties.id)")
    assert mask == ["land", "sea"]
    assert page.evaluate("__lyr['sdm-mask'][0].paint['fill-color'][3]") == "#d4dadc"  # light sea
    assert page.evaluate("__lyr.sdm[0].paint['raster-opacity']") == 0.55
    leg = page.locator(".sdmleg")
    assert page.evaluate("document.querySelector('#side #sdmbtn + .sdmleg') !== null")
    assert leg.is_visible()
    assert leg.locator("p").all_inner_texts() == [LEGEND, "iNaturalist range map"]
    btn.click()
    assert btn.get_attribute("aria-pressed") == "false" and sources(page) == []
    assert page.evaluate("Object.keys(__lyr)") == [] and leg.is_hidden() and btn.is_visible()
    assert page.errors == []
    page.close()


def test_a_second_pick_takes_the_overlay_and_the_toggle_away(browser, site):
    page = opened(browser, site, "#taxa=1000")
    btn = page.locator("#sdmbtn")
    btn.click()
    page.wait_for_function("window.__src && window.__src['sdm-range']")
    page.fill("#q", "Taxon 4")
    page.locator("#sugg li").first.wait_for()
    page.press("#q", "ArrowDown")
    page.press("#q", "Enter")
    page.wait_for_function(
        "location.hash.includes('taxa=1000%2C1004') || location.hash.includes('taxa=1000,1004')"
    )
    assert btn.is_hidden() and sources(page) == [] and page.locator(".sdmleg").is_hidden()
    assert page.errors == []
    page.close()


def test_without_the_range_file_only_the_model_is_drawn(browser, site):
    page = opened(browser, site, "#taxa=1000", range_file=False)
    page.locator("#sdmbtn").click()
    page.wait_for_function("window.__src && window.__src['sdm-mask']")
    page.wait_for_timeout(300)
    assert sources(page) == ["sdm", "sdm-mask"] and page.locator(".sdmleg").is_visible()
    assert page.errors == []
    page.close()
