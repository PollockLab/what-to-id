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
into the JSON so a quoted number can be traced to the files that produced it. The JSON also
holds the figure data (margin histogram per level, corrected share per margin bin) and the AUC of
the page order against plain orderings; `--cohort-out` writes the scored cohort for others to run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.levels import TAXONOMIST_MARGIN, WEIRD_SHARE, lookalike_known, species_masks
from what_to_id.pool_levels import STEPS, quantize

LEVELS = {0: "none", 1: "easy", 2: "taxonomist", 4: "weird", 5: "mislabel"}
# the Identify page shows Might be mislabelled first, then Odd shots, then Close calls; Clear
# matches sit in their own list after everything else
PAGE_PRIORITY = {5: 4, 4: 3, 2: 2, 0: 1, 1: 0}
MARGIN_EDGES = np.round(np.arange(-0.15, 0.1501, 0.005), 3)
CALIBRATION_BINS = 20
COHORT_COLUMNS = [
    *("id", "taxon_id", "taxon_name", "iconic_taxon", "own", "other", "other_name", "margin"),
    *("level", "left", "corrected", "name_b", "to_suggested", "to_suggested_genus"),
]


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
    b = pd.read_parquet(after, columns=["id", "taxon_id", "taxon_name"]).rename(
        columns={"taxon_id": "taxon_b", "taxon_name": "name_b"}
    )
    s = s.merge(b, on="id", how="left", validate="one_to_one")
    s["left"] = s["taxon_b"].isna()
    changed = ~s["left"] & (s["taxon_b"] != s["taxon_id"])
    s["corrected"] = changed & s["taxon_id"].isin(set(b["taxon_b"].unique()))
    # where a corrected record went: the suggested species itself, or its genus

    def genus(n: pd.Series) -> pd.Series:
        return n.str.split(" ").str[0]

    s["to_suggested"] = s["corrected"] & (s["name_b"] == s["other_name"])
    s["to_suggested_genus"] = s["corrected"] & (genus(s["name_b"]) == genus(s["other_name"]))
    return s


def rate_ratio(x: np.ndarray, y: np.ndarray, rng, reps: int) -> tuple[float, list[float]]:
    est = x.mean() / y.mean()
    bs = [rng.choice(x, x.size).mean() / rng.choice(y, y.size).mean() for _ in range(reps)]
    return float(est), [float(v) for v in np.percentile(bs, [2.5, 97.5])]


def auc(score: np.ndarray, y: np.ndarray, rng, reps: int) -> tuple[float, list[float]]:
    """P(a corrected record scores above an uncorrected one), ties half, bootstrap on both."""
    pos, neg = np.sort(score[y]), np.sort(score[~y])

    def one(p: np.ndarray, w: np.ndarray) -> float:
        cw = np.concatenate([[0], np.cumsum(w)])
        lo, hi = cw[np.searchsorted(neg, p, "left")], cw[np.searchsorted(neg, p, "right")]
        return float(np.mean((lo + hi) / 2) / cw[-1])

    est = one(pos, np.ones(len(neg)))
    uniform = np.full(len(neg), 1 / len(neg))
    bs = [one(rng.choice(pos, pos.size), rng.multinomial(len(neg), uniform)) for _ in range(reps)]
    return est, [float(v) for v in np.percentile(bs, [2.5, 97.5])]


def orderings(s: pd.DataFrame) -> dict[str, np.ndarray]:
    """Name -> score where a higher value is shown earlier."""
    level = s["level"].to_numpy()
    shown = np.select(
        [level == 4, level == 1], [s["top"], s["own"]], s["margin"]
    )  # what identify.py stores as `score` per level
    page = np.vectorize(PAGE_PRIORITY.get)(level) * STEPS + quantize(level, shown)
    return {
        "page": page.astype(np.float64),
        "margin_lowest_first": -s["margin"].to_numpy(),
        "own_lowest_first": -s["own"].to_numpy(),
        "top_lowest_first": -s["top"].to_numpy(),
    }


def figures(s: pd.DataFrame) -> dict:
    m = s["margin"].to_numpy()
    hist = {
        name: np.histogram(np.clip(m[s["level"] == k], *MARGIN_EDGES[[0, -1]]), MARGIN_EDGES)[0]
        .astype(int)
        .tolist()
        for k, name in LEVELS.items()
    }
    q = np.quantile(m, np.linspace(0, 1, CALIBRATION_BINS + 1))
    q[0], q[-1] = -np.inf, np.inf
    b = np.clip(np.searchsorted(q, m, "right") - 1, 0, CALIBRATION_BINS - 1)
    rate = s["corrected"].groupby(b).mean().reindex(range(CALIBRATION_BINS), fill_value=0)
    n = pd.Series(b).value_counts().reindex(range(CALIBRATION_BINS), fill_value=0)
    return {
        "margin_hist": {"edges": MARGIN_EDGES.tolist(), "counts": hist},
        "corrected_by_margin": {
            "edges": [float(v) for v in np.quantile(m, np.linspace(0, 1, CALIBRATION_BINS + 1))],
            "n": n.astype(int).tolist(),
            "corrected_per_1000": [round(1000 * float(v), 2) for v in rate],
        },
    }


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
    ap.add_argument("--cohort-out", type=Path, help="write the scored cohort as parquet")
    a = ap.parse_args(argv)
    s = cohort(a.scores, a.pool_before, a.pool_after)
    if a.cohort_out:
        s[COHORT_COLUMNS].to_parquet(a.cohort_out, index=False)
    rng = np.random.default_rng(a.seed)
    none = s.loc[s["level"] == 0, "corrected"].to_numpy()
    none_c = s[(s["level"] == 0) & s["corrected"]]
    levels = {}
    for k, name in LEVELS.items():
        d = s[s["level"] == k]
        row = {
            "n": int(len(d)),
            "left_per_1000": round(1000 * float(d["left"].mean()), 2),
            "corrected_per_1000": round(1000 * float(d["corrected"].mean()), 2),
        }
        c = d[d["corrected"]]
        for col in ("to_suggested", "to_suggested_genus"):
            row[f"{col}_share"] = round(float(c[col].mean()), 3) if len(c) else None
        if k:
            rr, ci = rate_ratio(d["corrected"].to_numpy(), none, rng, a.reps)
            row["corrected_rr"], row["corrected_rr_ci"] = round(rr, 2), [round(v, 2) for v in ci]
            for col in ("to_suggested", "to_suggested_genus"):
                rr, ci = rate_ratio(c[col].to_numpy(), none_c[col].to_numpy(), rng, a.reps)
                row[f"{col}_rr"], row[f"{col}_rr_ci"] = round(rr, 2), [round(v, 2) for v in ci]
        levels[name] = row
    base = {}
    shown = s["level"].isin([2, 4, 5]).to_numpy()  # the records the Might be wrong list holds
    for name, score in orderings(s).items():
        for suffix, rows in (("", np.ones(len(s), bool)), ("_shown", shown)):
            est, ci = auc(score[rows], s["corrected"].to_numpy()[rows], rng, a.reps)
            base[name + suffix] = {"auc": round(est, 3), "auc_ci": [round(v, 3) for v in ci]}
    close = s[s["level"] == 2]
    est, ci = auc(-close["margin"].to_numpy(), close["corrected"].to_numpy(), rng, a.reps)
    base["close_calls_lowest_margin_first"] = {
        "auc": round(est, 3),
        "auc_ci": [round(v, 3) for v in ci],
    }
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
        "cohort_file": a.cohort_out.name if a.cohort_out else None,
        "levels": levels,
        "baselines": base,
        "figures": figures(s),
    }
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["levels"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
