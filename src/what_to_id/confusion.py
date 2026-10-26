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

A second, label-independent prototype is the BioCLIP text vector of "a photo of <species>"
that `atlas_taxa` already writes next to the atlas index. `text_own`, `text_other`,
`text_other_name` and `text_margin` are the same quantities against those vectors. They never
see the pool's proposals, so a species whose proposals are mostly wrong still gets a sound
prototype, and the runner can compute them without the raw photo vectors. On the BC Needs ID
bundle the text margin predicts identifier disagreement better than the image margin (AUROC
0.80 vs 0.76, same 58k rows), so when text vectors are given the pairs table comes from it.
A Research Grade photo sample as prototype source was tried and does not transfer (AUROC 0.39
on the 466 species it covers), and trimming or filtering the proposals changes nothing.

`fir_table` and the `fir` subcommand are the manual Fir job: they stream the memory-mapped bulk
embeddings in chunks, score text margins only, and write the per-species confused pairs table
(`confusion.parquet`) next to the atlas index, registered in its manifest for the page to fetch.
The same pass also yields `fir_records`, the worst negative-margin photos per species
(`confusion-records.parquet`), registered under its own manifest key.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from what_to_id.atlas_index_io import read_manifest, write_manifest

MIN_PER_CLASS = 4
CHUNK = 4096
COLUMNS = ("id", "taxon_id", "n_class", "own", "other", "other_taxon_id", "margin")
FIR_SLICE = 1 << 18  # rows of E read into memory at once on Fir (1 GB at 1024 floats)
FIR_PAIRS_PER_SPECIES = 3
FIR_RECORDS_PER_SPECIES = 50
RECORD_COLUMNS = (
    "id",
    "taxon_id",
    "taxon_name",
    "iconic_taxon",
    "looks_like_taxon_id",
    "looks_like_name",
    "margin",
    "photo_url",
)
TABLE_COLUMNS = (
    "taxon_id",
    "taxon_name",
    "looks_like_taxon_id",
    "looks_like_name",
    "n_photos",
    "n_species_photos",
    "share",
    "built_at",
)
TEXT_COLUMNS = ("text_own", "text_other", "text_other_name", "text_margin")


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


def text_scores(E: np.ndarray, names: pd.Series, taxa: pd.Series, T: np.ndarray):
    """Per row (own, other, other_name) against unit text vectors `T`, one per name in `taxa`.

    `names` are the rows' proposed species names. Only species names (two words) in `taxa` act
    as prototypes. A row whose name has no prototype gets NaN `own`; `other` is always the best
    cosine to any prototype but the row's own.
    """
    E = np.asarray(E, dtype=np.float32)
    is_species = taxa.str.split().str.len() == 2
    protos = np.asarray(T, dtype=np.float32)[np.flatnonzero(is_species.to_numpy())]
    proto_names = taxa[is_species].to_numpy()
    col = pd.Series(np.arange(len(proto_names)), index=proto_names)
    own_col = names.map(col).fillna(-1).astype(int).to_numpy()
    n = len(names)
    own = np.full(n, np.nan)
    other = np.full(n, np.nan)
    other_name = np.full(n, None, dtype=object)
    if n == 0 or len(proto_names) < 2:
        return own, other, other_name
    for s in range(0, n, CHUNK):
        X = E[s : s + CHUNK]
        sims = X @ protos.T
        ar = np.arange(len(X))
        oc = own_col[s : s + CHUNK]
        ok = oc >= 0
        own[s : s + CHUNK][ok] = sims[ar[ok], oc[ok]]
        sims[ar[ok], oc[ok]] = -np.inf
        best = sims.argmax(1)
        other[s : s + CHUNK] = sims[ar, best]
        other_name[s : s + CHUNK] = proto_names[best]
    return own, other, other_name


def confusion_scores(
    pool: pd.DataFrame,
    E: np.ndarray,
    ids: np.ndarray,
    min_per_class: int = MIN_PER_CLASS,
    taxa: pd.Series | None = None,
    T: np.ndarray | None = None,
) -> pd.DataFrame:
    """`COLUMNS` for the pool rows ranked at species that have an embedding row in `ids`,
    plus `TEXT_COLUMNS` when text prototypes (`taxa` names and their vectors `T`) are given."""
    p = pool.loc[pool["rank"] == "species", ["id", "taxon_id", "taxon_name"]].dropna()
    pos = pd.Series(np.arange(len(ids)), index=ids)
    p = p[p["id"].isin(pos.index)]
    rows = pos[p["id"].to_numpy()].to_numpy()
    labels = p["taxon_id"].to_numpy().astype(np.int64)
    n_class, own, other, other_label = prototype_scores(E[rows], labels, min_per_class)
    out = pd.DataFrame(
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
    if taxa is not None and T is not None:
        t_own, t_other, t_name = text_scores(E[rows], p["taxon_name"], taxa, T)
        out["text_own"], out["text_other"], out["text_other_name"] = t_own, t_other, t_name
        out["text_margin"] = t_own - t_other
    return out


def read_taxa_vectors(names_path: str | Path, vectors_path: str | Path):
    """(names, unit vectors) from the `taxa-<sha>.tsv.gz` and `taxa-<sha>.f16` atlas files."""
    with gzip.open(names_path, "rt") as f:
        names = pd.Series([line.split("\t")[0] for line in f.read().splitlines()])
    T = np.fromfile(vectors_path, dtype=np.float16).reshape(len(names), -1).astype(np.float32)
    return names, T / np.linalg.norm(T, axis=1, keepdims=True).clip(1e-12)


def confused_pairs(
    scores: pd.DataFrame, names: pd.Series, top: int = 20, text: bool = False
) -> pd.DataFrame:
    """The labelled-species / looks-like-species pairs with most negative-margin photos.

    `text=True` uses the text-prototype columns; `looks_like` is then a name, not a taxon id.
    """
    margin, other = ("text_margin", "text_other_name") if text else ("margin", "other_taxon_id")
    neg = scores[scores[margin] < 0]
    pairs = neg.groupby(["taxon_id", other]).size().rename("n").reset_index()
    pairs = pairs.sort_values("n", ascending=False).head(top)
    pairs["taxon"] = pairs["taxon_id"].map(names)
    pairs["looks_like"] = pairs[other] if text else pairs[other].map(names)
    return pairs[["taxon", "looks_like", "n", "taxon_id", other]].reset_index(drop=True)


def fir_scores(
    pool: pd.DataFrame, E: np.ndarray, ids: np.ndarray, taxa: pd.Series, T: np.ndarray
) -> pd.DataFrame:
    """Text-margin scores per species-ranked pool row that has an embedding row in `ids`.

    Columns: id, taxon_id, taxon_name, margin, other_name, plus `iconic_taxon` and `photo_url`
    when the pool has them. `E` may be a memory map: rows are read in `FIR_SLICE` slices in file
    order. Rows with no text prototype for their name have a NaN margin.
    """
    extra = [c for c in ("iconic_taxon", "photo_url") if c in pool.columns]
    p = pool.loc[pool["rank"] == "species", ["id", "taxon_id", "taxon_name", *extra]].dropna(
        subset=["id", "taxon_id", "taxon_name"]
    )
    p = p.assign(
        pos=pd.Series(np.arange(len(ids)), index=ids).reindex(p["id"].to_numpy()).to_numpy()
    )
    p = p.dropna(subset=["pos"]).sort_values("pos")
    parts = []
    for s in range(0, len(p), FIR_SLICE):
        q = p.iloc[s : s + FIR_SLICE]
        own, other, other_name = text_scores(
            E[q["pos"].to_numpy().astype(np.int64)], q["taxon_name"], taxa, T
        )
        parts.append(
            q.drop(columns="pos")
            .assign(
                taxon_id=q["taxon_id"].to_numpy().astype(np.int64),
                margin=own - other,
                other_name=other_name,
            )
            .reset_index(drop=True)
        )
    if not parts:
        return pd.DataFrame(
            {
                **{c: pd.Series(dtype=p[c].dtype) for c in p.columns if c != "pos"},
                "margin": pd.Series(dtype=float),
                "other_name": pd.Series(dtype=object),
            }
        ).astype({"taxon_id": np.int64})
    return pd.concat(parts, ignore_index=True)


def _negatives(scores: pd.DataFrame, min_photos: int):
    """(photos per species at or above `min_photos`, the negative-margin rows of those species)."""
    scores = scores[scores["margin"].notna()]
    n_species = scores.groupby("taxon_id").size().rename("n_species_photos")
    n_species = n_species[n_species >= min_photos]
    neg = scores[(scores["margin"] < 0) & scores["taxon_id"].isin(n_species.index)]
    return n_species, neg


def fir_table(scores: pd.DataFrame, built_at: str, min_photos: int = MIN_PER_CLASS) -> pd.DataFrame:
    """The confused pairs table (`TABLE_COLUMNS`) from `fir_scores`.

    A photo counts for a pair when its text margin is below zero; its pair partner is the nearest
    other species text prototype, the first in `taxa` order on an exact tie. Species with fewer
    than `min_photos` scored photos are dropped, and pairs with a single photo.
    """
    n_species, neg = _negatives(scores, min_photos)
    pairs = neg.groupby(["taxon_id", "other_name"]).size().rename("n_photos").reset_index()
    # shortcut: at most 3 pairs per species, 2+ photos each; raise if the page needs a longer tail.
    pairs = pairs[pairs["n_photos"] >= 2].sort_values(
        ["taxon_id", "n_photos", "other_name"], ascending=[True, False, True]
    )
    pairs = pairs.groupby("taxon_id").head(FIR_PAIRS_PER_SPECIES)
    out = pd.DataFrame(
        {
            "taxon_id": pairs["taxon_id"].to_numpy(),
            "taxon_name": pairs["taxon_id"].map(_species_names(scores)).to_numpy(),
            "looks_like_taxon_id": _looks_like_ids(scores, pairs["other_name"]),
            "looks_like_name": pairs["other_name"].to_numpy(),
            "n_photos": pairs["n_photos"].to_numpy(),
            "n_species_photos": pairs["taxon_id"].map(n_species).to_numpy(),
        }
    )
    out["share"] = out["n_photos"] / out["n_species_photos"]
    out["built_at"] = built_at
    return out[list(TABLE_COLUMNS)].reset_index(drop=True)


def _species_names(scores: pd.DataFrame) -> pd.Series:
    return scores.drop_duplicates("taxon_id").set_index("taxon_id")["taxon_name"]


def _looks_like_ids(scores: pd.DataFrame, names: pd.Series):
    """Pool taxon id of each looks-like name when it is a pool species, else null."""
    by_name = scores.drop_duplicates("taxon_name").set_index("taxon_name")["taxon_id"]
    return names.map(by_name).astype("Int64").array


def fir_records(
    scores: pd.DataFrame, min_photos: int = MIN_PER_CLASS, cap: int = FIR_RECORDS_PER_SPECIES
) -> pd.DataFrame:
    """The worst photos per species (`RECORD_COLUMNS`) from `fir_scores`.

    One row per negative-margin photo of a species with at least `min_photos` scored photos,
    the `cap` most negative per species, sorted by (taxon_id, margin, id).
    """
    for c in ("iconic_taxon", "photo_url"):
        if c not in scores.columns:
            raise ValueError(f"pool has no {c!r} column, needed for the records table")
    _, neg = _negatives(scores, min_photos)
    neg = neg.sort_values(["taxon_id", "margin", "id"]).groupby("taxon_id").head(cap)
    out = pd.DataFrame(
        {
            "id": neg["id"].to_numpy(),
            "taxon_id": neg["taxon_id"].to_numpy(),
            "taxon_name": neg["taxon_name"].to_numpy(),
            "iconic_taxon": neg["iconic_taxon"].to_numpy(),
            "looks_like_taxon_id": _looks_like_ids(scores, neg["other_name"]),
            "looks_like_name": neg["other_name"].to_numpy(),
            "margin": neg["margin"].to_numpy().astype(np.float32),
            "photo_url": neg["photo_url"].to_numpy(),
        }
    )
    return out[list(RECORD_COLUMNS)].reset_index(drop=True)


def fir_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="confusion fir", description="Write confusion.parquet")
    ap.add_argument("--emb", required=True, help="E.npy, float32 (n x d), memory-mapped")
    ap.add_argument("--ids", required=True, help="ids.npy, int64 observation ids, rows of E")
    ap.add_argument(
        "--pool", required=True, help="pool parquet with id, taxon_id, taxon_name, rank"
    )
    ap.add_argument("--taxa-names", required=True, help="atlas taxa-<sha>.tsv.gz")
    ap.add_argument("--taxa-vectors", required=True, help="atlas taxa-<sha>.f16")
    ap.add_argument("--atlas-dir", required=True, help="atlas index dir holding manifest.json")
    args = ap.parse_args(argv)
    manifest = read_manifest(args.atlas_dir)
    cols = ["id", "taxon_id", "taxon_name", "rank", "iconic_taxon", "photo_url"]
    missing = [c for c in cols if c not in pq.read_schema(args.pool).names]
    if missing:
        raise ValueError(f"pool {args.pool} has no column {missing[0]!r}")
    pool = pd.read_parquet(args.pool, columns=cols)
    taxa, T = read_taxa_vectors(args.taxa_names, args.taxa_vectors)
    E = np.load(args.emb, mmap_mode="r")
    built_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    scores = fir_scores(pool, E, np.load(args.ids), taxa, T)
    out, records = fir_table(scores, built_at), fir_records(scores)
    atlas = Path(args.atlas_dir)
    out.to_parquet(atlas / "confusion.parquet", index=False)
    records.to_parquet(atlas / "confusion-records.parquet", index=False)
    manifest["confusion"] = {"name": "confusion.parquet", "built_at": built_at, "count": len(out)}
    manifest["confusion_records"] = {
        "name": "confusion-records.parquet",
        "built_at": built_at,
        "count": len(records),
    }
    write_manifest(args.atlas_dir, manifest)
    print(f"{len(out)} pairs for {out['taxon_id'].nunique()} species")
    print(f"{len(records)} records for {records['taxon_id'].nunique()} species")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["fir"]:
        return fir_main(argv[1:])
    ap = argparse.ArgumentParser(description="Label confusion scores (prototype margin) for a pool")
    ap.add_argument("pool", help="pool parquet with id, taxon_id, rank")
    ap.add_argument("--emb", required=True, nargs="+", help="embeddings npz files (ids, E)")
    ap.add_argument("--out", required=True, help="output parquet")
    ap.add_argument("--min-per-class", type=int, default=MIN_PER_CLASS)
    ap.add_argument("--taxa-names", help="atlas taxa-<sha>.tsv.gz (text prototypes)")
    ap.add_argument("--taxa-vectors", help="atlas taxa-<sha>.f16, same rows as --taxa-names")
    args = ap.parse_args(argv)
    if bool(args.taxa_names) != bool(args.taxa_vectors):
        ap.error("--taxa-names and --taxa-vectors go together")
    pool = pd.read_parquet(args.pool, columns=["id", "taxon_id", "taxon_name", "rank"])
    taxa, T = (
        read_taxa_vectors(args.taxa_names, args.taxa_vectors) if args.taxa_names else (None, None)
    )
    parts = []
    for f in args.emb:
        z = np.load(f)
        parts.append(confusion_scores(pool, z["E"], z["ids"], args.min_per_class, taxa, T))
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
    if taxa is not None:
        print(f"\n{int((out['text_margin'] < 0).sum())} closer to another species' text prototype")
        print(confused_pairs(out, names, text=True).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
