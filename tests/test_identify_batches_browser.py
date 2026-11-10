"""The Batches tab: Identify opens on the study's batches, Next batch serves them in turn,
each served batch and posted ID lands in the browser's trace, and #record= opens the levels."""

import json

import numpy as np
import pytest

from what_to_id import page_identify

from . import test_embeddings_browser as eb
from .embeddings_fixture import pool_frame
from .test_identify_browser import serve

browser = eb.browser
N = 300
WORDS = ("recency", "gap first", "gap_first", "similarity", "novelty", "surprise")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("batches-site")
    ids = np.random.default_rng(3).choice(2**32 - 2, N, replace=False) + 1
    server, pts = serve(root, pool_frame(ids), np.zeros(N, "float32"))
    pool = [int(i) for i in pts["id"][:4]]
    lists = {"A": {"Aves": [pool[:2], [pool[2]]]}, "B": {"Aves": [[pool[3]]]}}
    study = {"build": "b1", "day": "2026-09-01", "names": {"Aves": "Birds"}, "lists": lists}
    (root / "study.json").write_text(json.dumps(study))
    page_identify.build(root, study=root / "study.json")
    yield f"http://127.0.0.1:{server.server_port}", lists
    server.shutdown()


def open_batches(browser, base, hash_="", signed_in=False, size=(600, 900)):
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    page.errors, page.posts = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)

    def observations(route):
        ids = route.request.url.split("id=")[1].split("&")[0].split(",")
        results = [
            {
                "id": int(i),
                "quality_grade": "needs_id",
                "photos": [{"url": f"https://static.inaturalist.org/photos/{i}/square.jpg"}],
                "taxon": {"id": 3, "name": "Aves", "preferred_common_name": "Birds"},
            }
            for i in ids
        ]
        route.fulfill(json={"results": results}, headers={"access-control-allow-origin": "*"})

    def identifications(route):
        cors = {"access-control-allow-origin": "*", "access-control-allow-headers": "*"}
        if route.request.method == "POST":
            page.posts.append(json.loads(route.request.post_data))
        route.fulfill(json={}, headers=cors)

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.route("https://api.inaturalist.org/v1/identifications", identifications)
    if signed_in:
        user = json.dumps({"jwt": "test-token", "user": {"id": 7, "login": "me"}})
        page.add_init_script(f"sessionStorage.setItem('wtid-inat', {json.dumps(user)})")
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify")
    return page


def served(page):
    return page.evaluate("JSON.parse(localStorage.getItem('wtid-study-log')||'[]')")


def cards(page):
    page.wait_for_function("document.querySelectorAll('#sgrid .card img').length>0")
    return sorted(
        int(i) for i in page.eval_on_selector_all("#sgrid .card", "l=>l.map(c=>c.dataset.id)")
    )


def test_identify_opens_on_batches_and_next_batch_serves_each_in_turn(browser, site):
    base, lists = site
    page = open_batches(browser, base)
    assert page.evaluate("document.body.classList.contains('bt')")
    assert page.is_visible("#study") and not page.is_visible("#panel")
    assert page.is_disabled("#snext") and served(page) == []
    page.select_option("#sgroup", "Aves")
    batches = [b for label in lists.values() for b in label["Aves"]]
    seen = []
    for k in range(1, 4):
        if k > 1:
            page.click("#snext")
        got = cards(page)
        assert got in [sorted(b) for b in batches] and got not in seen
        seen.append(got)
        assert page.text_content("#sprog") == f"Batch {k} of 3"
        log = served(page)
        assert len(log) == k and sorted(log[-1]["ids"]) == got
        assert {log[-1]["group"], log[-1]["day"], log[-1]["build"]} == {"Aves", "2026-09-01", "b1"}
    assert page.is_disabled("#snext") and page.is_visible("#sdone")
    assert page.get_attribute("a[href='terms.html#study']", "target") == "_blank"
    text = page.inner_text("body").lower()
    assert not [w for w in WORDS if w in text]
    assert page.errors == []


def test_a_record_link_opens_the_levels_not_the_batches(browser, site):
    base, lists = site
    page = open_batches(browser, base, f"#record={lists['A']['Aves'][0][0]}")
    assert not page.evaluate("document.body.classList.contains('bt')")
    assert page.is_visible("#panel") and not page.is_visible("#study")
    assert page.errors == []


def test_signed_in_agree_posts_the_id_and_lands_in_the_trace(browser, site):
    base, _ = site
    page = open_batches(browser, base, signed_in=True)
    page.select_option("#sgroup", "Aves")
    first = cards(page)[0]
    button = page.locator(f"#sgrid .card[data-id='{first}'] .act", has_text="Agree")
    button.click()
    page.wait_for_function(
        "[...document.querySelectorAll('.act')].some(b=>b.textContent==='Posted')"
    )
    assert page.posts == [{"identification": {"observation_id": first, "taxon_id": 3}}]
    posts = [p for entry in served(page) for p in entry.get("posts", [])]
    assert [(p["id"], p["taxon"], p["user"]) for p in posts] == [(first, 3, 7)]
    assert "test-token" not in page.evaluate("JSON.stringify(localStorage)")
    assert page.errors == []
