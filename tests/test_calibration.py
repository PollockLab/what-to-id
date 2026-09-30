import hashlib
import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from what_to_id import calibration
from what_to_id.arms import Recency
from what_to_id.calibration import CUTOFF, START, Scenario, diagnose, interval, simulate
from what_to_id.confirmatory import confirmatory


def _analyse(events, served):
    users = sorted(events["user_id"].unique())
    return confirmatory(
        events, served, control="recency", start=START, cutoff=CUTOFF, users=users, reps=100, seed=4
    )


def test_events_use_capped_keyed_arms_and_repeated_ids_do_not_change_analysis():
    sc = Scenario(participants=8)
    events, served = simulate(sc, seed=5)
    single, other_served = simulate(replace(sc, duplicate_events=False), seed=5)
    pd.testing.assert_frame_equal(served, other_served)
    assert served.groupby("arm").size().eq(sc.batch_size * sc.max_batches).all()
    assert not served["id"].duplicated().any()
    assert len(events) == 2 * len(single)
    pd.testing.assert_frame_equal(_analyse(events, served), _analyse(single, served))
    zero_user = events.loc[events["user_id"].ne(1)]
    result = confirmatory(
        zero_user,
        served,
        control="recency",
        start=START,
        cutoff=CUTOFF,
        users=list(range(1, 9)),
        reps=100,
    )
    assert result["n_identifiers"].eq(7).all()


def test_diagnostic_is_deterministic_and_recovers_injected_effect():
    sc = Scenario(participants=8)
    null = diagnose(sc, reps=6, seed=8, flips=100)
    assert null == diagnose(sc, reps=6, seed=8, flips=100)
    effect = diagnose(replace(sc, effect=0.5), reps=6, seed=8, flips=100)
    got = effect["comparisons"]["similarity"]
    assert got["mean_participant_difference"] > 10
    assert got["holm"]["rejections"] > null["comparisons"]["similarity"]["holm"]["rejections"]
    assert effect["family_any_rejection"]["replicates"] == 6


def test_monte_carlo_interval_boundaries():
    assert interval(0, 100)["mc_interval_95"][0] == 0
    assert interval(100, 100)["mc_interval_95"][1] == 1
    lo, hi = interval(5, 100)["mc_interval_95"]
    assert lo < 0.05 < hi
    with pytest.raises(ValueError, match="reps"):
        interval(0, 0)


@pytest.mark.parametrize("kwargs", [{"effect": float("nan")}, {"participants": 0}, {"effect": 1}])
def test_bad_scenarios_fail(kwargs):
    with pytest.raises(ValueError):
        Scenario(**kwargs)


def test_small_pool_attempts_are_equal_and_precede_event_time(monkeypatch):
    real_rng = np.random.default_rng
    real_order = Recency.order

    class AllSuccess:
        def __init__(self, seed):
            self.rng = real_rng(seed)

        def __getattr__(self, name):
            return getattr(self.rng, name)

        def random(self, size):
            return np.zeros(size)

    def check_order(self, pool, *, seed):
        assert pool["created_at"].max() < pd.Timestamp(START)
        return real_order(self, pool, seed=seed)

    monkeypatch.setattr(calibration.np.random, "default_rng", AllSuccess)
    monkeypatch.setattr(Recency, "order", check_order)
    events, served = simulate(Scenario(participants=1, pool_size=40), seed=5)
    assert served.groupby("arm").size().nunique() > 1
    counts = events.merge(served, on="id").groupby("arm").size()
    assert counts.nunique() == 1
    assert counts.iloc[0] == 2 * served.groupby("arm").size().min()


def test_no_events_reports_omission_and_finite_json(monkeypatch):
    _, served = simulate(Scenario(), seed=5)
    empty = pd.DataFrame(columns=["id", "user_id", "created_at", "taxon_rank", "observer_id"])
    monkeypatch.setattr(calibration, "simulate", lambda sc, seed: (empty, served))
    result = diagnose(Scenario(participants=1), reps=1)
    assert result["omitted_zero_id_participants_across_replicates"] == 1
    assert result["family_any_rejection"]["rejections"] == 0
    json.dumps(result, allow_nan=False)


def test_shared_record_propensities_and_independent_rng_domains(monkeypatch):
    q = calibration.record_propensities(1000, seed=5)
    assert set(q) == {0.1, 0.5}
    np.testing.assert_array_equal(q, calibration.record_propensities(1000, seed=5))
    assert not np.array_equal(q, calibration.record_propensities(1000, seed=6))
    np.testing.assert_array_equal(
        calibration.response_probability(0.1, q, 1, 0),
        calibration.response_probability(0.5, q, 1, 0),
    )
    # Removing all record heterogeneity must leave the participant RNG stream and key alone.
    baseline, served = simulate(Scenario(), seed=5)
    _, shared_served = simulate(Scenario(record_difficulty_strength=1), seed=5)
    pd.testing.assert_frame_equal(served, shared_served)
    monkeypatch.setattr(
        calibration, "record_propensities", lambda pool_size, seed: np.full(pool_size, 0.5)
    )
    unchanged, same_served = simulate(Scenario(), seed=5)
    pd.testing.assert_frame_equal(baseline, unchanged)
    pd.testing.assert_frame_equal(served, same_served)
    # The pinned digest predates the constant observer column, so it hashes the other columns.
    pinned = baseline.drop(columns="observer_id").to_dict("records")
    digest = hashlib.sha256(json.dumps(pinned, sort_keys=True).encode())
    assert digest.hexdigest() == "0796e33a32b2a83d9b87a3bd6b16e744138a97a5aa422527b136c384558f6fab"


def test_effect_recovery_uses_enrolled_denominator(monkeypatch):
    events, served = simulate(Scenario(participants=1), seed=5)
    events.attrs["attempts_per_arm"] = 20
    monkeypatch.setattr(calibration, "simulate", lambda sc, seed: (events, served))
    result = diagnose(Scenario(participants=2, effect=0.2), reps=1)
    got = result["comparisons"]["similarity"]
    assert got["expected_injected_difference_per_enrolled_participant"] == 2
    assert got["mean_difference_per_enrolled_participant"] == got["mean_participant_difference"] / 2


@pytest.mark.parametrize("strength", [-1, 1.1, float("nan")])
def test_bad_record_strength_fails(strength):
    with pytest.raises(ValueError, match="record_difficulty_strength"):
        Scenario(record_difficulty_strength=strength)
