"""Per-batch signals recorded for every set alike: cohesion and novelty.

These are information, not gates. Cohesion is the mean cosine similarity of a batch's embedded
members to the batch's unit-normed centroid (1.0 means every photo looks the same to the model).
Novelty is the mean cosine distance of the members to their nearest Research Grade reference
embedding of the same group, the same quantity the novelty arm sorts on. Both are written into
the manifest for every batch so the read-back can test, across sets, whether tight batches or
unfamiliar batches get more species-level identifications.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.arms import Novelty, _align, _EmbeddingStore

COLUMNS = ("batch_id", "n_embedded", "cohesion", "novelty")


def cohesion(X: np.ndarray) -> float:
    """Mean cosine of unit rows to their unit-normed centroid; NaN with fewer than two rows."""
    if X.shape[0] < 2:
        return float("nan")
    c = X.mean(axis=0)
    norm = float(np.linalg.norm(c))
    if norm < 1e-12:
        return 0.0
    return float((X @ (c / norm)).mean())


def batch_signals(
    batches: pd.DataFrame,
    embeddings: Mapping[str, Path] | Path | str,
    reference: Mapping[str, Path] | Path | str | None = None,
    *,
    chunk: int = 4096,
) -> pd.DataFrame:
    """One row per batch_id with n_embedded, cohesion and novelty (NaN when not computable)."""
    required = {"batch_id", "group", "id"}
    if not required <= set(batches.columns):
        raise ValueError(f"batches frame needs columns {sorted(required)}")
    store = _EmbeddingStore(embeddings)
    ref_store = _EmbeddingStore(reference) if reference is not None else None
    nov = Novelty(embeddings, reference if reference is not None else {}, chunk=chunk)
    rows = []
    for group, gdf in batches.groupby("group", sort=True):
        emb_ids, E = store.lookup(str(group))
        R = ref_store.lookup(str(group))[1] if ref_store is not None else np.empty((0, 0))
        pos_in_emb, _, _ = _align(gdf, emb_ids)
        for bid, idx in gdf.groupby("batch_id", sort=False).indices.items():
            rows_in_emb = pos_in_emb[idx]
            rows_in_emb = rows_in_emb[rows_in_emb >= 0]
            X = (
                E[rows_in_emb]
                if rows_in_emb.size
                else np.empty((0, E.shape[1] if E.ndim == 2 else 0))
            )
            novelty = float("nan")
            if X.shape[0] and R.size:
                novelty = float(nov.distances(X, R).mean())
            rows.append(
                {
                    "batch_id": bid,
                    "n_embedded": int(X.shape[0]),
                    "cohesion": cohesion(X),
                    "novelty": novelty,
                }
            )
    out = pd.DataFrame(rows, columns=list(COLUMNS))
    return out.astype({"n_embedded": "int64", "cohesion": "float64", "novelty": "float64"})


def signals_by_batch(df: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    """Manifest-ready mapping batch_id -> {n_embedded, cohesion, novelty}; NaN becomes None."""
    out: dict[str, dict[str, float | int | None]] = {}
    for r in df.itertuples(index=False):
        out[str(r.batch_id)] = {
            "n_embedded": int(r.n_embedded),
            "cohesion": None if np.isnan(r.cohesion) else round(float(r.cohesion), 4),
            "novelty": None if np.isnan(r.novelty) else round(float(r.novelty), 4),
        }
    return out
