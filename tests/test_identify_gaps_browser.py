"""Identify's Prioritize popover: the filters (Top x%, blitz gap ceiling), the weighted
prioritizers, the base order, the badges as shortcuts, the hash and the fall back when the
where-to-blitz checklist does not load. The old sort= and conf= links order as before. iNaturalist
and where-to-blitz are stubbed."""

import json
import re
import struct
import zlib

import numpy as np

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
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
    """The checklist read (or failed): the summary has stopped saying it is reading."""
    page.wait_for_function("!document.getElementById('psum').textContent.includes('reading')")


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
        "&pri=conf:1,gap:1": lambda i, t: (band(i) - t, band(i), rank[i]),
        "&pri=conf:3": lambda i, t: (rank[i],),
        "&pri=gap:2": lambda i, t: (-t, rank[i]),
    }
    for sort, key in keys.items():
        page = open_with(browser, base, "&conf=all" + sort)
        ids = view(page)
        tier = {i: page.evaluate(f"__identify.gap({i})") for i in ids}
        assert [key(i, tier[i]) for i in ids] == sorted(key(i, tier[i]) for i in ids), sort
        assert page.errors == []
        page.close()
    page = open_with(browser, base, "&conf=all")  # the blend lets a gap outrank a lit record
    # over every level 3 record: the cap by suggestion leaves this fixture (3 look-alikes) a handful
    ids = sorted(pts["id"][pts["level"] == 3].tolist(), key=lambda i: rank[i])
    tier = {i: page.evaluate(f"__identify.gap({i})") for i in ids}
    ids.sort(key=lambda i: (band(i) - tier[i], band(i), rank[i]))
    blend = [(band(i), tier[i]) for i in ids]
    assert any(a[0] > b[0] for a, b in zip(blend, blend[1:], strict=False))


def test_all_prioritizers_off_orders_by_the_base_newest_first(browser, site):
    base, _ = site
    for hash_, newest in (
        ("&pri=none", True),
        ("&pri=none&base=new", True),
        ("&pri=none&base=old", False),
    ):
        page = open_with(browser, base, "&conf=all" + hash_)
        ids = view(page)
        assert len(ids) > 3 and ids == sorted(ids, reverse=newest), hash_  # id is newest first
        want = "Newest first (no prioritizers)" if newest else "Oldest first (no prioritizers)"
        assert page.inner_text("#psum") == want
        assert page.errors == []
        page.close()
    page = open_with(browser, base, "&conf=all&pri=none&base=rand:7")
    first = view(page)
    page.close()
    page = open_with(browser, base, "&conf=all&pri=none&base=rand:7")
    assert view(page) == first and first != sorted(first, reverse=True)  # the seed fixes it
    assert page.errors == []


def test_the_confidence_filter_keeps_its_top_percent_before_ordering(browser, site):
    base, pts = site
    n3, rank, band = ranks(base, pts)
    level3 = pts["id"][pts["level"] == 3].tolist()
    for value, pct in {"1": 1, "5": 5, "10": 10, "25": 25, "60": 60, "all": 100}.items():
        for sort in ("&sort=conf", "&sort=gaps", ""):
            page = open_with(browser, base, f"&conf={value}{sort}")
            ids = view(page)
            assert ids and all((rank[i] + 1) / n3 <= pct / 100 for i in ids), (value, sort)
            want = sum(1 for i in level3 if (rank[i] + 1) / n3 <= pct / 100)
            assert page.inner_text("#tab3 b") == f"{want:,}"  # the tab's count is the filter's
            page.close()


def test_the_default_is_top_5_percent_with_confidence_and_gaps_blended(browser, site):
    base, pts = site
    n3, rank, band = ranks(base, pts)
    page = open_with(browser, base, "")
    assert page.input_value("#ptop") == "5" and page.input_value("#pw-conf") == "1"
    assert page.input_value("#pw-gap") == "1" and page.input_value("#pw-risk") == "0"
    assert page.inner_text("#psum") == "Most confident first, then biggest blitz gaps"
    assert all(band(i) <= 1 for i in view(page))
    assert page.evaluate("location.hash") == "#lvl=3"  # a default link stays as it is
    assert page.locator("#preset").is_hidden()
    assert page.errors == []


def test_the_top_slider_changes_the_count_and_the_hash(browser, site):
    base, _ = site
    page = open_with(browser, base, "")
    before = page.inner_text("#tab3 b")
    page.click("#sortb")
    page.focus("#ptop")
    for _ in range(20):
        page.keyboard.press("ArrowRight")
    page.wait_for_function("location.hash.includes('conf=25')")
    page.wait_for_function(f"document.querySelector('#tab3 b').textContent !== '{before}'")
    assert page.is_visible("#preset")
    page.click("#preset")  # back to the defaults
    page.wait_for_function("location.hash === '#lvl=3'")
    page.wait_for_function(f"document.querySelector('#tab3 b').textContent === '{before}'")
    assert page.input_value("#ptop") == "5"
    assert page.errors == []


def test_the_gap_badge_applies_the_ceiling_on_every_level(browser, site):
    base, _ = site
    page = open_with(browser, base, "")
    page.wait_for_selector("#grid .card button.gap", state="attached")
    page.locator(
        "#grid .card:has(button.gap) .ph"
    ).first.click()  # the badges show in the compare panel
    badge = page.locator("#cpdet button.gap")
    days = int(re.search(r"Gap (\d+)/", badge.inner_text()).group(1))
    badge.click()
    page.wait_for_function(f"location.hash.includes('gap={days}')")
    page.wait_for_selector("#grid .card")
    texts = page.locator("#grid .card button.gap").all_inner_texts()
    got = [int(re.search(r"Gap (\d+)/", t).group(1)) for t in texts]
    assert got and max(got) <= days and page.locator("#grid .card").count() >= len(got)
    page.wait_for_function(
        f"document.getElementById('cap').textContent.includes('gap {days} days or fewer')"
    )
    page.click("#tab1")  # the ceiling holds on the other levels too
    page.wait_for_selector("#grid .card")
    assert f"gap={days}" in page.evaluate("location.hash")
    page.click("#sortb")
    assert page.is_visible("#pgap") and page.is_hidden("#ptop")  # Top x% needs the level 3 rank
    assert page.errors == []


def test_the_confidence_badge_keeps_its_band(browser, site):
    base, _ = site
    page = open_with(browser, base, "&conf=25")
    page.locator("#grid .card:has(button.conf) .ph").first.click()
    badge = page.locator("#cpdet button.conf")
    n = badge.inner_text().removeprefix("Top ").removesuffix("%")
    badge.click()
    if n == "5":
        page.wait_for_function("!location.hash.includes('conf=')")
    else:
        page.wait_for_function(f"location.hash.includes('conf={n}')")
    assert page.errors == []


def test_blitz_gaps_order_every_level_not_only_level_3(browser, site):
    base, _ = site
    page = open_level_3(browser, base, "#lvl=1&pri=gap:3")
    settle(page)
    page.wait_for_selector("#grid .card")
    ids = page.evaluate("__identify.view()")[1]
    tiers = [page.evaluate(f"__identify.gap({i})") for i in ids]
    assert tiers[0] == 2 and tiers == sorted(tiers, reverse=True)
    page.close()
    page = open_level_3(browser, base, "#lvl=1&pri=conf:3")  # by confidence alone it is not
    settle(page)
    page.wait_for_selector("#grid .card")
    ids = page.evaluate("__identify.view()")[1]
    tiers = [page.evaluate(f"__identify.gap({i})") for i in ids]
    assert tiers != sorted(tiers, reverse=True)
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
            href = card.locator("a.gapx").get_attribute("href")
            assert re.match(
                r"https://pollocklab\.github\.io/where-to-blitz/\?at=4\d\.\d+,-12\d\.\d+&", href
            )
            assert "&res=25000&g=" in href and href.endswith("&goal=cl")
    assert seen == {2: "Gap 4/30", 1: "Gap 22/30"}  # compact, one line
    big = page.locator("#grid .card .gap", has_text="Gap 4/30").first
    assert "Blitz gap: 4 of 30 observer-days in this 25 km cell" in big.get_attribute("aria-label")
    assert big.evaluate("e => getComputedStyle(e).whiteSpace") == "nowrap"
    assert page.locator("#grid .card .conf", has_text="Top").count() >= 1
    assert page.errors == []


def test_the_choices_are_kept_in_the_hash_and_survive_a_reload(browser, site):
    base, _ = site
    page = open_with(browser, base, "")
    page.click("#sortb")
    page.select_option("#pw-conf", "3")
    page.select_option("#pw-gap", "0")
    page.select_option("#pw-risk", "2")
    page.select_option("#pbase", "old")
    hash_ = page.evaluate("location.hash")
    assert "pri=conf:3,risk:2" in hash_ and "base=old" in hash_
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    assert [page.input_value(f"#pw-{k}") for k in ("conf", "gap", "risk")] == ["3", "0", "2"]
    assert page.input_value("#pbase") == "old"
    page.click("#tab1")  # at risk is a level 3 matter
    assert page.locator("#pw-risk").evaluate("e => e.closest('.prow2').hidden")
    assert page.errors == []


def test_without_the_checklist_level_3_lists_by_confidence_without_errors(browser, site):
    base, pts = site
    page = open_level_3(browser, base, "#lvl=3&conf=all", fail=True)
    page.wait_for_function("document.getElementById('psum').textContent.includes('did not')")
    rank = dict(zip(pts["id"].tolist(), rank_plane(base).tolist(), strict=True))
    got = [rank[i] for i in view(page)]
    assert got == sorted(got) and page.locator("#grid .gap").count() == 0
    assert page.errors == []
