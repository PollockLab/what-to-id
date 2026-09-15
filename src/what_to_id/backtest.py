"""Offline backtest of queue orders on the needs-ID queue rebuilt at a past freeze.

Each order ranks the queue at T; the top k records are scored on what happened to them after T
(see `outcomes`). This replays iNaturalist's organic identification, not a blitz, so it says which
records an order puts first, not how many IDs the order would win. Random orders give the
reference band.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

FAST_DAYS = 30


def outcomes(q: pd.DataFrame) -> pd.DataFrame:
    """Per record, 0/1 columns: fast (research grade within FAST_DAYS of T), slow (later), stuck
    (still needs ID now), corrected (taxon now on another branch), coarsened (taxon now an
    ancestor of the taxon at T), misid (corrected or coarsened: the taxon at T did not hold),
    refined (now more precise)."""
    d = q["days_to_rg"]
    rel = q["relation"]
    return pd.DataFrame(
        {
            "fast": (d <= FAST_DAYS),
            "slow": (d > FAST_DAYS),
            "stuck": q["grade_now"] != "research",
            "corrected": rel == "corrected",
            "coarsened": rel == "coarsened",
            "misid": rel.isin(["corrected", "coarsened"]),
            "refined": rel == "refined",
        },
        index=q.index,
    ).astype(float)


def order_by(q: pd.DataFrame, col: str, ascending: bool = False) -> np.ndarray:
    """Positions sorted by `col` (NaN last), ties broken newest first."""
    created = pd.to_datetime(q["created_at"], utc=True).astype("int64")
    frame = pd.DataFrame({"v": q[col].to_numpy(), "c": -created.to_numpy()})
    return frame.sort_values(
        ["v", "c"], ascending=[ascending, True], na_position="last"
    ).index.to_numpy()


def base_orders(q: pd.DataFrame) -> dict[str, np.ndarray]:
    created = pd.to_datetime(q["created_at"], utc=True).astype("int64").to_numpy()
    return {
        "newest": np.argsort(-created, kind="stable"),
        "oldest": np.argsort(created, kind="stable"),
    }


def top_k(out: pd.DataFrame, order: np.ndarray, ks: Sequence[int]) -> pd.DataFrame:
    vals = out.to_numpy()[order]
    rows = {k: vals[: min(k, len(vals))].mean(0) for k in ks}
    return pd.DataFrame(rows, index=out.columns).T.rename_axis("k")


def random_band(
    out: pd.DataFrame, ks: Sequence[int], reps: int = 200, seed: int = 0
) -> pd.DataFrame:
    """Mean and 2.5/97.5 percentiles of each outcome share in the top k of random orders."""
    rng = np.random.default_rng(seed)
    draws = np.stack([top_k(out, rng.permutation(len(out)), ks).to_numpy() for _ in range(reps)])
    idx = pd.Index(ks, name="k")
    lo, mid, hi = (
        pd.DataFrame(np.percentile(draws, p, axis=0), idx, out.columns) for p in (2.5, 50, 97.5)
    )
    return pd.concat({"lo": lo, "mid": mid, "hi": hi}, axis=1)


def compare(q: pd.DataFrame, orders: dict[str, np.ndarray], ks: Sequence[int]) -> pd.DataFrame:
    """Long table: order, k, outcome, share; plus the random band's lo/hi for each k and outcome."""
    q = q.reset_index(drop=True)
    out = outcomes(q)
    band = random_band(out, ks)
    rows = []
    for name, order in orders.items():
        for k, r in top_k(out, order, ks).iterrows():
            for o, v in r.items():
                rows.append(
                    {
                        "order": name,
                        "k": k,
                        "outcome": o,
                        "share": v,
                        "rand_lo": band["lo"].at[k, o],
                        "rand_hi": band["hi"].at[k, o],
                    }
                )
    return pd.DataFrame(rows)
