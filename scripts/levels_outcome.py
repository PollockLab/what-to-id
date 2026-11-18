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
level against records in no level gets a percentile bootstrap interval. Every level also gets
observer-clustered intervals (`what_to_id.cluster_bootstrap`: observers, not records, are
resampled), beside the record-level ones. `--exclude-pool` drops records that were in that pool
after levelling, for a held-out cohort. The inputs' sha256 go into the JSON so a quoted number can
be traced to the files that produced it. The JSON also holds the figure data (margin histogram per
level, corrected share per margin bin) and the AUC of the page order against plain orderings;
`--cohort-out` writes the scored cohort for others to run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.cluster_bootstrap import level_stats
from what_to_id.levels import WEIRD_SHARE, lookalike_known, species_masks, taxonomist_cut
from what_to_id.pool_levels import STEPS, quantize

LEVELS = {0: "none", 1: "easy", 2: "taxonomist", 4: "weird", 5: "mislabel"}
# the Identify page shows Might be mislabelled first, then Odd shots, then Close calls; Clear
# matches sit in their own list after everything else
PAGE_PRIORITY = {5: 4, 4: 3, 2: 2, 0: 1, 1: 0}
MARGIN_EDGES = np.round(np.arange(-0.15, 0.1501, 0.005), 3)
CALIBRATION_BINS = 20
COHORT_COLUMNS = [
    *("id", "taxon_id", "taxon_name", "iconic_taxon", "own", "other", "other_name", "margin"),
    *("user_id", "level", "left", "corrected", "name_b", "to_suggested", "to_suggested_genus"),
]


def cohort(scores: Path, before: Path, after: Path, exclude: Path | None = None) -> pd.DataFrame:
    """The scored cohort with levels and outcomes. `exclude` is a pool whose records are left
    out once levelled, to keep only records that were not Needs ID then (the held-out cohort)."""
    s = pd.read_parquet(scores, columns=["id", "taxon_name", "own", "other", "other_name"])
    p = pd.read_parquet(before, columns=["id", "taxon_id", "rank", "iconic_taxon", "user_id"])
    s = s.merge(p, on="id", how="inner", validate="one_to_one")
    s = s[(s["rank"] == "species") & s["own"].notna() & s["other"].notna()].reset_index(drop=True)
    s["margin"] = s["own"] - s["other"]
    s["top"] = s[["own", "other"]].max(axis=1)
    g = s["iconic_taxon"].fillna("")
    weird = s["top"] <= s.groupby(g)["top"].transform(lambda x: x.quantile(WEIRD_SHARE))
    easy, tax = species_masks(s, weird)
    mis = (s["margin"] < -taxonomist_cut(s)) & lookalike_known(s) & ~weird
    s["level"] = np.select([weird, easy, tax, mis], [4, 1, 2, 5], 0)
    if exclude:  # after the levels, which production assigns over the whole pool
        s = s[~s["id"].isin(pd.read_parquet(exclude, columns=["id"])["id"])].reset_index(drop=True)
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


def wilson(k: float, n: float) -> list[float]:
    """95% Wilson interval of a record-level proportion, per 1,000."""
    z, p = 1.959964, k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(1000 * float(mid - half), 2), round(1000 * float(mid + half), 2)]


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
    ap.add_argument("--exclude-pool", type=Path, help="drop records in this pool (held-out)")
    ap.add_argument("--cohort-out", type=Path, help="write the scored cohort as parquet")
    a = ap.parse_args(argv)
    s = cohort(a.scores, a.pool_before, a.pool_after, a.exclude_pool)
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
            "record_level": {  # as if records were independent, for comparison with `cluster`
                "corrected_per_1000_ci": wilson(d["corrected"].sum(), len(d)),
                "left_per_1000_ci": wilson(d["left"].sum(), len(d)),
            },
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
    shares = ("to_suggested", "to_suggested_genus")
    for name, stats in level_stats(s, LEVELS, a.reps, a.seed, shares).items():
        levels[name]["cluster"] = stats
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
                *((("pool_excluded", a.exclude_pool),) if a.exclude_pool else ()),
            )
        },
        "seed": a.seed,
        "bootstrap_reps": a.reps,
        "cluster": {
            "unit": "observer (user_id)",
            "observers": int(s["user_id"].nunique()),
            "records_without_observer": int(s["user_id"].isna().sum()),
            "interval": "95% percentile of resampled observers, all their records kept",
        },
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
