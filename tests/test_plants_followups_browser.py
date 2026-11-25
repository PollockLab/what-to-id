"""The Life groups setting beyond the map's views in Chromium: Confused pairs' tabs, the Food web
picker's groups, Identify's shortcut chips, and Explore switching every pane when localStorage
throws."""

import copy
import json

import pytest

from what_to_id import page_confusion, page_eating

from . import foodweb_page
from . import test_plants_everywhere_browser as pe
from .test_page_confusion import pairs_frame, records_frame
from .test_tree_browser import serve

browser, site, open_page, LI, SPLIT = pe.browser, pe.site, pe.open_page, pe.LI, pe.SPLIT

NO_STORAGE = """for (const k of ['getItem', 'setItem', 'removeItem'])
  Storage.prototype[k] = () => { throw new DOMException('blocked', 'SecurityError'); };"""


@pytest.fixture(scope="module")
def confusion(tmp_path_factory):
    root = tmp_path_factory.mktemp("confusion-plants")
    r = records_frame()
    r["iconic_taxon"] = r["iconic_taxon"].replace("Plantae", "Tracheophyta")
    r.to_parquet(root / "r.parquet")
    pairs_frame().to_parquet(root / "c.parquet")
    page_confusion.build(root, None, root / "c.parquet", root / "r.parquet")
    server, url = serve(root)
    yield url
    server.shutdown()


def tabs(browser, url):
    page = browser.new_page()
    page.goto(url)
    page.wait_for_selector("#pairs .pair")
    t = page.locator("#tabs button").all_inner_texts()
    page.close()
    return t


def test_confused_pairs_tabs_merge_the_split_plants_by_default(browser, confusion):
    # the tabs carry the Identify chips' names: Plants, or the split groups' own
    assert tabs(browser, f"{confusion}/confusion.html") == [
        "All 6",
        "Plants 4",
        "Fungi and lichens 2",
    ]
    assert tabs(browser, f"{confusion}/confusion.html?plants=split") == [
        "All 6",
        "Vascular plants 4",
        "Fungi and lichens 2",
    ]


@pytest.fixture(scope="module")
def food(tmp_path_factory):
    meta = copy.deepcopy(foodweb_page.META)
    meta["pairs"].append(["Mus musculus", "Quercus", 0.5])
    meta["parent"].update({"Quercus": "Fagaceae", "Fagaceae": "Tracheophyta"})
    meta["parent"]["Tracheophyta"] = "Plantae"
    meta["groups"].update(dict(zip(["Tracheophyta", "Bryophytes", "Algae"], SPLIT, strict=True)))
    root = tmp_path_factory.mktemp("food-plants")
    (root / page_eating.OBS_FILE).write_text(json.dumps(foodweb_page.OBS))
    (root / page_eating.METAWEB_FILE).write_text(json.dumps(meta))
    page_eating.build(root, "")
    yield from foodweb_page.serve(root, "food-web.html")


def picker_groups(browser, url):
    page = foodweb_page.open_page(browser, url + "#q=eaten&y=Mus musculus")
    page.locator("#sent input").click()
    t = page.locator("#sent .cb li[role=treeitem]").all_inner_texts()
    assert page.errors == []
    page.close()
    return " ".join(t)


def test_food_web_picker_groups_follow_the_setting(browser, food):
    text = picker_groups(browser, food.replace("food-web.html", "food-web.html?plants=inat"))
    assert "Plants" in text and not [s for s in SPLIT if s in text]
    assert "Vascular plants" in picker_groups(
        browser, food.replace("food-web.html", "food-web.html?plants=split")
    )


def test_identify_hides_the_bryophytes_chip_unless_plants_are_split(open_page):
    chips = "() => [...document.querySelectorAll('#clades button')].map(b => b.textContent)"
    page = open_page("identify.html")
    page.wait_for_function(LI)
    assert "Bryophytes" not in page.evaluate(chips)
    split = open_page("identify.html?plants=split")
    split.wait_for_function(LI)
    assert "Bryophytes" in split.evaluate(chips)


def test_explore_switches_every_pane_without_local_storage(browser, site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script(NO_STORAGE)
    ctx.route(
        "https://unpkg.com/**", lambda r: r.fulfill(body=pe.JS, content_type="text/javascript")
    )
    ctx.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    ctx.route("https://static.inaturalist.org/**", lambda r: r.fulfill(body=pe.PNG))
    page = ctx.new_page()
    page.goto(f"{site}/explore.html?view=identify-map")
    for n in ("identify", "map"):
        page.wait_for_function(f"document.getElementById('{n}').contentWindow.MapGroups?.current")
    page.wait_for_function(
        "typeof document.getElementById('map').contentDocument"
        ".querySelector('#gmode button')?.onclick === 'function'"
    )
    page.frame_locator("#map").locator("#gmode button[data-m=split]").click()
    page.wait_for_function("location.search.includes('plants=split')")
    page.wait_for_function(
        "document.getElementById('identify').contentWindow.MapGroups?.current === 'split'"
    )
    page.wait_for_function(
        "document.getElementById('map').contentWindow.MapGroups?.current === 'split'"
    )
    ctx.close()
