"""Measure a displayed layout against the model's actual ranked photo matches."""

from __future__ import annotations

import numpy as np


def projection_fidelity(coordinates: np.ndarray, neighbors: np.ndarray) -> tuple[dict, np.ndarray]:
    """Count full-space matches among each point's nearest displayed neighbors.

    Coordinates must be the values actually emitted to the viewer. Equal display
    distances use source row order, matching the generator's full-space tie rule.
    This measures a layout's local ranking loss, not identification accuracy.
    """
    coordinates = np.asarray(coordinates, dtype=np.float64)
    neighbors = np.asarray(neighbors)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2 or len(coordinates) < 2:
        raise ValueError("projection coordinates must have shape (observations, 2)")
    if not np.isfinite(coordinates).all():
        raise ValueError("projection coordinates must be finite")
    count = len(coordinates)
    if (
        neighbors.ndim != 2
        or neighbors.shape[0] != count
        or not 0 < neighbors.shape[1] < count
        or not np.issubdtype(neighbors.dtype, np.integer)
    ):
        raise ValueError("ranked neighbors must be an integer observation-by-k array")
    if np.any(neighbors < 0) or np.any(neighbors >= count):
        raise ValueError("ranked neighbors must refer to existing observations")
    if np.any(neighbors == np.arange(count)[:, None]):
        raise ValueError("an observation cannot be its own ranked neighbor")
    if any(len(np.unique(row)) != len(row) for row in neighbors):
        raise ValueError("ranked neighbors must be unique per observation")
    k = neighbors.shape[1]
    matches = np.empty(count, dtype=np.int64)
    for start in range(0, count, 128):
        stop = min(start + 128, count)
        difference = coordinates[start:stop, None, :] - coordinates[None, :, :]
        distances = np.square(difference).sum(axis=2)
        distances[np.arange(stop - start), np.arange(start, stop)] = np.inf
        displayed = np.argsort(distances, axis=1, kind="stable")[:, :k]
        matches[start:stop] = (
            (displayed[:, :, None] == neighbors[start:stop, None, :]).any(axis=2).sum(axis=1)
        )
    return {
        "k": k,
        "mean_neighbor_recall": float(matches.mean() / k),
        "metric": "full-space top-k matches recovered among the nearest displayed points",
        "tie_rule": "source cache row order",
        "scope": "the emitted coordinates and this life-group/model sample only",
    }, matches
