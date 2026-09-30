"""The confirmatory family: each tested list against the control, on its own primary outcome.

The pre-registration fixes one pinned outcome per tested list before the blitz, and ``PRIMARY``
pins it here: the weighted count (``cell_score``) for ``gap_first`` (H1), the plain count for
``similarity`` (H2) and ``novelty`` (H3). ``confirmatory`` counts participants only (``users``
is required), leaves out IDs the observer made on their own record, and runs on both counts the
record-level re-randomisation test (``analysis.record_totals`` and
``analysis.record_shuffle_p``, each record's list redrawn uniformly and independently over all
four design lists, as ``assign.assign_keyed`` draws it). That p is each row's ``p``.

Only H1 and H2 (``HOLM_FAMILY``) are confirmatory: their pinned-count rows have role
"primary", a one-sided p in the direction of the tested list ahead of the control, and Holm
over those two p values only (family-wise 0.05). H3's pinned-count row has role
"exploratory": a two-sided p, reported unadjusted, with ``p_holm`` NaN. Each list's other count
is a "secondary" row with a two-sided p and no Holm adjustment. The paired sign-flip p
(``p_signflip``) and the exact sign test (``p_sign``) are two-sided and reported on every row as
secondary checks. A tested list with no pinned outcome raises a ValueError that names it, so no
list enters the family without a stated outcome, and so does a design list (the control or a
tested list) with no served records.
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
# H1 and H2: one-sided, Holm over these two. The other pinned list (novelty, H3) is exploratory.
HOLM_FAMILY = ("gap_first", "similarity")
ROLES = ("primary", "exploratory", "secondary")
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


def role(arm: str, weight: str) -> str:
    """A row's role: primary for an H1 or H2 pinned count, exploratory for H3's, else secondary."""
    if primary_outcome(arm) != weight:
        return "secondary"
    return "primary" if arm in HOLM_FAMILY else "exploratory"


def alternative(arm: str, weight: str) -> str:
    """The record-level test's direction: one-sided ("greater") on primary rows only."""
    return "greater" if role(arm, weight) == "primary" else "two-sided"


def family(results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Primary, exploratory and secondary rows from per-weighting results, Holm on primaries.

    ``results`` maps each weighting in ``OUTCOME`` to a frame with one row per tested list:
    the ``analyse`` columns, with ``p`` the record-level p (sided as ``alternative`` says) and
    the sign-flip p in ``p_signflip``. Holm runs over the primary rows' ``p`` only; the
    exploratory and secondary rows get ``p_holm`` NaN. Any ``p_holm`` already there, which
    would adjust over every arm on one count, is dropped.
    """
    missing = [w for w in OUTCOME if w not in results]
    if missing:
        raise ValueError(f"results missing weightings {missing}")
    rows = []
    for weight, res in results.items():
        for row in res.drop(columns="p_holm", errors="ignore").to_dict("records"):
            rows.append({**row, "outcome": OUTCOME[weight], "role": role(row["arm"], weight)})
    out = pd.DataFrame(rows, columns=[c for c in COLUMNS if c != "p_holm"])
    is_primary = out["role"].eq("primary")
    adj = holm(dict(zip(out.loc[is_primary, "arm"], out.loc[is_primary, "p"], strict=True)))
    out["p_holm"] = np.where(is_primary, out["arm"].map(adj), np.nan)
    # The family comes first, then the exploratory row, then the secondary rows.
    out = out.sort_values(
        ["role", "arm"], key=lambda c: c.map(ROLES.index) if c.name == "role" else c
    )
    return out.reset_index(drop=True)


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
    """Each tested list against ``control`` on its pinned outcome, Holm over H1 and H2.

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
                totals,
                served,
                arm=arm,
                control=control,
                arms=design,
                reps=reps,
                seed=seed,
                alternative=alternative(arm, weight),
            )
            for arm in res["arm"]
        ]
        results[weight] = res.rename(columns={"p": "p_signflip"}).assign(p=record)
    return family(results)
