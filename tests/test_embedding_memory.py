import weakref

import numpy as np
import pandas as pd
import pytest

from what_to_id.arms import Novelty, Similarity, _EmbeddingStore, load_embeddings
from what_to_id.batches import build_batches
from what_to_id.signals import batch_signals

from .conftest import make_pool


def test_store_releases_previous_file(tmp_path):
    paths = {group: tmp_path / f"{group}.npz" for group in ("Aves", "Insecta")}
    for path in paths.values():
        np.savez(path, ids=[1, 2], E=np.eye(2))
    store = _EmbeddingStore(paths)
    first = store.lookup("Aves")
    references = [weakref.ref(array) for array in first]
    del first
    store.lookup("Insecta")
    assert all(reference() is None for reference in references)
    np.testing.assert_array_equal(store.lookup("Aves")[1], np.eye(2))


@pytest.mark.parametrize("bad_value", [None, np.nan, 2.0])
def test_validation_bounds_workspace_and_checks_last_chunk(tmp_path, monkeypatch, bad_value):
    E = np.zeros((8193, 2), dtype=np.float32)
    E[:, 0] = 1
    if bad_value is not None:
        E[-1, 0] = bad_value
    path = tmp_path / "e.npz"
    np.savez(path, ids=np.arange(len(E)), E=E)
    original = np.linalg.norm
    sizes = []

    def bounded_norm(X, *args, **kwargs):
        sizes.append(len(X))
        assert len(X) <= 8192
        return original(X, *args, **kwargs)

    monkeypatch.setattr(np.linalg, "norm", bounded_norm)
    if bad_value is None:
        np.testing.assert_array_equal(load_embeddings(path)[1], E)
        assert sizes == [8192, 1]
    else:
        with pytest.raises(ValueError, match="finite|unit norm"):
            load_embeddings(path)


@pytest.mark.labelfirst
def test_multigroup_selection_and_signals_match_separate_group_builds(tmp_path):
    import labelfirst

    assert callable(labelfirst.CoreSet)
    pool = make_pool(40, groups=["Aves", "Insecta"])
    pool["cell_score"] = np.linspace(0, 1, len(pool))
    candidates, references = {}, {}
    for group, rows in pool.groupby("iconic_taxon"):
        vectors = np.random.default_rng(12).normal(size=(len(rows), 16)).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        candidates[group], references[group] = (
            tmp_path / f"e_{group}.npz",
            tmp_path / f"r_{group}.npz",
        )
        np.savez(candidates[group], ids=rows["id"].to_numpy(), E=vectors)
        np.savez(references[group], ids=np.arange(3), E=vectors[:3])
    assignment = pd.DataFrame({"id": pool["id"], "arm": ["similarity", "novelty"] * 20})

    def build(rows):
        arms = {
            "similarity": Similarity(candidates, batch_size=4),
            "novelty": Novelty(candidates, references),
        }
        batches = build_batches(rows, assignment, arms, size=4, seed=3)
        return batches, batch_signals(batches, candidates, references)

    all_batches, all_signals = build(pool)
    separate = [build(rows) for _, rows in pool.groupby("iconic_taxon")]
    for actual, expected in (
        (all_batches, pd.concat([item[0] for item in separate])),
        (all_signals, pd.concat([item[1] for item in separate])),
    ):
        order = ["batch_id", "position"] if "position" in actual else ["batch_id"]
        pd.testing.assert_frame_equal(
            actual.sort_values(order).reset_index(drop=True),
            expected.sort_values(order).reset_index(drop=True),
            check_exact=True,
        )
