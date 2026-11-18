"""Fit the temperature of Narrow it down's At risk weighting by maximum likelihood.

The page weights a record's runner-up species 1 / (1 + exp(margin / TEMP)), the margin being the
cosine score of the suggestion minus the runner-up's (`score2`). Among Narrow it down records
(level 3 of identify-why.parquet) that later resolved to the suggestion or the runner-up, this
fits TEMP to "the runner-up was the later species" and compares its log loss with the page's
TEMP. The later species is that of the pool taken after (`--pool-after`, records still Needs ID
at species rank) or, for records that left it, the taxon on the day of `scripts/fetch_taxa_now.py`
(`--leaver-taxa`, a species name of two words). Records resolved to any other species or to a
rank above species are left out. The interval resamples observers (`cluster_bootstrap`).

    PYTHONPATH=src python scripts/narrow_temp.py --why identify-why.parquet \\
        --pool-after pool.parquet --leaver-taxa now.parquet --scored-on 2026-10-15 \\
        --outcome-on 2026-11-17 --out narrow_temp.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from what_to_id.cluster_bootstrap import observer_codes

PAGE_TEMP = 0.02  # identify_www.js
LEVEL_NARROW = 3
MIN_REPS = 1000
BOUNDS = (np.log(1e-4), np.log(1.0))  # the temperature, in cosine units, searched on a log scale


def log_loss(margin: np.ndarray, y: np.ndarray, temp: float, w: np.ndarray | None = None) -> float:
    """Mean negative log likelihood of y (the runner-up won) at weight 1 / (1 + exp(margin / T))."""
    z = margin / temp
    ll = -np.logaddexp(0, z) * y - np.logaddexp(0, -z) * (1 - y)  # log p(y), p = sigmoid(-z)
    return float(-np.average(ll, weights=w))


def fit_temp(margin: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> float:
    r = minimize_scalar(
        lambda u: log_loss(margin, y, float(np.exp(u)), w), bounds=BOUNDS, method="bounded"
    )
    return float(np.exp(r.x))


def bootstrap(margin, y, obs, reps: int, seed: int) -> list[float]:
    """Observer-clustered 95% percentile interval of the fitted temperature."""
    if reps < MIN_REPS:
        raise ValueError(f"reps must be at least {MIN_REPS}, got {reps}")
    m = int(obs.max()) + 1
    rng = np.random.default_rng(seed)
    fits = []
    for _ in range(reps):
        w = rng.multinomial(m, np.full(m, 1 / m))[obs].astype(float)
        fits.append(fit_temp(margin, y, w) if w.sum() else np.nan)
    return [float(v) for v in np.nanpercentile(fits, [2.5, 97.5])]


def resolved(why: Path, pool_after: Path, leaver_taxa: Path) -> pd.DataFrame:
    """Level-3 records that later were the suggestion (y 0) or the runner-up (y 1)."""
    d = pd.read_parquet(why, columns=["id", "level", "looks_like", "runner_up", "score2"])
    d = d[(d["level"] == LEVEL_NARROW) & d["runner_up"].notna() & d["score2"].notna()]
    p = pd.read_parquet(pool_after, columns=["id", "taxon_name", "rank", "user_id"])
    p = p[p["rank"] == "species"][["id", "taxon_name", "user_id"]]
    n = pd.read_parquet(leaver_taxa, columns=["id", "taxon_name", "user_id"]).dropna(
        subset=["taxon_name"]
    )
    n = n[n["taxon_name"].str.count(" ") == 1]  # a species, not a subspecies or a genus
    later = pd.concat([p, n[~n["id"].isin(p["id"])]]).drop_duplicates("id")
    d = d.merge(later, on="id", how="inner", validate="one_to_one")
    d["y"] = (d["taxon_name"] == d["runner_up"]).astype(float)
    return d[(d["taxon_name"] == d["looks_like"]) | (d["y"] == 1)].reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--why", type=Path, required=True)
    ap.add_argument("--pool-after", type=Path, required=True)
    ap.add_argument("--leaver-taxa", type=Path, required=True)
    ap.add_argument("--scored-on", required=True)
    ap.add_argument("--outcome-on", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--reps", type=int, default=1000)
    a = ap.parse_args(argv)
    d = resolved(a.why, a.pool_after, a.leaver_taxa)
    margin, y = d["score2"].to_numpy(float), d["y"].to_numpy()
    t = fit_temp(margin, y)
    ci = bootstrap(margin, y, observer_codes(d["user_id"]), a.reps, a.seed)
    out = {
        "script": "scripts/narrow_temp.py",
        "scored_on": a.scored_on,
        "outcome_on": a.outcome_on,
        "inputs": {
            n: {"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for n, p in (
                ("why", a.why),
                ("pool_after", a.pool_after),
                ("leaver_taxa", a.leaver_taxa),
            )
        },
        "seed": a.seed,
        "bootstrap_reps": a.reps,
        "resolved": int(len(d)),
        "runner_up_later": int(y.sum()),
        "observers": int(d["user_id"].nunique()),
        "temp": round(t, 4),
        "temp_ci": [round(v, 4) for v in ci],
        "page_temp": PAGE_TEMP,
        "log_loss": round(log_loss(margin, y, t), 4),
        "log_loss_page_temp": round(log_loss(margin, y, PAGE_TEMP), 4),
        "log_loss_even": round(log_loss(margin, y, 1e6), 4),
    }
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
