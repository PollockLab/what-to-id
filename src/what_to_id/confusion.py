"""Label confusion: how much a photo looks like its proposed species, against the closest other.

Each species with at least `MIN_PER_CLASS` photos gets a prototype, the unit-normed mean of its
photos' BioCLIP embeddings. A photo's `own` is its cosine to its own species prototype computed
without the photo (leave one out, so a species of four photos does not vouch for itself).
`other` is its best cosine to any other species prototype, and `other_taxon_id` names that
species. `margin = own - other`: below zero the photo sits closer to another species than to the
one it is labelled with. The margin ranks photos for a human to look at and never marks a label
as wrong: sister species share most of their embedding, so true labels on cryptic pairs also
score low.

This is the leave-one-out centroid score LabelFirst uses to grade open-set separability
(`labelfirst.eval.diagnose.osr`), applied per photo instead of aggregated to an AUROC.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

MIN_PER_CLASS = 4
CHUNK = 4096
COLUMNS = ("id", "taxon_id", "n_class", "own", "other", "other_taxon_id", "margin")


def prototype_scores(E: np.ndarray, labels: np.ndarray, min_per_class: int = MIN_PER_CLASS):
    """Per row (n_class, own, other, other_label) for unit-row `E` and integer `labels`.

    Rows whose label has fewer than `min_per_class` rows get n_class = that count and NaN scores.
    """
    if min_per_class < 2:
        raise ValueError("min_per_class must be at least 2 for a leave-one-out prototype")
    E = np.asarray(E, dtype=np.float32)
    labels = np.asarray(labels)
    n = len(labels)
    own = np.full(n, np.nan)
    other = np.full(n, np.nan)
    other_label = np.full(n, -1, dtype=np.int64)
    if n == 0:
        return np.zeros(0, dtype=np.int64), own, other, other_label
    classes, inv, counts = np.unique(labels, return_inverse=True, return_counts=True)
    n_class = counts[inv]
    keep = counts >= min_per_class
    if not keep.any():
        return n_class, own, other, other_label
    sums = np.zeros((len(classes), E.shape[1]), dtype=np.float64)
    np.add.at(sums, inv, E)
    protos = sums[keep] / np.linalg.norm(sums[keep], axis=1, keepdims=True).clip(1e-12)
    proto_class = classes[keep]
    proto_col = np.full(len(classes), -1)
    proto_col[keep] = np.arange(keep.sum())
    rows = np.flatnonzero(keep[inv])
    for s in range(0, len(rows), CHUNK):
        r = rows[s : s + CHUNK]
        X = E[r]
        loo = sums[inv[r]] - X
        loo /= np.linalg.norm(loo, axis=1, keepdims=True).clip(1e-12)
        own[r] = (X * loo).sum(1)
        sims = X @ protos.T.astype(np.float32)
        sims[np.arange(len(r)), proto_col[inv[r]]] = -np.inf
        best = sims.argmax(1)
        other[r] = sims[np.arange(len(r)), best]
        other_label[r] = proto_class[best]
    # A lone prototype has no "other" species to compare with.
    other[np.isinf(other)] = np.nan
    other_label[np.isnan(other)] = -1
    return n_class, own, other, other_label


def confusion_scores(
    pool: pd.DataFrame, E: np.ndarray, ids: np.ndarray, min_per_class: int = MIN_PER_CLASS
) -> pd.DataFrame:
    """`COLUMNS` for the pool rows ranked at species that have an embedding row in `ids`."""
    p = pool.loc[pool["rank"] == "species", ["id", "taxon_id"]].dropna()
    pos = pd.Series(np.arange(len(ids)), index=ids)
    p = p[p["id"].isin(pos.index)]
    rows = pos[p["id"].to_numpy()].to_numpy()
    labels = p["taxon_id"].to_numpy().astype(np.int64)
    n_class, own, other, other_label = prototype_scores(E[rows], labels, min_per_class)
    return pd.DataFrame(
        {
            "id": p["id"].to_numpy(),
            "taxon_id": labels,
            "n_class": n_class,
            "own": own,
            "other": other,
            "other_taxon_id": other_label,
            "margin": own - other,
        }
    )


def confused_pairs(scores: pd.DataFrame, names: pd.Series, top: int = 20) -> pd.DataFrame:
    """The labelled-species / looks-like-species pairs with most negative-margin photos."""
    neg = scores[scores["margin"] < 0]
    pairs = neg.groupby(["taxon_id", "other_taxon_id"]).size().rename("n").reset_index()
    pairs = pairs.sort_values("n", ascending=False).head(top)
    pairs["taxon"] = pairs["taxon_id"].map(names)
    pairs["looks_like"] = pairs["other_taxon_id"].map(names)
    return pairs[["taxon", "looks_like", "n", "taxon_id", "other_taxon_id"]].reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Label confusion scores (prototype margin) for a pool")
    ap.add_argument("pool", help="pool parquet with id, taxon_id, rank")
    ap.add_argument("--emb", required=True, nargs="+", help="embeddings npz files (ids, E)")
    ap.add_argument("--out", required=True, help="output parquet")
    ap.add_argument("--min-per-class", type=int, default=MIN_PER_CLASS)
    args = ap.parse_args(argv)
    pool = pd.read_parquet(args.pool, columns=["id", "taxon_id", "taxon_name", "rank"])
    parts = []
    for f in args.emb:
        z = np.load(f)
        parts.append(confusion_scores(pool, z["E"], z["ids"], args.min_per_class))
    out = pd.concat(parts, ignore_index=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    scored = out["margin"].notna()
    print(
        f"{len(out)} species-ranked rows, {int(scored.sum())} scored, "
        f"{int((out['margin'] < 0).sum())} closer to another species"
    )
    names = pool.drop_duplicates("taxon_id").set_index("taxon_id")["taxon_name"]
    print(confused_pairs(out, names).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
