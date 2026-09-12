import numpy as np
import pytest

from what_to_id.power import Scenario, _queue, power, simulate

SMALL = {"group_counts": (4000, 2000), "window": 300, "depth_median": 60.0}


def test_queue_counts_positions_once():
    rng = np.random.default_rng(0)
    whole, win = _queue(np.array([50, 20]), np.array([1.0, 1.0]), 1000, 30, rng)
    assert (whole, win) == (50, 30)
    assert _queue(np.array([], dtype=np.int64), np.array([]), 10, 5, rng) == (0, 0)
    assert _queue(np.array([500]), np.array([1.0]), 100, 1000, rng) == (100, 100)


def test_null_is_calibrated():
    sc = Scenario(8, 0.0, "sets", **SMALL)
    ref = simulate(sc, 600, seed=1)["window"]
    new = simulate(sc, 600, seed=2)["window"]
    thr = np.quantile(np.abs(ref), 0.95)
    assert 0.02 <= (np.abs(new) > thr).mean() <= 0.09


def test_rotation_shrinks_null_spread():
    sets = simulate(Scenario(10, 0.0, "sets", **SMALL), 400, seed=3)["window"]
    rot = simulate(Scenario(10, 0.0, "rotation", **SMALL), 400, seed=3)["window"]
    assert rot.std() < 0.5 * sets.std()


def test_lift_moves_the_difference_and_is_deterministic():
    sc = Scenario(20, 0.5, "rotation", **SMALL)
    a = power(sc, reps=200, seed=4)
    assert a == power(sc, reps=200, seed=4)
    assert a["window"]["mean_diff"] > 0 and a["window"]["power"] > 0.5


@pytest.mark.parametrize(
    "kw", [{"design": "cohort"}, {"n_identifiers": 0}, {"background": 1.0}, {"lift": -1.0}]
)
def test_scenario_rejects_bad_input(kw):
    base = {"n_identifiers": 5, "lift": 0.1}
    with pytest.raises(ValueError):
        Scenario(**{**base, **kw})
