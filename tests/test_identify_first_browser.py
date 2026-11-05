"""Identify's first cards (pool-levels-first.bin) in Chromium: drawn while the pool shards load, the
same rows the page builds once they land. iNaturalist is stubbed."""

import gzip
import json
import re
import urllib.request

import pytest

from what_to_id import page_identify, site_files

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site
open_identify = ib.open_identify


def first_lists(base):
    with urllib.request.urlopen(f"{base}/{site_files.MAP_NAME}") as r:
        name = site_files.read_meta(r.read().decode())["files"]["first"]
    with urllib.request.urlopen(f"{base}/{name}") as r:
        return json.loads(gzip.decompress(r.read()))["s"]


@pytest.mark.parametrize("hash_", ["", "#groups=Aves"])
def test_the_first_lists_are_the_lists_the_page_builds(browser, site, hash_):
    base, _ = site
    want = first_lists(base)[hash_[1:]]
    page = open_identify(browser, base, hash_)
    view, total = page.evaluate("__identify.view()"), page.evaluate("__identify.total()")
    for lv in (1, 3):
        assert total[lv] == want["total"][lv]
        assert [r[0] for r in want["rows"][lv]] == view[lv][:200] and want["n"][lv] == len(view[lv])
    # Might be wrong is the level lists of its kinds, one after another
    kinds = [k for k, _ in page_identify.KINDS]
    assert total[5] == sum(want["total"][k] for k in kinds)
    rows = {k: [r[0] for r in want["rows"][k]] for k in kinds}
    assert all(want["n"][k] == len(rows[k]) for k in kinds)  # whole, under the 200 a list holds
    assert view[5] == [i for k in kinds for i in rows[k]]
    assert page.errors == []


def cards(page):
    return page.eval_on_selector_all(
        "#grid .card",
        "l => l.map(e => [+e.dataset.id, e.querySelector('.title').textContent, "
        "(e.querySelector('.sp') || {}).textContent || ''])",
    )


def test_the_first_cards_show_before_the_records_and_stay_when_they_land(browser, site):
    base, _ = site
    first = first_lists(base)
    page = browser.new_page(viewport={"width": 380, "height": 800})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    held = []
    page.route(re.compile(r"/pool-\d+\.\w+\.bin"), lambda r: held.append(r))
    page.goto(f"{base}/identify.html#lvl=1")
    page.wait_for_selector("#grid .card .ph img")
    early = cards(page)
    assert [c[0] for c in early] == [r[0] for r in first[""]["rows"][1][:12]]
    assert any(c[2] for c in early)  # a cut species offers the rest of its records
    assert "loading all" in page.locator("#status").inner_text()
    assert page.evaluate("window.__identify") is None and held
    page.evaluate("location.hash = 'groups=Aves&lvl=1'")  # another first list
    aves = first["groups=Aves"]["rows"][1][0][0]
    page.wait_for_function(f"+document.querySelector('#grid .card').dataset.id === {aves}")
    page.evaluate("location.hash = 'months=9&lvl=1'")  # none built: it waits for the records
    page.wait_for_function("!document.querySelector('#grid .card')")
    assert "Loading all the records" in page.locator("#status").inner_text()
    page.evaluate("location.hash = 'lvl=1'")
    page.wait_for_selector("#grid .card .ph img")
    assert cards(page) == early
    page.click("#more")  # read on: the swap keeps the cards drawn and the scroll
    page.evaluate("scrollTo(0, 600)")
    drawn, y = cards(page), page.evaluate("scrollY")
    assert len(drawn) > len(early) and y > 0
    for r in held:
        r.continue_()
    page.wait_for_function("window.__identify")
    page.wait_for_selector("#grid .card .ph img")
    assert cards(page) == drawn and page.evaluate("scrollY") == y  # the same cards, where they were
    assert page.locator("#status").inner_text().startswith("2,100 ")
    assert page.errors == []


def test_a_species_picked_from_a_first_card_shows_once_the_records_land(browser, site):
    base, pts = site
    page = browser.new_page(viewport={"width": 380, "height": 800})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    held = []
    page.route(re.compile(r"/pool-\d+\.\w+\.bin"), lambda r: held.append(r))
    page.goto(f"{base}/identify.html#lvl=1")
    link = page.locator("#grid .card .sp").first
    rid = int(link.locator("xpath=..").get_attribute("data-id"))
    link.click()
    assert "taxa=" in page.evaluate("location.hash") and not page.locator("#grid .card").count()
    for r in held:
        r.continue_()
    page.wait_for_function("window.__identify")
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    assert {taxon[i] for i in page.evaluate("__identify.view()[1]")} == {taxon[rid]}
    assert page.errors == []
