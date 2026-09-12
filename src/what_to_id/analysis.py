"""Pre-registered read-back analysis for the rotation design.

Under ``rotation`` every identifier's batches cycle through all arms in equal share, so an
identifier's own count of species-level identifications in each arm is comparable across arms
without knowing which records they opened. The primary test, fixed before the blitz, is a
paired sign-flip permutation test on per-identifier differences (treatment minus control), one
per treatment arm, Holm-adjusted across treatment arms. A record an identifier gave several
species-level identifications counts once. Organic identifiers who never saw the page are
not balanced across arms: each arm serves its own top records, and the recency arm serves the
newest, which draw the most organic attention on iNaturalist. The test is therefore restricted
to the blitz participants' user ids (``users``), and a placebo run over a pre-blitz period on
the same served sets measures how far organic attention alone separates the arms. The same test
runs on simulated counts (``power.identifier_power``) and on the real read-back. Naive
timestamps are read as UTC. ``exposure`` counts the served records each participant marked
reviewed, per arm, from the read-back's ``reviewed_by``; it has no timestamps, so it is a
compliance check on the equal share rotation assumes, not an input to the test.
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


def _arm_of(served: pd.DataFrame) -> pd.Series:
    missing = [c for c in ("id", "arm") if c not in served.columns]
    if missing:
        raise ValueError(f"served missing columns {missing}")
    return served.drop_duplicates("id").set_index("id")["arm"]


def _by_arm(pairs: pd.DataFrame, arm_of: pd.Series) -> pd.DataFrame:
    """Distinct (user_id, id) pairs to a users-by-arms count frame with every served arm."""
    arms = sorted(arm_of.unique())
    if pairs.empty:
        return pd.DataFrame(columns=arms, dtype="int64")
    pairs = pairs.drop_duplicates().reset_index(drop=True)
    pairs = pairs.assign(arm=pairs["id"].map(arm_of))
    out = pairs.groupby(["user_id", "arm"]).size().unstack("arm", fill_value=0)
    return out.reindex(columns=arms, fill_value=0).astype("int64")


def identifier_counts(
    idents: pd.DataFrame,
    served: pd.DataFrame,
    *,
    start,
    cutoff,
    users: Sequence[int] | None = None,
) -> pd.DataFrame:
    """Records given a species-level identification, per identifier (rows) and arm (columns)."""
    missing = [c for c in IDENT_NEEDS if c not in idents.columns]
    if missing:
        raise ValueError(f"idents missing columns {missing}; read back with taxon_rank")
    arm_of = _arm_of(served)
    t0, t1 = _utc(start), _utc(cutoff)
    if t1 <= t0:
        raise ValueError(f"cutoff {cutoff} is not after start {start}")
    ts = pd.to_datetime(idents["created_at"], utc=True, errors="coerce")
    keep = (
        idents["id"].isin(arm_of.index)
        & idents["user_id"].notna()
        & ts.ge(t0)
        & ts.lt(t1)
        & idents["taxon_rank"].isin(SPECIES_RANKS)
    )
    if users is not None:
        keep &= idents["user_id"].isin({int(u) for u in users})
    return _by_arm(idents.loc[keep, ["user_id", "id"]], arm_of)


def exposure(
    obs: pd.DataFrame, served: pd.DataFrame, *, users: Sequence[int] | None = None
) -> pd.DataFrame:
    """Served records each user marked reviewed, per user (rows) and arm (columns)."""
    missing = [c for c in ("id", "reviewed_by") if c not in obs.columns]
    if missing:
        raise ValueError(f"obs missing columns {missing}; read back with reviewed_by")
    arm_of = _arm_of(served)
    sub = obs.loc[obs["id"].isin(arm_of.index), ["id", "reviewed_by"]]
    sub = sub.dropna(subset=["reviewed_by"]).explode("reviewed_by").dropna(subset=["reviewed_by"])
    sub = sub.rename(columns={"reviewed_by": "user_id"}).astype({"user_id": "int64"})
    if users is not None:
        sub = sub[sub["user_id"].isin({int(u) for u in users})]
    return _by_arm(sub[["user_id", "id"]], arm_of)


def exposure_summary(expo: pd.DataFrame) -> pd.DataFrame:
    """Per arm: users who reviewed any of its records, records reviewed, share of all reviews."""
    total = int(expo.to_numpy().sum())
    return pd.DataFrame(
        {
            "arm": list(expo.columns),
            "n_users": [int((expo[a] > 0).sum()) for a in expo.columns],
            "reviewed": [int(expo[a].sum()) for a in expo.columns],
            "share": [float(expo[a].sum() / total) if total else 0.0 for a in expo.columns],
        }
    )


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


def _print(res: pd.DataFrame) -> None:
    print("| " + " | ".join(res.columns) + " |")
    print("|" + "|".join("---" for _ in res.columns) + "|")
    for row in res.itertuples(index=False):
        print("| " + " | ".join(f"{v:.4g}" if isinstance(v, float) else str(v) for v in row) + " |")


def _users(path: Path) -> list[int]:
    lines = [ln.strip() for ln in path.read_text().splitlines()]
    try:
        return [int(ln) for ln in lines if ln and not ln.startswith("#")]
    except ValueError as e:
        raise SystemExit(f"{path}: one iNaturalist user id per line ({e})") from e


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-registered per-identifier arm comparison.")
    ap.add_argument("--idents", required=True, type=Path, help="read-back idents parquet")
    ap.add_argument("--served", required=True, type=Path, help="batches parquet (id, arm)")
    ap.add_argument("--control", required=True)
    ap.add_argument("--start", required=True, help="blitz start timestamp")
    ap.add_argument("--cutoff", required=True, help="count identifications made before this")
    ap.add_argument("--users", type=Path, help="participant iNaturalist user ids, one per line")
    ap.add_argument("--placebo-start", help="also test [placebo-start, start), e.g. the freeze")
    ap.add_argument("--obs", type=Path, help="read-back obs parquet; adds the exposure check")
    ap.add_argument("--reps", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    idents = pd.read_parquet(a.idents, engine="pyarrow")
    served = pd.read_parquet(a.served, engine="pyarrow")
    users = _users(a.users) if a.users else None
    windows = [("blitz", a.start, a.cutoff)]
    if a.placebo_start:
        windows.append(("placebo", a.placebo_start, a.start))
    for label, t0, t1 in windows:
        counts = identifier_counts(idents, served, start=t0, cutoff=t1, users=users)
        print(f"{label}: [{t0}, {t1})" + ("" if users is not None else ", all identifiers"))
        _print(analyse(counts, control=a.control, reps=a.reps, seed=a.seed))
    if a.obs:
        expo = exposure(pd.read_parquet(a.obs, engine="pyarrow"), served, users=users)
        who = "participants" if users is not None else "all users"
        print(f"exposure: served records marked reviewed, {who}, no timestamps")
        _print(exposure_summary(expo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
