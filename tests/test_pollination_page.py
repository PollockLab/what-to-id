"""The Pollination page in Chromium: the Food web template on pollination data, with insect cards"""

import json

import pytest

from what_to_id import page_eating

from . import test_embeddings_browser as eb
from .foodweb_page import META, OBS, open_page, serve

browser = eb.browser

POLLEN = {
    "source": "test",
    "rule": "r",
    "pairs": [
        ["Apis mellifera", "Trifolium repens", 0.9],
        ["Bombus mixtus", "Trifolium repens", 0.5],
        ["Bombus vosnesenskii", "Trifolium repens", 0.75],
        ["Bombus vosnesenskii", "Trifolium", 0.5],  # a genus-level record adds to the species'
        ["Bombus flavifrons", "Rosa", 0.5],  # another plant
        ["Bombus mixtus", "Rosa", 0.5, "pollinates"],
    ],
    "common": {"Trifolium repens": "White Clover", "Bombus mixtus": "Fuzzy-horned Bumble Bee"},
    "parent": {"Trifolium repens": "Plantae", "Bombus mixtus": "Bombus", "Apis mellifera": "Apis"},
    "rank": {},
    "groups": {},
}


def visit(id_, taxon, plant, q="needs_id"):
    return {
        "id": id_,
        "t": [taxon, id_, ""],
        "k": "visit",
        "c": 0,
        "q": q,
        "on": "",
        "at": "",
        "ph": "",
        "np": 1,
        "f": [plant, 2],
    }


# a bumble bee genus on clover (insect card), a research-grade honey bee (none), a genus with no
# plant named (none), and a Bombus mixtus at needs ID on Rosa (a card, no candidate in its taxon)
POLLEN_OBS = {
    "fetched": "2026-11-25",
    "field": "Interaction->Visited flower of",
    "n": {"obs": 4, "named": 3},
    "obs": [
        visit(1, "Bombus", "Trifolium repens"),
        visit(2, "Apis mellifera", "Trifolium repens", "research"),
        {k: v for k, v in visit(3, "Bombus", "").items() if k != "f"},
        visit(4, "Bombus mixtus", "Rosa"),
    ],
}


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    root = tmp_path_factory.mktemp("pollination-site")
    for name, data in (
        (page_eating.OBS_FILE, OBS),
        (page_eating.METAWEB_FILE, META),
        (page_eating.POLLINATION_OBS, POLLEN_OBS),
        (page_eating.POLLINATION_METAWEB, POLLEN),
    ):
        (root / name).write_text(json.dumps(data))
    assert page_eating.build(root).name == "food-web.html"
    yield next(serve(root, "pollination.html")), next(serve(root, "food-web.html"))


def test_the_pollination_page_asks_about_visits_and_leaves_the_cards_out(browser, sites):
    page = open_page(browser, sites[0])
    page.wait_for_selector("#mx td button", state="attached")
    assert page.locator("h1").inner_text() == "Pollination in BC"
    assert page.inner_text("#sent") == "What evidence is there for the pollination web?"
    assert [b.inner_text() for b in page.locator("#modes button").all()][1] == "X visits"
    assert not page.is_visible("#classes") and not page.is_visible("#export")
    assert page.is_visible("#mx") and page.is_visible("#net")
    assert page.locator("#net line.e.before").count() == 1
    page.click("#modes [data-q=eaten]")
    page.wait_for_function("document.getElementById('sent').textContent.startsWith('What visits')")
    assert "—" not in page.inner_text("body") and page.errors == []


def test_the_toggle_swaps_between_the_two_pages(browser, sites):
    page = open_page(browser, sites[0])
    assert page.locator("#kind [aria-checked=true]").inner_text() == "Pollination"
    page.click("#kind [data-q='food-web.html']")
    page.wait_for_url("**/food-web.html")
    page.wait_for_function("window.__food")
    assert page.locator("h1").inner_text() == "Food web in BC"
    assert page.locator("#kind [aria-checked=true]").inner_text() == "Predation"


def test_likely_visitors_stay_inside_the_taxon_and_rank_by_records(browser, sites):
    page = open_page(browser, sites[0])
    # genus Bombus on clover: no honey bee; vosnesenskii (0.75 and 0.5 add to 0.875) before mixtus
    got = page.evaluate("FoodLoop.likely('Bombus', 'Trifolium repens')")
    assert [n for n, _ in got] == ["Bombus vosnesenskii", "Bombus mixtus"]
    assert got[0][1] == pytest.approx(0.875)
    assert [
        n for n, _ in page.evaluate("FoodLoop.likely('Apis mellifera', 'Trifolium repens')")
    ] == ["Apis mellifera"]
    assert page.evaluate("FoodLoop.likely('Bombus', 'Rosa')")[0][0] == "Bombus flavifrons"
    assert page.evaluate("FoodLoop.likely('Osmia', 'Trifolium repens')") == []


def test_an_insect_card_lists_the_candidates_and_only_coarse_or_unconfirmed_records_get_one(
    browser, sites
):
    page = open_page(browser, sites[0])
    cards = page.locator("#cards > li")
    page.wait_for_function("document.querySelectorAll('#cards > li').length > 0")
    assert cards.count() == 2  # records 1 and 4; research-grade species and no plant get none
    card = page.locator("#cards > li", has_text="Likely visitors of White Clover")
    assert [a.inner_text() for a in card.locator(".lk a").all()] == [
        "Bombus vosnesenskii",
        "Fuzzy-horned Bumble Bee",
    ]
    assert (
        card.locator(".lk a")
        .nth(0)
        .get_attribute("href")
        .endswith("search?q=Bombus%20vosnesenskii")
    )
    assert "Honey" not in card.inner_text() and card.locator(".mk").count() == 0
    assert "—" not in page.inner_text("body") and page.errors == []


def test_a_needs_id_species_is_a_confirm_card_with_what_globi_has(browser, sites):
    page = open_page(browser, sites[0] + "#q=does&x=Bombus%20mixtus&y=Rosa")
    page.wait_for_function("window.__text && document.querySelectorAll('#cards > li').length > 0")
    card = page.locator("#cards > li").first
    assert "GloBI has one record of this species on Rosa, pollinates." in card.inner_text()
    assert card.locator("a.open").inner_text() == "Agree on iNaturalist"
    assert page.inner_text("#cand") == "The one card for this question is shown."
    assert not page.is_visible("#draw") and page.errors == []


def test_research_records_are_read_only_evidence_and_nothing_hides_the_button(browser, sites):
    page = open_page(browser, sites[0] + "#q=does&x=Apis%20mellifera&y=Trifolium%20repens")
    page.wait_for_function("window.__text && document.querySelectorAll('#cards > li').length > 0")
    card = page.locator("#cards > li").first
    assert "Already identified." in card.inner_text() and card.locator("button kbd").count() == 0
    assert page.inner_text("#cand") == "The one card for this question is shown."
    page.goto(sites[0] + "#q=does&x=Bombus%20vosnesenskii&y=Rosa")
    page.wait_for_function("window.__text")
    page.wait_for_function("document.getElementById('cand').textContent.startsWith('No photo')")
    assert page.inner_text("#cand") == "No photo of this pair yet."
    assert not page.is_visible("#draw")
