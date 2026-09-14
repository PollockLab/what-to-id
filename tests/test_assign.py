import numpy as np
import pandas as pd
import pytest

from what_to_id.assign import assign, assign_keyed, strata

from .conftest import make_pool

ARMS = ["recency", "gap_first", "similarity"]
KEY = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddee")
KEY2 = bytes.fromhex("ff112233445566778899aabbccddeeff00112233445566778899aabbccddee")


def test_strata_format():
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "iconic_taxon": ["Aves", None, "Insecta"],
            "user_id": pd.array([7, 7, None], dtype="Int64"),
        }
    )
    s = strata(pool)
    assert s.name == "stratum"
    assert s.iloc[0].startswith("Aves|") and s.iloc[0][-1] in "012"
    assert s.iloc[1].startswith("Unknown|")
    assert s.iloc[0].split("|")[1] == s.iloc[1].split("|")[1]  # same user, same bucket
    assert s.iloc[2] == "Insecta|na"


def test_balanced_per_stratum(pool):
    a = assign(pool, ARMS, seed=0)
    assert list(a.columns) == ["id", "arm", "stratum", "seed"]
    assert len(a) == len(pool)
    assert set(a["id"]) == set(pool["id"])
    assert (a["seed"] == 0).all()
    counts = a.groupby(["stratum", "arm"]).size().unstack(fill_value=0)
    assert ((counts.max(axis=1) - counts.min(axis=1)) <= 1).all()


def test_remainder_rotates():
    # 3 strata each with 4 records over 3 arms: the extra record must not always go to arm 0.
    pool = make_pool(12, groups=["Aves", "Insecta", "Plantae"], n_users=1)
    pool["iconic_taxon"] = np.repeat(["Aves", "Insecta", "Plantae"], 4)
    a = assign(pool, ARMS, seed=0)
    firsts = a.groupby("stratum")["arm"].agg(lambda s: s.value_counts().idxmax())
    assert firsts.nunique() > 1


def test_seed_reproducible_and_sensitive(pool):
    a0 = assign(pool, ARMS, seed=0)
    a0b = assign(pool, ARMS, seed=0)
    a1 = assign(pool, ARMS, seed=1)
    pd.testing.assert_frame_equal(a0, a0b)
    assert not a0["arm"].equals(a1["arm"])


def test_adding_stratum_keeps_others(pool):
    a = assign(pool, ARMS, seed=0)
    extra = make_pool(30, seed=9, groups=["Mollusca"])
    extra["id"] += 100000
    b = assign(pd.concat([pool, extra], ignore_index=True), ARMS, seed=0)
    merged = a.merge(b, on="id", suffixes=("_a", "_b"))
    assert (merged["arm_a"] == merged["arm_b"]).all()


def test_observer_split_across_arms():
    pool = make_pool(90, groups=["Aves"], n_users=1)
    a = assign(pool, ARMS, seed=0)
    assert a["stratum"].nunique() == 1
    counts = a["arm"].value_counts()
    assert counts.max() - counts.min() <= 1


def test_validation(pool):
    with pytest.raises(ValueError):
        assign(pool, [], seed=0)
    with pytest.raises(ValueError):
        assign(pool, ["a", "a"], seed=0)
    dup = pd.concat([pool, pool.head(1)], ignore_index=True)
    with pytest.raises(ValueError):
        assign(dup, ARMS, seed=0)


def test_keyed_schema_and_seed_marker(pool):
    a = assign_keyed(pool, ARMS, key=KEY)
    assert list(a.columns) == ["id", "arm", "stratum", "seed"]
    assert len(a) == len(pool)
    assert set(a["id"]) == set(pool["id"])
    assert (a["seed"] == -1).all()
    assert set(a["arm"]) <= set(ARMS)
    assert list(a["id"]) == sorted(a["id"])


def test_keyed_deterministic(pool):
    a = assign_keyed(pool, ARMS, key=KEY)
    b = assign_keyed(pool, ARMS, key=KEY)
    pd.testing.assert_frame_equal(a, b)


def test_keyed_different_keys_differ(pool):
    a = assign_keyed(pool, ARMS, key=KEY)
    b = assign_keyed(pool, ARMS, key=KEY2)
    assert not a["arm"].equals(b["arm"])


def test_keyed_stable_across_pool_changes(pool):
    a = assign_keyed(pool, ARMS, key=KEY)
    shrunk = pool.iloc[: len(pool) // 2].reset_index(drop=True)
    extra = make_pool(30, seed=9, groups=["Mollusca"])
    extra["id"] += 100000
    grown = pd.concat([pool, extra], ignore_index=True)
    b_shrunk = assign_keyed(shrunk, ARMS, key=KEY)
    b_grown = assign_keyed(grown, ARMS, key=KEY)
    merged_shrunk = a.merge(b_shrunk, on="id", suffixes=("_a", "_b"))
    merged_grown = a.merge(b_grown, on="id", suffixes=("_a", "_b"))
    assert (merged_shrunk["arm_a"] == merged_shrunk["arm_b"]).all()
    assert (merged_grown["arm_a"] == merged_grown["arm_b"]).all()


def test_keyed_roughly_balanced():
    pool = make_pool(20000, groups=["Aves"], n_users=200)
    two_arms = ["a", "b"]
    a = assign_keyed(pool, two_arms, key=KEY)
    share = a["arm"].value_counts(normalize=True)
    assert abs(share["a"] - 0.5) < 0.02
    assert abs(share["b"] - 0.5) < 0.02


def test_keyed_validation(pool):
    with pytest.raises(ValueError):
        assign_keyed(pool, [], key=KEY)
    with pytest.raises(ValueError):
        assign_keyed(pool, ["a", "a"], key=KEY)
    with pytest.raises(ValueError):
        assign_keyed(pool, ARMS, key=b"")
    dup = pd.concat([pool, pool.head(1)], ignore_index=True)
    with pytest.raises(ValueError):
        assign_keyed(dup, ARMS, key=KEY)
