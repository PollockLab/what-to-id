"""The Identify page in Chromium: a selection keeps what the map keeps, the cards follow the levels
file, and the photos come 200 ids to a request. iNaturalist is stubbed."""

import functools
import http.server
import threading

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_identify, pool_levels
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.page_map import decode_points, encode_points, render_map

from . import test_embeddings_browser as eb
from .embeddings_fixture import TREE, pool_frame
from .test_page_nav import FORBIDDEN

browser = eb.browser
N = 2100
LOOKS = ["Bombus a", "Bombus b", "Apis c"]
LABELS = ["Clear matches", "Close calls", page_identify.NARROW_LABEL, "Odd shots"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("identify-site")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    blobs, meta = encode_points(pool_frame(ids), TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    pts = decode_points(blobs, meta)
    i = np.arange(N)
    scored = pd.DataFrame(
        {
            "id": pts["id"].to_numpy(np.int64),
            "taxon_id": pts["taxon_id"].to_numpy(np.int64),
            "level": np.where(i % 6 == 0, 0, 1 + (i * 7) % 4).astype("int8"),
            "score": np.random.default_rng(2).normal(size=N).astype("float32"),
            "score2": np.float32(0),
            "looks_like": pd.Series([LOOKS[k % 3] for k in i], dtype="category"),
        }
    )[list(IDENTIFY_COLUMNS)]
    scored.to_parquet(root / "identify.parquet")
    pool_levels.build(root, parquet=root / "identify.parquet")
    page_identify.build(root)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pts = pts.assign(level=scored["level"].to_numpy())
    yield f"http://127.0.0.1:{server.server_port}", pts
    server.shutdown()


def open_identify(browser, base, hash_="", size=(600, 900)):
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    # the header's links to the site's other pages are not in this fixture's site
    page.on(
        "response",
        lambda r: page.errors.append(r.url) if r.status >= 400 and ".html" not in r.url else None,
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


def test_cards_follow_the_chosen_level_with_a_few_per_species_and_photos_in_batches(browser, site):
    base, pts = site
    page = open_identify(browser, base, "#lvl=1", (380, 500))
    page.wait_for_function("document.querySelectorAll('.card .ph img').length > 0")
    shown = page.evaluate("__identify.view()")
    level = dict(zip(pts["id"], pts["level"], strict=True))
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    for lv in (1, 2, 3, 4):
        assert shown[lv] and all(level[i] == lv for i in shown[lv])
        counts = pd.Series([taxon[i] for i in shown[lv]]).value_counts()
        assert counts.max() <= 3 and len(counts) == 7  # a few of each of the seven species
    assert page.locator("#grid .card").count() == 12
    assert all(len(c) <= 200 for c in page.calls) and page.calls
    before = len(page.calls)
    page.evaluate("scrollTo(0, document.body.scrollHeight)")
    page.wait_for_function("document.querySelectorAll('#grid .card').length === 21")
    assert len(page.calls) == before + 1 and len(page.calls[-1]) == 9
    tab(page, 3).click()
    page.wait_for_selector("#grid .card .look")
    text = page.locator("#grid .card .look").first.inner_text()
    assert text.startswith("Probably ") and text.split()[1] in {"Bombus", "Apis"}
    tab(page, 2).click()
    page.wait_for_selector("#grid .card .look")
    assert "Often confused with" in page.locator("#grid .card .look").first.inner_text()
    body = page.inner_text("body").lower()
    assert not any(word in body for word in FORBIDDEN)
    assert "no level yet" in page.locator(".about").text_content()
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
    assert html.count(page_identify.NARROW_LABEL) == 1  # only in the config the constant fills
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
    page.wait_for_function("__identify.total()[2] === 0 && __identify.total()[4] > 0")
    assert page.evaluate("__identify.level()") == 2
    assert page.locator("#batch").is_hidden()
    total = page.evaluate("__identify.total()")
    for lv in range(1, 5):
        assert ("zero" in tab(page, lv).get_attribute("class")) == (total[lv] == 0)
    page.locator("#none button", has_text=LABELS[3]).click()
    assert page.evaluate("__identify.level()") == 4
    assert page.locator("#none").is_hidden() and page.locator("#batch").is_visible()
    assert page.errors == []


def test_the_tabs_switch_the_cards_and_their_counts_are_the_totals(browser, site):
    base, pts = site
    page = open_identify(browser, base)
    total = page.evaluate("__identify.total()")
    assert page.evaluate("__identify.level()") == 2  # opens on Close calls
    assert page.get_by_role("tab", selected=True).count() == 1
    for lv, label in enumerate(LABELS, 1):
        assert " ".join(tab(page, lv).inner_text().split()) == f"{label} {total[lv]:,}"
    tab(page, 2).focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("__identify.level()") == 3
    assert tab(page, 3).get_attribute("aria-selected") == "true"
    assert tab(page, 3).get_attribute("tabindex") == "0"
    assert tab(page, 2).get_attribute("tabindex") == "-1"
    page.keyboard.press("End")
    assert page.evaluate("__identify.level()") == 4
    page.wait_for_selector("#grid .card")
    shown = {
        int(i) for i in page.eval_on_selector_all("#grid .card", "l => l.map(e => e.dataset.id)")
    }
    level = dict(zip(pts["id"], pts["level"], strict=True))
    assert shown and {level[i] for i in shown} == {4}
    assert page.locator("#desc").inner_text() == page_identify.LEVELS[3][2]
    page.reload()
    page.wait_for_function("window.__identify")
    assert page.evaluate("__identify.level()") == 4  # kept in the hash
    assert page.errors == []


def test_a_card_posts_its_record_on_click_and_focus_on_hover(browser, site):
    base, _ = site
    page, frame = wrapped(browser, base, "#lvl=1")
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
    for lv in (1, 2, 3, 4):
        tab(page, lv).click()
        want = sorted(page.evaluate("__identify.view()")[lv])
        href = page.get_attribute("#go", "href")
        assert sorted(int(i) for i in href.split("&id=")[1].split(",")) == want
        assert page.locator("#go").inner_text() == f"Identify these {len(want)}"
        assert page.locator("#go").get_attribute("target") == "_blank"
    assert page.errors == []
