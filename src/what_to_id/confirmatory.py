"""The confirmatory family: each tested list against the control, on its own primary outcome.

The draft protocol fixes one primary outcome per tested list before the blitz, and ``PRIMARY``
pins it here: the weighted count (``cell_score``) for ``gap_first``, the plain count for
``similarity`` and ``novelty``. ``confirmatory`` counts participants only (``users`` is
required), leaves out IDs the observer made on their own record, and runs on both counts the
primary test, record-level re-randomisation (``analysis.record_totals`` and
``analysis.record_shuffle_p``, each record's list redrawn uniformly and independently over the
design's lists, as ``assign.assign_keyed`` draws it). That p is each row's ``p``. Each list's
pinned count is its primary row, and Holm runs over those primary p values only, so with the
four-list design Holm runs over three comparisons. The paired sign-flip p (``p_signflip``) and
the exact sign test (``p_sign``) are reported on every row as secondary checks. Each list's
other count is a secondary row with its own p and no Holm adjustment. A tested list with no
pinned outcome raises a ValueError that names it, so no list enters the family without a stated
outcome, and so does a design list (the control or a tested list) with no served records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from what_to_id.analysis import (
    analyse,
    holm,
    identifier_counts,
    record_shuffle_p,
    record_totals,
    served_arms,
)

PRIMARY: dict[str, str] = {"gap_first": "cell_score", "similarity": "none", "novelty": "none"}
OUTCOME = {"cell_score": "weighted", "none": "plain"}
COLUMNS = (
    "arm",
    "control",
    "outcome",
    "role",
    "n_identifiers",
    "total",
    "total_control",
    "mean_diff",
    "p",
    "p_signflip",
    "p_sign",
    "p_holm",
)


def primary_outcome(arm: str) -> str:
    """The pinned primary weighting of a tested list; a clear error names a list with none."""
    if arm not in PRIMARY:
        raise ValueError(f"no primary outcome pinned for list {arm!r}; pinned: {sorted(PRIMARY)}")
    return PRIMARY[arm]


def family(results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Primary and secondary rows from per-weighting results, Holm on the primaries' ``p``.

    ``results`` maps each weighting in ``OUTCOME`` to a frame with one row per tested list:
    the ``analyse`` columns, with ``p`` the record-level p and the sign-flip p in
    ``p_signflip``. Any ``p_holm`` already there, which would adjust over every arm on one
    count, is dropped.
    """
    missing = [w for w in OUTCOME if w not in results]
    if missing:
        raise ValueError(f"results missing weightings {missing}")
    rows = []
    for weight, res in results.items():
        for row in res.drop(columns="p_holm", errors="ignore").to_dict("records"):
            role = "primary" if primary_outcome(row["arm"]) == weight else "secondary"
            rows.append({**row, "outcome": OUTCOME[weight], "role": role})
    out = pd.DataFrame(rows, columns=[c for c in COLUMNS if c != "p_holm"])
    is_primary = out["role"].eq("primary")
    adj = holm(dict(zip(out.loc[is_primary, "arm"], out.loc[is_primary, "p"], strict=True)))
    out["p_holm"] = np.where(is_primary, out["arm"].map(adj), np.nan)
    # "primary" sorts before "secondary", so the family comes first.
    return out.sort_values(["role", "arm"]).reset_index(drop=True)


def confirmatory(
    idents: pd.DataFrame,
    served: pd.DataFrame,
    *,
    control: str,
    start,
    cutoff,
    users: Sequence[int] | None,
    reps: int = 10000,
    seed: int = 0,
) -> pd.DataFrame:
    """Each tested list against ``control`` on its pinned outcome, Holm over the primaries.

    ``users`` is the participant list and must not be empty: the family counts participants
    only. Every design list, ``control`` and each list in ``PRIMARY``, must have served records,
    and the record-level redraw runs over those lists.
    """
    if users is None or len(users) == 0:
        raise ValueError("confirmatory counts participants only; users must not be empty")
    served = served_arms(served)
    arms = sorted(served["arm"].unique())
    if control not in arms:
        raise ValueError(f"control arm {control!r} not in {arms}")
    for arm in arms:
        if arm != control:
            primary_outcome(arm)
    design = sorted([control, *PRIMARY])
    empty = [arm for arm in design if arm not in arms]
    if empty:
        raise ValueError(f"lists with no served records: {empty}; the family needs every list")
    kw = {"start": start, "cutoff": cutoff, "users": users}
    results = {}
    for weight in OUTCOME:
        w = None if weight == "none" else weight
        counts = identifier_counts(idents, served, weight=w, **kw)
        res = analyse(counts, control=control, reps=reps, seed=seed)
        totals = record_totals(idents, served, weight=w, **kw)
        record = [
            record_shuffle_p(
                totals, served, arm=arm, control=control, arms=design, reps=reps, seed=seed
            )
            for arm in res["arm"]
        ]
        results[weight] = res.rename(columns={"p": "p_signflip"}).assign(p=record)
    return family(results)
