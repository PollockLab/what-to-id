"""Exact equivalence to the pre-conversion growth algorithm, including ties."""

import numpy as np
import pytest

from what_to_id.arms import Similarity


# Frozen pre-optimization implementation: preserve mixed-dtype rounding and tie choices.
def baseline_grow(self, X: np.ndarray, picks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Grow one batch per seed: repeatedly add the free row nearest the running centroid.

    Returns (batch index per row, cosine of each row to its batch's final centroid). Seeds
    that were already absorbed by an earlier batch are replaced by the nearest free row.
    """
    n = X.shape[0]
    free = np.ones(n, dtype=bool)
    member_of = np.full(n, -1, dtype=np.int64)
    for c, p in enumerate(picks):
        if not free.any():
            break
        if not free[p]:
            cand = np.flatnonzero(free)
            p = cand[(X[cand] @ X[p]).argmax()]
        members = [int(p)]
        free[p] = False
        centroid = X[p].astype(np.float64).copy()
        while len(members) < self.batch_size and free.any():
            sims = X @ (centroid / max(np.linalg.norm(centroid), 1e-12))
            sims[~free] = -np.inf
            q = int(sims.argmax())
            members.append(q)
            free[q] = False
            centroid += X[q]
        member_of[members] = c
    # Any rows left when seeds ran out join the last batch.
    member_of[member_of < 0] = len(picks) - 1
    member_sim = np.empty(n, dtype=np.float64)
    for c in np.unique(member_of):
        rows = np.flatnonzero(member_of == c)
        centroid = X[rows].mean(axis=0)
        member_sim[rows] = X[rows] @ (centroid / max(np.linalg.norm(centroid), 1e-12))
    return member_of, member_sim


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("case", ["random", "ties", "cancelled", "empty", "singleton"])
def test_growth_matches_original(dtype, case):
    if case == "random":
        X = np.random.default_rng(13).normal(size=(53, 17)).astype(dtype)
        X /= np.linalg.norm(X, axis=1, keepdims=True)
        picks = np.array([0, 1, 2, 20, 30, 50])
    elif case == "ties":
        X = np.tile(np.eye(3, dtype=dtype), (4, 1))
        picks = np.array([0, 3, 6])  # Later seeds have already been absorbed.
    elif case == "cancelled":
        X = np.array([[1, 0], [-1, 0], [0, 1], [0, -1]], dtype=dtype)
        picks = np.array([0])
    elif case == "singleton":
        X = np.ones((1, 1), dtype=dtype)
        picks = np.array([0])
    else:
        X = np.empty((0, 3), dtype=dtype)
        picks = np.array([], dtype=int)
    arm = Similarity("unused.npz", batch_size=9)
    expected = baseline_grow(arm, X, picks)
    actual = arm._grow(X, picks)
    for before, after in zip(expected, actual, strict=True):
        np.testing.assert_array_equal(before, after)
