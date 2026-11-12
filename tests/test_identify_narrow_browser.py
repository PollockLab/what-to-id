"""Identify's level 3 for improving IDs in Chromium: strict score order from the rank file, a copy
button and a confidence label on each card, a mark on records that already have a species, the
group control and the batch caption. iNaturalist is stubbed."""

import gzip
import urllib.request
from urllib.parse import parse_qs, urlparse

import numpy as np

from what_to_id import site_files

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site


def rank_plane(base):
    with urllib.request.urlopen(f"{base}/{site_files.MAP_NAME}") as r:
        meta = site_files.read_meta(r.read().decode())
    with urllib.request.urlopen(f"{base}/{meta['files']['rank']}") as r:
        return np.frombuffer(gzip.decompress(r.read()), "<u4")


def test_level_3_lists_strictly_by_rank_and_labels_the_top(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3")
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


def test_a_record_with_a_species_id_is_marked_already_suggested(browser, site):
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
    page.wait_for_selector("#grid .card.taken")
    cards = page.eval_on_selector_all(
        "#grid .card",
        "l => l.map(e => [+e.dataset.id, e.classList.contains('taken'), "
        "(e.querySelector('.note') || {}).textContent || ''])",
    )
    assert cards and all(t == (i % 2 == 0) for i, t, _ in cards)
    assert all(n == ("Species already suggested" if t else "") for _, t, n in cards)
    assert calls and all(len(c) <= 200 for c in calls)  # the photos' own requests, none added
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
