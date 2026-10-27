"""Level assignment on a small synthetic bundle: every level filled, its rule held, caps kept."""

import numpy as np
import pandas as pd
import pytest

from what_to_id import identify, levels
from what_to_id.atlas_index_io import VERSION, read_manifest, write_manifest
from what_to_id.confusion import fir_scores

TEXT = {"G a": [1, 0, 0, 0], "G b": [0, 1, 0, 0], "F c": [0, 0, 1, 0]}


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def bundle():
    """Per species: 8 clean photos, 1 just past a look-alike, 1 clearly wrong, 1 of nothing."""
    rng = np.random.default_rng(1)
    rows, names, groups = [], [], []
    for name, own, other, group in [
        ("G a", 0, 1, "Plantae"),
        ("G b", 1, 0, "Plantae"),
        ("F c", 2, 0, "Fungi"),
    ]:
        clean = np.zeros((8, 4))
        clean[:, own] = 1
        clean[:, 3] = rng.uniform(0, 0.5, 8)
        near, wrong, odd = np.zeros((3, 4))
        near[[own, other, 3]] = 1, 1.02, 0.2
        wrong[[own, other]] = 0.2, 1
        odd[3] = 1
        rows += [*clean, near, wrong, odd]
        names += [name] * 11
        groups += [group] * 11
    E = _unit(rows)
    ids = np.arange(100, 100 + len(E))
    pool = pd.DataFrame(
        {
            "id": ids,
            "taxon_id": [10 + list(TEXT).index(n) for n in names],
            "taxon_name": names,
            "rank": "species",
            "iconic_taxon": groups,
            "photo_url": [f"https://x/{i}.jpg" for i in ids],
        }
    )
    return pool, E, ids, pd.Series(list(TEXT)), _unit(list(TEXT.values()))


def scores():
    return fir_scores(*bundle())


def test_each_level_is_filled_and_its_rule_holds(monkeypatch):
    monkeypatch.setattr(levels, "MIN_LOOKALIKE_RECORDS", 1)  # the bundle has 11 records a species
    s = scores()
    out = levels.assign(s)
    assert list(out.columns) == list(levels.LEVEL_COLUMNS)
    assert set(out["level"]) == {"easy", "taxonomist", "weird"}
    assert out["id"].is_unique
    m = out.merge(s[["id", "own", "other", "margin"]], on="id")
    easy, tax, odd = (m[m["level"] == k] for k in ("easy", "taxonomist", "weird"))
    assert (easy["margin"] > 0).all() and (easy["score"] == easy["own"].astype(np.float32)).all()
    # the top quarter by own of 11 photos is 2 photos per species
    assert easy.groupby("taxon_id").size().eq(2).all()
    assert tax["margin"].between(-levels.TAXONOMIST_MARGIN, 0, inclusive="left").all()
    # the photos just past their look-alike, one per species
    assert (tax["id"] - 100).mod(11).eq(8).all() and len(tax) == 3
    assert set(tax["looks_like_name"]) == {"G a", "G b"}
    # the photo of nothing is the weird one, far from every species
    assert (odd["id"] - 100).mod(11).eq(10).all() and len(odd) == 3
    assert (odd["score"] < easy["score"].min()).all()
    # the clearly wrong photos sit in no level
    assert not ((m["id"] - 100) % 11 == 9).any()


def test_caps_hold_per_species_and_per_group():
    out = levels.assign(scores(), cap=1, per_species=1)
    assert out.groupby(["level", "iconic_taxon"]).size().le(1).all()
    assert out.groupby(["level", "taxon_id"]).size().le(1).all()
    full = levels.assign(scores(), per_species=1)
    assert full.groupby(["level", "taxon_id"]).size().le(1).all()
    assert set(full["iconic_taxon"]) == {"Plantae", "Fungi"}


def test_easy_interleaves_species_and_weird_takes_turns_by_group():
    out = levels.assign(scores())
    easy = out[out["level"] == "easy"]
    assert easy["taxon_id"].head(3).nunique() == 3
    odd = out[out["level"] == "weird"]
    assert odd["iconic_taxon"].head(2).nunique() == 2


def test_same_seed_same_order():
    s = scores()
    assert levels.assign(s, seed=3).equals(levels.assign(s, seed=3))


def test_empty_input_gives_an_empty_table():
    pool, E, ids, taxa, T = bundle()
    out = levels.assign(fir_scores(pool.iloc[:0], E, ids, taxa, T))
    assert out.empty and list(out.columns) == list(levels.LEVEL_COLUMNS)


def test_missing_column_is_named():
    with pytest.raises(ValueError, match="photo_url"):
        levels.assign(scores().drop(columns="photo_url"))


def test_cli_writes_the_table_and_manifest_key(tmp_path, capsys):
    import gzip

    pool, E, ids, taxa, T = bundle()
    np.save(tmp_path / "E.npy", E)
    np.save(tmp_path / "ids.npy", ids.astype(np.int64))
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    with gzip.open(tmp_path / "taxa.tsv.gz", "wt") as f:
        f.write("".join(f"{n}\t\n" for n in TEXT))
    T.astype(np.float16).tofile(tmp_path / "taxa.f16")
    write_manifest(tmp_path, {"version": VERSION, "parts": []})
    args = ["--emb", str(tmp_path / "E.npy"), "--ids", str(tmp_path / "ids.npy")]
    args += ["--pool", str(tmp_path / "pool.parquet"), "--atlas-dir", str(tmp_path)]
    args += ["--taxa-names", str(tmp_path / "taxa.tsv.gz")]
    args += ["--taxa-vectors", str(tmp_path / "taxa.f16")]
    assert levels.main(args) == 0
    table = pd.read_parquet(tmp_path / "levels.parquet")
    entry = read_manifest(tmp_path)["levels"]
    assert entry["name"] == "levels.parquet" and entry["count"] == len(table) > 0
    printed = capsys.readouterr().out
    assert "margin quantiles" in printed and "rows per group and level" in printed


def test_rare_lookalikes_are_dropped_from_look_alikes(monkeypatch):
    s = scores()  # every species has 11 records

    def look_alikes():
        out = levels.assign(s)
        return set(out[out["level"] == "taxonomist"]["looks_like_name"])

    monkeypatch.setattr(levels, "MIN_LOOKALIKE_RECORDS", 11)  # at the boundary: kept
    assert look_alikes() == {"G a", "G b"}
    monkeypatch.setattr(levels, "MIN_LOOKALIKE_RECORDS", 12)  # one short: dropped
    assert look_alikes() == set()
    assert {"easy", "weird"} <= set(levels.assign(s)["level"])


def test_bc_counts_replace_the_pool_count_of_a_lookalike(monkeypatch):
    s = scores()  # 11 pool records a species
    monkeypatch.setattr(levels, "MIN_LOOKALIKE_RECORDS", 20)

    def look_alikes(bc):
        out = levels.assign(s, bc_counts=bc)
        return set(out[out["level"] == "taxonomist"]["looks_like_name"])

    assert look_alikes(None) == set()  # rare in the pool
    # "G a" is common over BC, "G b" is rare there, "F c" is absent
    assert look_alikes(pd.Series({"G a": 500, "G b": 3})) == {"G a"}
    # one name over two taxa sums: 10 + 15 clears the bar
    assert look_alikes(pd.Series([10, 15, 3], index=["G a", "G a", "G b"])) == {"G a"}


def test_range_notes_join_by_id_on_look_alike_cards_only():
    out = levels.assign(scores())
    tax = out[out["level"] == "taxonomist"]
    notes = pd.DataFrame({"id": out["id"], "range_note": "Range: outside both ranges"})
    joined = levels.add_range_notes(out, notes.iloc[: len(out) - 1])
    assert (joined.loc[joined["level"] != "taxonomist", "range_note"].isna()).all()
    assert (joined["id"] == out["id"]).all()
    point = levels.add_range_notes(out, notes.assign(lat=1.5, lon=2.5, out_km=7))
    assert (
        point[["lat", "lon", "out_km"]].notna().all()
    ).all()  # every level, not only Close calls
    full = levels.add_range_notes(out, notes)
    assert (full.loc[tax.index, "range_note"] == "Range: outside both ranges").all()
    with pytest.raises(ValueError, match="range_note"):
        levels.add_range_notes(out, notes[["id"]])


# tree for the identify path: Fam > genus G > species "G a", "G b"; genus Empty has no prototype;
# "F c" is an outsider under another root; taxon 8 is not in the tree
TREE = {
    1: [0, "Root", "", "kingdom"],
    2: [1, "Fam", "", "family"],
    3: [2, "G", "", "genus"],
    4: [3, "G a", "", "species"],
    5: [3, "G b", "", "species"],
    6: [1, "F", "", "genus"],
    7: [6, "F c", "", "species"],
    9: [2, "Empty", "", "genus"],
}


def identify_bundle():
    pool, E, ids, taxa, T = bundle()
    pool = pool.assign(taxon_id=pool["taxon_id"].map({10: 4, 11: 5, 12: 7}))
    # near "G a" with some "G b", labelled genus / family / genus without prototypes / not in tree
    near = _unit([[1, 0.5, 0, 0.1]] * 4)
    extra = pd.DataFrame(
        {
            "id": [900, 901, 902, 903, 904],
            "taxon_id": [3, 2, 9, 8, 3],
            "taxon_name": ["G", "Fam", "Empty", "Nope", "G"],
            "rank": ["genus", "family", "genus", "genus", "genus"],
            "iconic_taxon": "Aves",
        }
    )
    E = np.vstack([E, near, _unit([[0, 0, 0, 1]])])
    return pd.concat([pool, extra], ignore_index=True), E, np.append(ids, extra["id"]), taxa, T


def identify_out(**kw):
    pool, E, ids, taxa, T = identify_bundle()
    s = identify.identify_scores(pool, E, ids, taxa, T, TREE)
    return s, identify.identify_levels(s, **kw)


def test_clades_are_contiguous_depth_first_ranges():
    order, clades = identify.clade_columns(TREE, ["F c", "G b", "G a", "X y"])
    assert order == ["G a", "G b", "F c", "X y"]
    assert clades[3] == clades[2] == (0, 2) and clades[4] == (0, 1) and clades[1] == (0, 3)
    assert 9 not in clades and 8 not in clades


def test_identify_species_rows_match_the_uncapped_levels(monkeypatch):
    monkeypatch.setattr(levels, "MIN_LOOKALIKE_RECORDS", 1)
    pool, E, ids, taxa, T = bundle()
    ref = levels.assign(fir_scores(pool, E, ids, taxa, T), cap=10**9, per_species=10**9)
    pool, E, ids, taxa, T = identify_bundle()
    s, out = identify_out()
    assert len(out) == len(pool) and out["id"].is_unique
    assert out["level"].dtype == np.int8 and out["score"].dtype == np.float32
    for code, key in ((1, "easy"), (2, "taxonomist"), (4, "weird")):
        got = set(out.loc[(out["level"] == code) & (out["id"] < 900), "id"])
        assert got == set(ref.loc[ref["level"] == key, "id"]) and got
    tax = out[out["level"] == 2]
    assert set(tax["looks_like"]) == {"G a", "G b"}
    assert out.loc[out["level"] == 1, "looks_like"].isna().all()


def test_higher_ranks_get_narrow_with_the_probable_species():
    s, out = identify_out()
    row = out.set_index("id")
    cos = _unit([[1, 0.5, 0, 0.1]])[0]
    for i in (900, 901):  # genus and family both hold the two G species
        assert row.loc[i, "level"] == 3 and row.loc[i, "looks_like"] == "G a"
        assert row.loc[i, "score"] == pytest.approx(cos[0] - cos[2], abs=1e-6)
        assert row.loc[i, "score2"] == pytest.approx(cos[0] - cos[1], abs=1e-6)
    assert out.loc[out["level"] != 3, "score2"].isna().all()
    assert row.loc[902, "level"] == 0 and row.loc[903, "level"] == 0  # no prototype, not in tree
    assert row.loc[904, "level"] == 4  # the photo of nothing, labelled genus: weird at its rank
    assert row.loc[[902, 903], "looks_like"].isna().all()


def test_the_root_has_no_outside_so_no_narrow_score():
    pool, E, ids, taxa, T = identify_bundle()
    pool.loc[pool["id"] == 901, ["taxon_id", "rank"]] = [1, "kingdom"]  # holds every tree species
    # a prototype the tree does not know is in no clade, and not outside the root either
    taxa, T = (
        pd.concat([taxa, pd.Series(["X y"])], ignore_index=True),
        np.vstack([T, _unit([[0, 0, -1, 0]])]),
    )
    s = identify.identify_scores(pool, E, ids, taxa, T, TREE)
    row = identify.identify_levels(s).set_index("id").loc[901]
    assert row["level"] == 3 and row["looks_like"] == "G a" and np.isnan(row["score"])


def test_weird_wins_at_any_rank():
    pool, E, ids, taxa, T = identify_bundle()
    E[-5:] = _unit([[0, 0, 0, 1]] * 5)  # nothing like a prototype, in group Aves
    s = identify.identify_scores(pool, E, ids, taxa, T, TREE)
    out = identify.identify_levels(s)
    assert (out.loc[out["id"] >= 900, "level"] == 4).all()
    assert np.allclose(out["score"].iloc[-5:], s["top"].iloc[-5:])


def test_empty_pool_gives_an_empty_table():
    pool, E, ids, taxa, T = identify_bundle()
    s = identify.identify_scores(pool.iloc[:0], E, ids, taxa, T, TREE)
    out = identify.identify_levels(s)
    assert out.empty and list(out.columns) == list(identify.IDENTIFY_COLUMNS)


def test_cli_identify_registers_the_new_key_and_leaves_levels(tmp_path, capsys):
    import gzip
    import json

    pool, E, ids, taxa, T = identify_bundle()
    np.save(tmp_path / "E.npy", E)
    np.save(tmp_path / "ids.npy", ids.astype(np.int64))
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    with gzip.open(tmp_path / "taxa.tsv.gz", "wt") as f:
        f.write("".join(f"{n}\t\n" for n in TEXT))
    T.astype(np.float16).tofile(tmp_path / "taxa.f16")
    (tmp_path / "taxonomy.json").write_text(
        json.dumps({"taxa": {str(k): v for k, v in TREE.items()}})
    )
    write_manifest(
        tmp_path, {"version": VERSION, "parts": [], "levels": {"name": "levels.parquet"}}
    )
    args = ["--emb", str(tmp_path / "E.npy"), "--ids", str(tmp_path / "ids.npy")]
    args += ["--pool", str(tmp_path / "pool.parquet"), "--atlas-dir", str(tmp_path)]
    args += ["--taxa-names", str(tmp_path / "taxa.tsv.gz")]
    args += ["--taxa-vectors", str(tmp_path / "taxa.f16")]
    args += ["--tree", str(tmp_path / "taxonomy.json"), "--identify"]
    assert levels.main(args) == 0
    table = pd.read_parquet(tmp_path / "identify.parquet")
    manifest = read_manifest(tmp_path)
    assert manifest["identify"]["name"] == "identify.parquet"
    assert manifest["identify"]["count"] == len(table) == len(pool)
    assert manifest["levels"] == {"name": "levels.parquet"}
    assert not (tmp_path / "levels.parquet").exists()
    assert "records per group and level" in capsys.readouterr().out
    with pytest.raises(ValueError, match="--tree"):
        (tmp_path / "taxonomy.json").write_text('{"taxa":{}}')
        levels.main(args)
