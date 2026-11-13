"""Identify's What, When and Where row in Chromium: When writes the map filter's from=, Where
links to the map, At risk and Invasive keep level 3 cards by their suggestion's BC status.
iNaturalist is stubbed."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site
KINDS = "new Set([...document.querySelectorAll('#grid .card .look i')].map(e=>e.textContent)).size"
IDS = {"Bombus a": 951, "Bombus b": 952, "Apis c": 953}


def open_row(browser, base, hash_):
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    page.asked = []

    def taxa(route):
        url = route.request.url
        if "/v1/taxa?" in url:
            name = parse_qs(urlparse(url).query)["q"][0]
            body = {"results": [{"id": IDS[name], "name": name}]}
        else:
            ids = [int(i) for i in url.split("/v1/taxa/")[1].split("?")[0].split(",")]
            page.asked.append((ids, parse_qs(urlparse(url).query)))
            bc = {"place": {"id": 7085}}
            body = {
                "results": [
                    {
                        "id": i,
                        "conservation_status": {"status": "wrong"},
                        "conservation_statuses": [{**bc, "iucn": 40}] if i == 953 else [],
                        "establishment_means": {"establishment_means": "introduced", **bc}
                        if i == 952
                        else None,
                    }
                    for i in ids
                ]
            }
        route.fulfill(json=body, headers={"access-control-allow-origin": "*"})

    page.route("**/v1/taxa**", taxa)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_selector("#grid .card .look")
    return page


def looks(page):
    return set(page.locator("#grid .card .look i").all_inner_texts())


def test_at_risk_and_invasive_keep_cards_by_their_suggestions_bc_status(browser, site):
    base, _ = site
    page = open_row(browser, base, "#lvl=3&conf=all")
    page.wait_for_function(KINDS + "===2")  # Bombus a never reaches level 3 here
    page.check("text=At risk")
    page.wait_for_function("document.querySelectorAll('#grid .card').length>0")
    page.wait_for_function(
        "[...document.querySelectorAll('#grid .card .look i')].every(e=>e.textContent==='Apis c')"
    )
    assert "risk=1" in page.evaluate("location.hash")
    page.check("text=Invasive")
    page.wait_for_function(KINDS + "===2")
    assert looks(page) == {"Apis c", "Bombus b"}
    assert page.asked and all(
        len(ids) <= 30 and q["preferred_place_id"] == ["7085"] for ids, q in page.asked
    )
    page.uncheck("text=At risk")
    page.wait_for_function(KINDS + "===1")
    assert looks(page) == {"Bombus b"}
    page.uncheck("text=Invasive")
    page.wait_for_function(KINDS + "===2")
    assert "risk=" not in page.evaluate("location.hash") and page.errors == []


def test_when_writes_the_map_filters_dates_and_where_links_to_the_map(browser, site):
    base, pts = site
    page = open_row(browser, base, "#lvl=3")
    assert page.locator("#when").input_value() == ""
    page.select_option("#when", "90")
    since = (datetime.now(UTC) - timedelta(days=90)).date().isoformat()
    assert f"from={since}" in page.evaluate("location.hash")
    want = {i for i, d in zip(pts["id"], ib.day(pts), strict=True) if d.date().isoformat() >= since}
    assert set(page.evaluate("__identify.ids()")) <= want
    page.select_option("#when", "")
    assert "from=" not in page.evaluate("location.hash")
    link = page.locator("a", has_text="Anywhere")
    assert link.get_attribute("href").startswith("explore.html?view=map#")
    page.goto(f"{base}/identify.html#lvl=3&from=2020-01-01&to=2020-02-01")
    page.reload()
    page.wait_for_function("window.__identify")
    assert page.locator("#when").input_value() == "c" and page.errors == []
