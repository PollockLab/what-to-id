"""Usage: python -m what_to_id.blind_power [--records 1000 2000 3000] [--draws 4000] [--seed 0]

Sample size for the blind student track, so the numbers in the pre-registration trace to code.
Per record count: settled records per source, Wilson half-width of the error rate e per source,
power of the two-proportion test on e for two effect sizes, the simulated 95% interval of the
detection rate d per source at the assumed d, and power to tell d apart between sources. The d
rows simulate the chain the estimator sees: erroneous records are a binomial draw from the settled
records, overturns a binomial draw from those, disagreements with the consensus add a consensus
error c that the estimator removes using a c measured on the settled share of the planted records,
and the test is the one-sided z test on the difference, a stand-in for the registered bootstrap.
The H3 columns are the power of the one-sided Spearman test of settled against level order when
the settled share falls by a small or a large step per level around the assumed share, records
split evenly over the five levels as ``blind_sample`` does.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

from .blind_report import Z, _correct, _wilson

COLUMNS = [
    "records", "n_cv", "n_typed", "half_cv", "half_typed", "power_e_small", "power_e_large",
    "d_lo_cv", "d_hi_cv", "d_lo_typed", "d_hi_typed", "power_d", "power_h3_small", "power_h3_large",
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


def _draw_d(n: int, e: float, d: float, draws: int, rng, c: float = 0.0, n_c: int = 0):
    """Detection-rate estimates and their denominators over simulated studies.

    The estimator sees disagreements, w = e + c - 2ec of the n settled records, and removes a c
    it measured on n_c held-out planted records; the overturns it divides by are the public's
    catches among the truly wrong first IDs.
    """
    true = rng.binomial(n, e, draws)
    hits = rng.binomial(true, d)
    # a wrong consensus hides a wrong first ID and flags a right one, on the same records
    seen = (true - rng.binomial(true, c) + rng.binomial(n - true, c)) / n
    c_hat = rng.binomial(n_c, c, draws) / n_c if n_c else c
    with np.errstate(invalid="ignore", divide="ignore"):
        errs = _correct(seen, c_hat) * n
        return hits / errs, errs


def level_power(n: int, settled: float, step: float, draws: int, rng, levels: int = 5) -> float:
    """Power of the one-sided Spearman test between level order and the settled indicator when
    the settled share falls by ``step`` per level around ``settled``, ``n`` records split evenly."""
    per = n // levels
    x = np.repeat(np.arange(levels), per)
    p = settled - step * (np.arange(levels) - (levels - 1) / 2)
    y = rng.random((draws, x.size)) < np.repeat(p, per)
    n1 = y.sum(1, keepdims=True)
    ry = np.where(y, x.size - n1 + (n1 + 1) / 2, (x.size - n1 + 1) / 2)  # ranks of a binary y
    rx = stats.rankdata(x)
    r = ((ry - ry.mean(1, keepdims=True)) * (rx - rx.mean())).sum(1)
    r /= np.sqrt(((ry - ry.mean(1, keepdims=True)) ** 2).sum(1) * ((rx - rx.mean()) ** 2).sum())
    t = r * np.sqrt((x.size - 2) / np.maximum(1 - r * r, 1e-12))
    return float(np.mean(stats.t.cdf(t, x.size - 2) < 0.05))


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
    c: float = 0.005,
    planted: int = 600,
    draws: int = 4000,
    seed: int = 0,
    h3_step_small: float = 0.02,
    h3_step_large: float = 0.05,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    n_c = int(planted * settled)
    for n in records:
        n_cv, n_typed = n * settled * cv_share, n * settled * (1 - cv_share)
        lo, hi = _wilson(np.array([e_cv * n_cv, e_typed * n_typed]), np.array([n_cv, n_typed]))
        half = (hi - lo) / 2
        d_cv_hat, _ = _draw_d(int(n_cv), e_cv, d, draws, rng, c, n_c)
        d_typed_hat, _ = _draw_d(int(n_typed), e_typed, d, draws, rng, c, n_c)
        a, n_a = _draw_d(int(n_cv), e_cv, d_cv, draws, rng, c, n_c)
        b, n_b = _draw_d(int(n_typed), e_typed, d_typed, draws, rng, c, n_c)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (b - a) / np.sqrt(a * (1 - a) / n_a + b * (1 - b) / n_b)
        rows.append([
            n, n_cv, n_typed, half[0], half[1],
            power_two_prop(e_cv, e_typed, n_cv, n_typed),
            power_two_prop(e_cv, e_typed_large, n_cv, n_typed),
            *np.nanpercentile(d_cv_hat, [2.5, 97.5]),
            *np.nanpercentile(d_typed_hat, [2.5, 97.5]),
            float(np.nanmean(z > Z_ONE_SIDED)),
            level_power(n, settled, h3_step_small, draws, rng),
            level_power(n, settled, h3_step_large, draws, rng),
        ])  # fmt: skip
    return pd.DataFrame(rows, columns=COLUMNS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--records", type=int, nargs="+", default=[1000, 2000, 3000])
    ap.add_argument("--draws", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--c", type=float, default=0.005, help="assumed consensus error")
    ap.add_argument("--planted", type=int, default=600, help="planted records c is measured on")
    a = ap.parse_args(argv)
    t = table(a.records, c=a.c, planted=a.planted, draws=a.draws, seed=a.seed)
    print(t.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
