from what_to_id.foodweb import pairs


def row(t, a, b, pa=None, pb=None):
    return {
        "interaction_type": t,
        "source_taxon_name": a,
        "target_taxon_name": b,
        "source_taxon_path": pa or f"Animalia | {a}",
        "target_taxon_path": pb or (b and f"Animalia | {b}"),
    }


def test_pairs_count_roll_up_to_genus_and_skip_other_types():
    owl = "Animalia | Aves | Bubo virginianus"
    rows = [
        row("eats", "Ardea herodias", "Oncorhynchus kisutch"),
        row("eats", "Ardea herodias", "Oncorhynchus kisutch"),
        row("preysOn", "Ardea alba", "Rana aurora"),
        row("parasiteOf", "Ardea herodias", "Rana aurora"),  # not a predation type
        row("eats", "Ardea herodias", None),  # no partner
        row("eats", "Larus glaucescens", "Larus glaucescens"),  # self
        row("eats", "Bubo (great horned owl)", "Microtus", pa=owl),  # the path names the taxon
        row("eats", "Ariolimax columbianus", "Gomphidius", pb="Fungi | Gomphidius"),  # grazing
    ]
    t = pairs(rows)
    assert t["n"] == 4
    assert t["eats"]["Ardea herodias"] == [["Oncorhynchus kisutch", 2]]
    assert t["eats"]["Ardea"] == [["Oncorhynchus kisutch", 2], ["Rana aurora", 1]]
    assert t["eatenBy"]["Oncorhynchus"] == [["Ardea herodias", 2]]
    assert t["eats"]["Bubo virginianus"] == [["Microtus", 1]]
    assert "Larus glaucescens" not in t["eats"]
    assert "Ariolimax" not in t["eats"]


def test_pairs_cap_and_empty():
    rows = [row("eats", "Ardea herodias", f"Prey{k} sp") for k in range(9)]
    assert len(pairs(rows, top=3)["eats"]["Ardea herodias"]) == 3
    assert pairs([]) == {"eats": {}, "eatenBy": {}, "n": 0}
