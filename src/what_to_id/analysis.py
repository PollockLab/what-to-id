"""Pre-registered read-back analysis for the rotation design.

Under ``rotation`` every identifier's batches cycle through all arms in equal share, so an
identifier's own count of species-level identifications in each arm is comparable across arms
without knowing which records they opened. The primary test, fixed before the blitz, is the
record-level re-randomisation in ``record_totals`` and ``record_shuffle_p``: it redraws the unit
the design randomises, the record, and recomputes the summed per-identifier difference
(treatment minus control). ``confirmatory`` runs it on each tested list's pinned count:
one-sided for ``gap_first`` and ``similarity`` with Holm over those two, two-sided and
unadjusted for the exploratory ``novelty``. ``analyse`` runs the paired sign-flip permutation
test on the same differences, one per treatment arm, and ``sign_test_p`` the exact binomial
sign test (positive vs negative differences, zeros dropped); both are two-sided, secondary and
reported next to the primary p.
An identification the observer made on their own record never counts: ``observer_id`` in the
idents, written by the read-back, names each record's observer. A record an identifier gave
several species-level identifications counts once, unless ``identifier_counts`` is weighted by
``cell_score``, in which case each distinct (user, record) pair contributes that record's cell
score (0 when missing) instead of 1, so the primary count favours identifications in data-poor
cells. Organic identifiers who never saw the page are not balanced across arms: each arm serves
its own top records, and the recency arm serves the newest, which draw the most organic
attention on iNaturalist. The test is therefore restricted to the blitz participants' user ids
(``users``), and a placebo run over a pre-blitz period on the same served sets measures how far
organic attention alone separates the arms. The sign-flip test also runs on simulated counts
(``power.identifier_power``). Naive timestamps are read as UTC.
``exposure`` counts the served records each participant marked reviewed, per arm, from the
read-back's ``reviewed_by``; it has no timestamps, so it is a compliance check on the equal
share rotation assumes, not an input to the test. ``served_arms`` normalises either a
single-build batches frame or a cumulative served log (mapped through a label -> arm map) to
one row per served id, and is shared by the analysis and read-back CLIs so a build served under
several daily labels is read as one arm assignment.

The CLI's default ``--weight primary`` runs the confirmatory family (``confirmatory``): each
tested list on its own pinned outcome, with the record-level p as ``p`` (one-sided for the two
primary rows, Holm over those two only; two-sided and unadjusted for the exploratory row), the
sign-flip and sign test p as ``p_signflip`` and ``p_sign``, and each list's
other count as an unadjusted secondary row. ``--weight none`` or ``cell_score`` runs every list
on one count with Holm over the sign-flip p of all of them, as ``analyse`` does, and prints
``p_record`` after ``p_holm``: the record-level p with the same users, weighting, window, reps
and seed, not Holm-adjusted.

Either way the record-level p redraws the split as the keyed build does (``strata`` None),
because the served inputs carry no stratum. It is valid only when every record in a list is
served: when a cap on batches binds, which records a list serves depends on the split, and
holding each record's identifications fixed under a redrawn split no longer matches the design.
The CLI cannot check this: a batches frame or a served log holds only the served records, not
the pool, and not the cap. Check the build record (every list and taxon group has fewer batches
than ``max_batches``, or no cap) before reading it.
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
IDENT_NEEDS = ("id", "user_id", "created_at", "taxon_rank", "observer_id")
EXACT_MAX = 12
WEIGHTS = ("none", "cell_score")
ALTERNATIVES = ("two-sided", "greater")
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
RECORD_NOTE = (
    "p_record: secondary record-level re-randomisation check, keyed split, not Holm-adjusted. "
    "Valid only if every record in a list is served (no cap on batches binds); the served "
    "files cannot show this, so check the build record."
)
PRIMARY_NOTE = (
    "p: record-level re-randomisation test, keyed split. Primary rows (gap_first, similarity): "
    "one-sided, tested list ahead of the control, Holm over those two. Exploratory row "
    "(novelty) and secondary rows: two-sided, not Holm-adjusted. p_signflip and p_sign are "
    "secondary. Valid only if every record in a list is served (no "
    "cap on batches binds); the served files cannot show this, so check the build record."
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


def _counted_pairs(
    idents: pd.DataFrame, ids: pd.Index, *, start, cutoff, users: Sequence[int] | None
) -> pd.DataFrame:
    """Distinct (user_id, id) pairs that count: species level, in the window, on a served record.

    An identification the observer made on their own record is dropped. A record with no known
    observer has no own IDs to drop, so every ID on it is kept.
    """
    missing = [c for c in IDENT_NEEDS if c not in idents.columns]
    if missing:
        raise ValueError(
            f"idents missing columns {missing}; read back with taxon_rank and observer_id"
        )
    t0, t1 = _utc(start), _utc(cutoff)
    if t1 <= t0:
        raise ValueError(f"cutoff {cutoff} is not after start {start}")
    ts = pd.to_datetime(idents["created_at"], utc=True, errors="coerce")
    by = pd.to_numeric(idents["user_id"], errors="coerce")
    own = by.eq(pd.to_numeric(idents["observer_id"], errors="coerce")).fillna(False).astype(bool)
    keep = (
        idents["id"].isin(ids)
        & by.notna()
        & ~own
        & ts.ge(t0)
        & ts.lt(t1)
        & idents["taxon_rank"].isin(SPECIES_RANKS)
    )
    if users is not None:
        keep &= idents["user_id"].isin({int(u) for u in users})
    return idents.loc[keep, ["user_id", "id"]].drop_duplicates()


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
    missing) instead of counting 1, so the counts are float; the default counts records. IDs
    the observer made on their own record are left out.
    """
    if weight is not None and weight not in WEIGHTS:
        raise ValueError(f"weight must be one of {WEIGHTS}, got {weight!r}")
    lookup = _served_lookup(served)
    arm_of = lookup["arm"]
    pairs = _counted_pairs(idents, arm_of.index, start=start, cutoff=cutoff, users=users)
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
    id and 0 for a served record nobody identified, so the record-level re-randomisation test
    can recompute the same statistic under a redrawn assignment. It counts the same pairs as
    ``identifier_counts``, so IDs the observer made on their own record are left out here too.
    """
    if weight is not None and weight not in WEIGHTS:
        raise ValueError(f"weight must be one of {WEIGHTS}, got {weight!r}")
    lookup = _served_lookup(served)
    ids = lookup.index
    pairs = _counted_pairs(idents, ids, start=start, cutoff=cutoff, users=users)
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
    arms: Sequence[str] | None = None,
    reps: int = 10000,
    seed: int = 0,
    alternative: str = "two-sided",
) -> float:
    """p of the same summed difference under a redrawn record-to-arm assignment.

    This is the primary test. It re-randomises the unit the design randomises, the record,
    where the sign-flip test re-randomises signs within identifiers. With ``strata`` None it
    draws each record's arm on its own and uniformly over ``arms``, which is what
    ``assign.assign_keyed`` does. ``arms`` is the design's lists; left None it is the lists
    that were served, which differs from the design only when a list served nothing. With
    ``strata`` given, one label per served id, it permutes the observed arms inside each
    stratum, which is what ``assign.assign`` does. It asks whether the observed difference is
    unusual when only the split of records changes, with each record's identifications held
    fixed. The observed split counts as one redraw, so p is never 0.

    ``alternative`` "two-sided" (the default) counts redraws whose absolute difference reaches
    the observed one; "greater" counts redraws whose difference (``arm`` minus ``control``)
    reaches the observed signed difference, the one-sided test that ``arm`` is ahead. Both use
    the same redraws and the same tie tolerance.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if alternative not in ALTERNATIVES:
        raise ValueError(f"alternative must be one of {ALTERNATIVES}, got {alternative!r}")
    two_sided = alternative == "two-sided"
    served = served_arms(served)
    seen = sorted(served["arm"].unique())
    arms = seen if arms is None else sorted(arms)
    missing = [name for name in (arm, control) if name not in arms]
    if missing:
        raise ValueError(f"arms {missing} not in {arms}")
    extra = [name for name in seen if name not in arms]
    if extra:
        raise ValueError(f"served arms {extra} not in the design's lists {arms}")
    w = served["id"].map(totals).fillna(0.0).to_numpy(dtype=np.float64)
    code = served["arm"].map({a: i for i, a in enumerate(arms)}).to_numpy(dtype=np.int64)
    i_arm, i_ctl = arms.index(arm), arms.index(control)
    obs = float(w[code == i_arm].sum() - w[code == i_ctl].sum())
    if two_sided:
        obs = abs(obs)
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
        hits += (abs(stat) if two_sided else stat) >= obs - 1e-9
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
    the exact binomial sign test on the same differences, reported unadjusted. This is the
    exploratory one-count comparison; the primary test is the record-level one that
    ``confirmatory`` runs, and there this sign-flip p is a secondary column.
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
    ap = argparse.ArgumentParser(
        description="Pre-registered per-identifier arm comparison.",
        epilog=f"{PRIMARY_NOTE} {RECORD_NOTE}",
    )
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
        choices=("primary", *WEIGHTS),
        default="primary",
        help="primary: each list on its pinned outcome, one-sided with Holm over gap_first and "
        "similarity, novelty exploratory; none or cell_score: "
        "every list on one count (cell_score sums each identifier's served cell_score)",
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
    if a.weight == "primary" and a.users is None:
        ap.error("--weight primary counts participants only; give --users")
    idents = pd.read_parquet(a.idents, engine="pyarrow")
    served_raw = pd.concat(
        [pd.read_parquet(p, engine="pyarrow") for p in a.served], ignore_index=True
    )
    served = served_arms(served_raw, _label_map(a.label_map))
    if a.weight != "none":
        n_missing = int(served["cell_score"].isna().sum())
        print(f"{n_missing} served record(s) with no cell_score (weighted as 0)")
    users = _users(a.users) if a.users else None
    windows = [("blitz", a.start, a.cutoff)]
    if a.placebo_start:
        windows.append(("placebo", a.placebo_start, a.start))
    print(PRIMARY_NOTE if a.weight == "primary" else RECORD_NOTE)
    for label, t0, t1 in windows:
        kw = {"start": t0, "cutoff": t1, "users": users}
        print(f"{label}: [{t0}, {t1})" + ("" if users is not None else ", all identifiers"))
        if a.weight == "primary":
            # Imported here: confirmatory builds on this module.
            from what_to_id.confirmatory import confirmatory

            # The record-level p is already the primary p here, so no p_record column.
            res = confirmatory(idents, served, control=a.control, reps=a.reps, seed=a.seed, **kw)
        else:
            weight = None if a.weight == "none" else a.weight
            counts = identifier_counts(idents, served, weight=weight, **kw)
            res = analyse(counts, control=a.control, reps=a.reps, seed=a.seed)
            totals = record_totals(idents, served, weight=weight, **kw)
            res["p_record"] = [
                record_shuffle_p(
                    totals, served, arm=arm, control=a.control, reps=a.reps, seed=a.seed
                )
                for arm in res["arm"]
            ]
        _print(res)
    if a.obs:
        expo = exposure(pd.read_parquet(a.obs, engine="pyarrow"), served, users=users)
        who = "participants" if users is not None else "all users"
        print(f"exposure: served records marked reviewed, {who}, no timestamps")
        _print(exposure_summary(expo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
