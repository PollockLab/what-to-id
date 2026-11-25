"""The Pollination data: GloBI pollinator-plant pairs, the metaweb without its scavenging rule,
and the Visited flower of observations. GloBI and iNaturalist are not called."""

import json

from what_to_id import foodweb, foodweb_obs, metaweb, page_eating

from .foodweb_page import META, OBS

BEE = "Animalia | Arthropoda | Insecta | Apis mellifera"
PLANT = "Plantae | Tracheophyta | Trifolium repens"


def row(kind, src=BEE, tgt=PLANT):
    return {"interaction_type": kind, "source_taxon_path": src, "target_taxon_path": tgt}


def test_pairs_keeps_animal_on_plant_rows_of_both_types_and_drops_the_rest():
    rows = [
        row("pollinates"),
        row("visitsFlowersOf"),
        row("visitsFlowersOf", tgt="Viridiplantae | Magnoliopsida | Trifolium repens"),
        row("pollinates", tgt=BEE),  # animal on animal
        row("pollinates", src=PLANT),  # plant as the pollinator
        row("pollinates", tgt=""),  # no path, so not known to be a plant
        row("eats"),  # another type
    ]
    t = foodweb.pairs(rows, "pollination")
    assert t["n"] == 3 and t["eats"] == {"Apis mellifera": [["Trifolium repens", 3]]}
    assert t["eatenBy"] == {"Trifolium repens": [["Apis mellifera", 3]]}
    assert foodweb.pairs([], "pollination")["n"] == 0
    assert foodweb.pairs(rows)["n"] == 0  # predation reads neither type nor animal-on-plant rows


def test_the_scavenging_rule_is_off_for_pollination():
    web = {"eats": {"Slug": [["Robin", 1]]}}
    group = {"Slug": "Mollusca", "Robin": "Aves"}
    assert metaweb.build(web, group)["pairs"] == []
    m = metaweb.build(web, group, scavenging=False)
    assert m["pairs"] == [["Slug", "Robin", 0.5]] and m["rule"] == metaweb.RULE_PLAIN


def test_groups_skips_a_group_of_several_taxa():
    taxa = [["Plantae", "", 5, "kingdom", -1, 0], ["Moss", "", 6, "species", 0, 0]]
    assert metaweb.groups(taxa, {"Algae": [1, 2], "Plantae": 5}) == {
        "Plantae": "Plantae",
        "Moss": "Plantae",
    }


def test_slim_reads_the_visited_flower_of_field():
    o = {
        "id": 1,
        "taxon": {"name": "Apis mellifera", "id": 7},
        "photos": [{"url": "https://x/photos/1/square.jpg"}],
        "ofvs": [{"field_id": 3126, "taxon": {"name": "Trifolium repens", "id": 9}}],
    }
    r = foodweb_obs.slim(o, "visit")
    assert r["k"] == "visit" and r["f"] == ["Trifolium repens", 9]
    other = {**o, "ofvs": [{"field_id": 13, "taxon": {"name": "Clupea", "id": 9}}]}
    assert "f" not in foodweb_obs.slim(other, "visit")  # the Eating field is not this field


def test_the_page_builds_only_with_its_data_and_links_the_two_pages(tmp_path):
    (tmp_path / page_eating.OBS_FILE).write_text(json.dumps(OBS))
    (tmp_path / page_eating.METAWEB_FILE).write_text(json.dumps(META))
    page_eating.build(tmp_path)
    assert not (tmp_path / page_eating.POLLINATION_NAME).exists()
    assert '"page": ' not in (tmp_path / page_eating.PAGE_NAME).read_text()
    for f in (page_eating.POLLINATION_OBS, page_eating.POLLINATION_METAWEB):
        (tmp_path / f).write_text("{}")
    page_eating.build(tmp_path)
    html = (tmp_path / page_eating.POLLINATION_NAME).read_text()
    assert "Pollination in BC" in html and "pollination-metaweb.json" in html
    assert '"page": "pollination.html"' in html and "—" not in html
    assert '"page": "food-web.html"' in (tmp_path / page_eating.PAGE_NAME).read_text()
