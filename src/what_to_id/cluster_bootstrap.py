"""Observer-clustered bootstrap for the per-level outcome rates of scripts/levels_outcome.py.

Records by one observer are not independent (the same person photographs, labels and gets
corrected alike), so a record-level interval is too narrow. Here the observer is the resampling
unit: each replicate draws observers with replacement and keeps all their records. Per observer
the data are summed once into counts, so a replicate is one multinomial draw and a matrix
product.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BATCH = 100  # replicates per multinomial draw: bounds memory at BATCH x observers integers
MIN_REPS = 1000
PCT = [2.5, 97.5]


def _ci(x: np.ndarray) -> list[float]:
    lo, hi = np.nanpercentile(x, PCT)
    return [round(float(lo), 2), round(float(hi), 2)]


def observer_codes(user_id: pd.Series) -> np.ndarray:
    """Dense observer codes; a record with no observer is its own cluster (never merged)."""
    codes, _ = pd.factorize(user_id)  # NaN codes as -1
    missing = codes < 0
    codes[missing] = codes.max() + 1 + np.arange(missing.sum())
    return codes


def level_stats(
    s: pd.DataFrame, levels: dict[int, str], reps: int, seed: int, ratio_cols: tuple = ()
) -> dict[str, dict]:
    """Per level name, observer-clustered 95% percentile intervals and the contrasts with level 0.

    `s` has `user_id`, `level` and boolean `left`, `corrected` and `ratio_cols` (booleans that
    count among corrected records, e.g. `to_suggested`). Every level gets corrected_per_1000_ci
    and left_per_1000_ci; every level but 0 (no level, the reference) also gets
    `<outcome>_diff_per_1000` (level minus no level, with `_ci`) for corrected and left,
    corrected_rr_ci, and `<col>_rr_ci` (share among corrected, level over no level).
    """
    if reps < MIN_REPS:
        raise ValueError(f"reps must be at least {MIN_REPS}, got {reps}")
    if 0 not in levels:
        raise ValueError("levels must hold 0, the no-level reference")
    obs = observer_codes(s["user_id"])
    m = int(obs.max()) + 1 if len(obs) else 0
    if not m:
        raise ValueError("no records")
    cols = ["n", "left", "corrected", *ratio_cols]
    ks = list(levels)
    x = np.zeros((m, len(ks), len(cols)))  # observers x level x column counts
    for j, k in enumerate(ks):
        at = (s["level"] == k).to_numpy()
        for c, col in enumerate(cols):
            w = np.ones(at.sum()) if col == "n" else s.loc[at, col].to_numpy(float)
            x[:, j, c] = np.bincount(obs[at], weights=w, minlength=m)
    rng = np.random.default_rng(seed)
    p = np.full(m, 1 / m)
    draws = (rng.multinomial(m, p, size=min(BATCH, reps - i)) for i in range(0, reps, BATCH))
    flat = x.reshape(m, -1)
    boot = np.concatenate([d @ flat for d in draws]).reshape(reps, len(ks), len(cols))
    full = x.sum(0)
    ref = ks.index(0)
    out = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        for j, k in enumerate(ks):
            rate = {
                "corrected": boot[:, :, 2] / boot[:, :, 0],
                "left": boot[:, :, 1] / boot[:, :, 0],
            }
            row = {
                "corrected_per_1000_ci": _ci(1000 * rate["corrected"][:, j]),
                "left_per_1000_ci": _ci(1000 * rate["left"][:, j]),
            }
            if k:
                for name, i in (("corrected", 2), ("left", 1)):
                    est = 1000 * (full[j, i] / full[j, 0] - full[ref, i] / full[ref, 0])
                    row[f"{name}_diff_per_1000"] = round(float(est), 2)
                    row[f"{name}_diff_per_1000_ci"] = _ci(
                        1000 * (rate[name][:, j] - rate[name][:, ref])
                    )
                row["corrected_rr_ci"] = _ci(rate["corrected"][:, j] / rate["corrected"][:, ref])
                for c, col in enumerate(ratio_cols, start=3):
                    share = boot[:, :, c] / boot[:, :, 2]
                    row[f"{col}_rr_ci"] = _ci(share[:, j] / share[:, ref])
            out[levels[k]] = row
    return out
