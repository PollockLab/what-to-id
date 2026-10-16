"""The map's park picker (map_area.js): its search in node, and its keyboard, chips and hash in a
headless browser over a stand-in map, when playwright is installed."""

import json
import shutil
import subprocess

import pytest

from what_to_id.map_parks import encode_rings
from what_to_id.page_map import _ASSETS

NODE = shutil.which("node")
KINDS = ["Park", "Ecological reserve", "Protected area", "Recreation area", "Conservancy"]


def _row(key, name, kind=0, place=0, bb=(-123.2, 49.2, -123.1, 49.3), alt=""):
    w, s, e, n = bb
    rings = "" if place else encode_rings([[w, s, e, s, e, n, w, n]])
    return [key, name, kind, place, list(bb), rings, alt]


def node(body: str, rows: list):
    js = (
        ((_ASSETS / "identify_links.js").read_text() + (_ASSETS / "map_area.js").read_text())
        + f"\nvar K={json.dumps(KINDS)},R={json.dumps(rows)};"
        + "var P=R.map(function(r){return MapArea.entry(r,K);});"
        + f"process.stdout.write(JSON.stringify((function(){{{body}}})()));"
    )
    return json.loads(
        subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout
    )


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_search_ignores_case_accents_and_designation_words():
    rows = [
        _row("1", "Écureuil Lake Park"),
        _row("2", "Nism̓aakqin Conservancy", 4),
        _row("3", "Garibaldi Park"),
        _row("4", "Garibaldi Lake Ecological Reserve", 1),
        _row("5", "Tweedsmuir Park", alt="Kluskoil"),
    ]
    got = node(
        "function m(i,t){var r=MapArea.match(P[i],t);"
        "return r&&[r.rank,r.b?P[i].name.slice(r.a,r.b):null];}"
        "return [m(0,'ecureuil'),m(0,'ÉCUREUIL lake provincial park'),m(1,'nismaakqin'),"
        "m(2,'garibaldi park'),m(3,'Garibaldi park'),m(3,'ecological reserve'),"
        "m(2,'ecological reserve'),m(4,'kluskoil'),m(0,'reuil'),m(2,'park')];",
        rows,
    )
    assert got == [
        [0, "Écureuil"],
        [0, "Écureuil Lake"],
        [0, "Nism̓aakqin"],
        [0, "Garibaldi"],
        [0, "Garibaldi"],
        [0, "Ecological Reserve"],
        None,
        [2, None],
        [1, "reuil"],
        [0, "Park"],
    ]


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_rows_group_selected_then_in_view_then_the_rest_and_word_starts_first():
    rows = [
        _row("1", "Alpha Park"),
        _row("2", "Beagle Park"),
        _row("3", "Charlie Park"),
        _row("4", "Eagle Park"),
    ]
    got = node(
        "function g(t){return MapArea.listing(P,t,sel,view).groups.map(function(x){"
        "return [x.label,x.rows.map(function(r){return r.p.key;})];});}"
        "function sel(p){return p.key==='3';}function view(p){return p.key==='2'||p.key==='3';}"
        "return [g(''),g(' '),g('eagle')];",
        rows,
    )
    empty = [["Selected", ["3"]], ["In view", ["2"]], ["All parks", ["1", "4"]]]
    assert got == [empty, empty, [["", ["4", "2"]]]]


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_rows_stop_at_200_and_count_the_rest():
    rows = [_row(str(i), f"Lake {i:03d} Park") for i in range(250)]
    got = node(
        "var f=function(){return false;},a=MapArea.listing(P,'',f,f),"
        "b=MapArea.listing(P,'lake 1',f,f);"
        "return [a.n,a.more,a.groups[0].rows.length,b.n,b.more];",
        rows,
    )
    assert got == [250, 50, 200, 100, 0]


# The browser harness: map_area.js and its CSS on a page with a stand-in map whose view holds
# Garibaldi Park only; the park list comes from ctx.get, and iNaturalist's place answers are routed.
PARKS = [
    _row("0001", "Garibaldi Park"),
    _row("0002", "Joffre Lakes Park", bb=(-122.5, 50.3, -122.4, 50.4)),
    _row("0003", "Golden Ears Park", bb=(-122.5, 49.2, -122.4, 49.3)),
    _row("0096", "Cape Scott Park", place=132254, bb=(-128.4, 50.7, -128.2, 50.8)),
]
HARNESS = """<!doctype html><meta charset="utf-8"><style>%s</style><body><script>%s
var CHANGES=0,map={addControl:function(c){document.body.appendChild(c.onAdd());},on:function(){},
  getBounds:function(){return {getWest:function(){return -124;},getEast:function(){return -122.9;},
    getSouth:function(){return 49;},getNorth:function(){return 49.5;}};},
  fitBounds:function(){},getCanvas:function(){return {style:{}};},
  doubleClickZoom:{enable:function(){},disable:function(){}}};
var h=new URLSearchParams(location.hash.slice(1)),PARKS=%s,
  AREA=MapArea({map:map,S:{},LAST:0,P:function(){return {n:0};},keep:function(){},
    change:function(){CHANGES++;},hash:h.get('area')||'',park:h.get('park')||'',
    bcpark:h.get('bcpark')||'',fit:false,place:7085,parks:'parks',get:function(){
      var j=JSON.stringify({kinds:%s,parks:PARKS});
      return Promise.resolve(new TextEncoder().encode(j).buffer);}});
</script>"""


def _browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        return pw, pw.chromium.launch()
    except Exception as e:  # no browser installed
        pw.stop()
        pytest.skip(f"no chromium for playwright: {e}")


@pytest.fixture(scope="module")
def browser():
    pw, b = _browser()
    yield b
    b.close()
    pw.stop()


def _page(browser, frag=""):
    html = HARNESS % (
        (_ASSETS / "map.css").read_text() + (_ASSETS / "map_area.css").read_text(),
        ((_ASSETS / "identify_links.js").read_text() + (_ASSETS / "map_area.js").read_text()),
        json.dumps(PARKS),
        json.dumps(KINDS),
    )
    pg = browser.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    ring = [[[-128.4, 50.7], [-128.2, 50.7], [-128.2, 50.8], [-128.4, 50.8], [-128.4, 50.7]]]
    place = {
        "results": [
            {
                "id": 132254,
                "name": "Cape Scott Park",
                "geometry_geojson": {"type": "Polygon", "coordinates": ring},
            }
        ]
    }
    pg.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json=place))
    pg.route("http://harness/**", lambda r: r.fulfill(body=html, content_type="text/html"))
    pg.goto("http://harness/map.html" + frag)
    pg.errors = errors
    return pg


def _state(pg):
    return pg.evaluate(
        """() => ({hash: AREA.hash(),
        chips: [...document.querySelectorAll('.achip')].map(c => c.firstChild.textContent),
        open: document.querySelector('[role=combobox]').getAttribute('aria-expanded'),
        ticked: [...document.querySelectorAll('[role=option][aria-selected=true] .anm')]
          .map(e => e.textContent),
        text: document.querySelector('[role=combobox]').value})"""
    )


def _chips(pg, n):
    pg.wait_for_function(f"() => document.querySelectorAll('.achip:not(.aload)').length === {n}")


def test_keyboard_ticks_parks_keeps_the_list_open_and_backspace_removes_the_last(browser):
    pg = _page(browser)
    box = pg.get_by_role("combobox")
    box.focus()
    pg.wait_for_selector("[role=option]")
    heads = pg.eval_on_selector_all(".ahead", "e => e.map(x => x.textContent)")
    assert heads == ["In view", "All parks"]
    box.press_sequentially("garib")
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Enter")
    box.press_sequentially("joff")
    pg.keyboard.press("Enter")
    _chips(pg, 2)
    s = _state(pg)
    assert s["chips"] == ["Garibaldi Park", "Joffre Lakes Park"] and s["hash"] == "bcpark=0001,0002"
    assert s["open"] == "true" and s["ticked"] == ["Joffre Lakes Park"]
    assert pg.eval_on_selector(".anm b", "e => e.textContent") == "Joff"
    # Backspace clears the selected text; in the full list Space ticks the highlighted row
    pg.keyboard.press("Backspace")
    for _ in range(3):
        pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Space")
    _chips(pg, 3)
    assert _state(pg)["ticked"] == ["Garibaldi Park", "Joffre Lakes Park", "Cape Scott Park"]
    # Escape closes the list; Backspace in the empty box drops the last chip
    pg.keyboard.press("Escape")
    assert _state(pg)["open"] == "false"
    pg.keyboard.press("Backspace")
    _chips(pg, 2)
    assert _state(pg)["hash"] == "bcpark=0001,0002"
    pg.wait_for_function("() => document.querySelector('.alive').textContent.includes('removed')")
    assert pg.errors == []


def test_removing_a_chip_unticks_its_row_and_selected_parks_come_first(browser):
    pg = _page(browser, "#bcpark=0003,0002")
    _chips(pg, 2)
    pg.get_by_role("combobox").focus()
    pg.wait_for_selector("[role=option]")
    assert pg.eval_on_selector_all(".ahead", "e => e.map(x => x.textContent)") == [
        "Selected",
        "In view",
        "All parks",
    ]
    assert _state(pg)["ticked"] == ["Golden Ears Park", "Joffre Lakes Park"]
    assert pg.text_content(".ahdr") == "2 selected · Clear all"
    pg.click("[aria-label='Remove Golden Ears Park']")
    _chips(pg, 1)
    assert _state(pg)["ticked"] == ["Joffre Lakes Park"]
    pg.click(".ahdr button")
    _chips(pg, 0)
    assert _state(pg)["ticked"] == [] and _state(pg)["hash"] == "" and pg.errors == []


@pytest.mark.parametrize(
    "frag,chips,hash",
    [
        ("", [], ""),
        ("#bcpark=0002", ["Joffre Lakes Park"], "bcpark=0002"),
        (
            "#bcpark=0001,0096,0003",
            ["Garibaldi Park", "Cape Scott Park", "Golden Ears Park"],
            "bcpark=0001,0096,0003",
        ),
        ("#bcpark=96", ["Cape Scott Park"], "bcpark=0096"),
        ("#park=132254", ["Cape Scott Park"], "park=132254"),
    ],
)
def test_hash_round_trips_and_old_links_load(browser, frag, chips, hash):
    pg = _page(browser, frag)
    _chips(pg, len(chips))
    s = _state(pg)
    assert s["chips"] == chips and s["hash"] == hash and pg.errors == []
    if hash:
        back = _page(browser, "#" + hash)
        _chips(back, len(chips))
        assert _state(back)["hash"] == hash


def test_unreadable_shared_area_requires_explicit_recovery_before_identify(browser):
    from .test_map_area_recovery import recovery_html

    page = browser.new_page()
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("http://area-recovery/**", lambda route: route.fulfill(body=recovery_html()))
    page.route("https://**", lambda route: (external.append(route.request.url), route.abort()))
    raw = "future&groups=Aves#tail%25"
    from urllib.parse import quote

    page.goto("http://area-recovery/map.html#area=" + quote(raw, safe=""))
    assert page.locator("#identify").get_attribute("href") is None
    assert page.locator("#identify").get_attribute("aria-disabled") == "true"
    assert page.get_by_text("Area unresolved", exact=True).is_visible()
    assert page.get_by_role("button", name="Clear invalid area", exact=True).is_visible()
    assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('area')") == raw
    page.reload()
    assert page.locator("#identify").get_attribute("href") is None
    # A stale href must not bypass the capture guard through ordinary keyboard or mouse activation.
    pages_before = len(page.context.pages)
    page.locator("#identify").evaluate(
        "a=>{a.href='https://www.inaturalist.org/observations/identify';a.tabIndex=0;}"
    )
    page.locator("#identify").focus()
    page.keyboard.press("Enter")
    box = page.locator("#identify").bounding_box()
    for button in ["left", "middle"]:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, button=button)
    assert len(page.context.pages) == pages_before
    page.evaluate("refilter()")
    assert page.locator("#identify").get_attribute("href") is None
    page.get_by_role("button", name="Draw area", exact=True).click()
    page.get_by_role("button", name="Cancel", exact=True).click()
    assert page.evaluate("AREA.invalid()") is True
    page.get_by_role("button", name="Clear invalid area", exact=True).click()
    assert (
        page.locator("#identify")
        .get_attribute("href")
        .startswith("https://www.inaturalist.org/observations/identify?")
    )
    assert page.locator("#identify").get_attribute("aria-disabled") is None
    assert page.evaluate("AREA.hash()") == ""
    page.goto("http://area-recovery/map.html?case=replace#area=ab!")
    page.locator('input[type="file"]').set_input_files(
        {"name": "broken.geojson", "mimeType": "application/geo+json", "buffer": b"{"}
    )
    page.wait_for_function("document.querySelector('.anote').textContent.includes('not JSON')")
    assert page.evaluate("AREA.invalid()") is True
    assert page.locator("#identify").get_attribute("href") is None
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    page.locator('input[type="file"]').set_input_files(
        {
            "name": "area.geojson",
            "mimeType": "application/geo+json",
            "buffer": json.dumps(geometry).encode(),
        }
    )
    page.wait_for_function("!AREA.invalid() && AREA.on()")
    assert page.evaluate("Array.from(AREA.mask(3))") == [1, 0, 0]
    assert page.locator("#identify").get_attribute("href").endswith("&id=101")
    assert errors == [] and external == []
    page.close()


def test_pending_and_partial_shared_parks_need_recovery_before_identify(browser):
    from .test_map_area_recovery import recovery_html

    page = browser.new_page()
    requests, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("http://area-recovery/**", lambda route: route.fulfill(body=recovery_html()))
    page.route("https://api.inaturalist.org/**", lambda route: requests.append(route))
    with page.expect_request("**/111"), page.expect_request("**/222"):
        page.goto("http://area-recovery/map.html#park=111,222", wait_until="domcontentloaded")
    page.wait_for_function("AREA.invalid()")
    assert page.locator("#identify").get_attribute("href") is None
    assert page.get_by_text("Area unresolved", exact=True).is_visible()
    assert "Loading Park 111 and Park 222" in page.locator(".anote").inner_text()
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    assert len(requests) == 2
    for route in requests:
        place = int(route.request.url.rsplit("/", 1)[-1])
        record = {"id": place}
        if place == 111:
            record["geometry_geojson"] = geometry
        route.fulfill(json={"results": [record]})
    page.wait_for_function("AREA.mask(3)!==null")
    assert page.evaluate("AREA.invalid()") is True
    assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('park')") == "111,222"
    assert page.locator("#identify").get_attribute("href") is None
    assert "Could not restore Park 222" in page.locator(".anote").inner_text()
    page.get_by_role("button", name="Remove Park 222", exact=True).click()
    assert page.evaluate("AREA.invalid()") is False
    assert "place_id=111" in page.locator("#identify").get_attribute("href")
    assert page.evaluate("AREA.hash()") == "park=111"
    assert errors == []
    page.close()


@pytest.mark.parametrize("replace", [False, True])
def test_cleared_or_replaced_park_ignores_late_boundary_response(browser, replace):
    from .test_map_area_recovery import recovery_html

    page = browser.new_page()
    requests = []
    page.route("http://area-recovery/**", lambda route: route.fulfill(body=recovery_html()))
    page.route("https://api.inaturalist.org/**", lambda route: requests.append(route))
    with page.expect_request("**/111"):
        page.goto("http://area-recovery/map.html#park=111", wait_until="domcontentloaded")
    assert len(requests) == 1 and page.evaluate("AREA.invalid()") is True
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    if replace:
        page.locator('input[type="file"]').set_input_files(
            {"name": "broken.geojson", "mimeType": "application/geo+json", "buffer": b"{"}
        )
        page.wait_for_function("document.querySelector('.anote').textContent.includes('not JSON')")
        assert page.evaluate("AREA.invalid()") is True
        assert page.evaluate("AREA.hash()") == "park=111"
        page.locator('input[type="file"]').set_input_files(
            {
                "name": "area.geojson",
                "mimeType": "application/geo+json",
                "buffer": json.dumps(geometry).encode(),
            }
        )
        page.wait_for_function("!AREA.invalid() && AREA.on()")
    else:
        page.get_by_role("button", name="Remove Park 111", exact=True).click()
    before = page.evaluate("window.probe()")
    with page.expect_response("**/111"):
        requests[0].fulfill(json={"results": [{"id": 111, "geometry_geojson": geometry}]})
    page.wait_for_load_state("networkidle")
    assert page.evaluate("window.probe()") == before
    assert before["invalid"] is False
    page.close()


@pytest.mark.parametrize("list_body", [{"kinds": ["Park"], "parks": []}, {}])
def test_unavailable_shared_bc_park_keeps_key_and_explicit_clear(browser, list_body):
    from .test_map_area_recovery import recovery_html

    page = browser.new_page()
    requests = []
    page.route("http://area-recovery/**", lambda route: route.fulfill(body=recovery_html()))
    page.route("http://area-recovery/parks", lambda route: requests.append(route))
    with page.expect_request("http://area-recovery/parks"):
        page.goto("http://area-recovery/map.html#bcpark=0096", wait_until="domcontentloaded")
    assert page.evaluate("AREA.invalid()") is True
    assert page.locator("#identify").get_attribute("href") is None
    requests[0].fulfill(json=list_body)
    page.wait_for_function(
        "document.querySelector('.anote').textContent.includes('Could not restore')"
    )
    assert page.evaluate("AREA.hash()") == "bcpark=0096"
    assert page.locator("#identify").get_attribute("href") is None
    assert page.get_by_role("button", name="Remove BC park 0096", exact=True).is_visible()
    assert "BC park 0096" in page.locator(".anote").inner_text()
    page.get_by_role("button", name="Clear unresolved areas", exact=True).click()
    assert page.evaluate("AREA.invalid()") is False
    assert page.evaluate("AREA.hash()") == ""
    assert (
        page.locator("#identify").get_attribute("href").startswith("https://www.inaturalist.org/")
    )
    page.close()


def test_failed_park_replacement_preserves_prior_unreadable_shared_area(browser):
    from .test_map_area_recovery import recovery_html

    page = browser.new_page()
    page.route("http://area-recovery/**", lambda route: route.fulfill(body=recovery_html()))
    parks = {
        "kinds": ["Park"],
        "parks": [["0096", "Test park", 0, 111, [0, 0, 1, 1], "", ""]],
    }
    page.route("http://area-recovery/parks", lambda route: route.fulfill(json=parks))
    page.route(
        "https://api.inaturalist.org/**", lambda route: route.fulfill(json={"results": [{}]})
    )
    page.goto("http://area-recovery/map.html#area=ab!")
    page.get_by_role("combobox", name="BC parks and protected areas").click()
    page.get_by_role("option").filter(has_text="Test park").click()
    page.wait_for_function(
        "document.querySelector('.anote').textContent.includes('Could not restore')"
    )
    assert page.evaluate("AREA.invalid()") is True
    assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('area')") == "ab!"
    assert page.locator("#identify").get_attribute("href") is None
    page.get_by_role("button", name="Remove Test park", exact=True).click()
    assert page.evaluate("AREA.invalid()") is True
    assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('area')") == "ab!"
    page.get_by_role("button", name="Clear invalid area", exact=True).click()
    assert page.evaluate("AREA.invalid()") is False
    assert (
        page.locator("#identify").get_attribute("href").startswith("https://www.inaturalist.org/")
    )
    page.close()
