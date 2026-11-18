"""Identify's level 3 for improving IDs in Chromium: strict score order from the rank file, a copy
button and a confidence label on each card, a mark on records that already have a species, the
group control and the batch caption. iNaturalist is stubbed."""

import urllib.request
from urllib.parse import parse_qs, urlparse

import pandas as pd

from what_to_id import pool_levels, site_files

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .identify_sheets import reveal
from .test_identify_browser import LOOKS

browser = eb.browser
site = ib.site


def rank_plane(base):
    with urllib.request.urlopen(f"{base}/{site_files.MAP_NAME}") as r:
        meta = site_files.read_meta(r.read().decode())
    with urllib.request.urlopen(f"{base}/{meta['files']['levels']}") as r:
        level, _ = pool_levels.unpack(r.read())
    with urllib.request.urlopen(f"{base}/{meta['files']['rank']}") as r:
        return pool_levels.unpack_rank(r.read(), level)  # dense: 0 off level 3


def test_level_3_lists_strictly_by_rank_and_labels_the_top(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3&sort=conf&conf=all")
    page.wait_for_selector("#grid .card .conf", state="attached")
    rank = dict(zip(pts["id"].tolist(), rank_plane(base).tolist(), strict=True))
    got = [rank[i] for i in page.evaluate("__identify.view()")[3]]
    assert got == sorted(got) and len(set(got)) == len(got) and got[0] == 0
    first = page.locator("#grid .card").first
    assert first.locator(".conf").inner_text() == "Best 1%"
    assert page.locator("#grid .card .conf", has_text="Best").count() >= 1
    assert page.errors == []


def test_the_tab_count_waits_with_a_placeholder_until_the_percentiles_are_read(browser, site):
    base, _ = site
    with urllib.request.urlopen(f"{base}/{site_files.MAP_NAME}") as r:
        files = site_files.read_meta(r.read().decode())["files"]
    page = browser.new_page()
    eb.stub_inat(page, None)
    held, requested = [], []
    page.on("request", lambda r: requested.append(r.url))
    # the look-alikes arrive, the percentiles it waits with do not
    page.route(f"**/{files['pct']}*", lambda r: held.append(r))
    page.goto(f"{base}/identify.html")
    page.wait_for_function("window.__identify")
    page.wait_for_timeout(500)
    count = page.locator('#tabs [data-lv="3"]').locator("xpath=*[2]")
    assert held and count.inner_text() == "…"
    assert not [u for u in requested if files["rank"] in u]  # level 3 alone reads the rank
    for r in held:
        r.continue_()
    page.wait_for_function(
        "/^[0-9]/.test(document.querySelector('#tabs [data-lv=\"3\"]').children[1].textContent)"
    )


def test_the_tab_count_falls_back_to_the_rank_when_the_percentiles_fail(browser, site):
    base, _ = site
    with urllib.request.urlopen(f"{base}/{site_files.MAP_NAME}") as r:
        files = site_files.read_meta(r.read().decode())["files"]
    page = browser.new_page()
    eb.stub_inat(page, None)
    requested = []
    page.on("request", lambda r: requested.append(r.url))
    page.route(f"**/{files['pct']}*", lambda r: r.abort())
    page.goto(f"{base}/identify.html")
    page.wait_for_function(
        "/^[0-9]/.test(document.querySelector('#tabs [data-lv=\"3\"]').children[1].textContent)"
    )
    assert [u for u in requested if files["rank"] in u]


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
    page.wait_for_function("window.__identify")  # the full records may reorder the first cards
    page.locator("#grid .card .copy").first.wait_for(state="attached")
    name = page.locator("#grid .card .look i").first.inner_text()
    ib.panel(page, page.locator("#grid .card").first)
    b = page.locator("#cpc .copy")
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
    page.wait_for_function("window.__identify")  # the records load after the first cards
    page.wait_for_load_state("networkidle")
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
    page.click("#bwhat")
    page.locator("#groups .gb", has_text="Birds").first.click()
    want = sorted(pts.loc[pts["iconic_taxon"] == "Aves", "id"].tolist())
    page.wait_for_function(f"__identify.ids().length === {len(want)}")
    assert ib.ids(page) == want and "groups=Aves" in page.evaluate("location.hash")
    page.click("#gall")
    page.wait_for_function(f"__identify.ids().length === {len(pts)}")
    assert "groups=" not in page.evaluate("location.hash")
    page.goto(f"{base}/identify.html#lvl=1&groups=Aves,-Insecta")
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    assert page.inner_text("#bwhat b") == "Birds, not Insects"
    assert page.errors == []


def test_level_3_caps_by_the_suggested_species_and_other_levels_by_label(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3&conf=all")
    page.wait_for_selector(
        "#grid .card .look", state="attached"
    )  # the look-alikes landed, the list was drawn again
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
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card .look", state="attached")
    cards = len(page.evaluate("__identify.view()")[3])
    records = page.evaluate("__identify.total()")[3]
    assert page.inner_text("#tab3 b") == f"{records:,}"
    every = sum(1 for x in pts["level"] if x == 3)  # no filter: every level 3 record before the cut
    cut = f"the most confident 5% of {every:,}"
    assert page.inner_text("#cap") == (
        f"{cards:,} cards to ID ({records:,} records, {cut}; up to 3 per suggested species)"
    )
    assert page.inner_text("#count") == f"{cards:,} cards"  # a phone keeps the short heading
    reveal(page, "#ptop")
    page.evaluate(
        "() => { const e = document.getElementById('ptop'); e.value = 100;"
        " e.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.wait_for_function(
        "location.hash.includes('conf=all')"
        " && !document.getElementById('cap').textContent.includes('most confident')"
    )
    records = page.evaluate("__identify.total()")[3]
    assert page.inner_text("#tab3 b") == f"{records:,}"
    assert f"({records:,} records; up to 3 per suggested species)" in page.inner_text("#cap")
    assert page.errors == []


def test_the_tab_names_the_cut_and_show_all_lifts_it_and_back(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "#lvl=3")
    page.wait_for_selector("#grid .card .look", state="attached")
    records, every = page.evaluate("__identify.total()")[3], int((pts["level"] == 3).sum())
    assert records < every
    assert " ".join(page.inner_text("#tab3").split()) == f"Narrow it down {records:,} · best 5%"
    assert page.text_content("#count .rel").endswith(
        f" of {records:,} records, the most confident 5% of {every:,}"
    )
    b = page.locator("#showall")
    assert b.inner_text() == "Show all" and b.is_visible()
    b.focus()
    page.keyboard.press("Enter")
    page.wait_for_function(f"__identify.total()[3] === {every}")
    assert "conf=all" in page.evaluate("location.hash")
    assert page.inner_text("#tab3").split() == ["Narrow", "it", "down", f"{every:,}"]
    assert b.inner_text() == "Best 5% only"
    b.click()
    page.wait_for_function(f"__identify.total()[3] === {records}")
    assert "conf=" not in page.evaluate("location.hash") and b.inner_text() == "Show all"
    page.goto(f"{base}/identify.html#lvl=3&conf=all")  # the hash round-trips
    page.reload()
    page.wait_for_function(f"window.__identify && __identify.total()[3] === {every}")
    assert page.locator("#showall").inner_text() == "Best 5% only"
    assert page.errors == []


def test_a_drop_after_show_more_keeps_the_batch_and_the_counts(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script("window.IntersectionObserver = undefined")  # only the button extends
    page.add_init_script(  # batches of 3, so a short list has several
        "Object.defineProperty(window, 'IdentifyLinks', {configurable: true, set(v) {"
        " const b = v.batches; v.batches = (ids, x) => { const r = [];"
        " for (let k = 0; k < ids.length; k += 3) r.push(b(ids.slice(k, k + 3), x)[0]);"
        " return r; };"
        " Object.defineProperty(window, 'IdentifyLinks', {value: v, writable: true}); }});"
    )
    eb.stub_inat(page, None)
    later = []

    def observations(route):  # on Show more's own request, even ids already hold a species ID
        ids = [int(i) for i in parse_qs(urlparse(route.request.url).query)["id"][0].split(",")]
        gone = len(later) == 1
        later.extend([1] if gone else [])  # later answers, for the refills, keep theirs
        ident = [{"current": True, "taxon": {"rank_level": 10, "name": "Bombus a"}}]
        route.fulfill(
            json={
                "results": [
                    {
                        "id": i,
                        "quality_grade": "needs_id",
                        "photos": [],
                        "taxon": {"name": "Bombus", "rank_level": 20},
                        "identifications": ident if gone and i % 2 == 0 else [],
                    }
                    for i in ids
                ]
            },
            headers={"access-control-allow-origin": "*"},
        )

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.route(  # two cards a page, so the six at level 3 need Show more; no ids asked ahead
        "**/identify.html*",
        lambda r: r.fulfill(
            response=(f := r.fetch()),
            body=f.text().replace("LIMIT=12", "LIMIT=2").replace("Math.min(24,lis.length)", "0"),
        ),
    )
    page.goto(f"{base}/identify.html#lvl=3&conf=all")
    page.wait_for_selector("#grid .card")
    page.wait_for_load_state("networkidle")
    assert page.locator("#more").is_visible()  # the fixture lists more than one page
    page.click("#next")
    assert page.inner_text("#bn").startswith("Batch 2 of ")
    before = len(page.evaluate("__identify.view()")[3])
    later.append(1)
    page.click("#more")
    page.wait_for_function(f"__identify.view()[3].length < {before}")
    page.wait_for_load_state("networkidle")
    view = page.evaluate("__identify.view()")[3]
    assert int(page.inner_text("#cap").split(" cards")[0].replace(",", "")) == len(view)
    left = len(view) - page.locator("#grid .card").count()
    more = page.locator("#more")
    assert more.is_hidden() if not left else more.inner_text() == f"Show more ({left} left)"
    n = -(-len(view) // 3)
    assert page.inner_text("#bn") == f"Batch 2 of {n}"  # the batch held through the drop
    assert page.errors == []
