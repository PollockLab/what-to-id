"""Identify's level 3 Sort control: the Blitz gaps order (confidence band, then gap tier, then rank)
against the Confidence order, the gap badge, the hash and the fall back when the where-to-blitz
checklist does not load. iNaturalist and where-to-blitz are stubbed."""

import json
import re
import struct
import zlib

import numpy as np

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .identify_sheets import reveal
from .test_identify_narrow_browser import rank_plane

browser = eb.browser
site = ib.site

DIR = "https://pollocklab.github.io/where-to-blitz/cluster_results/checklist/"
LATTICE = {"ncol": 220, "nrow": 181, "res_m": 25000, "x0": -2150000, "y1": 4300000}


def png(w, h, rgba):
    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\0" + rgba[r].tobytes() for r in range(h))
    head = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", head)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def checklist_png():
    """Opaque cells whose observer-days cycle 4, 22, 40 with the cell, so all three tiers occur."""
    h, w = LATTICE["nrow"], LATTICE["ncol"]
    days = np.array([4, 22, 40])[(np.arange(w)[None, :] + np.arange(h)[:, None]) % 3]
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 1], img[..., 2], img[..., 3] = days // 256, days % 256, 255
    return png(w, h, img)


def stub_checklist(page, fail=False):
    groups = {g: {"png": f"{g}.png"} for g in ("All biodiversity", "Aves", "Insecta", "Plantae")}
    sidecar = {
        "schema_version": 3,
        "rule_of_thumb_units": 30,
        "tiers": {"25000": {"lattice": LATTICE, "groups": groups}},
    }
    cors = {"access-control-allow-origin": "*"}
    tile = checklist_png()

    def route(r):
        if fail:
            return r.fulfill(status=500, headers=cors)
        if r.request.url.endswith("checklist.json"):
            return r.fulfill(
                body=json.dumps(sidecar), content_type="application/json", headers=cors
            )
        return r.fulfill(body=tile, content_type="image/png", headers=cors)

    page.route(DIR + "**", route)


def open_level_3(browser, base, hash_="#lvl=3", fail=False):
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    stub_checklist(page, fail)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    return page


def view(page):
    return page.evaluate("__identify.view()")[3]


LIMITS = {"1": 0, "5": 1, "25": 2, "all": 3}


def settle(page):
    """The checklist read (or failed): the controls' second note has stopped saying Loading."""
    page.wait_for_function(
        "!document.querySelector('#sorto .segnote:last-child').textContent.includes('Loading')"
    )


def open_with(browser, base, hash_, fail=False):
    page = open_level_3(browser, base, "#lvl=3" + hash_, fail)
    settle(page)
    page.wait_for_selector("#grid .card")
    return page


def ranks(base, pts):
    n3 = int((pts["level"] == 3).sum())
    rank = dict(zip(pts["id"].tolist(), rank_plane(base).tolist(), strict=True))
    return n3, rank, lambda i: int(np.searchsorted([0.01, 0.05, 0.25], (rank[i] + 1) / n3))


def test_each_sort_state_orders_level_3_as_it_says(browser, site):
    base, pts = site
    n3, rank, band = ranks(base, pts)
    keys = {
        "": lambda i, t: (band(i) - t, band(i), rank[i]),  # the blend
        "&sort=conf": lambda i, t: (rank[i],),
        "&sort=gaps": lambda i, t: (-t, rank[i]),
        "&sort=conf,gaps": lambda i, t: (band(i) - t, band(i), rank[i]),
    }
    for sort, key in keys.items():
        page = open_with(browser, base, "&conf=all" + sort)
        ids = view(page)
        tier = {i: page.evaluate(f"__identify.gap({i})") for i in ids}
        assert [key(i, tier[i]) for i in ids] == sorted(key(i, tier[i]) for i in ids), sort
        assert page.errors == []
        page.close()
    page = open_with(
        browser, base, "&conf=all"
    )  # the blend lets a gap outrank a lit record of the next band up
    # over every level 3 record: the cap by suggestion leaves this fixture (3 look-alikes) a handful
    ids = sorted(pts["id"][pts["level"] == 3].tolist(), key=lambda i: rank[i])
    tier = {i: page.evaluate(f"__identify.gap({i})") for i in ids}
    ids.sort(key=lambda i: (band(i) - tier[i], band(i), rank[i]))
    blend = [(band(i), tier[i]) for i in ids]
    assert any(a[0] > b[0] for a, b in zip(blend, blend[1:], strict=False))


def test_the_confidence_filter_keeps_its_bands_before_sorting(browser, site):
    base, pts = site
    n3, rank, band = ranks(base, pts)
    level3 = pts["id"][pts["level"] == 3].tolist()
    for value, lim in LIMITS.items():
        for sort in ("&sort=conf", "&sort=gaps", ""):
            page = open_with(browser, base, f"&conf={value}{sort}")
            ids = view(page)
            assert ids and all(band(i) <= lim for i in ids), (value, sort)
            want = sum(1 for i in level3 if band(i) <= lim)
            assert page.inner_text("#tab3 b") == f"{want:,}"  # the tab's count is the filter's
            assert "records shown" not in page.inner_text("#sort") + page.inner_text("#sorto")
            page.close()


def test_the_default_is_top_5_percent_with_both_sorts_on(browser, site):
    base, pts = site
    n3, rank, band = ranks(base, pts)
    page = open_with(browser, base, "")
    on = page.evaluate(
        "[...document.querySelectorAll('#sort [aria-checked=true], #sorto [aria-checked=true]')].map(b => b.textContent)"
    )
    assert on == ["Top 5%", "Confidence", "Blitz gaps"]
    assert all(band(i) <= 1 for i in view(page))
    assert page.evaluate("location.hash") == "#lvl=3"
    page.close()


def test_the_last_sort_on_stays_on(browser, site):
    base, _ = site
    page = open_with(browser, base, "&sort=conf")
    reveal(page, "#sorto .seg")
    page.click("#sorto button:has-text('Confidence')")
    assert page.get_attribute("#sorto button >> nth=0", "aria-checked") == "true"
    assert "sort=conf" in page.evaluate("location.hash")
    page.click("#sorto button:has-text('Blitz gaps')")
    assert "sort=" not in page.evaluate("location.hash")  # both on again
    page.click("#sorto button:has-text('Confidence')")
    assert "sort=gaps" in page.evaluate("location.hash")
    assert page.errors == []


def test_the_badge_names_the_gap_and_links_to_the_cell(browser, site):
    base, _ = site
    page = open_level_3(browser, base)
    page.wait_for_selector("#grid .card .gap", state="attached")
    seen = {}
    for card in page.locator("#grid .card").all():
        tier = page.evaluate(f"__identify.gap({card.get_attribute('data-id')})")
        badge = card.locator(".gap")
        assert badge.count() == (1 if tier else 0)  # nothing on a lit cell
        if tier:
            seen[tier] = badge.inner_text()
            href = badge.get_attribute("href")
            assert re.match(
                r"https://pollocklab\.github\.io/where-to-blitz/\?at=4\d\.\d+,-12\d\.\d+&", href
            )
            assert "&res=25000&g=" in href and href.endswith("&goal=cl")
    assert seen == {2: "Gap 4/30", 1: "Gap 22/30"}  # compact, one line
    big = page.locator("#grid .card .gap", has_text="Gap 4/30").first
    assert big.get_attribute("aria-label") == "Blitz gap: 4 of 30 observer-days in this 25 km cell"
    assert "30 make a checklist" in big.get_attribute("title")
    assert big.evaluate("e => getComputedStyle(e).whiteSpace") == "nowrap"
    assert page.locator("#grid .card .conf", has_text="Top").count() >= 1
    assert page.errors == []


def test_the_choices_are_kept_in_the_hash_and_shown_on_level_3_only(browser, site):
    base, _ = site
    page = open_with(browser, base, "")
    reveal(page, "#sort .seg")
    page.click("#sort button:has-text('Top 25%')")
    page.keyboard.press("Escape")
    reveal(page, "#sorto .seg")
    page.click("#sorto button:has-text('Blitz gaps')")
    hash_ = page.evaluate("location.hash")
    assert "conf=25" in hash_ and "sort=conf" in hash_
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    on = page.evaluate(
        "[...document.querySelectorAll('#sort [aria-checked=true], #sorto [aria-checked=true]')].map(b => b.textContent)"
    )
    assert on == ["Top 25%", "Confidence"]
    page.click("#tab1")
    assert page.locator("#sort").get_attribute("hidden") is not None and page.locator("#sortb").is_hidden()
    assert page.errors == []


def test_without_the_checklist_level_3_lists_by_confidence_without_errors(browser, site):
    base, pts = site
    page = open_level_3(browser, base, "#lvl=3&conf=all", fail=True)
    page.wait_for_function(
        "document.querySelector('#sorto .segnote:last-child').textContent.includes('did not')"
    )
    rank = dict(zip(pts["id"].tolist(), rank_plane(base).tolist(), strict=True))
    got = [rank[i] for i in view(page)]
    assert got == sorted(got) and page.locator("#grid .gap").count() == 0
    assert page.errors == []
