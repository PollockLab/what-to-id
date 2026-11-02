import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import public_overturn as po


def _ident(
    user, own, taxon, rank="species", anc=(), vision=None, current=True, created="2025-01-02"
):
    return {
        "user": {"id": user},
        "own_observation": own,
        "vision": vision,
        "current": current,
        "taxon_id": taxon,
        "taxon": {"rank": rank, "ancestor_ids": list(anc)},
        "created_at": created,
    }


def _obs(id, ct, idents, grade="needs_id", iconic="Aves", user_idents=0, taxon=None):
    return {
        "id": id,
        "quality_grade": grade,
        "created_at": "2025-05-01T00:00:00-07:00",
        "community_taxon_id": ct,
        "user": {"id": 1, "identifications_count": user_idents},
        "taxon": {"id": taxon or ct, "iconic_taxon_name": iconic},
        "identifications": idents,
    }


RAW = [
    # CV first ID upheld by a second identifier
    _obs(1, 10, [_ident(1, True, 10, vision=True), _ident(2, False, 10)]),
    # typed first ID overturned
    _obs(2, 11, [_ident(1, True, 10, vision=False), _ident(2, False, 11)], user_idents=5),
    # CV first ID at species, community taxon is a descendant of it: upheld
    _obs(3, 12, [_ident(1, True, 10, vision=True), _ident(2, False, 12, anc=[10])]),
    # no community taxon: tested, not overturned
    _obs(4, None, [_ident(1, True, 10, vision=True), _ident(2, False, 13, rank="order")]),
    # genus-rank first ID: not tested
    _obs(5, 10, [_ident(1, True, 9, rank="genus", vision=True), _ident(2, False, 10)]),
    # own second thought before anyone else: first own ID is the earlier one
    _obs(
        6,
        10,
        [
            _ident(1, True, 10, vision=False, created="2025-01-03"),
            _ident(1, True, 11, vision=True, created="2025-01-01"),
            _ident(2, False, 10),
        ],
        user_idents=2000,
    ),
    # casual and no-other records drop out
    _obs(7, 10, [_ident(1, True, 10, vision=True), _ident(2, False, 10)], grade="casual"),
    _obs(8, None, [_ident(1, True, 10, vision=True)]),
]
ROWS = [po.summarise(o) for o in RAW]


def test_scored_unit_and_overturn():
    df = po.scored(ROWS).set_index("id")
    assert df.index.tolist() == [1, 2, 3, 4, 5, 6, 8]
    assert df["tested"].tolist() == [True, True, True, True, False, True, False]
    assert df["overturned"].tolist() == [False, True, False, False, False, True, False]
    assert df.loc[6, "source"] == "cv" and df.loc[6, "first_taxon"] == 11
    assert df.loc[[2, 6], "experience"].tolist() == ["<10 ids", "1000+ ids"]


def test_table_and_duplicates_dropped():
    out = po.table(po.scored(ROWS + ROWS[:1]), "group").set_index("source")
    assert out.loc["cv", ["n", "tested", "overturned"]].tolist() == [6, 4, 1]
    assert out.loc["typed", ["n", "tested", "overturned"]].tolist() == [1, 1, 1]
    assert out.loc["cv", "overturn"] == 0.25
    assert po.table(po.scored([]), "group").empty


def test_within_species_ratio():
    df = pd.DataFrame(
        {
            "tested": True,
            "first_taxon": [1, 1, 1, 1, 2, 2],
            "source": ["cv", "cv", "typed", "typed", "cv", "typed"],
            "overturned": [True, False, True, True, False, False],
        }
    )
    rr, k = po.within_species(df)
    assert k == 2 and rr == 2.0  # species 1: typed 2 of 2 against cv 1 of 2; species 2 adds nothing


def test_matched_table_per_stratum():
    df = pd.DataFrame(
        {
            "tested": True,
            "experience": ["a"] * 6 + ["b"] * 4,
            "first_taxon": [1, 1, 1, 1, 2, 2, 3, 3, 3, 3],
            "source": ["cv", "cv", "typed", "typed", "cv", "typed", "cv", "typed", "cv", "cv"],
            "overturned": [True, False, True, True, False, False, False, True, False, False],
        }
    )
    out = po.matched_table(df, "experience").set_index("stratum")
    assert out.loc["a", ["tested", "species"]].tolist() == [6, 2]
    assert (
        out.loc["a", "crude"] == pytest.approx((2 / 3) / (1 / 3)) and out.loc["a", "matched"] == 2.0
    )
    assert np.isnan(out.loc["b", "crude"]) and np.isnan(out.loc["b", "matched"])  # no cv overturn
    assert po.matched_table(df.iloc[:0], "experience").empty


def test_level_table():
    levels = pd.DataFrame({"id": [1, 2, 4, 5], "taxon_id": [10, 11, 10, 10], "level": [1, 5, 1, 2]})
    out = po.level_table(ROWS, levels).set_index("level")
    assert out.loc["easy", ["n", "has_other"]].tolist() == [2, 1.0]
    assert out.loc["easy", "contradicted"] == 0.5  # record 4's order-rank ID is not the label
    assert out.loc["mislabel", "contradicted"] == 0.0 and out.loc["taxonomist", "n"] == 1


def test_main_tables(tmp_path, capsys):
    p = tmp_path / "r.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    assert po.main(["tables", str(p)]) == 0
    out = capsys.readouterr().out
    assert "Mantel-Haenszel" in out and "<10 ids" in out
