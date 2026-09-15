"""Surprise: how unexpected a record's proposed taxon is where, and in what climate, it was seen.

A record's score is an empirical tail probability against its taxon's reference records
(research grade, observed before the freeze): the share of reference records that sit in a denser
part of the taxon's own cloud than the record does. 1 means the record is less typical than every
reference record. A taxon with fewer than `MIN_REF` references scores 1, because it is close to
unknown in the region. Density is a Gaussian kernel sum, in km for geography and in standardized
units for climate, leaving each reference point out of its own density.

This is the kernel form of the per-taxon environmental outlier tests used for occurrence
cleaning (reverse jackknife, occTest's environmental block); it ranks records for a human to
look at and never marks one as wrong.
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

MIN_REF = 5
MAX_REF = 1500
CHUNK = 2000
SPECIES, GENUS = 10, 20


def to_km(lat: np.ndarray, lon: np.ndarray, lat0: float = 54.0) -> np.ndarray:
    """Equirectangular km around `lat0`. Error under 5% in the BC box, fine for a 25 km kernel."""
    return np.column_stack([lon * 111.32 * math.cos(math.radians(lat0)), lat * 110.57])


def _density(ref: np.ndarray, q: np.ndarray, h: float) -> np.ndarray:
    out = np.empty(len(q))
    for s in range(0, len(q), CHUNK):
        d2 = ((q[s : s + CHUNK, None, :] - ref[None, :, :]) ** 2).sum(-1)
        out[s : s + CHUNK] = np.exp(-d2 / (2 * h * h)).sum(1)
    return out


def tail_prob(ref: np.ndarray, q: np.ndarray, h: float, seed: int = 0) -> np.ndarray:
    """Share of `ref` points whose leave-one-out density beats each query point's density."""
    ref = ref[~np.isnan(ref).any(1)]
    if len(ref) < MIN_REF:
        return np.ones(len(q))
    if len(ref) > MAX_REF:
        ref = ref[np.random.default_rng(seed).choice(len(ref), MAX_REF, replace=False)]
    n = len(ref)
    d_ref = np.sort((_density(ref, ref, h) - 1.0) * n / (n - 1))
    d_q = _density(ref, q, h)
    out = (n - np.searchsorted(d_ref, d_q, side="right")) / n
    out[np.isnan(q).any(1)] = np.nan
    return out


def taxon_key(lineage: Sequence[int], rank_level: Mapping[int, float]) -> int | None:
    """The species in `lineage` (a subspecies climbs to it), else the genus, else None."""
    for want in (SPECIES, GENUS):
        for t in reversed(lineage):
            if rank_level.get(t) == want:
                return t
    return None


def score(
    pool: pd.DataFrame,
    ref: pd.DataFrame,
    cols: Sequence[str],
    h: float,
    key: str = "key",
    seed: int = 0,
) -> pd.Series:
    """Tail probability of each pool row against the reference rows with the same `key`.

    `ref` may list a record under several keys (its species and its genus). Rows of `pool` with
    no key score NaN.
    """
    out = pd.Series(np.nan, index=pool.index)
    groups = dict(tuple(ref.groupby(key)))
    empty = np.empty((0, len(cols)))
    for k, rows in pool[pool[key].notna()].groupby(key):
        r = groups[k][list(cols)].to_numpy(float) if k in groups else empty
        out[rows.index] = tail_prob(r, rows[list(cols)].to_numpy(float), h, seed)
    return out


REF_COLS = ["latitude", "longitude", "positional_accuracy", "taxon_id", "quality_grade"]
REF_COLS += ["observed_on"]


def geo_scores(
    pool: pd.DataFrame, ref: pd.DataFrame, taxa: pd.DataFrame, before: str, h: float = 25.0
) -> pd.DataFrame:
    """Geo surprise of each pool record's taxon (`id`, `lat`, `lon`, `taxon_id`) against
    iNat Open Data rows (`REF_COLS`) that are research grade, observed before `before` and placed
    within 2 km. A reference row counts for its species and for its genus. `n_ref` is how many of
    those reference rows carry the record's own key: 0 when the key has none, NaN when the record
    has no key."""
    rl = dict(zip(taxa.taxon_id, taxa.rank_level, strict=True))
    anc = dict(zip(taxa.taxon_id, taxa.ancestry, strict=True))

    def lin(t: int) -> tuple[int, ...]:
        a = anc.get(t)
        return (tuple(int(x) for x in a.split("/")) if isinstance(a, str) else ()) + (t,)

    def at(t: int, want: int) -> int | None:
        return next((x for x in reversed(lin(t)) if rl.get(x) == want), None)

    tid = pd.to_numeric(pool["taxon_id"], errors="coerce")
    p = pd.DataFrame({"id": pool["id"].to_numpy(), "lat": pool["lat"], "lon": pool["lon"]})
    p["key"] = [taxon_key(lin(int(t)), rl) if pd.notna(t) else None for t in tid]
    r = ref[
        (ref.quality_grade == "research")
        & (ref.observed_on < before)
        & (ref.positional_accuracy.isna() | (ref.positional_accuracy <= 2000))
    ]
    ut = r.taxon_id.dropna().astype(int).unique()
    sp, ge = {t: at(t, SPECIES) for t in ut}, {t: at(t, GENUS) for t in ut}
    long = pd.concat([r.assign(key=r.taxon_id.map(sp)), r.assign(key=r.taxon_id.map(ge))])
    long = long[long.key.isin(set(p.key.dropna()))]
    for d, la, lo in ((p, "lat", "lon"), (long, "latitude", "longitude")):
        xy = to_km(d[la].to_numpy(float), d[lo].to_numpy(float))
        d["x"], d["y"] = xy[:, 0], xy[:, 1]
    p["surprise"] = score(p, long, ["x", "y"], h=h)
    n_ref = p["key"].map(long.groupby("key").size())
    p["n_ref"] = np.where(p["key"].isna(), np.nan, n_ref.fillna(0.0))
    return p[["id", "surprise", "n_ref"]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Geo surprise scores for a pool (--surprise-scores)")
    ap.add_argument("pool", help="pool parquet with id, lat, lon, taxon_id")
    ap.add_argument("--ref", required=True, help="iNat Open Data observations (tsv, may be .gz)")
    ap.add_argument("--taxa", required=True, help="iNat Open Data taxa.csv.gz")
    ap.add_argument("--before", required=True, help="only references observed before YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    pool = pd.read_parquet(a.pool)
    ref = pd.read_csv(a.ref, sep="\t", usecols=REF_COLS)
    taxa = pd.read_csv(a.taxa, sep="\t", usecols=["taxon_id", "ancestry", "rank_level"])
    s = geo_scores(pool, ref, taxa, a.before)
    s.to_parquet(a.out, index=False)
    print(
        f"{len(s)} records, {int(s.surprise.notna().sum())} scored, {(s.surprise == 1).sum()} at 1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
