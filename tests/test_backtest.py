import numpy as np
import pandas as pd

from what_to_id.backtest import base_orders, compare, order_by, outcomes, top_k


def queue():
    return pd.DataFrame(
        {
            "created_at": ["2025-09-01T00:00:00Z", "2025-09-03T00:00:00Z", "2025-09-02T00:00:00Z"],
            "days_to_rg": [5.0, 60.0, np.nan],
            "grade_now": ["research", "research", "needs_id"],
            "relation": ["same", "corrected", "none"],
            "s": [0.2, np.nan, 0.9],
        }
    )


def test_outcomes():
    o = outcomes(queue())
    assert o.fast.tolist() == [1, 0, 0] and o.slow.tolist() == [0, 1, 0]
    assert o.stuck.tolist() == [0, 0, 1] and o.corrected.tolist() == [0, 1, 0]


def test_orders_and_nan_last():
    q = queue()
    b = base_orders(q)
    assert b["newest"].tolist() == [1, 2, 0] and b["oldest"].tolist() == [0, 2, 1]
    assert order_by(q, "s").tolist() == [2, 0, 1]


def test_top_k_and_compare():
    q = queue()
    t = top_k(outcomes(q), np.array([1, 2, 0]), [1, 3])
    assert t.loc[1, "corrected"] == 1.0 and abs(t.loc[3, "stuck"] - 1 / 3) < 1e-9
    c = compare(q, base_orders(q), [2])
    assert set(c.order) == {"newest", "oldest"} and (c.rand_lo <= c.rand_hi).all()
