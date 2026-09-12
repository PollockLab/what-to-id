"""Pre-registered read-back analysis for the rotation design.

Under ``rotation`` every identifier's batches cycle through all arms in equal share, so an
identifier's own count of species-level identifications in each arm is comparable across arms
without knowing which records they opened. The primary test, fixed before the blitz, is a
paired sign-flip permutation test on per-identifier differences (treatment minus control), one
per treatment arm, Holm-adjusted across treatment arms. A record an identifier gave several
species-level identifications counts once. Everyone with a qualifying identification on a
served record counts, blitz participant or not: records are randomised, so identifiers who
never saw the page add noise but no bias. The same test runs on simulated counts
(``power.identifier_power``) and on the real read-back. Naive timestamps are read as UTC.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

SPECIES_RANKS = frozenset({"species", "hybrid", "subspecies", "variety", "form", "infrahybrid"})
IDENT_NEEDS = ("id", "user_id", "created_at", "taxon_rank")
EXACT_MAX = 12
RESULT_COLUMNS = ("arm", "control", "n_identifiers", "total", "total_control", "mean_diff", "p")


def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def identifier_counts(idents: pd.DataFrame, served: pd.DataFrame, *, start, cutoff) -> pd.DataFrame:
    """Records given a species-level identification, per identifier (rows) and arm (columns)."""
    missing = [c for c in IDENT_NEEDS if c not in idents.columns]
    if missing:
        raise ValueError(f"idents missing columns {missing}; read back with taxon_rank")
    missing = [c for c in ("id", "arm") if c not in served.columns]
    if missing:
        raise ValueError(f"served missing columns {missing}")
    t0, t1 = _utc(start), _utc(cutoff)
    if t1 <= t0:
        raise ValueError(f"cutoff {cutoff} is not after start {start}")
    arm_of = served.drop_duplicates("id").set_index("id")["arm"]
    ts = pd.to_datetime(idents["created_at"], utc=True, errors="coerce")
    keep = (
        idents["id"].isin(arm_of.index)
        & idents["user_id"].notna()
        & ts.ge(t0)
        & ts.lt(t1)
        & idents["taxon_rank"].isin(SPECIES_RANKS)
    )
    sub = idents.loc[keep, ["user_id", "id"]].drop_duplicates()
    arms = sorted(arm_of.unique())
    if sub.empty:
        return pd.DataFrame(columns=arms, dtype="int64")
    sub = sub.assign(arm=sub["id"].map(arm_of))
    out = sub.groupby(["user_id", "arm"]).size().unstack("arm", fill_value=0)
    return out.reindex(columns=arms, fill_value=0).astype("int64")


def sign_flip_p(diff: Sequence[float], *, reps: int = 10000, seed: int = 0) -> float:
    """Two-sided p of the summed paired differences; exact up to EXACT_MAX non-zero pairs."""
    d = np.asarray(diff, dtype=np.float64)
    d = d[d != 0]
    if d.size == 0:
        return 1.0
    obs = abs(d.sum())
    if d.size <= EXACT_MAX:
        signs = np.array(list(product((-1.0, 1.0), repeat=d.size)))
        return float((np.abs(signs @ d) >= obs - 1e-9).mean())
    if reps < 1:
        raise ValueError("reps must be >= 1")
    rng = np.random.default_rng(seed)
    signs = rng.choice((-1.0, 1.0), size=(reps, d.size))
    return float((1 + (np.abs(signs @ d) >= obs - 1e-9).sum()) / (reps + 1))


def holm(p: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p values, same keys."""
    keys = sorted(p, key=lambda k: p[k])
    out, running = {}, 0.0
    for i, k in enumerate(keys):
        running = max(running, min(1.0, (len(keys) - i) * p[k]))
        out[k] = running
    return out


def analyse(
    counts: pd.DataFrame, *, control: str, reps: int = 10000, seed: int = 0
) -> pd.DataFrame:
    """One row per treatment arm against ``control``, with raw and Holm-adjusted p."""
    if control not in counts.columns:
        raise ValueError(f"control arm {control!r} not in {list(counts.columns)}")
    rows = []
    for arm in (c for c in counts.columns if c != control):
        d = (counts[arm] - counts[control]).to_numpy()
        rows.append(
            {
                "arm": arm,
                "control": control,
                "n_identifiers": int(len(counts)),
                "total": int(counts[arm].sum()),
                "total_control": int(counts[control].sum()),
                "mean_diff": float(d.mean()) if d.size else 0.0,
                "p": sign_flip_p(d, reps=reps, seed=seed),
            }
        )
    out = pd.DataFrame(rows, columns=list(RESULT_COLUMNS))
    adj = holm(dict(zip(out["arm"], out["p"], strict=True)))
    return out.assign(p_holm=out["arm"].map(adj))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-registered per-identifier arm comparison.")
    ap.add_argument("--idents", required=True, type=Path, help="read-back idents parquet")
    ap.add_argument("--served", required=True, type=Path, help="batches parquet (id, arm)")
    ap.add_argument("--control", required=True)
    ap.add_argument("--start", required=True, help="blitz start timestamp")
    ap.add_argument("--cutoff", required=True, help="count identifications made before this")
    ap.add_argument("--reps", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    counts = identifier_counts(
        pd.read_parquet(a.idents, engine="pyarrow"),
        pd.read_parquet(a.served, engine="pyarrow"),
        start=a.start,
        cutoff=a.cutoff,
    )
    res = analyse(counts, control=a.control, reps=a.reps, seed=a.seed)
    print("| " + " | ".join(res.columns) + " |")
    print("|" + "|".join("---" for _ in res.columns) + "|")
    for row in res.itertuples(index=False):
        print("| " + " | ".join(f"{v:.4g}" if isinstance(v, float) else str(v) for v in row) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
