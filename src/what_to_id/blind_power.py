"""Usage: python -m what_to_id.blind_power [--records 1000 2000 3000] [--draws 4000] [--seed 0]

Sample size for the blind student track, so the numbers in the pre-registration trace to code.
Per record count: settled records per source, Wilson half-width of the error rate e per source,
power of the two-proportion test on e for two effect sizes, the simulated 95% interval of the
detection rate d per source at the assumed d, and power to tell d apart between sources. The d
rows simulate the chain the estimator sees: erroneous records are a binomial draw from the settled
records, overturns a binomial draw from those, and the test is the one-sided z test on the
difference, a stand-in for the registered bootstrap.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import norm

from .blind_report import Z, _wilson

COLUMNS = [
    "records", "n_cv", "n_typed", "half_cv", "half_typed", "power_e_small", "power_e_large",
    "d_lo_cv", "d_hi_cv", "d_lo_typed", "d_hi_typed", "power_d",
]  # fmt: skip
Z_ONE_SIDED = 1.644854


def power_two_prop(p1: float, p2: float, n1: float, n2: float, one_sided: bool = False) -> float:
    """Normal-approximation power of the unpooled z test for p1 != p2 (or p2 > p1 one-sided)."""
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    crit = Z_ONE_SIDED if one_sided else Z
    return float(
        norm.sf(crit - abs(p2 - p1) / se)
        + (0 if one_sided else norm.cdf(-crit - abs(p2 - p1) / se))
    )


def _draw_d(n: int, e: float, d: float, draws: int, rng):
    """Detection-rate estimates and their denominators over simulated studies."""
    errs = rng.binomial(n, e, draws)
    hits = rng.binomial(errs, d)
    with np.errstate(invalid="ignore"):
        return hits / errs, errs


def table(
    records: list[int],
    settled: float = 0.8,
    cv_share: float = 0.75,
    e_cv: float = 0.06,
    e_typed: float = 0.09,
    e_typed_large: float = 0.12,
    d: float = 0.75,
    d_cv: float = 0.6,
    d_typed: float = 0.8,
    draws: int = 4000,
    seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for n in records:
        n_cv, n_typed = n * settled * cv_share, n * settled * (1 - cv_share)
        lo, hi = _wilson(np.array([e_cv * n_cv, e_typed * n_typed]), np.array([n_cv, n_typed]))
        half = (hi - lo) / 2
        d_cv_hat, _ = _draw_d(int(n_cv), e_cv, d, draws, rng)
        d_typed_hat, _ = _draw_d(int(n_typed), e_typed, d, draws, rng)
        a, n_a = _draw_d(int(n_cv), e_cv, d_cv, draws, rng)
        b, n_b = _draw_d(int(n_typed), e_typed, d_typed, draws, rng)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (b - a) / np.sqrt(a * (1 - a) / n_a + b * (1 - b) / n_b)
        rows.append([
            n, n_cv, n_typed, half[0], half[1],
            power_two_prop(e_cv, e_typed, n_cv, n_typed),
            power_two_prop(e_cv, e_typed_large, n_cv, n_typed),
            *np.nanpercentile(d_cv_hat, [2.5, 97.5]),
            *np.nanpercentile(d_typed_hat, [2.5, 97.5]),
            float(np.nanmean(z > Z_ONE_SIDED)),
        ])  # fmt: skip
    return pd.DataFrame(rows, columns=COLUMNS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--records", type=int, nargs="+", default=[1000, 2000, 3000])
    ap.add_argument("--draws", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    print(table(a.records, draws=a.draws, seed=a.seed).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
