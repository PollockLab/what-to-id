"""The tree card's reach line in Chromium: the share of a genus or family's BC records that reach
species Research Grade, read from api.inaturalist.org's total_results alone."""

from urllib.parse import parse_qs, urlparse

import pytest

from . import test_tree_browser as tb
from .embeddings_fixture import TREE
from .test_tree_idents_browser import CORS, ok

browser = tb.browser
site = tb.site


@pytest.fixture(scope="module")
def under_life(tmp_path_factory):
    """Family F is the fixture root, which has no card line: put it under Life beside a species."""
    yield from tb.built(
        tmp_path_factory,
        {
            **TREE,
            800: [700, "Family F", "", "family"],
            700: [None, "Life", "", "stateofmatter"],
            1006: [700, "Taxon 6", "", "species"],
        },
    )


def open_card(browser, site, sel, den, num):
    """The tree on taxon sel, observation counts answered den (all) and num (species RG)."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.errors, page.calls = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    tb.stub_taxa(page)
    page.route(
        "https://api.inaturalist.org/v1/observations/identifiers*",
        lambda r: ok(5)(r, 0),
    )

    def obs(route):
        q = {k: v[0] for k, v in parse_qs(urlparse(route.request.url).query).items()}
        page.calls.append(q)
        total = num if q.get("quality_grade") == "research" else den
        route.fulfill(json={"total_results": total, "results": []}, headers=CORS)

    page.route("https://api.inaturalist.org/v1/observations?*", obs)
    page.goto(f"{site}/tree.html#sel={sel}")
    page.wait_for_selector("#card h2")
    return page


def test_a_genus_shows_its_share_with_the_counts_in_the_tooltip(browser, site):
    page = open_card(browser, site, 900, 1000, 725)
    page.wait_for_function(
        "document.querySelector('#card [data-reach]')?.textContent.includes('In BC')"
    )
    assert page.inner_text("#card [data-reach]") == "In BC, 73% of Genus A records reach species"
    tip = page.get_attribute("#card [data-reach]", "title")
    assert tip.startswith("725 of 1,000 records") and "added before 20" in tip
    den, num = page.calls
    assert len(page.calls) == 2 and den["per_page"] == num["per_page"] == "0"
    assert den["place_id"] == "7085" and den["taxon_id"] == "900" and "quality_grade" not in den
    assert den["photos"] == den["verifiable"] == "true" and den["captive"] == "false"
    assert num["quality_grade"] == "research" and num["hrank"] == "species"
    assert {k: v for k, v in num.items() if k not in ("quality_grade", "hrank")} == den
    assert "—" not in tip and page.errors == []
    page.close()


def test_a_family_shows_it_too(browser, under_life):
    page = open_card(browser, under_life, 800, 200, 50)
    page.wait_for_function(
        "document.querySelector('#card [data-reach]')?.textContent.includes('In BC')"
    )
    assert page.inner_text("#card [data-reach]") == "In BC, 25% of Family F records reach species"
    page.close()


def test_it_says_nothing_below_fifty_records(browser, site):
    page = open_card(browser, site, 900, 49, 40)
    page.wait_for_function("document.querySelector('#card [data-reach]')?.hidden")
    assert page.inner_text("#card [data-reach]") == "" and len(page.calls) == 1
    page.close()


def test_a_species_asks_nothing(browser, site):
    page = open_card(browser, site, 1000, 1000, 900)
    page.wait_for_selector("#card [data-idents]")
    page.wait_for_function(
        "document.querySelector('#card [data-idents]').textContent.includes('identifiers')"
    )
    assert page.query_selector("#card [data-reach]") is None and page.calls == []
    page.close()
