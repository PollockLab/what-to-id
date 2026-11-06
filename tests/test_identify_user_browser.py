"""Identify's User box on a pool with an observer file: the My taxa first top line and badges, and
the Observer view with no records."""

import numpy as np
import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame
from .test_identify_routing_browser import GENUS_A, counted

browser = eb.browser
N = ib.N


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("pyarrow")
    ids = np.random.default_rng(1).choice(2**32 - 2, N, replace=False) + 1
    score = np.random.default_rng(2).normal(size=N).astype("float32")
    frame = pool_frame(ids)
    frame["user_id"] = [10 + i % 2 for i in range(N)]
    server, pts = ib.serve(tmp_path_factory.mktemp("identify-user"), frame, score)
    yield f"http://127.0.0.1:{server.server_port}", pts
    server.shutdown()


def test_my_taxa_first_says_so_above_the_cards_and_badges_the_users_genera(browser, site):
    base, pts = site
    page = counted(browser, base, "#lvl=1&user=JDoe&umode=first")
    page.wait_for_function("__identify.user()")
    m = page.evaluate("__identify.mine()")
    assert page.locator("#grid li").first.get_attribute("class") == "sep top"
    assert page.locator("#grid .sep.top").inner_text() == f"Your genera first · {m} cards"
    taxon = dict(zip(pts["id"], pts["taxon_id"], strict=True))
    rows = page.evaluate("__identify.view()[1]")
    badged = page.locator("#grid .card:has(.badge)")
    shown = page.locator("#grid .card").count()
    assert badged.count() == min(m, shown) and all(
        taxon[i] in GENUS_A for i in rows[: badged.count()]
    )
    assert badged.first.locator(".badge").inner_text() == "Your genus"
    page.close()
    page = counted(browser, base, "#lvl=1&user=JDoe&umode=taxa")
    page.wait_for_function("__identify.user()")
    assert page.locator("#grid .sep, #grid .badge").count() == 0
    page.close()


def test_a_user_with_no_genus_gets_no_top_line_or_badge(browser, site):
    base, _ = site
    page = counted(browser, base, "#lvl=1&user=42&umode=first")
    page.route(
        "https://api.inaturalist.org/v1/identifications/species_counts*",
        lambda r: r.fulfill(json={"total_results": 0, "results": []}),
    )
    page.reload()
    page.wait_for_function(
        "window.__identify && /fewer than/.test(document.querySelector('#usrbox p').textContent)"
    )
    assert page.evaluate("__identify.user()") is False
    assert page.locator("#grid .sep, #grid .badge").count() == 0
    page.close()


def test_an_observer_view_with_no_records_offers_my_taxa_first(browser, site):
    base, _ = site
    page = counted(
        browser, base, "#lvl=1&user=JDoe"
    )  # an old link: Observer, and JDoe (777) posted nothing
    page.wait_for_function("document.querySelector('#none button')")
    assert page.inner_text("#none").startswith("No records observed by JDoe here.")
    assert "zoom out" not in page.inner_text("#none")
    page.click("#none button")
    page.wait_for_function("__identify.user() && __identify.ids().length")
    assert page.input_value("#usrbox select") == "first"
    assert "umode=first" in page.evaluate("location.hash") and page.errors == []
    page.close()
