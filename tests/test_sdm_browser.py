"""The range popover's habitat line in Chromium, on Identify and on the map's record card: the
ECCC model's value at the record's point from the tiler (stubbed), read beside the range map."""

import functools
import gzip
import http.server
import json
import threading
from urllib.parse import parse_qs, urlparse

import pytest

from what_to_id.site_files import END, START, dump, read_meta, write_meta

from . import test_identify_ranges_browser as rb
from .test_map_oneid_browser import open_map

browser = rb.browser
SDM = "Habitat model (ECCC 1 km): "
COG = "https://example.org/sdm/{slug}.tif"
# Taxon 0 in range, Taxon 1 just outside (80 km at level 5), Taxon 2 1,234 km outside and introduced
# (record 2); Taxon 4 has no model
VALUES = {"taxon-0": [43.0], "taxon-1": [255], "taxon-2": [70.0]}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("sdm-site")
    rb.write_site(root, introduced=(2,))
    page = root / "map.html"
    html = page.read_text()
    meta = read_meta(html)
    taxa = json.loads(gzip.decompress((root / meta["taxa"]).read_bytes()))
    slugs = {f"Taxon {k}": f"taxon-{k}" for k in (0, 1, 2)}
    meta["sdm"] = {
        "cog": COG,
        "taxa": {str(i): slugs[t[0]] for i, t in enumerate(taxa) if t[0] in slugs},
    }
    page.write_text(html[: html.find(START) + len(START)] + dump(meta) + html[html.find(END) :])
    write_meta(root, meta)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(rb.ib.Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def tiler(page):
    """Answers the point lookup per model as the tiler does; logs each request's URL."""
    page.asked = []

    def point(route):
        page.asked.append(route.request.url)
        slug = parse_qs(urlparse(route.request.url).query)["url"][0].rsplit("/", 1)[1][:-4]
        route.fulfill(json={"values": VALUES[slug]}, headers={"access-control-allow-origin": "*"})

    page.route("**/cog/point/**", point)


def habitat(page, chip_text):
    chip = page.locator(".rchip", has_text=chip_text)
    if not chip.is_visible():  # Identify's chips sit in the compare panel, the map card's show
        rb.ib.panel(page, page.locator(".card", has=chip))
    chip.click()
    line = page.locator("#rpop .rsdm")
    page.wait_for_function(
        "!document.querySelector('#rpop .rsdm').textContent.includes('checking')"
    )
    return line.inner_text()


def test_identify_reads_the_model_at_the_point_beside_the_range_map(browser, site):
    page = rb.opened(browser, site, "#lvl=1&out=0")
    tiler(page)
    assert habitat(page, "In range") == SDM + "43 % suitable here"
    url = urlparse(page.asked[0])
    assert url.netloc == "tiler2.biodiversite-quebec.ca" and url.path.startswith("/cog/point/-")
    assert parse_qs(url.query)["url"] == ["https://example.org/sdm/taxon-0.tif"]
    assert habitat(page, "Just outside range") == SDM + "no value here"  # 255 is nodata
    assert habitat(page, "1,200 km outside") == (
        SDM + "70 % suitable here. Habitat suits it and the species is introduced: "
        "the range map is likely behind its spread"
    )
    assert (
        habitat(page, "In range") == SDM + "43 % suitable here" and len(page.asked) == 3
    )  # cached
    assert page.locator("#rpop .rcap").inner_text() == ""  # the range caption is its own line
    assert page.errors == []


def test_far_outside_native_and_suitable_reads_as_a_possible_extension(browser, site):
    page = rb.opened(browser, site, "#lvl=5&out=0")
    VALUES["taxon-1"] = [70.0]
    try:
        tiler(page)
        assert habitat(page, "80 km outside") == (
            SDM + "70 % suitable here. Habitat suits it: possibly a range extension, "
            "worth an expert look"
        )
    finally:
        VALUES["taxon-1"] = [255]
    assert page.errors == []


def test_the_map_card_reads_the_introduced_flag(browser, site):
    page = open_map(browser, f"{site}/map.html?standalone=1", "#record=3000&at=9/49/-123")
    tiler(page)
    page.locator("#card .rchip").wait_for()
    assert habitat(page, "1,200 km outside").endswith("the range map is likely behind its spread")
    assert page.errors == []
    page.close()


def test_far_outside_and_unsuitable_or_unreadable(browser, site):
    page = rb.opened(browser, site, "#lvl=1&out=0")
    VALUES["taxon-2"] = [12.0]
    try:
        tiler(page)
        assert habitat(page, "1,200 km outside") == (
            SDM
            + "12 % suitable here. Habitat does not suit it either: check the ID or the location"
        )
    finally:
        VALUES["taxon-2"] = [70.0]
    page.close()
    page = rb.opened(browser, site, "#lvl=1&out=0")
    page.route("**/cog/point/**", lambda r: r.abort())  # the tiler is down
    assert habitat(page, "1,200 km outside") == SDM + "no value here"
    assert page.errors == []


def test_a_label_without_a_model_has_no_habitat_line(browser, site):
    page = rb.opened(browser, site, "#lvl=5&kind=2")
    tiler(page)
    habitat_chip = page.locator(".rchip", has_text="Fits the look-alike")
    rb.ib.panel(page, page.locator(".card", has=habitat_chip))
    habitat_chip.click()
    assert page.locator("#rpop").is_visible() and page.locator("#rpop .rsdm").is_hidden()
    assert page.asked == [] and page.errors == []


def test_the_map_card_popover_has_the_habitat_line(browser, site):
    page = open_map(browser, f"{site}/map.html?standalone=1", "#record=1000&at=9/49/-123")
    tiler(page)
    page.locator("#card .rchip").wait_for()
    assert habitat(page, "In range") == SDM + "43 % suitable here"
    assert page.errors == []
    page.close()
