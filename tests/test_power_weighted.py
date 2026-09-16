import json

import numpy as np
import pandas as pd
import pytest

from what_to_id.power_weighted import (
    WeightedScenario,
    blitz_lists,
    main,
    pool_frames,
    preview_lists,
    weighted_power,
    worked,
)

GROUPS = ("A", "B")
COUNTS = (4000, 2000)
SMALL = {"groups": GROUPS, "group_counts": COUNTS, "batch_size": 20, "max_batches": 5}


def _pool(scores_a, scores_b) -> pd.DataFrame:
    scores = np.concatenate([scores_a, scores_b])
    n = scores.size
    return pd.DataFrame(
        {
            "id": np.arange(1, n + 1, dtype=np.int64),
            "iconic_taxon": ["A"] * len(scores_a) + ["B"] * len(scores_b),
            "created_at": pd.date_range("2026-09-01", periods=n, freq="min", tz="UTC"),
            "cell_score": scores,
        }
    )


FLAT = _pool(np.full(300, 0.5), np.full(200, 0.5))


@pytest.mark.parametrize("exposure", ["preview", "blitz"])
def test_zero_effect_rejects_near_alpha(exposure):
    # Equal scores and ID rates: both lists are the same, so rejections are false positives.
    sc = WeightedScenario(15, 1.0, exposure, n_arms=2, **SMALL)
    r = weighted_power(sc, FLAT, reps=400, seed=1, alpha=0.2, flips=500)
    assert r["level"] == 0.2
    assert 0.12 <= r["power"] + r["behind"] <= 0.28


def test_larger_id_factor_gives_more_power():
    got = [
        weighted_power(
            WeightedScenario(15, f, "preview", n_arms=2, **SMALL), FLAT, reps=200, seed=2
        )["power"]
        for f in (1.0, 1.3, 1.8)
    ]
    assert got[0] < got[1] < got[2]
    assert got[2] > 0.8


def test_a_binding_cap_gives_the_data_poor_list_higher_scores():
    # Half the records score 0.1 and half 0.9. In the preview every record is served, so the
    # lists meet the same scores; in the blitz the cap keeps only the data-poor list's top.
    rng = np.random.default_rng(0)
    split = _pool(rng.choice([0.1, 0.9], 300), rng.choice([0.1, 0.9], 200))
    kw = {**SMALL, "n_arms": 2}
    prev = weighted_power(
        WeightedScenario(15, 1.0, "preview", **{**kw, "max_batches": None}), split, reps=150, seed=3
    )
    blitz = weighted_power(
        WeightedScenario(15, 1.0, "blitz", **{**kw, "max_batches": 2}), split, reps=150, seed=3
    )
    assert abs(prev["score_met_data_poor"] - prev["score_met_control"]) < 0.1
    assert blitz["score_met_data_poor"] > 0.85 > 0.6 > blitz["score_met_control"]
    assert blitz["power"] > 0.9 > prev["power"] + prev["behind"]


def test_worked_starts_at_a_batch_and_wraps():
    rng = np.random.default_rng(0)
    seq = np.arange(50.0)
    starts = set()
    for _ in range(60):
        got = worked(seq, 15, 20, rng)
        assert got.size == 15 and got[0] in (0, 20, 40)
        assert np.array_equal(got, (got[0] + np.arange(15)) % 50)
        starts.add(got[0])
    assert starts == {0, 20, 40}
    assert sorted(worked(seq, 500, 20, rng)) == list(seq)
    assert worked(seq, 0, 20, rng).size == 0
    assert worked(seq[:0], 10, 20, rng).size == 0


def test_served_lists_follow_the_cap():
    rng = np.random.default_rng(1)
    pool = _pool(rng.random(300), rng.random(200))
    frames = pool_frames(pool, GROUPS)
    sc = WeightedScenario(5, 1.0, "preview", n_arms=2, **SMALL)
    for (c, t), full in zip(preview_lists(frames, sc, rng), (300, 200), strict=True):
        assert c.size <= 100 and t.size <= 100
        means = [t[i : i + 20].mean() for i in range(0, t.size, 20)]
        assert means == sorted(means, reverse=True)
        assert c.size + t.size <= full
    uncapped = WeightedScenario(5, 1.0, "preview", n_arms=2, **{**SMALL, "max_batches": None})
    sizes = [c.size + t.size for c, t in preview_lists(frames, uncapped, rng)]
    assert sizes == [300, 200]
    for c, t in blitz_lists(frames, WeightedScenario(5, 1.0, "blitz", n_arms=2, **SMALL), rng):
        assert c.size == t.size == 100
        # Each data-poor list keeps the top 100 of about 2000 or 1000 draws.
        assert t.min() > np.quantile(pool["cell_score"], 0.8)


@pytest.mark.parametrize(
    "kw",
    [
        {"exposure": "daily"},
        {"n_identifiers": 0},
        {"id_factor": 0.0},
        {"id_factor": -0.5},
        {"id_factor": float("nan")},
        {"n_arms": 1},
        {"batch_size": 0},
        {"max_batches": 0},
        {"groups": ("A",), "group_counts": (10, 20)},
        {"groups": (), "group_counts": ()},
        {"group_counts": (4000, 0)},
        {"depths": ()},
    ],
)
def test_scenario_rejects_bad_input(kw):
    base = {"n_identifiers": 5, **SMALL}
    with pytest.raises(ValueError):
        WeightedScenario(**{**base, **kw})


@pytest.mark.parametrize(
    "pool, kw, match",
    [
        (FLAT.drop(columns="cell_score"), {}, "missing columns"),
        (FLAT[FLAT["iconic_taxon"] == "A"], {}, "no records for groups"),
        (FLAT, {"reps": 0}, "reps"),
        (FLAT, {"alpha": 1.0}, "alpha"),
    ],
)
def test_weighted_power_rejects_bad_input(pool, kw, match):
    with pytest.raises(ValueError, match=match):
        weighted_power(WeightedScenario(5, 1.0, **SMALL), pool, **kw)


def test_cli_writes_weighted_and_plain_rows(tmp_path):
    rng = np.random.default_rng(4)
    pool = _pool(rng.random(300), rng.random(200)).rename(columns={"iconic_taxon": "g"})
    groups = {"A": "Plantae", "B": "Insecta"}
    pool["iconic_taxon"] = pool.pop("g").map(groups)
    others = pd.DataFrame(
        {
            "id": np.arange(10_000, 10_080),
            "iconic_taxon": np.repeat(
                [
                    "Fungi",
                    "Arachnida",
                    "Mollusca",
                    "Aves",
                    "Mammalia",
                    "Actinopterygii",
                    "Reptilia",
                    "Amphibia",
                ],
                10,
            ),
            "created_at": pd.Timestamp("2026-09-01", tz="UTC"),
            "cell_score": 0.2,
        }
    )
    path = tmp_path / "pool.parquet"
    pd.concat([pool, others], ignore_index=True).to_parquet(path)
    out = tmp_path / "rows.json"
    argv = ["--pool", str(path), "--identifiers", "4", "--factors", "0.8", "--lifts", "0.2"]
    assert main([*argv, "--reps", "3", "--out", str(out)]) == 0
    rows = json.loads(out.read_text())
    assert [r["outcome"] for r in rows] == ["weighted", "weighted", "plain"]
    assert [r["scenario"]["exposure"] for r in rows[:2]] == ["preview", "blitz"]
    assert rows[0]["scenario"]["max_batches"] == 20
    nocap = ["--exposures", "blitz", "--lifts", "", "--max-batches", "0"]
    assert main([*argv, *nocap, "--reps", "3", "--out", str(out)]) == 0
    rows = json.loads(out.read_text())
    assert [r["outcome"] for r in rows] == ["weighted"]
    assert rows[0]["scenario"]["max_batches"] is None
