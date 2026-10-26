import numpy as np
import pandas as pd
import pytest

from what_to_id.atlas_index_io import VERSION, read_manifest, write_manifest
from what_to_id.confusion import (
    RECORD_COLUMNS,
    TABLE_COLUMNS,
    confused_pairs,
    confusion_scores,
    fir_records,
    fir_scores,
    fir_table,
    main,
    prototype_scores,
    read_taxa_vectors,
    text_scores,
)


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_mislabelled_row_sits_closer_to_the_other_prototype():
    rng = np.random.default_rng(0)
    a = _unit(rng.normal(size=(5, 8)) + np.r_[10, 0, 0, 0, 0, 0, 0, 0])
    b = _unit(rng.normal(size=(5, 8)) + np.r_[0, 10, 0, 0, 0, 0, 0, 0])
    E = np.vstack([a, b])
    labels = np.array([1] * 5 + [2] * 4 + [1])  # the last b-row is labelled as a
    n_class, own, other, other_label = prototype_scores(E, labels)
    assert n_class.tolist() == [6] * 5 + [4] * 4 + [6]
    assert (own[:5] > other[:5]).all()
    assert own[9] < other[9] and other_label[9] == 2
    assert other_label[0] == 2


def test_small_classes_and_singletons_score_nan():
    E = _unit(np.eye(4))
    n_class, own, other, other_label = prototype_scores(E, np.array([1, 1, 1, 2]), min_per_class=3)
    assert np.isnan(own[3]) and n_class[3] == 1
    # The only prototype has no other to compare with.
    assert np.isnan(other[:3]).all() and (other_label[:3] == -1).all()
    assert np.isfinite(own[:3]).all()


def test_confusion_scores_joins_species_rows_to_embeddings():
    E = _unit(np.eye(7))
    ids = np.array([10, 11, 12, 13, 14, 15, 16])
    pool = pd.DataFrame(
        {
            "id": [10, 11, 12, 13, 14, 15, 16],
            "taxon_id": [1, 1, 1, 1, 2, 2, 2],
            "taxon_name": ["G a"] * 4 + ["G", "G b", "G b"],
            "rank": ["species"] * 4 + ["genus", "species", "species"],
        }
    )
    out = confusion_scores(pool, E, ids, min_per_class=2)
    assert out["id"].tolist() == [10, 11, 12, 13, 15, 16]
    assert out.loc[out.taxon_id == 1, "other_taxon_id"].eq(2).all()
    assert out.loc[out.taxon_id == 2, "other_taxon_id"].eq(1).all()
    assert out["margin"].notna().all()


def test_confused_pairs_counts_negative_margins_per_pair():
    scores = pd.DataFrame(
        {
            "taxon_id": [1, 1, 2, 1],
            "other_taxon_id": [2, 2, 1, 3],
            "margin": [-0.1, -0.2, -0.3, 0.1],
        }
    )
    out = confused_pairs(scores, pd.Series({1: "a", 2: "b", 3: "c"}))
    assert out[["taxon", "looks_like", "n"]].values.tolist() == [["a", "b", 2], ["b", "a", 1]]


def test_confused_pairs_text_uses_the_other_name_directly():
    scores = pd.DataFrame(
        {
            "taxon_id": [1, 1, 2],
            "text_other_name": ["Genus beta", "Genus beta", "Genus alpha"],
            "text_margin": [-0.1, -0.2, 0.3],
        }
    )
    out = confused_pairs(scores, pd.Series({1: "Genus alpha", 2: "Genus beta"}), text=True)
    assert out[["taxon", "looks_like", "n"]].values.tolist() == [["Genus alpha", "Genus beta", 2]]


def test_text_scores_use_only_species_names_and_skip_the_own_prototype():
    T = _unit(np.eye(3))
    taxa = pd.Series(["Genus", "Genus alpha", "Genus beta"])
    E = _unit([[1, 0.2, 0], [0, 0, 1], [0, 1, 0]])
    names = pd.Series(["Genus alpha", "Genus beta", "Genus"])
    own, other, other_name = text_scores(E, names, taxa, T)
    assert own[0] > other[0] and other_name[0] == "Genus beta"
    assert np.isnan(own[2]) and other_name[2] == "Genus alpha"
    # "Genus" is not a species, so it never acts as a prototype even though row 1 points at it.
    assert other_name[1] == "Genus alpha" and own[1] == 1.0 and other[1] == 0.0


def test_confusion_scores_adds_text_columns_and_cli_reads_atlas_files(tmp_path):
    import gzip

    E = _unit(np.eye(4))
    ids = np.array([10, 11, 12, 13])
    pool = pd.DataFrame(
        {
            "id": ids,
            "taxon_id": [1, 1, 2, 2],
            "taxon_name": ["G a", "G a", "G b", "G b"],
            "rank": "species",
        }
    )
    with gzip.open(tmp_path / "taxa.tsv.gz", "wt") as f:
        f.write("G a\tcommon\nG b\t\n")
    T = _unit([[1, 1, 0, 0], [0, 0, 1, 1]]).astype(np.float16)
    T.tofile(tmp_path / "taxa.f16")
    taxa, Tv = read_taxa_vectors(tmp_path / "taxa.tsv.gz", tmp_path / "taxa.f16")
    out = confusion_scores(pool, E, ids, min_per_class=2, taxa=taxa, T=Tv)
    assert out["text_other_name"].tolist() == ["G b", "G b", "G a", "G a"]
    assert (out["text_margin"] > 0).all()
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    np.savez(tmp_path / "emb.npz", ids=ids, E=E)
    args = [str(tmp_path / "pool.parquet"), "--emb", str(tmp_path / "emb.npz")]
    args += ["--out", str(tmp_path / "out.parquet"), "--min-per-class", "2"]
    args += [
        "--taxa-names",
        str(tmp_path / "taxa.tsv.gz"),
        "--taxa-vectors",
        str(tmp_path / "taxa.f16"),
    ]
    assert main(args) == 0
    assert "text_margin" in pd.read_parquet(tmp_path / "out.parquet").columns


BUILT = "2026-10-15T00:00:00Z"


def _table(pool, E, ids, taxa, T):
    return fir_table(fir_scores(pool, E, ids, taxa, T), BUILT)


def _records(pool, E, ids, taxa, T, **kw):
    scores = fir_scores(pool, E, ids, taxa, T)
    return fir_records(scores, fir_table(scores, BUILT), **kw)


def _fir_inputs(species, per_species, vecs, text, ids_extra=0):
    """E rows of `vecs[i]` for `per_species[i]` photos of `species[i]`; text prototypes `text`."""
    rows, names = [], []
    for name, n, v in zip(species, per_species, vecs, strict=True):
        rows += [v] * n
        names += [name] * n
    E = _unit(rows)
    ids = np.arange(100, 100 + len(E))
    pool = pd.DataFrame(
        {
            "id": ids,
            "taxon_id": [10 + species.index(n) for n in names],
            "taxon_name": names,
            "rank": "species",
            "iconic_taxon": "Plantae",
            "photo_url": [f"https://x/{i}.jpg" for i in ids],
        }
    )
    taxa = pd.Series(list(text))
    return pool, E, ids, taxa, _unit(list(text.values()))


def test_fir_table_counts_photos_closer_to_another_text_prototype():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [5, 5], [[0, 1, 0], [0, 1, 0]], text)
    out = _table(pool, E, ids, taxa, T)
    a = out[out.taxon_name == "G a"].iloc[0]
    assert (a.looks_like_name, a.looks_like_taxon_id) == ("G b", 11)
    assert (a.n_photos, a.n_species_photos, a.share) == (5, 5, 1.0)
    assert out["built_at"].eq(BUILT).all()
    assert out["looks_like_taxon_id"].dtype == "Int64"
    assert "G a" not in out[out.taxon_name == "G b"]["looks_like_name"].tolist()


def test_fir_table_empty_pool_and_single_species_give_no_rows():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [5], [[0, 1, 0]], text)
    empty = _table(pool.iloc[:0], E, ids, taxa, T)
    assert empty.empty and list(empty.columns) == list(TABLE_COLUMNS)
    one = {"G a": [1, 0, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [5], [[0, 1, 0]], one)
    assert _table(pool, E, ids, taxa, T).empty


def test_fir_table_tie_picks_the_first_prototype_in_taxa_order():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0], "G c": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [5], [[0, 1, 0]], text)
    out = _table(pool, E, ids, taxa, T)
    assert out["looks_like_name"].tolist() == ["G b"]


def test_fir_table_four_photo_floor():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    kw = dict(vecs=[[0, 1, 0], [0, 1, 0]], text=text)
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [3, 5], **kw)
    out = _table(pool, E, ids, taxa, T)
    assert "G a" not in out["taxon_name"].tolist()
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [4, 5], **kw)
    assert "G a" in _table(pool, E, ids, taxa, T)["taxon_name"].tolist()


def test_fir_table_keeps_three_pairs_per_species_with_two_photos_or_more():
    text = {"G a": [1, 0, 0, 0, 0], "G b": [0, 1, 0, 0, 0], "G c": [0, 0, 1, 0, 0]}
    text |= {"G d": [0, 0, 0, 1, 0], "G e": [0, 0, 0, 0, 1]}
    rows = [[0, 1, 0, 0, 0]] * 4 + [[0, 0, 1, 0, 0]] * 3 + [[0, 0, 0, 1, 0]] * 2
    rows += [[0, 0, 0, 0, 1]] * 2 + [[1, 0, 0, 0, 0.1]] + [[1, 0, 0, 0, 0]] * 2
    E = _unit(rows)
    ids = np.arange(len(E))
    pool = pd.DataFrame({"id": ids, "taxon_id": 1, "taxon_name": "G a", "rank": "species"})
    taxa, T = pd.Series(list(text)), _unit(list(text.values()))
    out = _table(pool, E, ids, taxa, T)
    # b:4, c:3, d:2 and e:2 tie on count; d wins by name.
    assert out[["looks_like_name", "n_photos"]].values.tolist() == [
        ["G b", 4],
        ["G c", 3],
        ["G d", 2],
    ]
    assert out["n_species_photos"].eq(14).all()


def test_fir_cli_writes_table_and_manifest_key(tmp_path):
    import gzip

    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [5, 5], [[0, 1, 0], [0, 1, 0]], text)
    np.save(tmp_path / "E.npy", E)
    np.save(tmp_path / "ids.npy", ids.astype(np.int64))
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    with gzip.open(tmp_path / "taxa.tsv.gz", "wt") as f:
        f.write("G a\t\nG b\t\n")
    T.astype(np.float16).tofile(tmp_path / "taxa.f16")
    atlas = tmp_path / "atlas"
    atlas.mkdir()
    args = ["fir", "--emb", str(tmp_path / "E.npy"), "--ids", str(tmp_path / "ids.npy")]
    args += ["--pool", str(tmp_path / "pool.parquet"), "--atlas-dir", str(atlas)]
    args += ["--taxa-names", str(tmp_path / "taxa.tsv.gz")]
    args += ["--taxa-vectors", str(tmp_path / "taxa.f16")]
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        main(args)
    write_manifest(atlas, {"version": VERSION, "parts": []})
    assert main(args) == 0
    table = pd.read_parquet(atlas / "confusion.parquet")
    entry = read_manifest(atlas)["confusion"]
    assert entry["name"] == "confusion.parquet" and entry["count"] == len(table) == 1
    assert entry["built_at"] == table["built_at"].iloc[0]
    assert table[["looks_like_name", "n_photos"]].values.tolist() == [["G b", 5]]
    records = pd.read_parquet(atlas / "confusion-records.parquet")
    rec = read_manifest(atlas)["confusion_records"]
    assert rec["name"] == "confusion-records.parquet" and rec["count"] == len(records) == 5
    assert rec["built_at"] == entry["built_at"]
    assert list(records.columns) == list(RECORD_COLUMNS)


def test_fir_cli_rejects_a_pool_without_photo_url(tmp_path):
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, *_ = _fir_inputs(["G a"], [5], [[0, 1, 0]], text)
    pool.drop(columns="photo_url").to_parquet(tmp_path / "pool.parquet", index=False)
    args = ["fir", "--emb", "e", "--ids", "i", "--pool", str(tmp_path / "pool.parquet")]
    args += ["--taxa-names", "n", "--taxa-vectors", "v", "--atlas-dir", str(tmp_path)]
    write_manifest(tmp_path, {"version": VERSION, "parts": []})
    with pytest.raises(ValueError, match="photo_url"):
        main(args)


def test_fir_records_are_the_negative_margin_photos_with_their_look_alike():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [5, 4], [[1, 0, 0], [0, 1, 0]], text)
    # The first two G a photos look like G b; the rest, and all of G b, sit on their own species.
    E = _unit([[0, 1, 0]] * 2 + [[1, 0, 0]] * 3 + [[0, 1, 0]] * 4)
    out = _records(pool, E, ids, taxa, T)
    assert list(out.columns) == list(RECORD_COLUMNS)
    assert out["id"].tolist() == [100, 101]
    a = out.iloc[0]
    assert (a.taxon_name, a.looks_like_name, a.looks_like_taxon_id) == ("G a", "G b", 11)
    assert (a.iconic_taxon, a.photo_url) == ("Plantae", "https://x/100.jpg")
    assert out["margin"].dtype == np.float32 and (out["margin"] < 0).all()
    assert out["looks_like_taxon_id"].dtype == "Int64"


def test_fir_records_looks_like_is_null_for_a_name_outside_the_pool():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [5], [[0, 1, 0]], text)
    out = _records(pool, E, ids, taxa, T)
    assert len(out) == 5
    assert out["looks_like_name"].eq("G b").all() and out["looks_like_taxon_id"].isna().all()


def test_fir_records_cap_keeps_the_most_negative_per_pair_sorted():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [6, 4], [[0, 1, 0], [0, 1, 0]], text)
    # G a photos drift towards G a with id, so the lowest ids are the most negative.
    E = E.copy()
    for k in range(6):
        E[k] = _unit([[k * 0.1, 1, 0]])[0]
    out = _records(pool, E, ids, taxa, T, cap=3)
    a = out[out.taxon_name == "G a"]
    assert a["id"].tolist() == [100, 101, 102]
    assert a["margin"].is_monotonic_increasing
    assert out["taxon_id"].is_monotonic_increasing


def test_fir_records_keep_only_the_listed_pairs():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0], "G c": [0, 0, 1]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [5], [[1, 0, 0]], text)
    # Two photos look like G b, one like G c: G c is a single-photo partner and never a pair.
    E = _unit([[0, 1, 0]] * 2 + [[0, 0, 1]] + [[1, 0, 0]] * 2)
    out = _records(pool, E, ids, taxa, T)
    assert out["id"].tolist() == [100, 101]
    assert out["looks_like_name"].eq("G b").all()


def test_every_listed_pair_has_records():
    text = {"G a": [1, 0, 0, 0], "G b": [0, 1, 0, 0], "G c": [0, 0, 1, 0], "G d": [0, 0, 0, 1]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [60], [[1, 0, 0, 0]], text)
    # 55 photos look like G b, 3 like G c, 2 like G d: three pairs, the first capped at 50.
    E = _unit([[0, 1, 0, 0]] * 55 + [[0, 0, 1, 0]] * 3 + [[0, 0, 0, 1]] * 2)
    scores = fir_scores(pool, E, ids, taxa, T)
    pairs, recs = fir_table(scores, BUILT), fir_records(scores, fir_table(scores, BUILT))
    per_pair = recs.groupby("looks_like_name").size()
    assert per_pair.reindex(pairs["looks_like_name"]).tolist() == [50, 3, 2]


def test_fir_records_four_photo_floor():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    kw = dict(vecs=[[0, 1, 0], [0, 1, 0]], text=text)
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [3, 5], **kw)
    assert "G a" not in _records(pool, E, ids, taxa, T)["taxon_name"].tolist()
    pool, E, ids, taxa, T = _fir_inputs(["G a", "G b"], [4, 5], **kw)
    assert "G a" in _records(pool, E, ids, taxa, T)["taxon_name"].tolist()


def test_fir_records_need_iconic_taxon_and_photo_url():
    text = {"G a": [1, 0, 0], "G b": [0, 1, 0]}
    pool, E, ids, taxa, T = _fir_inputs(["G a"], [5], [[0, 1, 0]], text)
    with pytest.raises(ValueError, match="iconic_taxon"):
        _records(pool.drop(columns="iconic_taxon"), E, ids, taxa, T)
