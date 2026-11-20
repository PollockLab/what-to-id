from what_to_id.foodweb import pairs


def row(t, a, b, pa=None, pb=None):
    return {
        "interaction_type": t,
        "source_taxon_name": a,
        "target_taxon_name": b,
        "source_taxon_path": pa or f"Animalia | {a}",
        "target_taxon_path": pb or (b and f"Animalia | {b}"),
    }


def test_pairs_count_own_names_and_skip_other_types():
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
    assert t["eats"]["Ardea alba"] == [["Rana aurora", 1]]
    assert "Ardea" not in t["eats"]
    assert "Oncorhynchus" not in t["eatenBy"]
    assert t["eats"]["Bubo virginianus"] == [["Microtus", 1]]
    assert "Larus glaucescens" not in t["eats"]
    assert "Ariolimax" not in t["eats"]


def test_pairs_keep_every_partner_and_empty():
    rows = [row("eats", "Ardea herodias", f"Prey{k} sp") for k in range(9)]
    assert len(pairs(rows)["eats"]["Ardea herodias"]) == 9
    assert pairs([]) == {"eats": {}, "eatenBy": {}, "n": 0}


def test_pairs_congeners_make_no_genus_predator():
    rows = [
        row("eats", "Larus glaucescens", "Mytilus edulis"),
        row("eats", "Larus occidentalis", "Engraulis mordax"),
        row("eats", "Larus", "Clupea"),  # recorded at genus: stays
    ]
    t = pairs(rows)
    assert t["eats"]["Larus"] == [["Clupea", 1]]
    assert t["eats"]["Larus glaucescens"] == [["Mytilus edulis", 1]]
    rows.pop()
    assert "Larus" not in pairs(rows)["eats"]
