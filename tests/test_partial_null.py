import numpy as np
import pandas as pd
import pytest

from what_to_id.analysis import holm, record_shuffle_p
from what_to_id.calibration import interval

ARMS = ["gap_first", "novelty", "recency", "similarity"]
N, R, B = 600, 1000, 999


@pytest.mark.parametrize(
    ("tested", "other"), [("gap_first", "similarity"), ("similarity", "gap_first")]
)
def test_record_shuffle_p_is_exact_under_a_partial_null(tested, other):
    """Another list with a real effect must not inflate the test of a list equal to the control.

    Every record on recency and on the tested list is identified, none on the other list or
    novelty, with each record's list drawn independently and uniformly. The tested list equals the
    control, so its Holm-adjusted rejection rate must stay near or below 0.05.
    """
    y = {"recency": 1.0, tested: 1.0, other: 0.0, "novelty": 0.0}
    rng = np.random.default_rng(20261026)
    rejections = 0
    for r in range(R):
        arm = np.array(ARMS)[rng.integers(4, size=N)]
        served = pd.DataFrame({"id": np.arange(N), "arm": arm})
        totals = pd.Series([y[a] for a in arm], index=served["id"])
        p = {
            t: record_shuffle_p(
                totals,
                served,
                arm=t,
                control="recency",
                arms=ARMS,
                reps=B,
                seed=r,
                alternative="greater",
            )
            for t in (tested, other)
        }
        rejections += holm(p)[tested] < 0.05
    ci = interval(int(rejections), R)
    print(tested, ci)
    assert ci["mc_interval_95"][1] <= 0.07
