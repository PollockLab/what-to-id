"""Pre-registered read-back analysis for the rotation design.

Under ``rotation`` every identifier's batches cycle through all arms in equal share, so an
identifier's own count of species-level identifications in each arm is comparable across arms
without knowing which records they opened. The primary test, fixed before the blitz, is a
paired sign-flip permutation test on per-identifier differences (treatment minus control), one
per treatment arm, Holm-adjusted across treatment arms; ``sign_test_p`` runs the same paired
comparison as an exact binomial sign test (positive vs negative differences, zeros dropped) and
is reported alongside it, unadjusted. ``record_totals`` and ``record_shuffle_p`` add a
secondary, pre-registered check that re-randomises the unit the design randomises, the record,
instead of the sign within an identifier, and recomputes the same summed difference; it is not
a replacement for the primary test. A record an identifier gave several species-level
identifications counts once, unless ``identifier_counts`` is weighted by ``cell_score``, in
which case each distinct (user, record) pair contributes that record's cell score (0 when
missing) instead of 1, so the primary count favours identifications in data-poor cells. Organic
identifiers who never saw the page are not balanced across arms: each arm serves its own top
records, and the recency arm serves the newest, which draw the most organic attention on
iNaturalist. The test is therefore restricted to the blitz participants' user ids (``users``),
and a placebo run over a pre-blitz period on the same served sets measures how far organic
attention alone separates the arms. The same test runs on simulated counts
(``power.identifier_power``) and on the real read-back. Naive timestamps are read as UTC.
``exposure`` counts the served records each participant marked reviewed, per arm, from the
read-back's ``reviewed_by``; it has no timestamps, so it is a compliance check on the equal
share rotation assumes, not an input to the test. ``served_arms`` normalises either a
single-build batches frame or a cumulative served log (mapped through a label -> arm map) to
one row per served id, and is shared by the analysis and read-back CLIs so a build served under
several daily labels is read as one arm assignment.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

SPECIES_RANKS = frozenset({"species", "hybrid", "subspecies", "variety", "form", "infrahybrid"})
IDENT_NEEDS = ("id", "user_id", "created_at", "taxon_rank")
EXACT_MAX = 12
WEIGHTS = ("none", "cell_score")
RESULT_COLUMNS = (
    "arm",
    "control",
    "n_identifiers",
    "total",
    "total_control",
    "mean_diff",
    "p",
    "p_sign",
)


def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def served_arms(served: pd.DataFrame, label_map: Mapping[str, str] | None = None) -> pd.DataFrame:
    """One row per distinct served id: ``id``, ``arm``, ``cell_score``.

    Accepts either a single-build batches frame (an ``arm`` column) or a cumulative served log
    (a ``label`` column, mapped through ``label_map`` to arm names). Raises a clear ValueError
    if a label has no entry in ``label_map``, or if an id is served under two different arms.
    ``cell_score`` is the first non-null value seen for the id, NaN if none or the column is
    absent.
    """
    if "arm" in served.columns:
        pairs = served[["id", "arm"]]
    elif "label" in served.columns:
        if label_map is None:
            raise ValueError("served has a 'label' column; label_map is required to map it")
        unknown = sorted(set(served["label"].unique()) - set(label_map))
        if unknown:
            raise ValueError(f"labels not in label_map: {unknown}")
        pairs = pd.DataFrame({"id": served["id"], "arm": served["label"].map(label_map)})
    else:
        raise ValueError("served missing columns ['arm'] or ['label']")
    n_arms = pairs.groupby("id")["arm"].nunique()
    conflicts = sorted(n_arms[n_arms > 1].index.tolist())
    if conflicts:
        raise ValueError(f"ids served under more than one arm: {conflicts}")
    arm_of = pairs.drop_duplicates("id").set_index("id")["arm"]
    if "cell_score" in served.columns:
        scored = served[["id", "cell_score"]].dropna(subset=["cell_score"])
        score_of = scored.drop_duplicates("id", keep="first").set_index("id")["cell_score"]
    else:
        score_of = pd.Series(dtype="float64")
    out = pd.DataFrame({"id": arm_of.index, "arm": arm_of.to_numpy()})
    out["cell_score"] = out["id"].map(score_of).astype("float64")
    return out.reset_index(drop=True)


def _served_lookup(served: pd.DataFrame) -> pd.DataFrame:
    return served_arms(served).set_index("id")


def _by_arm(pairs: pd.DataFrame, arm_of: pd.Series) -> pd.DataFrame:
    """Distinct (user_id, id) pairs to a users-by-arms count frame with every served arm."""
    arms = sorted(arm_of.unique())
    if pairs.empty:
        return pd.DataFrame(columns=arms, dtype="int64")
    pairs = pairs.drop_duplicates().reset_index(drop=True)
    pairs = pairs.assign(arm=pairs["id"].map(arm_of))
    out = pairs.groupby(["user_id", "arm"]).size().unstack("arm", fill_value=0)
    return out.reindex(columns=arms, fill_value=0).astype("int64")


def _by_arm_weighted(pairs: pd.DataFrame, arm_of: pd.Series, score_of: pd.Series) -> pd.DataFrame:
    """Distinct (user_id, id) pairs to a users-by-arms frame summing cell_score (NaN as 0)."""
    arms = sorted(arm_of.unique())
    if pairs.empty:
        return pd.DataFrame(columns=arms, dtype="float64")
    pairs = pairs.drop_duplicates().reset_index(drop=True)
    pairs = pairs.assign(arm=pairs["id"].map(arm_of), score=pairs["id"].map(score_of).fillna(0.0))
    out = pairs.groupby(["user_id", "arm"])["score"].sum().unstack("arm", fill_value=0.0)
    return out.reindex(columns=arms, fill_value=0.0).astype("float64")


def identifier_counts(
    idents: pd.DataFrame,
    served: pd.DataFrame,
    *,
    start,
    cutoff,
    users: Sequence[int] | None = None,
    weight: str | None = None,
) -> pd.DataFrame:
    """Records given a species-level identification, per identifier (rows) and arm (columns).

    ``weight="cell_score"`` sums each distinct (user, record) pair's served cell_score (0 when
    missing) instead of counting 1, so the counts are float; the default counts records.
    """
    if weight is not None and weight not in WEIGHTS:
        raise ValueError(f"weight must be one of {WEIGHTS}, got {weight!r}")
    missing = [c for c in IDENT_NEEDS if c not in idents.columns]
    if missing:
        raise ValueError(f"idents missing columns {missing}; read back with taxon_rank")
    lookup = _served_lookup(served)
    arm_of = lookup["arm"]
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
    pairs = idents.loc[keep, ["user_id", "id"]]
    if weight == "cell_score":
        return _by_arm_weighted(pairs, arm_of, lookup["cell_score"])
    return _by_arm(pairs, arm_of)


def exposure(
    obs: pd.DataFrame, served: pd.DataFrame, *, users: Sequence[int] | None = None
) -> pd.DataFrame:
    """Served records each user marked reviewed, per user (rows) and arm (columns)."""
    missing = [c for c in ("id", "reviewed_by") if c not in obs.columns]
    if missing:
        raise ValueError(f"obs missing columns {missing}; read back with reviewed_by")
    arm_of = _served_lookup(served)["arm"]
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


def record_totals(
    idents: pd.DataFrame,
    served: pd.DataFrame,
    *,
    start,
    cutoff,
    users: Sequence[int] | None = None,
    weight: str | None = None,
) -> pd.Series:
    """Per served record: what it contributes to the summed per-identifier difference.

    The primary statistic, the sum over identifiers of (count on an arm minus count on the
    control), collapses to a per-record total: distinct (user, record) pairs on the arm's
    records minus those on the control's. This returns that per-record total, indexed by served
    id and 0 for a served record nobody identified, so the record-level re-randomisation check
    can recompute the same statistic under a redrawn assignment.
    """
    if weight is not None and weight not in WEIGHTS:
        raise ValueError(f"weight must be one of {WEIGHTS}, got {weight!r}")
    missing = [c for c in IDENT_NEEDS if c not in idents.columns]
    if missing:
        raise ValueError(f"idents missing columns {missing}; read back with taxon_rank")
    lookup = _served_lookup(served)
    ids = lookup.index
    t0, t1 = _utc(start), _utc(cutoff)
    if t1 <= t0:
        raise ValueError(f"cutoff {cutoff} is not after start {start}")
    ts = pd.to_datetime(idents["created_at"], utc=True, errors="coerce")
    keep = (
        idents["id"].isin(ids)
        & idents["user_id"].notna()
        & ts.ge(t0)
        & ts.lt(t1)
        & idents["taxon_rank"].isin(SPECIES_RANKS)
    )
    if users is not None:
        keep &= idents["user_id"].isin({int(u) for u in users})
    pairs = idents.loc[keep, ["user_id", "id"]].drop_duplicates()
    per_id = pairs.groupby("id").size().astype("float64")
    if weight == "cell_score":
        per_id = per_id * lookup["cell_score"].reindex(per_id.index).fillna(0.0)
    return per_id.reindex(ids).fillna(0.0).astype("float64")


def record_shuffle_p(
    totals: pd.Series,
    served: pd.DataFrame,
    *,
    arm: str,
    control: str,
    strata: pd.Series | None = None,
    reps: int = 10000,
    seed: int = 0,
) -> float:
    """Two-sided p of the same summed difference under a redrawn record-to-arm assignment.

    The primary test re-randomises signs within identifiers, the unit of analysis. This
    re-randomises the unit the design actually randomises, the record. With ``strata`` None it
    draws each record's arm on its own and uniformly, which is what ``assign.assign_keyed``
    does. With ``strata`` given, one label per served id, it permutes the observed arms inside
    each stratum, which is what ``assign.assign`` does. It is a secondary check, not the
    primary test: it asks whether the observed difference is unusual when only the split of
    records changes, with each record's identifications held fixed.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    served = served_arms(served)
    arms = sorted(served["arm"].unique())
    missing = [name for name in (arm, control) if name not in arms]
    if missing:
        raise ValueError(f"arms {missing} not in {arms}")
    w = served["id"].map(totals).fillna(0.0).to_numpy(dtype=np.float64)
    code = served["arm"].map({a: i for i, a in enumerate(arms)}).to_numpy(dtype=np.int64)
    i_arm, i_ctl = arms.index(arm), arms.index(control)
    obs = abs(float(w[code == i_arm].sum() - w[code == i_ctl].sum()))
    rng = np.random.default_rng(seed)
    if strata is None:
        blocks = None
    else:
        labels = served["id"].map(strata)
        if labels.isna().any():
            raise ValueError("strata is missing a label for at least one served id")
        blocks = [np.flatnonzero(labels.to_numpy() == s) for s in sorted(labels.unique())]
    hits = 0
    for _ in range(reps):
        if blocks is None:
            drawn = rng.integers(len(arms), size=w.size)
        else:
            drawn = code.copy()
            for block in blocks:
                drawn[block] = rng.permutation(code[block])
        stat = w[drawn == i_arm].sum() - w[drawn == i_ctl].sum()
        hits += abs(stat) >= obs - 1e-9
    return float((1 + hits) / (reps + 1))


def sign_test_p(diff: Sequence[float]) -> float:
    """Two-sided exact binomial sign test on positive vs negative differences, zeros dropped."""
    d = np.asarray(diff, dtype=np.float64)
    d = d[d != 0]
    if d.size == 0:
        return 1.0
    positive = int((d > 0).sum())
    return float(binomtest(positive, d.size, 0.5, alternative="two-sided").pvalue)


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
    """One row per treatment arm against ``control``, with raw and Holm-adjusted p.

    ``p`` is the paired sign-flip permutation p, Holm-adjusted into ``p_holm``; ``p_sign`` is
    the exact binomial sign test on the same differences, reported unadjusted.
    """
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
                "p_sign": sign_test_p(d),
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


def _label_map(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    return json.loads(path.read_text())


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-registered per-identifier arm comparison.")
    ap.add_argument("--idents", required=True, type=Path, help="read-back idents parquet")
    ap.add_argument(
        "--served",
        required=True,
        type=Path,
        nargs="+",
        help="one or more batches (id, arm) or served-log (id, label) parquet files",
    )
    ap.add_argument(
        "--label-map", type=Path, help="JSON {label: arm}, required if --served files are logs"
    )
    ap.add_argument(
        "--weight",
        choices=WEIGHTS,
        default="none",
        help="cell_score sums each identifier's served cell_score instead of counting records",
    )
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
    served_raw = pd.concat(
        [pd.read_parquet(p, engine="pyarrow") for p in a.served], ignore_index=True
    )
    served = served_arms(served_raw, _label_map(a.label_map))
    weight = None if a.weight == "none" else a.weight
    if weight is not None:
        n_missing = int(served["cell_score"].isna().sum())
        print(f"{n_missing} served record(s) with no cell_score (weighted as 0)")
    users = _users(a.users) if a.users else None
    windows = [("blitz", a.start, a.cutoff)]
    if a.placebo_start:
        windows.append(("placebo", a.placebo_start, a.start))
    for label, t0, t1 in windows:
        counts = identifier_counts(idents, served, start=t0, cutoff=t1, users=users, weight=weight)
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
