"""The confirmatory family: each tested list against the control, on its own primary outcome.

The draft protocol fixes one primary outcome per tested list before the blitz, and ``PRIMARY``
pins it here: the weighted count (``cell_score``) for ``gap_first``, the plain count for
``similarity`` and ``novelty``. ``confirmatory`` runs the paired sign-flip test on both counts,
keeps each list's pinned count as its primary row, and applies Holm over those primary p values
only, so with the four-list design Holm runs over three comparisons. Each list's other count is
reported as a secondary row with its own p and no Holm adjustment. A tested list with no pinned
outcome raises a ValueError that names it, so no list enters the family without a stated outcome.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from what_to_id.analysis import analyse, holm, identifier_counts, served_arms

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
    "p_sign",
    "p_holm",
)


def primary_outcome(arm: str) -> str:
    """The pinned primary weighting of a tested list; a clear error names a list with none."""
    if arm not in PRIMARY:
        raise ValueError(f"no primary outcome pinned for list {arm!r}; pinned: {sorted(PRIMARY)}")
    return PRIMARY[arm]


def family(results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Primary and secondary rows from ``analyse`` results keyed by weighting, Holm on primaries.

    ``results`` maps each weighting in ``OUTCOME`` to the ``analyse`` frame for that count. The
    frames' own ``p_holm``, which adjusts over every arm on one count, is dropped.
    """
    missing = [w for w in OUTCOME if w not in results]
    if missing:
        raise ValueError(f"results missing weightings {missing}")
    rows = []
    for weight, res in results.items():
        for row in res.drop(columns="p_holm").to_dict("records"):
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
    users: Sequence[int] | None = None,
    reps: int = 10000,
    seed: int = 0,
) -> pd.DataFrame:
    """Each tested list against ``control`` on its pinned outcome, Holm over the primaries."""
    served = served_arms(served)
    arms = sorted(served["arm"].unique())
    if control not in arms:
        raise ValueError(f"control arm {control!r} not in {arms}")
    for arm in arms:
        if arm != control:
            primary_outcome(arm)
    kw = {"start": start, "cutoff": cutoff, "users": users}
    results = {}
    for weight in OUTCOME:
        counts = identifier_counts(
            idents, served, weight=None if weight == "none" else weight, **kw
        )
        results[weight] = analyse(counts, control=control, reps=reps, seed=seed)
    return family(results)
