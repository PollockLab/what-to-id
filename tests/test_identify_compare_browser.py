"""The compare panel in Chromium: the record's photos large and zoomable, each candidate with
a row of reference photos and a range map with the record's point, and the keys that step through
them. iNaturalist is stubbed."""

from urllib.parse import parse_qs, urlparse

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from . import test_identify_ranges_browser as rb

browser = ib.browser
site = rb.site  # two range cells, records 0-9
SIMILAR = (901, 902, 903)
CORS = {"access-control-allow-origin": "*"}


def open_compare(browser, base, size=(1280, 900)):
    """Level 1 with iNaturalist stubbed: each similar species has 5 reference photos, each
    observation 3 photos; `page.taxa` holds the taxa requests."""
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    page.errors, page.taxa = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route(ib.WTB, lambda r: r.abort())

    def api(route):
        url = route.request.url
        path = url.split("/v1/", 1)[1]
        if path.startswith("identifications/similar_species"):
            body = {
                "results": [{"count": 5, "taxon": {"id": t, "name": f"Sim {t}"}} for t in SIMILAR]
            }
        elif path.startswith("taxa/"):
            page.taxa.append(parse_qs(urlparse(url).query))
            ids = [int(i) for i in path.split("?")[0].split("/")[1].split(",")]
            photos = [
                {"photo": {"url": f"https://static.inaturalist.org/photos/{k}/square.jpg"}}
                for k in range(5)
            ]
            body = {  # only the similar species come back whole; the others keep the table's row
                "results": [
                    {"id": i, "name": f"Sim {i}", "taxon_photos": photos}
                    for i in ids
                    if i in SIMILAR
                ]
            }
        else:
            body = {"results": []}
        route.fulfill(json=body, headers=CORS)

    page.route("https://api.inaturalist.org/v1/**", api)
    eb.stub_inat(page, None)

    def observations(route):
        ids = [int(i) for i in parse_qs(urlparse(route.request.url).query)["id"][0].split(",")]
        photos = [
            {"url": f"https://static.inaturalist.org/photos/{k}/square.jpg"} for k in range(3)
        ]
        results = [
            {
                "id": i,
                "quality_grade": "needs_id",
                "observed_on": "2026-05-01",
                "place_guess": "Vancouver, BC",
                "photos": photos,
                "taxon": {"name": f"Taxon {i}"},
            }
            for i in ids
        ]
        route.fulfill(json={"results": results}, headers=CORS)

    page.route("https://api.inaturalist.org/v1/observations*", observations)  # the later route wins
    page.goto(f"{base}/identify.html#lvl=1")
    page.wait_for_function("window.__identify && __identify.ranges()")
    page.wait_for_selector("#grid .card .links", state="attached")
    page.locator('#grid .card[data-id="1000"] .car').click()  # record 0: its label has a range
    page.wait_for_function("document.querySelectorAll('#cprefs .cpref').length === 4")
    return page


def test_each_candidate_has_a_photo_row_and_a_range_map(browser, site):
    page = open_compare(browser, site)
    rows = page.locator("#cprefs .cpref")
    names = [t.split(" ", 1)[1] for t in rows.locator("h3").all_inner_texts()]
    assert names[0].startswith("Taxon") and names[1:] == [
        "Sim 901",
        "Sim 902",
        "Sim 903",
    ]  # the data's order
    assert rows.nth(1).locator(".cpph img").count() == 5
    assert "5 photos" in rows.nth(1).locator(".cptools").inner_text()
    assert rows.nth(1).locator(".cpph").get_attribute("aria-label") == "Reference photos of Sim 901"
    assert (
        "No reference photo" in rows.nth(0).inner_text()
    )  # the table row, no photos fetched for it
    first = rows.nth(0).locator(".cpmap")
    assert (
        first.locator("canvas").is_visible()
        and first.locator("canvas").get_attribute("role") == "img"
    )
    assert first.locator(".cpmapcap").inner_text() in ("Record in range", "Record outside range")
    assert first.locator("canvas").get_attribute("aria-label").startswith("Range of Taxon")
    assert rows.nth(1).locator(".cpmapcap").inner_text() == "No range map"  # not in the range file
    assert rows.nth(1).locator("canvas").is_hidden()
    assert all(q["preferred_place_id"] == ["7085"] for q in page.taxa)
    assert page.errors == []


def test_the_keys_step_candidates_reference_photos_and_the_records_photos(browser, site):
    page = open_compare(browser, site)
    rows = page.locator("#cprefs .cpref")
    assert rows.nth(0).get_attribute("aria-current") == "true"
    page.keyboard.press("ArrowDown")
    assert (
        rows.nth(1).get_attribute("aria-current") == "true"
        and rows.nth(0).get_attribute("aria-current") is None
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        "document.querySelector('#cprefs .cpref:nth-child(2) .cpph').scrollLeft > 0"
    )
    page.keyboard.press("ArrowLeft")
    page.wait_for_function(
        "document.querySelector('#cprefs .cpref:nth-child(2) .cpph').scrollLeft === 0"
    )
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")  # stops at the first
    assert rows.nth(0).get_attribute("aria-current") == "true"
    big = page.locator("#cpobs .cpbig")
    assert (
        big.get_attribute("alt") == "Observation photo 1 of 3"
        and page.locator("#cpobs .cpthumb").count() == 3
    )
    page.keyboard.press("Shift+ArrowRight")
    assert big.get_attribute("alt") == "Observation photo 2 of 3"
    assert page.locator("#cpobs .cpthumb").nth(1).get_attribute("aria-pressed") == "true"
    page.keyboard.press("Shift+ArrowLeft")
    page.keyboard.press("Shift+ArrowLeft")  # wraps to the last
    assert big.get_attribute("alt") == "Observation photo 3 of 3"
    stage = page.locator("#cpobs .cpstage")
    assert stage.get_attribute("aria-pressed") == "false"
    page.keyboard.press("z")
    assert stage.get_attribute("aria-pressed") == "true" and "zoom" in stage.get_attribute("class")
    stage.click()  # a click zooms back out
    assert stage.get_attribute("aria-pressed") == "false"
    page.keyboard.press("Escape")
    assert not page.locator("#cpanel").is_visible()
    assert page.errors == []


def test_the_panel_holds_the_record_beside_the_candidates_on_a_wide_screen(browser, site):
    page = open_compare(browser, site, (1440, 900))
    left, right = page.locator(".cpl").bounding_box(), page.locator(".cpr").bounding_box()
    assert left["x"] + left["width"] <= right["x"] and abs(left["y"] - right["y"]) < 2
    panel = page.locator("#cpanel").bounding_box()
    assert panel["x"] + panel["width"] == 1440 and panel["height"] == 900
    assert (
        page.evaluate("document.querySelector('main').getBoundingClientRect().right")
        <= panel["x"] + 1
    )
    page.set_viewport_size({"width": 390, "height": 844})  # one column on a phone
    left, right = page.locator(".cpl").bounding_box(), page.locator(".cpr").bounding_box()
    assert right["y"] >= left["y"] + left["height"] - 1
    assert page.evaluate("document.querySelector('#cpanel').scrollWidth <= 390")
    assert page.errors == []
