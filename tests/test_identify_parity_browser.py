"""Every filter of the map's What panel in Identify: the map opens with the filter in its hash, Identify opens with the same
hash and keeps the records the map's rule keeps, the key still in the address. The map is the real page over stand-ins for
MapLibre and deck.gl, iNaturalist is stubbed."""

import numpy as np
import pytest

from what_to_id.map_projects import PROJECTS, encode_projects

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame
from .test_map_groups_browser import STUB

browser = eb.browser
PID = PROJECTS[0]["id"]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("identify-parity")
    ids = np.random.default_rng(1).choice(2**32 - 2, ib.N, replace=False) + 1
    frame, i = pool_frame(ids), np.arange(ib.N)
    frame["introduced"] = i % 5 == 0
    frame["threatened"] = i % 7 == 0
    frame["pos_acc"] = np.array([np.nan, 5000, 500, 50, 5])[i // 3 % 5]
    frame["ident_count"], frame["agree"] = 2 + i % 2, np.where(i % 3 == 0, 2, 0)
    mine = np.sort(frame["id"].to_numpy()[i % 4 == 0])
    (root / "projects.bin").write_bytes(encode_projects({PID: {"ids": mine, "since": "2026-10-01T00:00:00Z"}}))
    score = np.random.default_rng(2).normal(size=ib.N).astype("float32")
    server, pts = ib.serve(root, frame, score, projects=root / "projects.bin")
    yield f"http://127.0.0.1:{server.server_port}", pts.assign(mine=pts["id"].isin(mine))
    server.shutdown()


def one_id(p):  # map_filter.js oneId: one more agreeing ID gives Research Grade
    return 3 * (p["agree"] + 2) > 2 * (p["ident_count"] + 2)


# (hash, the map's verdict per record in pandas)
CASES = [
    ("only=introduced", lambda p: p["introduced"]),
    ("only=-introduced", lambda p: ~p["introduced"]),
    ("only=threatened", lambda p: p["threatened"]),
    ("only=oneid", one_id),
    ("only=-oneid", lambda p: ~one_id(p)),
    ("acc=known", lambda p: p["acc_class"] >= 1),
    ("acc=1000", lambda p: p["acc_class"] >= 2),
    ("acc=10", lambda p: p["acc_class"] >= 4),
    ("acc=unknown", lambda p: p["acc_class"] == 0),
    ("only=introduced&acc=100", lambda p: p["introduced"] & (p["acc_class"] >= 3)),
    ("projects=%d" % PID, lambda p: p["mine"]),
    ("projects=-%d" % PID, lambda p: ~p["mine"]),
    ("groups=Aves", lambda p: p["iconic_taxon"] == "Aves"),
    ("groups=-Aves", lambda p: p["iconic_taxon"] != "Aves"),
    ("groups=Plantae&only=introduced", lambda p: (p["iconic_taxon"] == "Plantae") & p["introduced"]),
    ("taxa=900", lambda p: p["taxon_id"].isin([1000, 1001, 1002])),
]


def open_map(browser, base, hash_):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(
            body=STUB if r.request.url.endswith(".js") else "", content_type="text/javascript"
        ),
    )
    page.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json={"results": []}))
    page.goto(f"{base}/map.html?standalone=1#{hash_}")
    page.wait_for_function("!/^Loading/.test(document.getElementById('count').textContent)")
    return page


@pytest.mark.parametrize(("hash_", "verdict"), CASES, ids=[c[0] for c in CASES])
def test_a_map_filter_in_the_hash_keeps_the_same_records_in_identify(browser, site, hash_, verdict):
    base, pts = site
    m = open_map(browser, base, hash_)
    carried = m.evaluate("location.hash")
    assert all(t in carried for t in hash_.split("&")) and m.errors == []
    page = ib.open_identify(browser, base, carried)
    want = sorted(pts["id"][verdict(pts)].tolist())
    assert want and len(want) < len(pts)
    page.wait_for_function(f"__identify.ids().length === {len(want)}")  # the projects file lands late
    assert ib.ids(page) == want
    assert all(t in page.evaluate("location.hash") for t in hash_.split("&")) and page.errors == []


def test_the_what_panel_holds_the_shortcuts_show_only_accuracy_and_projects(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base, "", size=(1440, 900))
    page.wait_for_function("__identify.ids().length > 0")
    page.click("#bwhat")
    page.locator("#flags button", has_text="Introduced").click()
    page.wait_for_function(f"__identify.ids().length === {int(pts['introduced'].sum())}")
    assert "only=introduced" in page.evaluate("location.hash")
    assert page.inner_text("#bwhat b") == "Introduced to BC"
    page.evaluate("a => { a.value = 3; a.dispatchEvent(new Event('input')); }", page.query_selector("#accr"))
    want = pts["introduced"] & (pts["acc_class"] >= 3)
    page.wait_for_function(f"__identify.ids().length === {int(want.sum())}")
    assert "acc=100&" in page.evaluate("location.hash") + "&"
    page.locator("#flags button", has_text="Introduced").click()  # a second click leaves it out
    page.locator("#projbox .chips button").first.click()
    page.wait_for_function("location.hash.includes('projects=')")
    mine = pts["mine"] & (pts["acc_class"] >= 3) & ~pts["introduced"]
    page.wait_for_function(f"__identify.ids().length === {int(mine.sum())}")
    assert page.locator("#clades button").count() > 0 and page.errors == []
    page.locator("#clades button").first.click()
    page.wait_for_function("location.hash.includes('taxa=')")


def test_a_user_in_the_hash_survives_the_trip_from_the_map(browser, site):
    base, _ = site
    carried = open_map(browser, base, "user=JDoe&umode=taxa").evaluate("location.hash")
    page = ib.open_identify(browser, base, carried)
    page.wait_for_function("__identify.ids().length > 0")
    assert "user=JDoe" in page.evaluate("location.hash") and page.errors == []
