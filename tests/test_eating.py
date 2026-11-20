"""The Food web data: feeding observations and food-word hits slimmed from iNaturalist and the
stand-in metaweb with its implausibility rule. iNaturalist is not called."""

import json

from what_to_id import foodweb_obs, metaweb

from .foodweb_page import META


def obs(id_, field=None, **kw):
    return {
        "id": id_,
        "taxon": {"name": "Larus glaucescens", "id": 7, "preferred_common_name": "Gull"},
        "photos": [{"url": "https://x/photos/1/square.jpg"}],
        "quality_grade": "needs_id",
        "comments_count": 2,
        "ofvs": [field] if field else [],
        **kw,
    }


def test_slim_keeps_the_named_prey_or_the_text_and_drops_what_cannot_show():
    named = foodweb_obs.slim(
        obs(1, {"field_id": 13, "taxon": {"name": "Clupea", "id": 9}}), "eating"
    )
    assert named["f"] == ["Clupea", 9] and named["ph"].endswith("/medium.jpg") and named["c"] == 2
    assert named["ll"] is None  # no location, no marker
    placed = foodweb_obs.slim(obs(6, location="49.25,-123.123456"), "eating")
    assert placed["ll"] == [49.25, -123.1235]
    text = foodweb_obs.slim(obs(2, {"field_id": 879, "value": " a hawk " + "x" * 200}), "by")
    assert text["x"].startswith("a hawk") and len(text["x"]) == foodweb_obs.TEXT and "f" not in text
    assert "f" not in foodweb_obs.slim(
        obs(3, {"field_id": 13}), "eating"
    )  # the wrong field is ignored
    assert foodweb_obs.slim(obs(4, field=None, photos=[]), "eating") is None
    assert foodweb_obs.slim({**obs(5), "taxon": None}, "eating") is None


def test_counts_split_named_text_only_and_empty():
    rows = [
        {"f": ["a", 1], "c": 1, "q": "research"},
        {"x": "fish", "c": 0, "q": "needs_id"},
        {"c": 0, "q": "needs_id"},
    ]
    assert foodweb_obs.counts(rows) == {
        "obs": 3,
        "named": 1,
        "text_only": 1,
        "empty": 1,
        "with_comments": 1,
        "needs_id": 2,
    }
    assert foodweb_obs.counts([])["obs"] == 0


def test_metaweb_carries_common_names_and_the_ancestors_of_its_names():
    taxa = [["Life", "", 1, "root", -1, 0], ["Muridae", "Mice", 2, "family", 0, 0]]
    taxa += [["Mus musculus", "House Mouse", 3, "species", 1, 0]]
    m = metaweb.build({"eats": {"Strix": [["Mus musculus", 1]]}}, taxa=taxa)
    assert m["common"] == {"Mus musculus": "House Mouse"}
    assert m["parent"] == {"Mus musculus": "Muridae", "Muridae": "Life"}
    assert metaweb.build({"eats": {}})["common"] == {}


def test_metaweb_probability_halves_the_doubt_and_drops_a_slug_eating_a_bird():
    web = {"eats": {"Slug": [["Robin", 1], ["Moss", 1]], "Owl": [["Robin", 3]]}}
    taxa = [["Mollusca", "", 1, "class", -1, 0], ["Slug", "", 2, "species", 0, 0]]
    taxa += [["Aves", "", 3, "class", -1, 0], ["Robin", "", 4, "species", 2, 0]]
    group = metaweb.groups(taxa, {"Mollusca": 1, "Aves": 3})
    assert group == {"Mollusca": "Mollusca", "Slug": "Mollusca", "Aves": "Aves", "Robin": "Aves"}
    pairs = metaweb.build(web, group)["pairs"]
    assert pairs == [["Owl", "Robin", 0.875], ["Slug", "Moss", 0.5]]
    assert len(metaweb.build(web)["pairs"]) == 3  # without groups nothing is dropped
    assert metaweb.build({"eats": {}})["pairs"] == []


def test_metaweb_carries_ranks_and_group_labels_for_the_picker():
    taxa = [["Aves", "", 3, 0, -1, 0], ["Strix", "", 4, 1, 0, 0]]
    m = metaweb.build(
        {"eats": {"Strix": [["Strix", 1]]}},
        taxa=taxa,
        ranks=["class", "genus"],
        labels={"Aves": "Birds"},
    )
    assert m["groups"] == {"Aves": "Birds"} and m["rank"] == {"Strix": "genus", "Aves": "class"}
    assert metaweb.build({"eats": {}})["groups"] == {}


def test_slim_text_keeps_a_photographed_predator_species_with_its_words():
    taxon = {"name": "Strix varia", "id": 1, "rank": "species"}
    hit = {
        **obs(10, description="  Eating a vole " + "x" * 400, tags=["predation"]),
        "taxon": taxon,
    }
    r = foodweb_obs.slim_text(hit, {"Strix"})
    assert (
        r["k"] == "text"
        and r["d"].startswith("Eating a vole")
        and len(r["d"]) == foodweb_obs.TEXT * 3
    )
    assert r["g"] == ["predation"] and foodweb_obs.slim_text(hit, {"Buteo"}) is None
    genus = {**hit, "taxon": {**hit["taxon"], "rank": "genus"}}
    assert (
        foodweb_obs.slim_text(genus, {"Strix"}) is None
        and foodweb_obs.slim_text({**hit, "photos": []}, {"Strix"}) is None
    )
    assert foodweb_obs.predators(META) == {"Strix", "Buteo"}


def test_slim_keeps_the_photo_count_and_no_text():
    two = [{"url": "https://x/photos/1/square.jpg"}] * 2
    r = foodweb_obs.slim(obs(7, photos=two, comments=[{"body": "nice shot"}]), "eating")
    assert r["np"] == 2 and "nt" not in r and "nice shot" not in json.dumps(r)


def test_fetches_stop_before_inaturalists_10000_result_limit(monkeypatch, capsys):
    import requests

    seen = []

    class R:
        def __init__(self, page):
            self.page = page

        def raise_for_status(self):
            assert self.page * foodweb_obs.PER_PAGE <= foodweb_obs.LIMIT

        def json(self):
            return {"results": [{"id": 1}] * foodweb_obs.PER_PAGE}

    def get(url, params, **kw):
        seen.append(params["page"])
        return R(params["page"])

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(foodweb_obs, "slim", lambda o, k: None)
    foodweb_obs.fetch("eating", pause=0)
    assert max(seen) == foodweb_obs.LIMIT // foodweb_obs.PER_PAGE
    seen.clear()
    foodweb_obs.fetch_text({"Strix"}, pause=0)
    assert max(seen) == foodweb_obs.LIMIT // foodweb_obs.PER_PAGE
    assert "cut at iNaturalist's 10000 result limit" in capsys.readouterr().err
