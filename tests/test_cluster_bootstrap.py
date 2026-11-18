"""The observer-clustered bootstrap of scripts/levels_outcome.py."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from what_to_id import cluster_bootstrap

LEVELS = {0: "none", 1: "easy"}
ROOT = Path(__file__).resolve().parents[1]


def _toy(per_observer: int, observers: int, clustered: bool) -> pd.DataFrame:
    """Level 1 corrects 20% of records, level 0 none; `clustered` puts all of an observer's
    level-1 corrections on 1 in 5 observers instead of spreading them."""
    rng = np.random.default_rng(0)
    n = per_observer * observers
    user = np.repeat(np.arange(observers), per_observer)
    level = np.tile([0, 1], n // 2)
    if clustered:
        corrected = (user % 5 == 0) & (level == 1)
    else:
        corrected = (rng.random(n) < 0.2) & (level == 1)  # 20% of level 1
    return pd.DataFrame(
        {"user_id": user, "level": level, "corrected": corrected, "left": False, "to_x": corrected}
    )


def _width(row: dict, key: str) -> float:
    lo, hi = row[key]
    return hi - lo


def test_same_seed_same_intervals_and_seed_changes_them():
    s = _toy(20, 100, clustered=False)
    a = cluster_bootstrap.level_stats(s, LEVELS, 1000, seed=7)
    assert str(a) == str(cluster_bootstrap.level_stats(s, LEVELS, 1000, seed=7))  # str: NaN != NaN
    assert str(a) != str(cluster_bootstrap.level_stats(s, LEVELS, 1000, seed=8))


def test_clustering_widens_the_interval_against_independent_records():
    s = _toy(20, 100, clustered=True)
    clustered = cluster_bootstrap.level_stats(s, LEVELS, 1000, seed=1)["easy"]
    spread = cluster_bootstrap.level_stats(_toy(20, 100, False), LEVELS, 1000, seed=1)["easy"]
    # same 20% rate in both toys, but only the clustered one lumps it on a fifth of the observers
    assert _width(clustered, "corrected_per_1000_ci") > 2 * _width(spread, "corrected_per_1000_ci")
    # the record-level Wilson interval cannot tell the two apart
    spec = importlib.util.spec_from_file_location("lo", ROOT / "scripts" / "levels_outcome.py")
    lo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lo)
    k = int(s[s["level"] == 1]["corrected"].sum())
    wilson = lo.wilson(k, int((s["level"] == 1).sum()))
    assert wilson[1] - wilson[0] < 0.5 * _width(clustered, "corrected_per_1000_ci")
    assert clustered["corrected_diff_per_1000"] == pytest.approx(200.0)
    lo_, hi = clustered["corrected_diff_per_1000_ci"]
    assert lo_ < 200 < hi


def test_one_record_per_observer_is_the_independent_case():
    s = _toy(1, 4000, clustered=False)
    row = cluster_bootstrap.level_stats(s, LEVELS, 1000, seed=3)["easy"]
    spec = importlib.util.spec_from_file_location("lo", ROOT / "scripts" / "levels_outcome.py")
    lo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lo)
    wilson = lo.wilson(int(s[s["level"] == 1]["corrected"].sum()), 2000)
    assert _width(row, "corrected_per_1000_ci") == pytest.approx(wilson[1] - wilson[0], rel=0.15)


def test_a_record_without_observer_is_its_own_cluster():
    codes = cluster_bootstrap.observer_codes(pd.Series([5, None, 5, None], dtype="Int64"))
    assert codes[0] == codes[2] and len({*codes}) == 3


@pytest.mark.filterwarnings("ignore:All-NaN")  # no level-0 corrections: the ratio is undefined
def test_ratio_columns_and_reference_level_keys():
    s = _toy(20, 100, clustered=True)
    out = cluster_bootstrap.level_stats(s, LEVELS, 1000, seed=1, ratio_cols=("to_x",))
    assert set(out["none"]) == {"corrected_per_1000_ci", "left_per_1000_ci"}
    assert "to_x_rr_ci" in out["easy"] and "corrected_rr_ci" in out["easy"]


def test_reps_below_a_thousand_and_missing_reference_are_errors():
    s = _toy(2, 10, clustered=False)
    with pytest.raises(ValueError, match="at least 1000"):
        cluster_bootstrap.level_stats(s, LEVELS, 999, seed=1)
    with pytest.raises(ValueError, match="no-level reference"):
        cluster_bootstrap.level_stats(s, {1: "easy"}, 1000, seed=1)


def test_cohort_carries_the_observer_and_drops_the_excluded_pool_after_levelling(tmp_path):
    spec = importlib.util.spec_from_file_location("lo", ROOT / "scripts" / "levels_outcome.py")
    lo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lo)
    ids = np.arange(1, 41)
    own = np.random.default_rng(0).uniform(0.3, 0.7, 40)
    pd.DataFrame(
        {"id": ids, "taxon_name": "Sp a", "own": own, "other": own - 0.01, "other_name": "Sp b"}
    ).to_parquet(tmp_path / "scores.parquet")
    pd.DataFrame(
        {"id": ids, "taxon_id": 1, "rank": "species", "iconic_taxon": "Aves", "user_id": ids % 7}
    ).to_parquet(tmp_path / "before.parquet")
    pd.DataFrame({"id": ids[::2], "taxon_id": 1, "taxon_name": "Sp a"}).to_parquet(
        tmp_path / "after.parquet"
    )
    pd.DataFrame({"id": ids[:10]}).to_parquet(tmp_path / "old.parquet")
    args = (tmp_path / "scores.parquet", tmp_path / "before.parquet", tmp_path / "after.parquet")
    everyone = lo.cohort(*args)
    held = lo.cohort(*args, exclude=tmp_path / "old.parquet")
    assert "user_id" in lo.COHORT_COLUMNS and set(everyone["user_id"]) == set(range(7))
    assert sorted(held["id"]) == list(range(11, 41))
    # levels came from all 40 records, so a held-out record has the level it had in the full run
    full = everyone.set_index("id")["level"]
    assert (held.set_index("id")["level"] == full.loc[held["id"]]).all()
