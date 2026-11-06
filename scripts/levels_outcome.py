"""Do the Identify levels predict which records the crowd corrects? Writes the JSON terms.html
quotes.

    PYTHONPATH=src python scripts/levels_outcome.py --scores confusion-scores-A.parquet \\
        --pool-before pool-A.parquet --pool-after pool-B.parquet --scored-on 2026-10-15 \\
        --out src/what_to_id/terms_assets/levels_outcome.json

Cohort: the species-labelled records of pool A with a score (`own`, `other`), given their level
by the rules of `what_to_id.levels` (the look-alike count taken over the pool, as the Fir run
without BC counts). Outcome at pool B: "left" when the record is no longer Needs ID; "corrected"
when it is still there under another taxon that still exists in B (a taxon that vanished from B
is a swap, merge or split and is counted as neither). The rate ratio of corrected records in a
level against records in no level gets a percentile bootstrap interval. The inputs' sha256 go
into the JSON so a quoted number can be traced to the files that produced it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.levels import TAXONOMIST_MARGIN, WEIRD_SHARE, lookalike_known, species_masks

LEVELS = {0: "none", 1: "easy", 2: "taxonomist", 4: "weird", 5: "mislabel"}


def cohort(scores: Path, before: Path, after: Path) -> pd.DataFrame:
    s = pd.read_parquet(scores, columns=["id", "taxon_name", "own", "other", "other_name"])
    p = pd.read_parquet(before, columns=["id", "taxon_id", "rank", "iconic_taxon"])
    s = s.merge(p, on="id", how="inner", validate="one_to_one")
    s = s[(s["rank"] == "species") & s["own"].notna() & s["other"].notna()].reset_index(drop=True)
    s["margin"] = s["own"] - s["other"]
    s["top"] = s[["own", "other"]].max(axis=1)
    g = s["iconic_taxon"].fillna("")
    weird = s["top"] <= s.groupby(g)["top"].transform(lambda x: x.quantile(WEIRD_SHARE))
    easy, tax = species_masks(s, weird)
    mis = (s["margin"] < -TAXONOMIST_MARGIN) & lookalike_known(s) & ~weird
    s["level"] = np.select([weird, easy, tax, mis], [4, 1, 2, 5], 0)
    b = pd.read_parquet(after, columns=["id", "taxon_id"]).rename(columns={"taxon_id": "taxon_b"})
    s = s.merge(b, on="id", how="left", validate="one_to_one")
    s["left"] = s["taxon_b"].isna()
    changed = ~s["left"] & (s["taxon_b"] != s["taxon_id"])
    s["corrected"] = changed & s["taxon_id"].isin(set(b["taxon_b"].unique()))
    return s


def rate_ratio(x: np.ndarray, y: np.ndarray, rng, reps: int) -> tuple[float, list[float]]:
    est = x.mean() / y.mean()
    bs = [rng.choice(x, x.size).mean() / rng.choice(y, y.size).mean() for _ in range(reps)]
    return float(est), [float(v) for v in np.percentile(bs, [2.5, 97.5])]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, required=True)
    ap.add_argument("--pool-before", type=Path, required=True)
    ap.add_argument("--pool-after", type=Path, required=True)
    ap.add_argument("--scored-on", required=True, help="date of --scores and --pool-before")
    ap.add_argument("--outcome-on", required=True, help="date of --pool-after")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--reps", type=int, default=1000)
    a = ap.parse_args(argv)
    s = cohort(a.scores, a.pool_before, a.pool_after)
    rng = np.random.default_rng(a.seed)
    none = s.loc[s["level"] == 0, "corrected"].to_numpy()
    levels = {}
    for k, name in LEVELS.items():
        d = s[s["level"] == k]
        row = {
            "n": int(len(d)),
            "left_per_1000": round(1000 * float(d["left"].mean()), 2),
            "corrected_per_1000": round(1000 * float(d["corrected"].mean()), 2),
        }
        if k:
            rr, ci = rate_ratio(d["corrected"].to_numpy(), none, rng, a.reps)
            row["corrected_rr"], row["corrected_rr_ci"] = round(rr, 2), [round(v, 2) for v in ci]
        levels[name] = row
    out = {
        "script": "scripts/levels_outcome.py",
        "scored_on": a.scored_on,
        "outcome_on": a.outcome_on,
        "inputs": {
            n: {"name": p.name, "sha256": sha256(p)}
            for n, p in (
                ("scores", a.scores),
                ("pool_before", a.pool_before),
                ("pool_after", a.pool_after),
            )
        },
        "seed": a.seed,
        "bootstrap_reps": a.reps,
        "cohort": int(len(s)),
        "levels": levels,
    }
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["levels"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
