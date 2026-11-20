"""foodweb_vlm: the filter on a model run's prey suggestions."""

import json

from what_to_id import foodweb_vlm


def row(**kw):
    r = {"obs_id": "7", "p_feeding": "0.9512", "prey_bbox_0_1000": "[1.0, 2.0, 30.0, 40.0]",
         "prey_name_qwen": "Western Toad", "taxon_name": "Thamnophis elegans vagrans",
         "predator_canmw": "Thamnophis elegans", "prey_bioclip_1": "Thamnophis sirtalis",
         "prey_bioclip_1_p": "0.8", "prey_bioclip_2": "Anaxyrus boreas", "prey_bioclip_2_p": "0.5",
         "prey_bioclip_3": "Pseudacris regilla", "prey_bioclip_3_p": "0.29"}  # fmt: skip
    return {**r, **kw}


def test_same_genus_below_the_floor_and_none_names_are_dropped():
    r = foodweb_vlm.slim(row())
    assert r == {
        "p": 0.951,
        "box": [1, 2, 30, 40],
        "name": "Western Toad",
        "prey": [["Anaxyrus boreas", 0.5]],
    }
    assert "name" not in foodweb_vlm.slim(row(prey_name_qwen="none"))
    assert "name" not in foodweb_vlm.slim(row(prey_name_qwen="Toad (none)"))


def test_empty_box_and_empty_suggestions_are_absent_or_empty():
    r = foodweb_vlm.slim(row(prey_bbox_0_1000="", prey_bioclip_1="", prey_bioclip_1_p=""))
    assert "box" not in r and r["prey"] == [["Anaxyrus boreas", 0.5]]


def test_the_file_keeps_only_the_hint_fields(tmp_path):
    out, src = tmp_path / "v.json", tmp_path / "s.csv"
    src.write_text("obs_id,p_feeding,taxon_name,observer\n9,0.2,Larus glaucescens,someone\n")
    assert foodweb_vlm.main(["--csv", str(src), "--out", str(out)]) == 0
    d = json.loads(out.read_text())
    assert d["obs"] == {"9": {"p": 0.2, "prey": []}} and "Qwen3-VL-8B" in d["model"]
    src.write_text("obs_id,p_feeding\n")
    assert foodweb_vlm.main(["--csv", str(src), "--out", str(out)]) == 1
