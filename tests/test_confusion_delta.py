import gzip

import numpy as np
import pandas as pd
import pytest

from what_to_id.atlas_index_io import VERSION, read_manifest, write_manifest
from what_to_id.confusion import (
    SCORE_COLUMNS,
    current_scores,
    daily_scores,
    fir_records,
    fir_scores,
    fir_table,
    main,
)

TEXT = {"G a": [1, 0, 0], "G b": [0, 1, 0], "G c": [0, 0, 1]}


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _inputs(seed=0, n=40):
    """`n` species records with noisy vectors, labelled so some sit nearer another prototype."""
    rng = np.random.default_rng(seed)
    names = rng.choice(list(TEXT), n)
    near = rng.choice(list(TEXT), n)
    E = _unit(np.array([TEXT[k] for k in near]) + rng.normal(0, 0.3, (n, 3)))
    ids = np.arange(100, 100 + n)
    pool = pd.DataFrame(
        {
            "id": ids,
            "taxon_id": [10 + list(TEXT).index(k) for k in names],
            "taxon_name": names,
            "rank": "species",
            "iconic_taxon": "Plantae",
            "photo_url": [f"https://x/{i}.jpg" for i in ids],
        }
    )
    return pool, E, ids, pd.Series(list(TEXT)), _unit(list(TEXT.values()))


def _tables(scores):
    out = fir_table(scores, "t")
    return out, fir_records(scores, out)


def test_delta_from_a_partial_state_matches_a_full_run():
    pool, E, ids, taxa, T = _inputs()
    full = fir_scores(pool, E, ids, taxa, T)
    state = full[list(SCORE_COLUMNS)].iloc[:25]  # the Fir run saw 25; the deltas hold the rest
    new = daily_scores(state, pool, E[25:], ids[25:], taxa, T)
    assert sorted(new["id"]) == sorted(ids)
    want, got = _tables(full), _tables(current_scores(new, pool))
    for w, g in zip(want, got, strict=True):
        key = list(w.columns[:2])
        pd.testing.assert_frame_equal(
            w.sort_values(key).reset_index(drop=True),
            g.sort_values(key).reset_index(drop=True),
            check_dtype=False,
        )


def test_delta_rescores_renames_with_a_vector_and_drops_the_rest():
    pool, E, ids, taxa, T = _inputs()
    state = fir_scores(pool, E, ids, taxa, T)[list(SCORE_COLUMNS)]
    now = pool.copy()
    now.loc[0, "taxon_name"] = "G c" if now.loc[0, "taxon_name"] != "G c" else "G a"
    now.loc[1, "taxon_name"] = "G c" if now.loc[1, "taxon_name"] != "G c" else "G a"
    now = now.drop(index=2)  # left the pool
    new = daily_scores(state, now, E[:1], ids[:1], taxa, T)  # only record 0 has a delta vector
    assert ids[0] in set(new["id"]) and not {ids[1], ids[2]} & set(new["id"])
    row = new[new["id"] == ids[0]].iloc[0]
    assert row["taxon_name"] == now.loc[0, "taxon_name"]
    want = fir_scores(now.iloc[:1], E[:1], ids[:1], taxa, T).iloc[0]
    assert row["own"] == pytest.approx(want["own"]) and row["other_name"] == want["other_name"]
    cur = current_scores(new, now)
    assert len(cur) == len(now) - 1 and cur["margin"].notna().all()


def test_delta_with_no_vectors_keeps_the_state():
    pool, E, ids, taxa, T = _inputs()
    state = fir_scores(pool, E, ids, taxa, T)[list(SCORE_COLUMNS)]
    new = daily_scores(state, pool, E[:0], ids[:0], taxa, T)
    assert len(new) == len(state)


def _write_taxa(folder):
    folder.mkdir()
    with gzip.open(folder / "taxa-x.tsv.gz", "wt") as f:
        f.write("".join(f"{k}\t\n" for k in TEXT))
    _unit(list(TEXT.values())).astype(np.float16).tofile(folder / "taxa-x.f16")


def test_delta_cli_extends_the_live_scores_and_keeps_other_manifest_keys(tmp_path):
    pool, E, ids, taxa, T = _inputs()
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    _write_taxa(tmp_path / "taxa")
    live, index = tmp_path / "live", tmp_path / "index"
    live.mkdir()
    index.mkdir()
    args = ["delta", "--live", str(live), "--index", str(index), "--pool"]
    args += [str(tmp_path / "pool.parquet"), "--taxa", str(tmp_path / "taxa")]
    write_manifest(index, {"version": VERSION, "parts": [], "identify": {"name": "i"}})
    assert main(args) == 0  # nothing to extend before the Fir run
    assert not (index / "confusion.parquet").exists()
    T16 = np.fromfile(tmp_path / "taxa" / "taxa-x.f16", dtype=np.float16).reshape(3, -1)
    seed = fir_scores(pool, E, ids, taxa, T16.astype(np.float32))
    seed[list(SCORE_COLUMNS)].iloc[:25].to_parquet(live / "confusion-scores.parquet")
    np.savez(tmp_path / "a.npz", ids=ids[25:35], E=E[25:35].astype(np.float16))
    np.savez(tmp_path / "b.npz", ids=ids[30:], E=E[30:].astype(np.float16))  # overlaps a
    assert main([*args, "--vectors", str(tmp_path / "a.npz"), str(tmp_path / "b.npz")]) == 0
    m = read_manifest(index)
    assert m["identify"] == {"name": "i"}
    scores = pd.read_parquet(index / "confusion-scores.parquet")
    assert m["confusion_scores"]["count"] == len(scores) == len(ids)
    table = pd.read_parquet(index / "confusion.parquet")
    assert m["confusion"]["count"] == len(table) > 0
    assert m["confusion"]["built_at"] == table["built_at"].iloc[0]
    assert m["confusion_records"]["count"] == len(
        pd.read_parquet(index / "confusion-records.parquet")
    )
