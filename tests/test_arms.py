from unittest import mock

import numpy as np
import pandas as pd
import pytest

from what_to_id.arms import ARMS, GapFirst, Novelty, Recency, Similarity, Surprise, build_arm

from .conftest import make_pool


def _created(pool):
    return pd.to_datetime(pool["created_at"], utc=True).to_numpy()


def test_recency_monotone(pool):
    order = Recency().order(pool, seed=0)
    assert sorted(order.tolist()) == list(range(len(pool)))
    c = _created(pool)[order]
    assert (c[:-1] >= c[1:]).all()


def test_recency_tie_break_id_desc():
    pool = pd.DataFrame({"id": [1, 3, 2], "created_at": ["2026-01-01T00:00:00Z"] * 3})
    assert pool["id"].to_numpy()[Recency().order(pool, seed=0)].tolist() == [3, 2, 1]


def test_gap_first_monotone_nan_last(pool):
    rng = np.random.default_rng(0)
    score = rng.random(len(pool))
    score[:30] = np.nan
    pool = pool.assign(cell_score=score)
    order = GapFirst().order(pool, seed=0)
    assert sorted(order.tolist()) == list(range(len(pool)))
    s = score[order]
    n_ok = int(np.isfinite(score).sum())
    assert np.isfinite(s[:n_ok]).all() and np.isnan(s[n_ok:]).all()
    assert (s[: n_ok - 1] >= s[1:n_ok]).all()
    # NaN tail is in recency order.
    c = _created(pool)[order][n_ok:]
    assert (c[:-1] >= c[1:]).all()


def test_gap_first_requires_column(pool):
    with pytest.raises(ValueError, match="cell_score"):
        GapFirst().order(pool, seed=0)


def _two_cluster_npz(path, ids, seed=0, d=16):
    rng = np.random.default_rng(seed)
    a, b = rng.normal(size=d), rng.normal(size=d)
    half = len(ids) // 2
    E = np.vstack(
        [
            a + 0.15 * rng.normal(size=(half, d)),
            b + 0.15 * rng.normal(size=(len(ids) - half, d)),
        ]
    ).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    np.savez(path, ids=np.asarray(ids, dtype=np.int64), E=E, backbone="synthetic")
    return E


def _mean_intra_batch_distance(E_by_id, batches):
    ds = []
    for b in batches:
        X = np.stack([E_by_id[i] for i in b])
        sims = X @ X.T
        n = len(b)
        ds.append((1 - sims[np.triu_indices(n, 1)]).mean())
    return float(np.mean(ds))


def test_similarity_groups_similar_records(tmp_path, pool):
    pytest.importorskip("labelfirst")
    pool = pool[pool["iconic_taxon"] == "Aves"].reset_index(drop=True)
    ids = pool["id"].to_numpy()
    embedded_ids = ids[:-5]  # last five records have no embedding
    npz = tmp_path / "emb_Aves.npz"
    E = _two_cluster_npz(npz, embedded_ids)
    E_by_id = dict(zip(embedded_ids.tolist(), E, strict=True))
    size = 10
    arm = Similarity({"Aves": npz}, batch_size=size)
    from labelfirst.strategies.coreset import CoreSet

    original = CoreSet.select
    with mock.patch.object(CoreSet, "select", autospec=True, side_effect=original) as sel:
        order = arm.order(pool, seed=0)
    assert sel.called
    assert sorted(order.tolist()) == list(range(len(pool)))
    ordered_ids = ids[order]
    assert set(ordered_ids[-5:].tolist()) == set(ids[-5:].tolist())
    tail = pool.iloc[order[-5:]]
    c = pd.to_datetime(tail["created_at"], utc=True).to_numpy()
    assert (c[:-1] >= c[1:]).all()

    head = ordered_ids[:-5]
    batches = [head[i : i + size].tolist() for i in range(0, len(head), size)]
    rng = np.random.default_rng(0)
    rand = rng.permutation(head)
    rand_batches = [rand[i : i + size].tolist() for i in range(0, len(rand), size)]
    assert _mean_intra_batch_distance(E_by_id, batches) < _mean_intra_batch_distance(
        E_by_id, rand_batches
    )


def test_similarity_centre_order_by_cell_score(tmp_path):
    pytest.importorskip("labelfirst")
    n = 40
    pool = make_pool(n, groups=["Aves"])
    npz = tmp_path / "e.npz"
    _two_cluster_npz(npz, pool["id"].to_numpy())
    # First cluster (rows 0..19) gets low cell score, second cluster high.
    pool["cell_score"] = np.r_[np.full(20, 0.1), np.full(20, 0.9)]
    order = Similarity(npz, batch_size=20).order(pool, seed=3)
    assert set(order[:20].tolist()) == set(range(20, 40))


def test_similarity_no_embeddings_falls_back_to_recency(tmp_path, pool):
    pytest.importorskip("labelfirst")
    npz = tmp_path / "e.npz"
    _two_cluster_npz(npz, [1, 2, 3, 4])
    sub = pool.head(20)
    assert (
        Similarity(npz, batch_size=5).order(sub, seed=0).tolist()
        == Recency().order(sub, seed=0).tolist()
    )


def test_novelty_far_from_reference_first(tmp_path):
    n = 40
    pool = make_pool(n, groups=["Aves"])
    ids = pool["id"].to_numpy()
    emb = tmp_path / "emb_Aves.npz"
    E = _two_cluster_npz(emb, ids)
    # Reference sits entirely in the first cluster (rows 0..19), so rows 20..39 are the novel ones.
    ref = tmp_path / "ref_Aves.npz"
    np.savez(ref, ids=np.arange(1, 6, dtype=np.int64), E=E[:5], backbone="synthetic")
    arm = Novelty({"Aves": emb}, {"Aves": ref})
    order = arm.order(pool, seed=0)
    assert sorted(order.tolist()) == list(range(n))
    assert set(order[:20].tolist()) == set(range(20, 40))
    dist = arm.distances(E, np.load(ref)["E"])
    d = dist[order]
    assert (d[:-1] >= d[1:] - 1e-9).all()


def test_novelty_unembedded_last_in_recency_order(tmp_path):
    pool = make_pool(30, groups=["Aves"])
    ids = pool["id"].to_numpy()
    emb = tmp_path / "e.npz"
    E = _two_cluster_npz(emb, ids[:-6])  # last six rows have no embedding
    ref = tmp_path / "r.npz"
    np.savez(ref, ids=np.arange(3, dtype=np.int64), E=E[:3], backbone="synthetic")
    order = Novelty(emb, ref).order(pool, seed=0)
    tail = pool.iloc[order[-6:]]
    assert set(tail["id"].tolist()) == set(ids[-6:].tolist())
    c = _created(tail)
    assert (c[:-1] >= c[1:]).all()


def test_novelty_without_reference_falls_back_to_recency(tmp_path, pool):
    emb = tmp_path / "e.npz"
    _two_cluster_npz(emb, pool["id"].to_numpy())
    sub = pool.head(20)
    arm = Novelty(emb, {"Insecta": tmp_path / "missing.npz"})
    assert arm.order(sub, seed=0).tolist() == Recency().order(sub, seed=0).tolist()


def test_novelty_rejects_dim_mismatch(tmp_path):
    pool = make_pool(8, groups=["Aves"])
    emb = tmp_path / "e.npz"
    _two_cluster_npz(emb, pool["id"].to_numpy(), d=16)
    ref = tmp_path / "r.npz"
    np.savez(ref, ids=np.arange(2, dtype=np.int64), E=np.eye(2, 8, dtype=np.float32), backbone="")
    with pytest.raises(ValueError, match="dims differ"):
        Novelty(emb, ref).order(pool, seed=0)
    with pytest.raises(ValueError):
        Novelty(emb, ref, chunk=0)


def test_surprise_orders_by_score_nan_last(pool):
    score = np.random.default_rng(1).random(len(pool))
    score[:20] = np.nan
    order = Surprise().order(pool.assign(surprise=score), seed=0)
    assert sorted(order.tolist()) == list(range(len(pool)))
    s = score[order]
    n_ok = int(np.isfinite(score).sum())
    assert (s[: n_ok - 1] >= s[1:n_ok]).all() and np.isnan(s[n_ok:]).all()
    with pytest.raises(ValueError, match="surprise-scores"):
        Surprise().order(pool, seed=0)


def test_surprise_tie_break_by_fewest_n_ref(pool):
    pool = pool.iloc[:4].copy()
    pool["surprise"] = [1.0, 1.0, 1.0, 0.5]
    pool["surprise_n_ref"] = [3.0, 0.0, np.nan, 1.0]
    order = Surprise().order(pool, seed=0)
    # Fewer n_ref first among the surprise==1 tie (0 < 3 < NaN), the surprise==0.5 record last.
    assert pool["id"].to_numpy()[order].tolist() == pool["id"].iloc[[1, 0, 2, 3]].tolist()


def test_surprise_without_n_ref_column_keeps_old_order(pool):
    score = np.random.default_rng(1).random(len(pool))
    pool = pool.assign(surprise=score)
    without_col = Surprise().order(pool, seed=0)
    # A pool where every row ties on n_ref falls back to the same recency/id tie-break.
    tied_n_ref = Surprise().order(pool.assign(surprise_n_ref=0.0), seed=0)
    assert (without_col == tied_n_ref).all()


def test_surprise_tie_break_by_sinr(pool):
    pool = pool.iloc[:4].copy()
    pool["surprise"] = [1.0, 1.0, 1.0, 0.5]
    pool["surprise_sinr"] = [0.2, 0.9, 0.5, 1.0]
    order = Surprise().order(pool, seed=0)
    # Higher surprise_sinr first among the surprise==1 tie, the surprise==0.5 record still last.
    assert pool["id"].to_numpy()[order].tolist() == pool["id"].iloc[[1, 2, 0, 3]].tolist()


def test_surprise_sinr_nan_falls_back_to_n_ref(pool):
    pool = pool.iloc[:4].copy()
    pool["surprise"] = 1.0
    pool["surprise_sinr"] = [0.9, np.nan, np.nan, 0.9]
    pool["surprise_n_ref"] = [5.0, 1.0, 3.0, 2.0]
    order = Surprise().order(pool, seed=0)
    # Scored SINR goes before unscored SINR; within each group, fewer n_ref first.
    assert pool["id"].to_numpy()[order].tolist() == pool["id"].iloc[[3, 0, 1, 2]].tolist()


def test_surprise_sinr_never_overrides_higher_surprise(pool):
    pool = pool.iloc[:2].copy()
    pool["surprise"] = [0.9, 0.5]
    pool["surprise_sinr"] = [0.1, 1.0]
    order = Surprise().order(pool, seed=0)
    assert pool["id"].to_numpy()[order].tolist() == pool["id"].tolist()


def test_surprise_without_sinr_column_keeps_old_order(pool):
    score = np.random.default_rng(1).random(len(pool))
    n_ref = np.random.default_rng(2).random(len(pool))
    pool = pool.assign(surprise=score, surprise_n_ref=n_ref)
    without_col = Surprise().order(pool, seed=0)
    # A pool where every row ties on surprise_sinr falls back to the same n_ref tie-break.
    tied_sinr = Surprise().order(pool.assign(surprise_sinr=0.0), seed=0)
    assert (without_col == tied_sinr).all()


def test_build_arm():
    assert set(ARMS) == {"recency", "gap_first", "similarity", "novelty", "surprise"}
    assert build_arm("recency").name == "recency"
    with pytest.raises(ValueError):
        build_arm("nope")
    with pytest.raises(ValueError):
        Similarity({}, batch_size=0)
