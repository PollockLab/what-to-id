"""Explore's filter rail in Chromium: the map's own filter panel as a column left of every pane,
open at 1280 px, folded and remembered, kept as the rail alone while the map pane is hidden, and a
sheet on a phone. Runs offline on the site and stand-ins of test_explore_home_browser.py."""

from . import test_explore_home_browser as eh

browser, site, open_page, map_frame, BLOCK = (
    eh.browser,
    eh.site,
    eh.open_page,
    eh.map_frame,
    eh.BLOCK,
)
SECTIONS = ["selbar", "grpsec", "taxsec", "flagbox", "projbox"]
# the left edge and width of a frame in the page, and of the rail inside the map's frame
BOX = """id => { const r = document.getElementById(id).getBoundingClientRect();
  return [r.left, r.width]; }"""
COUNT = "document.getElementById('count').textContent"


def rail(page):
    return map_frame(page).evaluate(f"({BOX})('side')")


def test_the_rail_is_open_at_1280_left_of_identify_with_its_sections(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    assert rail(page) == [0, 280]
    (mx, mw), (ix, _) = page.evaluate(f"({BOX})('map')"), page.evaluate(f"({BOX})('identify')")
    assert mx == 0 and ix >= mw  # the map's frame, its rail first, then Identify
    ids = frame.evaluate("[...document.querySelectorAll('#side > [id]')].map(e => e.id)")
    assert [i for i in ids if i in SECTIONS] == SECTIONS
    assert frame.is_visible("#grpsec") and frame.is_visible("#taxsec")  # the fixture has no flags
    assert frame.is_hidden("#toggle")  # no drawer button
    assert page.errors == []
    page.close()


def test_a_group_row_filters_identify_and_the_map_and_clear_all_removes_it(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    idf = next(f for f in page.frames if "identify.html" in f.url)
    idf.evaluate("window.got = []; addEventListener('message', e => got.push(e.data))")
    frame.locator("#groups > li").nth(2).locator(".gb").click()  # Aves, the smallest
    frame.wait_for_function(f"{COUNT}.startsWith('30 ')")
    page.wait_for_function("location.hash.includes('groups=Aves')")
    idf.wait_for_function("got.some(d => d.type === 'wtid-selection' && d.sel === 'groups=Aves')")
    name = frame.locator("#groups > li.on .nm").text_content()
    chips = frame.locator("#selbar .chips button")
    assert frame.is_visible("#selbar") and name in chips.first.text_content()
    frame.click("#selbar .lbl button")  # Clear all
    frame.wait_for_function(f"{COUNT}.startsWith('300 ')")
    page.wait_for_function("!location.hash.includes('groups=')")
    assert frame.is_hidden("#selbar")
    assert page.errors == []
    page.close()


def test_the_space_controls_stay_clickable_beside_the_open_rail_with_a_filter_on(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    frame.locator("#groups > li").nth(2).locator(".gb").click()
    frame.wait_for_function(f"{COUNT}.startsWith('30 ')")
    card = frame.locator(".maplibregl-ctrl.area").bounding_box()
    assert card["x"] >= 280  # beside the rail, not under it
    frame.get_by_role(
        "button", name="Draw area", exact=True
    ).click()  # a real click: nothing covers it
    assert frame.is_visible("[data-a=cancel]")
    frame.click("[data-a=cancel]")
    page.close()
    # a phone with the map pane and its filters sheet shut
    page = open_page(browser, f"{site[0]}/explore.html?view=map", width=390)
    frame = map_frame(page)
    frame.get_by_role("button", name="Draw area", exact=True).click()
    assert frame.is_visible("[data-a=cancel]")
    assert page.errors == []
    page.close()


def test_the_rail_folds_to_a_strip_and_stays_folded(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    frame.click("#railx")
    frame.wait_for_function("document.documentElement.classList.contains('rail-off')")
    assert rail(page) == [0, 36] and frame.text_content("#railx") == "Filters"
    assert frame.evaluate("localStorage.getItem('wtid-rail')") == "0"
    page.reload()
    frame = map_frame(page)
    assert rail(page) == [0, 36]
    frame.click("#railx")
    assert rail(page) == [0, 280] and frame.evaluate("localStorage.getItem('wtid-rail')") == "1"
    frame.evaluate("localStorage.removeItem('wtid-rail')")
    assert page.errors == []
    page.close()


def test_with_the_map_hidden_the_rail_stays_and_counts_all_of_bc(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html")
    frame = map_frame(page)
    page.click("[data-p=map]")
    page.wait_for_function("document.getElementById('map').classList.contains('rail')")
    frame.wait_for_function("document.documentElement.classList.contains('rail-only')")
    assert page.evaluate(f"({BOX})('map')") == [0, 280] and frame.is_hidden("#map")
    assert frame.evaluate("document.querySelectorAll('#scope button')[1].ariaPressed") == "true"
    # the hidden map still counts: a pick here reaches Identify and the counts follow it
    frame.locator("#groups > li").nth(2).locator(".gb").click()
    frame.wait_for_function(f"{COUNT}.startsWith('30 ')")
    page.wait_for_function("location.hash.includes('groups=Aves')")
    assert frame.locator("#groups > li .gc").all_text_contents() == ["170", "100", "30"]
    page.click("[data-p=map]")  # the map back: In view again, and its canvas
    frame.wait_for_function("!document.documentElement.classList.contains('rail-only')")
    assert frame.evaluate("document.querySelectorAll('#scope button')[0].ariaPressed") == "true"
    assert frame.is_visible("#map") and page.evaluate(f"({BOX})('map')")[1] > 600
    assert page.errors == []
    page.close()


def test_on_a_phone_the_rail_is_a_sheet_from_the_filters_button(browser, site):
    page = open_page(browser, f"{site[0]}/explore.html", width=390)
    page.wait_for_function("document.getElementById('identify')")
    assert page.evaluate("!document.getElementById('map')")  # a phone holds one pane, Identify
    page.click("#fb")
    frame = map_frame(page)
    page.wait_for_function("document.getElementById('map').classList.contains('sheet')")
    x, w = page.evaluate(f"({BOX})('map')")
    assert x == 0 and w == 390 and page.get_attribute("#fb", "aria-expanded") == "true"
    assert frame.is_visible("#grpsec")
    frame.click("#railx")  # Hide
    page.wait_for_function("!document.getElementById('map').classList.contains('sheet')")
    assert page.is_hidden("#map") and page.get_attribute("#fb", "aria-expanded") == "false"
    assert frame.evaluate("localStorage.getItem('wtid-rail')") is None  # a phone keeps nothing
    assert page.errors == []
    page.close()


def test_with_storage_blocked_the_rail_opens_and_folds(browser, site):
    page = open_page(browser, "about:blank")
    page.add_init_script(BLOCK)
    page.goto(f"{site[0]}/explore.html")
    frame = map_frame(page)
    assert rail(page) == [0, 280]
    frame.click("#railx")
    assert rail(page) == [0, 36]
    frame.click("#railx")
    frame.locator("#groups > li").nth(2).locator(".gb").click()
    frame.wait_for_function(f"{COUNT}.startsWith('30 ')")
    assert page.errors == []
    page.close()
