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
