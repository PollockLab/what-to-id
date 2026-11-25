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


@pytest.fixture(scope="module")
def caught(tmp_path_factory):
    meta = {
        **foodweb_page.META,
        "parent": {**foodweb_page.META["parent"], "Pandalus danae": "Caridea"},
    }
    hits = [
        foodweb_page.hit(801, "Caught a shrimp! "),
        foodweb_page.hit(802, "Caught in a spider web"),
        foodweb_page.hit(803, "Song Sparrow prey"),
        {
            **foodweb_page.hit(804, "Prey, see its own record"),
            "lk": ["Stichaeidae", 49, "Pricklebacks"],
        },
        foodweb_page.hit(805, "Caught it eating"),
    ]
    with pytest.MonkeyPatch.context() as m:
        m.setattr(foodweb_page, "META", meta)
        m.setattr(foodweb_page, "TEXT", {**foodweb_page.TEXT, "obs": hits})
        yield from build_site(tmp_path_factory.mktemp("caught-site"))


def test_caught_or_prey_names_a_prey_or_draws_no_card(browser, caught):
    page = open_page(browser, caught + "#q=eats&x=Strix varia")
    draw_all(page)
    assert "Barred Owl may be eating Caridea" in card_of(page, 801)
    assert "Barred Owl may be eating Pricklebacks" in card_of(page, 804)
    assert "links the prey’s observation" in card_of(page, 804)
    assert "may be eating something" in card_of(page, 805)  # a strong food word still counts
    for i in (802, 803):
        assert page.locator(f"#cards a[href$='/observations/{i}']").count() == 0
    assert page.errors == []
