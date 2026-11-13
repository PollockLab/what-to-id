"""Daily Identify levels: new records scored against cut-offs frozen from the base table."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import identify
from what_to_id.atlas_index_io import VERSION, read_manifest, write_manifest

from .test_levels import TEXT, TREE, _unit, identify_bundle

NONE, EASY, TAX, WEIRD, MISLABEL = 0, 1, 2, 4, 5


def rows(tops, own=0.9, other=0.1, taxon_id=4, group="Plantae", start=1000):
    """Species-ranked score rows of 'G a', one per `top`, whose look-alike is 'G b'."""
    n = len(tops)
    return pd.DataFrame(
        {
            "id": np.arange(start, start + n),
            "taxon_id": taxon_id,
            "taxon_name": "G a",
            "rank": "species",
            "iconic_taxon": group,
            "top": np.asarray(tops, dtype=np.float64),
            "own": own,
            "other": other,
            "other_name": "G b",
            "in_best": np.nan,
            "in_second": np.nan,
            "out_best": np.nan,
            "in_name": None,
        }
    )


def frozen(weird=0.5, easy=0.8, n=10):
    return identify.Frozen(
        pd.Series({"Plantae": weird}), pd.Series({4: easy}), pd.Series({4: n}, dtype="int64")
    )


def levels_of(s, fz, bc=100):
    return identify.identify_levels(s, pd.Series({"G b": bc}), fz)["level"].tolist()


def test_frozen_cutoffs_reproduce_the_full_run():
    pool, E, ids, taxa, T = identify_bundle()
    s = identify.identify_scores(pool, E, ids, taxa, T, TREE)
    base = identify.identify_levels(s)
    again = identify.identify_levels(s, frozen=identify.freeze_cutoffs(base, pool))
    assert (again["level"] == base["level"]).all() and (base["level"] == EASY).any()
    assert (base["level"] == WEIRD).any()


def test_weird_boundary_is_inclusive_and_unknown_groups_are_never_weird():
    assert levels_of(rows([0.4999, 0.5, 0.5001]), frozen(weird=0.5)) == [WEIRD, WEIRD, EASY]
    assert levels_of(rows([0.1], group="Aves"), frozen()) == [EASY]  # no cut for Aves: not weird


def test_easy_needs_the_species_cut_and_four_base_records():
    s = rows([0.9, 0.9], own=[0.8, 0.7999])
    assert levels_of(s, frozen(easy=0.8)) == [EASY, NONE]
    assert levels_of(rows([0.9]), frozen(n=3)) == [NONE]  # too few base records for a Clear match
    assert levels_of(rows([0.9]), frozen(n=4)) == [EASY]
    assert levels_of(rows([0.9], taxon_id=99), frozen()) == [NONE]  # species not in the base


def test_mislabel_boundary_needs_margin_below_the_cut_and_a_known_lookalike():
    close, far = dict(own=0.5, other=0.5199), dict(own=0.5, other=0.5201)
    assert levels_of(rows([0.9], **close), frozen()) == [TAX]
    assert levels_of(rows([0.9], **far), frozen()) == [MISLABEL]
    assert levels_of(rows([0.9], **far), frozen(), bc=19) == [NONE]
    assert levels_of(rows([0.9], **far), frozen(), bc=20) == [MISLABEL]


def test_delta_appends_new_ids_and_leaves_base_rows_alone():
    pool, E, ids, taxa, T = identify_bundle()
    s = identify.identify_scores(pool, E, ids, taxa, T, TREE)
    base = identify.identify_levels(s)
    new = pd.DataFrame(
        {"id": [5000, 5001], "taxon_id": [4, 4], "taxon_name": "G a", "rank": "species"}
    ).assign(iconic_taxon="Plantae")
    # id 100 is in the base and now has a vector of nothing: it keeps its level
    E2 = np.vstack([E, _unit([[1, 0, 0, 0], [0, 0, 0, 1]])])
    E2[0] = _unit([[0, 0, 0, 1]])[0]
    out = identify.identify_delta(
        base, pd.concat([pool, new], ignore_index=True), E2, np.append(ids, [5000, 5001]),
        taxa, T, TREE,
    )  # fmt: skip
    assert len(out) == len(base) + 2
    pd.testing.assert_frame_equal(
        out.iloc[: len(base)].reset_index(drop=True), base, check_categorical=False
    )
    assert out["level"].iloc[-2:].tolist() == [EASY, WEIRD]
    assert out["id"].is_unique


def test_no_new_records_returns_the_base():
    pool, E, ids, taxa, T = identify_bundle()
    base = identify.identify_levels(identify.identify_scores(pool, E, ids, taxa, T, TREE))
    out = identify.identify_delta(base, pool, E[:0], ids[:0], taxa, T, TREE)
    pd.testing.assert_frame_equal(out, base, check_categorical=False)
    empty = identify.identify_delta(base.iloc[:0], pool.iloc[:0], E[:0], ids[:0], taxa, T, TREE)
    assert empty.empty and list(empty.columns) == [*identify.IDENTIFY_COLUMNS, "runner_up"]


def test_cli_extends_the_live_table_and_keeps_the_new_manifest(tmp_path):
    pool, E, ids, taxa, T = identify_bundle()
    base = identify.identify_levels(identify.identify_scores(pool, E, ids, taxa, T, TREE))
    live, index, folder = tmp_path / "live", tmp_path / "index", tmp_path / "taxa"
    for d in (live, index, folder):
        d.mkdir()
    base.to_parquet(live / "identify.parquet", index=False)
    write_manifest(live, {"version": VERSION, "identify": {"name": "identify.parquet", "emb": "x"}})
    write_manifest(index, {"version": VERSION, "parts": ["delta-1"], "identify": {"stale": 1}})
    with gzip.open(folder / "taxa-abc.tsv.gz", "wt") as f:
        f.write("".join(f"{n}\t\n" for n in TEXT))
    T.astype(np.float16).tofile(folder / "taxa-abc.f16")
    (tmp_path / "taxonomy.json").write_text(
        json.dumps({"taxa": {str(k): v for k, v in TREE.items()}})
    )
    new = pd.DataFrame({"id": [5000], "taxon_id": [4], "taxon_name": "G a", "rank": "species"})
    pd.concat([pool, new.assign(iconic_taxon="Plantae")]).to_parquet(tmp_path / "pool.parquet")
    np.savez(tmp_path / "raw.npz", ids=np.array([5000]), E=_unit([[1, 0, 0, 0]]).astype("f2"))
    args = ["--live", str(live), "--index", str(index), "--pool", str(tmp_path / "pool.parquet")]
    args += ["--tree", str(tmp_path / "taxonomy.json"), "--taxa", str(folder)]
    args += ["--vectors", str(tmp_path / "raw.npz")]
    assert identify.main(args) == 0
    out = pd.read_parquet(index / "identify.parquet")
    assert len(out) == len(base) + 1 and out["level"].iloc[-1] == EASY
    m = read_manifest(index)
    assert m["parts"] == ["delta-1"]  # this run's manifest, not the live one
    assert m["identify"]["emb"] == "x" and m["identify"]["count"] == len(out)
    assert "stale" not in m["identify"] and "delta_at" in m["identify"]
    (live / "identify.parquet").unlink()  # before the first Fir run there is nothing to extend
    (index / "identify.parquet").unlink()
    assert identify.main(args) == 0 and not (index / "identify.parquet").exists()


def test_vectors_with_the_wrong_width_are_refused(tmp_path):
    with pytest.raises(ValueError, match="dims"):
        pool, E, ids, taxa, T = identify_bundle()
        np.savez(tmp_path / "raw.npz", ids=ids[:1], E=np.zeros((1, 3), "f2"))
        base = identify.identify_levels(identify.identify_scores(pool, E, ids, taxa, T, TREE))
        live, index, folder = tmp_path / "live", tmp_path / "index", tmp_path / "taxa"
        for d in (live, index, folder):
            d.mkdir()
        base.to_parquet(live / "identify.parquet", index=False)
        write_manifest(live, {"version": VERSION, "identify": {"name": "identify.parquet"}})
        with gzip.open(folder / "taxa-abc.tsv.gz", "wt") as f:
            f.write("".join(f"{n}\t\n" for n in TEXT))
        T.astype(np.float16).tofile(folder / "taxa-abc.f16")
        (tmp_path / "t.json").write_text(json.dumps({"taxa": {"1": TREE[1]}}))
        pool.to_parquet(tmp_path / "pool.parquet")
        identify.main(
            ["--live", str(live), "--index", str(index), "--pool", str(tmp_path / "pool.parquet"),
             "--tree", str(tmp_path / "t.json"), "--taxa", str(folder),
             "--vectors", str(tmp_path / "raw.npz")]
        )  # fmt: skip


def table():
    """The bundle's pool, vectors and full-run levels."""
    pool, E, ids, taxa, T = identify_bundle()
    base = identify.identify_levels(identify.identify_scores(pool, E, ids, taxa, T, TREE))
    return pool, E, ids, taxa, T, base


def refresh(pool, E, ids, taxa, T, base, reconstruct=None):
    return identify.identify_delta(base, pool, E, ids, taxa, T, TREE, reconstruct=reconstruct)


def test_renamed_records_are_rescored_from_reconstructed_vectors():
    pool, E, ids, taxa, T, base = table()
    sp = pool[pool["rank"] == "species"]["id"].iloc[0]
    row = base["id"] == sp
    moved = pool.assign(taxon_id=np.where(pool["id"] == sp, 5, pool["taxon_id"]))
    vec = dict(zip(ids, E, strict=True))
    calls = []

    def reconstruct(want):
        calls.append(sorted(want))
        return np.array(want), np.array([vec[i] for i in want])

    out = refresh(moved, E[:0], ids[:0], taxa, T, base, reconstruct)
    assert calls == [[sp]]  # only the renamed row is read back
    assert out.loc[out["id"] == sp, "taxon_id"].item() == 5
    assert len(out) == len(base) and out["id"].is_unique
    rest = out["id"] != sp
    pd.testing.assert_frame_equal(
        out[rest].reset_index(drop=True), base[~row].reset_index(drop=True), check_categorical=False
    )


def test_raw_vectors_win_over_reconstruction_and_a_missing_vector_keeps_the_old_row():
    pool, E, ids, taxa, T, base = table()
    a, b = pool[pool["rank"] == "species"]["id"].iloc[:2]
    moved = pool.assign(taxon_id=np.where(pool["id"].isin([a, b]), 5, pool["taxon_id"]))
    raw = np.array([a])
    out = refresh(moved, E[np.isin(ids, raw)], raw, taxa, T, base, lambda want: (want[:0], E[:0]))
    assert out.loc[out["id"] == a, "taxon_id"].item() == 5
    assert (
        out.loc[out["id"] == b, "taxon_id"].item() == base.loc[base["id"] == b, "taxon_id"].item()
    )
    assert len(out) == len(base)


def test_records_that_left_the_pool_drop_out():
    pool, E, ids, taxa, T, base = table()
    gone = pool["id"].iloc[:3]
    out = refresh(pool[~pool["id"].isin(gone)], E[:0], ids[:0], taxa, T, base)
    assert len(out) == len(base) - 3 and not out["id"].isin(gone).any()
    unlabelled = pool.assign(taxon_id=pool["taxon_id"].mask(pool["id"].isin(gone)))
    assert refresh(unlabelled, E[:0], ids[:0], taxa, T, base).equals(out)


def test_pool_records_in_the_index_but_never_scored_get_a_row():
    pool, E, ids, taxa, T, base = table()
    hole = base["id"].iloc[5]
    vec = dict(zip(ids, E, strict=True))
    out = refresh(
        pool, E[:0], ids[:0], taxa, T, base[base["id"] != hole],
        lambda want: (np.array(want), np.array([vec[i] for i in want])),
    )  # fmt: skip
    assert hole in set(out["id"]) and len(out) == len(base)
    assert (
        out.loc[out["id"] == hole, "level"].item() == base.loc[base["id"] == hole, "level"].item()
    )


def test_untouched_pool_never_calls_reconstruct():
    pool, E, ids, taxa, T, base = table()

    def boom(want):
        raise AssertionError("nothing to rescore")

    out = refresh(pool, E[:0], ids[:0], taxa, T, base, boom)
    pd.testing.assert_frame_equal(out, base, check_categorical=False)
