"""Identify's level 3 for improving IDs in Chromium: strict score order from the rank file, a copy
button and a confidence label on each card, a mark on records that already have a species, the
group control and the batch caption. iNaturalist is stubbed."""

import gzip
import urllib.request
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from what_to_id import site_files

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .test_identify_browser import LOOKS

browser = eb.browser
site = ib.site


def rank_plane(base):
    with urllib.request.urlopen(f"{base}/{site_files.MAP_NAME}") as r:
        meta = site_files.read_meta(r.read().decode())
    with urllib.request.urlopen(f"{base}/{meta['files']['rank']}") as r:
        return np.frombuffer(gzip.decompress(r.read()), "<u4")


def test_level_3_lists_strictly_by_rank_and_labels_the_top(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3&sort=conf&conf=all")
    page.wait_for_selector("#grid .card .conf")
    rank = dict(zip(pts["id"].tolist(), rank_plane(base).tolist(), strict=True))
    got = [rank[i] for i in page.evaluate("__identify.view()")[3]]
    assert got == sorted(got) and len(set(got)) == len(got) and got[0] == 0
    first = page.locator("#grid .card").first
    assert first.locator(".conf").inner_text() == "Top 1%"
    assert page.locator("#grid .card .conf", has_text="Top").count() >= 1
    assert page.errors == []


def test_the_copy_button_copies_the_suggestion_and_says_so(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script(
        "window.COPIED = []; Object.defineProperty(navigator, 'clipboard', {value: "
        "{writeText: t => window.DENY ? Promise.reject(new Error('denied')) "
        ": (COPIED.push(t), Promise.resolve())}});"
    )
    eb.stub_inat(page, None)
    page.goto(f"{base}/identify.html#lvl=3")
    b = page.locator("#grid .card .copy").first
    b.wait_for()
    name = page.locator("#grid .card .look i").first.inner_text()
    assert b.inner_text() == "Copy" and b.get_attribute("aria-label") == f"Copy {name}"
    assert b.get_attribute("aria-live") == "polite"
    b.click()
    assert b.inner_text() == "Copied" and page.evaluate("COPIED") == [name]
    page.evaluate("window.DENY = true")  # a refused clipboard says so, no error
    b.click()
    assert b.inner_text() == "Copy failed" and page.errors == []


def test_a_record_with_a_species_id_is_dropped(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    calls = []

    def observations(route):  # even ids hold a current ID at species
        ids = [int(i) for i in parse_qs(urlparse(route.request.url).query)["id"][0].split(",")]
        calls.append(ids)
        ident = [{"current": True, "taxon": {"rank_level": 10, "name": "Bombus a"}}]
        route.fulfill(
            json={
                "results": [
                    {
                        "id": i,
                        "quality_grade": "needs_id",
                        "photos": [],
                        "taxon": {"name": "Bombus", "rank_level": 20},
                        "identifications": ident if i % 2 == 0 else [],
                    }
                    for i in ids
                ]
            },
            headers={"access-control-allow-origin": "*"},
        )

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.goto(f"{base}/identify.html#lvl=3")
    page.wait_for_function(
        "(l => l.length && l.every(e => e.dataset.id % 2))"
        "([...document.querySelectorAll('#grid .card')])"
    )
    assert calls and all(len(c) <= 200 for c in calls)  # the photos' own requests, none added
    view = page.evaluate("__identify.view()")[3]
    assert view and all(i % 2 for i in view)  # dropped from the list, not only the grid
    cards = int(page.inner_text("#cap").split(" cards")[0].replace(",", ""))
    assert cards == len(view)  # the caption counts only cards that can show
    left = len(view) - page.locator("#grid .card").count()
    more = page.locator("#more")
    assert more.is_hidden() if not left else more.inner_text() == f"Show more ({left} left)"
    assert page.errors == []


def test_the_group_control_sets_the_groups_filter(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=1")
    page.wait_for_function("__identify.ids().length > 0")
    assert page.locator("#grpsel").input_value() == ""
    page.select_option("#grpsel", "Aves")
    want = sorted(pts.loc[pts["iconic_taxon"] == "Aves", "id"].tolist())
    page.wait_for_function(f"__identify.ids().length === {len(want)}")
    assert ib.ids(page) == want and "groups=Aves" in page.evaluate("location.hash")
    page.select_option("#grpsel", "")
    page.wait_for_function(f"__identify.ids().length === {len(pts)}")
    assert "groups=" not in page.evaluate("location.hash")
    page.goto(f"{base}/identify.html#lvl=1&groups=Aves,-Insecta")
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    assert page.locator("#grpsel").input_value() == "*"
    assert page.errors == []


def test_level_3_caps_by_the_suggested_species_and_other_levels_by_label(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3&conf=all")
    page.wait_for_selector("#grid .card .look")  # the look-alikes landed, the list was drawn again
    look = dict(zip(pts["id"].tolist(), [LOOKS[k % 3] for k in range(len(pts))], strict=True))
    view = page.evaluate("__identify.view()")
    per = pd.Series([look[i] for i in view[3]]).value_counts()
    held = pd.Series([look[i] for i in pts["id"][pts["level"] == 3]]).value_counts()
    assert len(per) > 1 and per.max() <= 3 and per.sum() == held.clip(upper=3).sum()
    # +N more would pick the label, not the suggestion
    assert page.locator("#grid .card .sp").count() == 0
    tax = dict(zip(pts["id"].tolist(), pts["taxon_id"].tolist(), strict=True))
    by_label = pd.Series([tax[i] for i in view[1]]).value_counts()
    assert by_label.max() <= 3  # the other levels still cap by label
    assert page.errors == []


def test_level_3_has_one_count_line_that_agrees_with_the_tab(browser, site):
    base, _ = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card .look")
    cards = len(page.evaluate("__identify.view()")[3])
    records = page.evaluate("__identify.total()")[3]
    assert page.inner_text("#tab3 b") == f"{records:,}"
    assert page.inner_text("#cap") == (
        f"{cards:,} cards to ID ({records:,} records, Top 5%; up to 3 per suggested species)"
    )
    assert page.locator("#cap").is_visible() and "records shown" not in page.inner_text("#sort")
    page.click("#sort button:has-text('All')")
    records = page.evaluate("__identify.total()")[3]
    assert page.inner_text("#tab3 b") == f"{records:,}"
    assert f"({records:,} records; up to 3 per suggested species)" in page.inner_text("#cap")
    assert page.errors == []
