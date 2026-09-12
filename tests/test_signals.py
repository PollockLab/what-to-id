import numpy as np
import pandas as pd
import pytest

from what_to_id.signals import COLUMNS, batch_signals, cohesion, signals_by_batch


def _unit(rng, n, d):
    E = rng.normal(size=(n, d)).astype(np.float32)
    return E / np.linalg.norm(E, axis=1, keepdims=True)


def _npz(path, ids, E):
    np.savez(path, ids=np.asarray(ids, dtype=np.int64), E=E, backbone="synthetic")


def test_cohesion_identical_rows_is_one_and_random_is_lower():
    rng = np.random.default_rng(0)
    one = np.tile(_unit(rng, 1, 32), (10, 1))
    assert cohesion(one) == pytest.approx(1.0, abs=1e-6)
    assert cohesion(_unit(rng, 10, 32)) < 0.7
    assert np.isnan(cohesion(one[:1]))
    assert cohesion(np.vstack([one[:1], -one[:1]])) == 0.0


def test_batch_signals_tight_vs_mixed(tmp_path):
    rng = np.random.default_rng(1)
    d = 32
    a, b = _unit(rng, 1, d)[0], _unit(rng, 1, d)[0]
    A = a + 0.05 * rng.normal(size=(10, d))
    B = b + 0.05 * rng.normal(size=(10, d))
    E = np.vstack([A, B]).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    ids = np.arange(1, 21)
    emb = tmp_path / "emb.npz"
    _npz(emb, ids, E)
    # Reference sits on cluster A only, so batch "tight-A" is familiar and "tight-B" is novel.
    ref = tmp_path / "ref.npz"
    _npz(ref, np.arange(100, 105), E[:5])
    batches = pd.DataFrame(
        {
            "batch_id": ["tight-A"] * 10 + ["tight-B"] * 10 + ["mixed"] * 10,
            "group": "Aves",
            "id": [*ids[:10], *ids[10:], *ids[:5], *ids[10:15]],
        }
    )
    sig = batch_signals(batches, {"Aves": emb}, {"Aves": ref}).set_index("batch_id")
    assert list(sig.reset_index().columns) == list(COLUMNS)
    assert (sig["n_embedded"] == 10).all()
    assert sig.loc["tight-A", "cohesion"] > 0.9 > sig.loc["mixed", "cohesion"]
    assert sig.loc["tight-B", "cohesion"] > 0.9
    assert (
        sig.loc["tight-B", "novelty"] > sig.loc["mixed", "novelty"] > sig.loc["tight-A", "novelty"]
    )
    assert sig.loc["tight-A", "novelty"] < 0.05  # half its members are the reference itself


def test_batch_signals_without_reference_and_unembedded(tmp_path):
    rng = np.random.default_rng(2)
    emb = tmp_path / "emb.npz"
    _npz(emb, [1, 2, 3], _unit(rng, 3, 8))
    batches = pd.DataFrame(
        {"batch_id": ["x", "x", "x", "x", "y"], "group": "Aves", "id": [1, 2, 3, 99, 98]}
    )
    sig = batch_signals(batches, emb).set_index("batch_id")
    assert sig.loc["x", "n_embedded"] == 3 and sig.loc["y", "n_embedded"] == 0
    assert np.isnan(sig.loc["y", "cohesion"]) and sig["novelty"].isna().all()
    d = signals_by_batch(sig.reset_index())
    assert d["y"] == {"n_embedded": 0, "cohesion": None, "novelty": None}
    assert d["x"]["novelty"] is None and 0.0 <= d["x"]["cohesion"] <= 1.0


def test_batch_signals_group_without_file(tmp_path):
    rng = np.random.default_rng(3)
    emb = tmp_path / "emb.npz"
    _npz(emb, [1, 2], _unit(rng, 2, 8))
    batches = pd.DataFrame({"batch_id": ["z", "z"], "group": "Fungi", "id": [1, 2]})
    sig = batch_signals(batches, {"Aves": emb})
    assert sig.loc[0, "n_embedded"] == 0 and np.isnan(sig.loc[0, "cohesion"])
    with pytest.raises(ValueError, match="columns"):
        batch_signals(batches.drop(columns="group"), emb)
