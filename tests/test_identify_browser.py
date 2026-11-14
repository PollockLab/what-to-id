"""The Identify page in Chromium: a selection keeps what the map keeps, the cards follow the levels
file, and the photos come 200 ids to a request. iNaturalist is stubbed."""

import functools
import gzip
import http.server
import json
import re
import threading

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_identify, pool_levels, site_files
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.map_projects import add_projects
from what_to_id.page_lookalike import site_records
from what_to_id.page_map import align_totals, decode_points, encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .identify_sheets import reveal
from .test_page_nav import FORBIDDEN

browser = eb.browser
N = 2100
LOOKS = ["Bombus a", "Bombus b", "Apis c"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(root, frame, score, projects=None, totals=None):
    """Writes the map, levels and Identify pages for these pool rows and scores, and serves them;
    `projects` is a pool-projects.bin path for the map's Projects, `totals` the all-record counts
    as page_map.fetch_totals returns them, written as the map's totals file."""
    blobs, meta = encode_points(frame, TREE)
    if totals is not None:
        gz = gzip.compress(json.dumps(align_totals(totals, meta)).encode())
        blobs["pool-totals.bin"] = gz
        meta.setdefault("files", {})["totals"] = "pool-totals.bin"
    add_projects(blobs, meta, projects)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    meta["value"] = [[953, 2, 5]]  # the at-risk list: Apis c, the www tests' third suggestion
    (root / "map.html").write_text(render_map(meta, freeze=None))
    pts = decode_points(blobs, meta)
    i = np.arange(len(frame))
    scored = pd.DataFrame(
        {
            "id": pts["id"].to_numpy(np.int64),
            "taxon_id": pts["taxon_id"].to_numpy(np.int64),
            "level": np.where(i % 6 == 0, 0, 1 + (i * 7) % 4).astype("int8"),
            "score": score,
            "score2": (i % 5 * 0.012).astype("float32"),  # close, fair and clear margins
            "looks_like": pd.Series([LOOKS[k % 3] for k in i], dtype="category"),
            "runner_up": pd.Series([LOOKS[(k + 1) % 3] for k in i], dtype="category"),
        }
    )[[*IDENTIFY_COLUMNS, "runner_up"]]
    scored.loc[scored.index[scored["level"] == 4][0], "level"] = 5  # the one likely mislabel
    scored.to_parquet(root / "identify.parquet")
    pool_levels.build(root, parquet=root / "identify.parquet")
    page_identify.build(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, pts.assign(level=scored["level"].to_numpy())


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    score = np.random.default_rng(2).normal(size=N).astype("float32")
    server, pts = serve(tmp_path_factory.mktemp("identify-site"), pool_frame(ids), score)
    yield f"http://127.0.0.1:{server.server_port}", pts
    server.shutdown()


def panel(page, card):
    """Open the compare panel on a card the way a user does: close any open one, click the photo."""
    if page.locator("#cpanel:visible").count():
        page.locator("#cpx").click()
    card.locator(".car").click()
    page.wait_for_selector("#cpanel:visible")
    return page.locator("#cpanel")


WTB = "https://pollocklab.github.io/where-to-blitz/**"


def open_identify(browser, base, hash_="", size=(600, 900), touch=False):
    view = {"width": size[0], "height": size[1]}
    page = (
        browser.new_context(viewport=view, has_touch=True, is_mobile=True).new_page()
        if touch
        else browser.new_page(viewport=view)
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route(WTB, lambda r: r.abort())  # no live checklist: every gap stays 0 unless stubbed
    # the header's links to the site's other pages are not in this fixture's site
    page.on(
        "response",
        lambda r: page.errors.append(r.url) if r.status >= 400 and ".html" not in r.url else None,
    )
    # the panel's taxa and look-alike lookups: empty answers, not the live API's 4xx for fake ids
    page.route(
        "https://api.inaturalist.org/v1/**",
        lambda r: r.fulfill(json={"results": []}, headers={"access-control-allow-origin": "*"}),
    )
    page.calls = eb.stub_inat(page, None)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify")
    return page


def ids(page):
    return sorted(page.evaluate("__identify.ids()"))


def day(pts):
    return pd.to_datetime(pts["observed_on"])


# (hash, the map's verdict per record in pandas): a picked group beside a taxon adds to it, a
# left-out one subtracts, and the dates cut what is left
CASES = [
    ("", lambda p: p["id"] > 0),
    ("#groups=Aves", lambda p: p["iconic_taxon"] == "Aves"),
    ("#groups=-Aves", lambda p: p["iconic_taxon"] != "Aves"),
    ("#taxa=900", lambda p: p["taxon_id"].isin([1000, 1001, 1002])),
    (
        "#groups=Aves&taxa=900",
        lambda p: p["taxon_id"].isin([1000, 1001, 1002]) | (p["iconic_taxon"] == "Aves"),
    ),
    (
        "#groups=-Aves&taxa=900",
        lambda p: p["taxon_id"].isin([1000, 1001, 1002]) & (p["iconic_taxon"] != "Aves"),
    ),
    ("#from=2026-08-10&to=2026-09-10", lambda p: day(p).between("2026-08-10", "2026-09-10")),
    ("#months=9", lambda p: day(p).dt.month == 9),
]


@pytest.mark.parametrize(("hash_", "verdict"), CASES, ids=[c[0] or "all" for c in CASES])
def test_a_selection_keeps_exactly_the_records_the_map_filter_keeps(browser, site, hash_, verdict):
    base, pts = site
    page = open_identify(browser, base, hash_)
    want = sorted(pts["id"][verdict(pts)].tolist())
    assert want and ids(page) == want
    assert page.errors == []


def test_the_area_and_the_lasso_narrow_the_same_ids_as_the_map_keeps(browser, site):
    base, pts = site
    page = open_identify(browser, base)
    west = float(np.median(pts["lon"]))
    ring = [west, 48, -122, 48, -122, 50, west, 50]  # the east half of the points
    area = page.evaluate("r => MapArea.encode([r])", ring)
    page.evaluate("a => postMessage({type: 'wtid-area', area: a}, location.origin)", area)
    page.wait_for_function("__identify.ids().length < 2100")
    inside = pts["lon"] > west
    assert ids(page) == sorted(pts["id"][inside].tolist())
    lasso = sorted(pts["id"][inside].tolist())[::3] + [1]  # one id the pool does not hold
    page.evaluate(
        "l => postMessage({type: 'wtid-keep', ids: new Uint32Array(l)}, location.origin)", lasso
    )
    page.wait_for_function(f"__identify.ids().length === {len(lasso) - 1}")
    assert ids(page) == sorted(set(lasso) - {1})
    page.evaluate("postMessage({type: 'wtid-keep', ids: null}, location.origin)")
    page.wait_for_function(f"__identify.ids().length === {int(inside.sum())}")
    assert page.errors == []


def tab(page, lv):
    return page.locator(f"#tab{lv}")


def kind(page, name):
    return page.locator("#kind .segb", has_text=re.compile(f"^{name} "))


ORDER = [k for k, _ in page_identify.KINDS]  # Might be wrong lists its kinds in this order


def test_cards_follow_the_chosen_level_with_a_few_per_species_and_photos_in_batches(browser, site):
    base, pts = site
    page = open_identify(browser, base, "#lvl=1", (380, 500))
    page.wait_for_function("document.querySelectorAll('.card .ph img').length > 0")
    shown = page.evaluate("__identify.view()")
    level = dict(zip(pts["id"], pts["level"], strict=True))
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    for lv in (1, 3):
        assert shown[lv] and all(level[i] == lv for i in shown[lv])
    counts = pd.Series([taxon[i] for i in shown[1]]).value_counts()
    assert counts.max() <= 3 and len(counts) == 7  # a few of each of the seven species
    assert len(shown[3]) == 6  # level 3 caps by suggestion: its records suggest 2 species, 3 each
    assert not shown[2] and not shown[4]  # both in Might be wrong
    kinds = [level[i] for i in shown[5]]
    assert kinds == sorted(kinds, key=ORDER.index) and set(kinds) == {5, 4, 2}
    for k in (4, 2):  # the cut is per kind
        counts = pd.Series([taxon[i] for i in shown[5] if level[i] == k]).value_counts()
        assert counts.max() <= 3 and len(counts) == 7
    assert page.locator("#grid .card").count() == 12
    assert all(len(c) <= 200 for c in page.calls) and page.calls
    before = len(page.calls)
    page.evaluate("scrollTo(0, document.body.scrollHeight)")
    page.wait_for_function("document.querySelectorAll('#grid .card').length === 21")
    assert len(page.calls) == before + 1 and len(page.calls[-1]) == 9
    tab(page, 3).click()
    page.wait_for_selector("#grid .card .look", state="attached")
    text = page.locator("#grid .card .look").first.inner_text()
    assert text.startswith("Probably ") and text.split()[1] in {"Bombus", "Apis"}
    tab(page, 5).click()
    page.wait_for_selector("#grid .card .kind", state="attached")
    assert page.locator("#grid .card .kind").first.text_content() == "Likely mislabelled"
    assert page.locator("#grid .card .look").first.inner_text().startswith("Looks more like ")
    kind(page, "Close calls").click()
    page.wait_for_selector("#grid .card .look", state="attached")
    assert "Looks more like" in page.locator("#grid .card .look").first.inner_text()
    assert page.locator("#grid .card .kind").count() == 0  # one kind shown, no tags
    kind(page, "Likely mislabelled").click()
    assert page.locator("#grid .card").count() == 1
    assert "Might be wrong" in page.locator(".about").text_content()
    body = page.inner_text("body").lower()
    assert not any(word in body for word in FORBIDDEN)
    assert "photo download" in page.locator(".about").text_content()
    assert page.errors == []


def test_the_selection_changes_what_the_cards_show(browser, site):
    base, pts = site
    page = open_identify(browser, base, "#groups=Aves")
    page.wait_for_function("document.querySelectorAll('.card').length > 0")
    shown = {i for lv in page.evaluate("__identify.view()") if lv for i in lv}
    assert shown <= set(pts["id"][pts["iconic_taxon"] == "Aves"])
    page.evaluate("location.hash = ''")
    page.wait_for_function("__identify.ids().length === 2100")
    assert page.errors == []


def test_the_page_names_the_narrowing_group_from_one_constant_and_has_the_header():
    html = page_identify.render()
    assert html.count(page_identify.NARROW_LABEL) == 2  # the config and the About, both from it
    template = (page_identify.ASSETS / page_identify.PAGE_NAME).read_text()
    assert page_identify.NARROW_LABEL not in template
    assert "<nav" in html
    assert not [w for w in FORBIDDEN if w in html.lower()]


def wrapped(browser, base, hash_=""):
    """identify.html in a parent page that records what the frame posts, as the split page does."""
    page = browser.new_page(viewport={"width": 400, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.calls = eb.stub_inat(page, None)
    page.route(
        f"{base}/wrap.html",
        lambda r: r.fulfill(
            content_type="text/html",
            body=f"<script>var got=[];addEventListener('message',e=>got.push(e.data))</script>"
            f'<iframe id=f src="{base}/identify.html{hash_}" width=400 height=800></iframe>',
        ),
    )
    page.goto(f"{base}/wrap.html")
    frame = page.frame_locator("#f").owner.element_handle().content_frame()
    frame.wait_for_function("window.__identify")
    return page, frame


def test_a_viewport_narrows_the_ids_and_the_status_count_and_empty_restores_them(browser, site):
    base, pts = site
    page = open_identify(browser, base)
    west = float(np.median(pts["lon"]))
    view = page.evaluate("r => MapArea.encode([r])", [west, 48, -122, 48, -122, 50, west, 50])
    page.evaluate("a => postMessage({type: 'wtid-view', area: a}, location.origin)", view)
    page.wait_for_function("__identify.ids().length < 2100")
    want = sorted(pts["id"][pts["lon"] > west].tolist())
    assert ids(page) == want
    status = page.locator("#status").inner_text()
    assert status.startswith(f"{len(want):,} in view") and "3 per species" in status
    page.evaluate("postMessage({type: 'wtid-view', area: ''}, location.origin)")
    page.wait_for_function("__identify.ids().length === 2100")
    assert page.locator("#status").inner_text().startswith("2,100 ")
    levelled = page.evaluate("__identify.levelled()")
    assert f"· {levelled:,} in a level" in page.locator("#status").inner_text()
    reveal(page, "#status a")
    page.locator("#status a", has_text="in a level").click()
    assert page.locator("#about").get_attribute("open") is not None
    assert page.errors == []


def test_an_empty_level_hides_its_batch_link_and_points_at_the_levels_that_have_records(
    browser, site
):
    base, pts = site
    page = open_identify(browser, base)
    k = int(np.flatnonzero(pts["level"] == 4)[0])
    x, y, d = float(pts["lon"][k]), float(pts["lat"][k]), 1e-4
    view = page.evaluate(
        "r => MapArea.encode([r])", [x - d, y - d, x + d, y - d, x + d, y + d, x - d, y + d]
    )
    page.evaluate("a => postMessage({type: 'wtid-view', area: a}, location.origin)", view)
    page.wait_for_function("__identify.total()[1] === 0 && __identify.total()[5] > 0")
    assert page.evaluate("__identify.level()") == 1
    assert page.locator("#batch").is_hidden()
    total = page.evaluate("__identify.total()")
    for lv, *_ in page_identify.LEVELS:
        assert ("zero" in tab(page, lv).get_attribute("class")) == (total[lv] == 0)
    page.locator("#none button", has_text="Might be wrong").click()
    assert page.evaluate("__identify.level()") == 5
    assert page.locator("#none").is_hidden() and page.locator("#batch").is_visible()
    assert page.errors == []


def test_the_tabs_switch_the_cards_and_their_counts_are_the_totals(browser, site):
    base, pts = site
    page = open_identify(browser, base)
    total = page.evaluate("__identify.total()")
    assert page.evaluate("__identify.level()") == 1  # a first visit opens on Easy confirms
    assert page.get_by_role("tab", selected=True).count() == 1
    assert [t.get_attribute("id") for t in page.get_by_role("tab").all()] == [
        "tab1",
        "tab5",
        "tab3",
    ]
    for lv, label, _ in page_identify.LEVELS:
        assert " ".join(tab(page, lv).inner_text().split()) == f"{label} {total[lv]:,}"
    assert total[5] == int(pts["level"].isin([2, 4, 5]).sum())
    tab(page, 1).focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("__identify.level()") == 5
    assert tab(page, 5).get_attribute("aria-selected") == "true"
    assert tab(page, 5).get_attribute("tabindex") == "0"
    assert tab(page, 1).get_attribute("tabindex") == "-1"
    page.keyboard.press("ArrowRight")
    assert page.evaluate("__identify.level()") == 3
    page.wait_for_selector("#grid .card")
    shown = {
        int(i) for i in page.eval_on_selector_all("#grid .card", "l => l.map(e => e.dataset.id)")
    }
    level = dict(zip(pts["id"], pts["level"], strict=True))
    assert shown and {level[i] for i in shown} == {3}
    assert page.locator("#desc").inner_text() == page_identify.LEVELS[2][2]
    page.reload()
    page.wait_for_function("window.__identify")
    assert page.evaluate("__identify.level()") == 3  # kept in the hash
    assert page.errors == []


def test_a_card_posts_its_record_on_click_and_focus_on_hover(browser, site):
    base, _ = site
    # sort=conf: the default order moves the cards once the survey layer arrives
    page, frame = wrapped(browser, base, "#lvl=1&sort=conf")
    frame.wait_for_selector("#grid .card")
    first = frame.locator("#grid .card").first
    rid = int(first.get_attribute("data-id"))
    first.hover()
    page.wait_for_function("got.some(m => m.type === 'wtid-focus')")
    first.locator(".ph").click()
    page.wait_for_function("got.some(m => m.type === 'wtid-record')")
    got = page.evaluate("got.filter(m => m.type && m.type.startsWith('wtid-'))")
    assert {"type": "wtid-focus", "id": rid} in got and {"type": "wtid-record", "id": rid} in got
    assert page.errors == []


def test_scrolling_loads_more_cards(browser, site):
    base, _ = site
    page = open_identify(browser, base, "#lvl=1", (380, 500))
    page.wait_for_function("document.querySelectorAll('#grid .card').length === 12")
    assert page.locator("#more").is_visible()  # the fallback button
    page.evaluate("scrollTo(0, document.body.scrollHeight)")
    page.wait_for_function("document.querySelectorAll('#grid .card').length === 21")
    assert page.locator("#more").is_hidden()
    assert page.errors == []


def test_the_batch_links_cover_the_listed_ids(browser, site):
    base, _ = site
    page = open_identify(browser, base)
    for lv in (1, 3, 5):
        tab(page, lv).click()
        want = sorted(page.evaluate("__identify.view()")[lv])
        href = page.get_attribute("#go", "href")
        assert sorted(int(i) for i in href.split("&id=")[1].split(",")) == want
        assert page.locator("#go").inner_text() == f"Identify these {len(want)} on iNaturalist"
        assert page.locator("#go").get_attribute("target") == "_blank"
    page.evaluate("IdentifyLinks.MAX_IDS = 5")  # past the cap the button names both numbers
    tab(page, 1).click()
    tab(page, 5).click()
    n = len(page.evaluate("__identify.view()")[5])
    assert page.locator("#go").inner_text() == "Identify the first 5 on iNaturalist"
    assert page.locator("#bn").inner_text() == "" and page.locator("#next").is_hidden()
    # two records per batch: the arrows must change the button's words, not only its link
    page.evaluate(
        "() => { const f = IdentifyLinks.batches; IdentifyLinks.batches = ids => "
        "[ids.slice(0, 2), ids.slice(2, 4), ids.slice(4)].map(b => f(b)[0]); }"
    )
    tab(page, 1).click()
    tab(page, 5).click()
    first = page.get_attribute("#go", "href")
    assert page.locator("#go").inner_text() == "Identify these 2 on iNaturalist"
    assert page.locator("#bn").inner_text() == "Batch 1 of 3"
    assert (
        page.locator("#cap").inner_text()
        == f"{n:,} cards (up to 3 per species) · first 5 in 3 batches of 200, in the order shown"
    )
    page.click("#next")
    assert page.locator("#go").inner_text() == "Identify these 2 on iNaturalist"
    assert page.locator("#bn").inner_text() == "Batch 2 of 3"
    assert page.get_attribute("#go", "href") != first and page.locator("#prev").is_enabled()
    page.click("#next")
    assert page.locator("#go").inner_text() == "Identify this record on iNaturalist"
    # one record skips the Identify grid: its own page, at the ID form
    assert re.fullmatch(
        r"https://www\.inaturalist\.ca/observations/\d+#comment-id-tabs",
        page.get_attribute("#go", "href"),
    )
    assert page.locator("#bn").inner_text() == "Batch 3 of 3"
    assert page.locator("#next").is_disabled()
    assert page.errors == []


def test_the_batches_follow_the_card_order_not_the_newest_ids(browser, site):
    base, _ = site
    page = open_identify(browser, base)
    # a list holds 21 cards, so append 200 newer ids: sorted newest first they would fill batch 1
    page.evaluate(
        "() => { const f = IdentifyLinks.batches; IdentifyLinks.batches = (ids, kept) => "
        "f(Array.from(ids).concat(Array.from({length: 200}, (_, i) => 1e10 + i)), kept); }"
    )
    tab(page, 5).click()
    shown = page.evaluate("__identify.view()")[5]
    first = [int(i) for i in page.get_attribute("#go", "href").split("&id=")[1].split(",")]
    assert set(shown) <= set(first) and first == sorted(first, reverse=True)
    assert page.errors == []


def test_without_the_range_file_the_cards_have_no_range_chips(browser, site):
    base, _ = site
    page = open_identify(browser, base, "#lvl=1")
    page.wait_for_selector("#grid .card")
    assert page.evaluate("__identify.ranges()") is False
    assert page.locator(".rchip, .card .range").count() == 0 and page.locator("#rout").is_hidden()


def test_a_cut_species_offers_its_other_records_and_picking_it_shows_them_all(browser, site):
    base, pts = site
    page = open_identify(browser, base, "#lvl=1")
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    page.wait_for_selector("#grid .card .sp", state="attached")
    shown = page.evaluate("__identify.view()")[1]
    link = page.locator("#grid .card .sp").first
    species = taxon[int(link.locator("xpath=ancestor::li[1]").get_attribute("data-id"))]
    have = int(((pts["taxon_id"] == species) & (pts["level"] == 1)).sum())
    assert have > 3 and sum(taxon[i] == species for i in shown) == 3
    lead = f"+{have - 3} more "
    name = link.inner_text()[len(lead) :]
    assert link.inner_text().startswith(lead) and name
    assert link.get_attribute("aria-label") == f"Show {have - 3} more records of {name}"
    link.click()
    page.wait_for_function(f"__identify.view()[1].length === {have}")
    assert {taxon[i] for i in page.evaluate("__identify.view()[1]")} == {species}
    assert "taxa=" in page.evaluate("location.hash") and "lvl=1" in page.evaluate("location.hash")
    assert page.locator("#grid .sp").count() == 0
    page.click("#unpick")
    page.wait_for_function("__identify.view()[1].length < 30")
    assert "taxa=" not in page.evaluate("location.hash") and page.locator("#unpick").is_hidden()
    assert page.errors == []


def test_cards_show_before_the_look_alike_file_and_fill_it_in_where_they_stand(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    held = []
    page.route("**/pool-levels-looks.*", lambda r: held.append(r))
    page.goto(f"{base}/identify.html#lvl=3")
    page.wait_for_function("window.__identify")  # the first cards carry their look-alike
    # the cards' photos are in, so there is room to scroll
    page.wait_for_function("document.documentElement.scrollHeight > innerHeight + 40")
    assert page.locator("#grid .card .look").count() == 0
    page.evaluate("scrollTo(0, 40)")
    held[0].continue_()
    page.wait_for_selector("#grid .card .look", state="attached")
    assert page.locator("#grid .card .look").first.inner_text().startswith("Probably ")
    assert page.evaluate("scrollY") == 40  # filled in place, not redrawn from the top
    assert page.errors == []


def test_a_level_lists_the_newest_records_first_within_a_score_bucket_across_shards(
    browser, tmp_path
):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(4).choice(2**32 - 2, N, replace=False) + 1
    frame = pool_frame(ids)
    frame.loc[frame.index % 2 == 0, "observed_on"] = "2026-01-15"  # before the recent 90 days
    score = np.random.default_rng(5).normal(size=N).astype("float32")
    server, pts = serve(tmp_path, frame, score)
    try:
        assert list(tmp_path.glob("pool-1.*.bin"))  # the older shard
        _, q = pool_levels.unpack(site_files.path(tmp_path, "levels").read_bytes())
        bucket = dict(zip(site_records(tmp_path)[0].tolist(), q.tolist(), strict=True))
        page = open_identify(browser, f"http://127.0.0.1:{server.server_port}", "#lvl=1")
        level = dict(zip(pts["id"], pts["level"], strict=True))
        for rows in page.evaluate("__identify.view()"):
            for a, b in zip(rows or [], (rows or [])[1:], strict=False):
                if level[a] == level[b] == 3:  # strictly by score (the rank file)
                    assert bucket[a] >= bucket[b], (a, b)
                elif level[a] == level[b]:  # Might be wrong lists its kinds one after another
                    assert bucket[a] > bucket[b] or a > b, (a, b)
                else:
                    assert ORDER.index(level[a]) < ORDER.index(level[b]), (a, b)
        assert page.errors == []
    finally:
        server.shutdown()
