"""Text hits of caught and prey name a prey only after the verb, or by a linked observation."""

import pytest
import requests

from what_to_id import foodweb_obs

from . import foodweb_page
from . import test_embeddings_browser as eb
from .foodweb_page import build_site, open_page
from .test_eating import obs
from .test_eating_page import card_of, draw_all

browser = eb.browser


def test_a_linked_observation_becomes_the_prey_taxon(monkeypatch):
    taxon = {"name": "Megaceryle alcyon", "id": 2548, "rank": "species"}
    d = {
        44: "prey: https://inaturalist.ca/observations/45",
        9: "www.inaturalist.org/observations/9",
    }
    d[46] = d[44]
    recs = [
        foodweb_obs.slim_text({**obs(i, description=d[i]), "taxon": taxon}, {"Megaceryle alcyon"})
        for i in (44, 9, 46)
    ]
    assert [r.get("lk") for r in recs] == [45, None, 45]  # a link to itself is not a prey
    recs[2]["lk"] = 47  # its linked observation has no taxon

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            fish = {"name": "Stichaeidae", "id": 49, "preferred_common_name": "Pricklebacks"}
            return {"results": [{"id": 45, "taxon": fish}, {"id": 47}]}

    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    foodweb_obs.linked(recs, pause=0)
    assert recs[0]["lk"] == ["Stichaeidae", 49, "Pricklebacks"]
    assert "lk" not in recs[1] and "lk" not in recs[2]


def test_a_linked_plant_is_no_prey(monkeypatch):
    rec = {"t": ["Bembix americana", 53072, ""], "lk": 45}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            tansy = {"name": "Tanacetum vulgare", "id": 55971, "iconic_taxon_name": "Plantae"}
            return {"results": [{"id": 45, "taxon": tansy}]}

    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    foodweb_obs.linked([rec], pause=0)
    assert "lk" not in rec  # "Feeding on: <tansy>" is a flower visit


def site(tmp, hits, vlm):
    meta = {
        **foodweb_page.META,
        "parent": {**foodweb_page.META["parent"], "Pandalus danae": "Caridea"},
    }
    with pytest.MonkeyPatch.context() as m:
        m.setattr(foodweb_page, "META", meta)
        m.setattr(foodweb_page, "TEXT", {**foodweb_page.TEXT, "obs": hits})
        m.setattr(foodweb_page, "VLM", vlm)
        yield from build_site(tmp)


@pytest.fixture(scope="module")
def caught(tmp_path_factory):
    hits = [
        foodweb_page.hit(801, "Caught a shrimp! "),
        foodweb_page.hit(802, "Caught in a spider web"),
        foodweb_page.hit(803, "Song Sparrow prey"),
        {
            **foodweb_page.hit(804, "Prey, see its own record"),
            "lk": ["Stichaeidae", 49, "Pricklebacks"],
        },
        foodweb_page.hit(805, "Caught it eating"),
        foodweb_page.hit(806, "Caught my eye, a bird of prey"),
        foodweb_page.hit(807, "Caught by a crab"),
        foodweb_page.hit(808, "Caught in the act of eating a shrimp"),
        foodweb_page.hit(809, "Spotted by a friend, caught by me. A shrimp nearby"),
        foodweb_page.hit(810, "Eating. Small birds were mobbing it"),
        foodweb_page.hit(811, "Caught on trail camera, a shrimp nearby"),
        foodweb_page.hit(812, "Feeding on coyote scat, a shrimp on it"),
    ]
    guess = {"p": 0.95, "prey": [["Mus musculus", 0.6]]}
    vlm = {**foodweb_page.VLM, "obs": {"801": guess, "805": guess}}
    yield from site(tmp_path_factory.mktemp("caught-site"), hits, vlm)


@pytest.fixture(scope="module")
def negated(tmp_path_factory):
    hits = [
        foodweb_page.hit(813, "Could not see if it caught anything, a shrimp nearby"),
        foodweb_page.hit(814, "It didn't catch the shrimp"),
        foodweb_page.hit(815, "No prey, a shrimp in the water"),
        foodweb_page.hit(816, "Dove and missed the shrimp"),
        foodweb_page.hit(817, "Eating a bee fly"),
        foodweb_page.hit(818, "Eating a robber-fly"),
        foodweb_page.hit(819, "Eating a bee"),
        foodweb_page.hit(
            820, "caught on trail camera - looking for roosting ducks (eating dead and soft salmon)"
        ),
        foodweb_page.hit(
            821, "Feeding on what appears to be a stickleback (it didn't actually swallow it)"
        ),
        foodweb_page.hit(
            822, "Eating a feral rock pigeon/dove. Bird was calm with me a few feet away."
        ),
    ]
    yield from site(tmp_path_factory.mktemp("negated-site"), hits, foodweb_page.VLM)


def test_caught_or_prey_names_a_prey_or_draws_no_card(browser, caught):
    page = open_page(browser, caught + "#q=eats&x=Strix varia")
    draw_all(page)
    assert "may be eating" not in card_of(page, 801)  # a model-study card is blind
    assert "Barred Owl may be eating Pricklebacks" in card_of(page, 804)
    assert "links the prey’s observation" in card_of(page, 804)
    assert "may be eating" not in card_of(page, 805)
    assert "Barred Owl may be eating Caridea" in card_of(page, 808)
    assert "may be eating something" in card_of(page, 810)  # the mobbers are no prey
    assert page.locator("#cards .vlm").count() == 0
    # no prey in the observer's credit ("caught by me", "caught on camera"), nor on the scat it eats
    for i in (802, 803, 806, 807, 809, 811, 812):
        assert page.locator(f"#cards a[href$='/observations/{i}']").count() == 0
    assert page.errors == []


def test_a_negated_catch_a_compound_name_or_another_animals_meal_names_no_prey(browser, negated):
    page = open_page(browser, negated + "#q=eats&x=Strix varia")
    draw_all(page)
    # "could not see", "didn't catch", "no prey", "missed", and a meal the text gives to the ducks
    for i, prey in (
        (813, "Caridea"),
        (814, "Caridea"),
        (815, "Caridea"),
        (816, "Caridea"),
        (820, "almon"),
    ):
        cards = page.locator(f"#cards li:has(a[href$='/observations/{i}'])")
        assert prey not in " ".join(cards.all_inner_texts())
    # a bee fly or robber fly is no bee or fly prey, a plain bee still is
    assert "may be eating something" in card_of(page, 817)
    assert "may be eating something" in card_of(page, 818)
    assert "Anthophila" in card_of(page, 819)
    assert "Gasterosteidae" in card_of(page, 821)  # the stickleback text of 44693670
    assert "may be eating Aves" in card_of(page, 822)  # the rock pigeon text of 329488383
    assert page.errors == []
