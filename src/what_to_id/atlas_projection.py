"""Measure a displayed layout against the model's actual ranked photo matches."""

from __future__ import annotations

import numpy as np

TSNE_VERSION = "1.9.1"


def display_projection(
    vectors: np.ndarray, pca_coordinates: np.ndarray, *, method: str = "pca"
) -> tuple[np.ndarray, dict]:
    """Fit a display layout without changing or normalizing source vectors.

    t-SNE uses the fixed configuration evaluated on the frozen atlas sample.
    Neither layout defines biological classes or changes full-space retrieval.
    Constant and effectively one-dimensional cohorts retain their linear layout.
    """
    vectors = np.asarray(vectors)
    pca_coordinates = np.asarray(pca_coordinates, dtype=np.float64)
    if method not in {"pca", "tsne"}:
        raise ValueError("projection method must be pca or tsne")
    if vectors.ndim != 2 or len(vectors) < 3 or vectors.shape[1] < 1 or vectors.dtype != np.float32:
        raise ValueError("projection vectors must be a float32 matrix with at least three rows")
    if not np.isfinite(vectors).all():
        raise ValueError("projection vectors must be finite")
    if pca_coordinates.shape != (len(vectors), 2) or not np.isfinite(pca_coordinates).all():
        raise ValueError("PCA coordinates must be a finite observation-by-two matrix")
    metadata = {
        "requested_method": "t-SNE" if method == "tsne" else "PCA",
        "method": "PCA",
        "fit_scope": "independently per life group and encoder",
        "display_only": True,
        "source_vectors_dtype": "float32",
        "source_vectors_renormalized": False,
        "parameters": {"n_components": 2},
        "sklearn_version": None,
        "fallback_reason": None,
        "interpretation": (
            "approximate photo layout; no species, ecology or identification inference"
        ),
    }
    if method == "pca":
        return pca_coordinates, metadata
    if vectors.shape[1] < 2:
        metadata["fallback_reason"] = "fewer than two source features"
    elif not np.any(vectors != vectors[0]):
        metadata["fallback_reason"] = "constant source vectors"
    elif (
        np.linalg.norm(pca_coordinates[:, 1])
        <= max(float(np.linalg.norm(pca_coordinates[:, 0])), 1.0) * 1e-10
    ):
        metadata["fallback_reason"] = "fewer than two varying PCA axes"
    if metadata["fallback_reason"] is not None:
        return pca_coordinates, metadata

    try:
        import sklearn
        from sklearn.manifold import TSNE
        from threadpoolctl import threadpool_limits
    except ImportError as error:
        raise RuntimeError(
            "t-SNE requires the optional atlas build dependencies. "
            "Install what-to-id[atlas], or install requirements.lock and requirements-atlas.lock."
        ) from error
    if sklearn.__version__ != TSNE_VERSION:
        raise RuntimeError(
            f"t-SNE requires scikit-learn=={TSNE_VERSION}; found {sklearn.__version__}. "
            "Install the pinned atlas build dependencies."
        )
    parameters = {
        "n_components": 2,
        "perplexity": min(30, len(vectors) - 1),
        "learning_rate": "auto",
        "early_exaggeration": 12,
        "max_iter": 1000,
        "metric": "euclidean",
        "init": "pca",
        "method": "barnes_hut",
        "angle": 0.5,
        "n_jobs": 1,
        "random_state": 0,
    }
    # Keep native BLAS/OpenMP execution aligned with the single-threaded experiment.
    with threadpool_limits(limits=1):
        coordinates = TSNE(**parameters).fit_transform(vectors)
    if coordinates.shape != pca_coordinates.shape or not np.isfinite(coordinates).all():
        raise ValueError("t-SNE produced an invalid display layout")
    metadata.update(
        method="t-SNE",
        parameters=parameters,
        sklearn_version=sklearn.__version__,
        native_thread_limit=1,
        small_sample_perplexity_adjusted=len(vectors) <= 30,
    )
    return coordinates, metadata


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
