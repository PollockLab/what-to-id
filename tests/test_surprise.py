import numpy as np
import pandas as pd

from what_to_id.surprise import geo_scores, main, score, tail_prob, taxon_key

RNG = np.random.default_rng(0)


def test_far_point_is_more_surprising_than_centre():
    ref = RNG.normal(size=(400, 2))
    got = tail_prob(ref, np.array([[0.0, 0.0], [4.0, 4.0]]), h=0.5)
    assert got[0] < 0.2 and got[1] == 1.0


def test_tail_prob_is_roughly_uniform_on_draws_from_the_reference():
    ref = RNG.normal(size=(1000, 2))
    got = tail_prob(ref, RNG.normal(size=(1000, 2)), h=0.4)
    assert 0.4 < got.mean() < 0.6


def test_too_few_references_score_one_and_nan_query_stays_nan():
    assert tail_prob(np.zeros((3, 2)), np.zeros((2, 2)), h=1.0).tolist() == [1.0, 1.0]
    got = tail_prob(RNG.normal(size=(50, 2)), np.array([[np.nan, 0.0]]), h=1.0)
    assert np.isnan(got[0])


def test_taxon_key_prefers_species_then_genus():
    rl = {1: 70, 2: 20, 3: 10, 4: 5, 5: 11}
    assert taxon_key((1, 2, 3, 4), rl) == 3
    assert taxon_key((1, 2, 5), rl) == 2
    assert taxon_key((1,), rl) is None


def _geo_inputs():
    taxa = pd.DataFrame(
        {
            "taxon_id": [1, 20, 30, 31],
            "ancestry": [None, "1", "1/20", "1/20"],
            "rank_level": [70, 20, 10, 10],
        }
    )
    n = 100
    ref = pd.DataFrame(
        {
            "latitude": 49 + RNG.normal(0, 0.05, n),
            "longitude": -123 + RNG.normal(0, 0.05, n),
            "positional_accuracy": [10] * n,
            "taxon_id": [30] * n,
            "quality_grade": ["research"] * (n - 2) + ["needs_id", "research"],
            "observed_on": ["2024-06-01"] * (n - 1) + ["2026-01-01"],
        }
    )
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "lat": [49.0, 55.0, 49.0, 49.0],
            "lon": [-123.0, -130.0, -123.0, -123.0],
            "taxon_id": pd.array([30, 30, 31, None], dtype="Int64"),
        }
    )
    return pool, ref, taxa


def test_geo_scores_against_open_data_rows():
    pool, ref, taxa = _geo_inputs()
    s = geo_scores(pool, ref, taxa, before="2025-01-01")
    assert s.id.tolist() == [1, 2, 3, 4]
    got = s.surprise.to_numpy()
    assert got[0] < 0.5 and got[1] == 1.0 and got[2] == 1.0 and np.isnan(got[3])


def test_main_writes_id_and_surprise(tmp_path):
    pool, ref, taxa = _geo_inputs()
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    ref.to_csv(tmp_path / "obs.tsv.gz", sep="\t", index=False)
    taxa.to_csv(tmp_path / "taxa.csv.gz", sep="\t", index=False)
    args = [str(tmp_path / "pool.parquet"), "--ref", str(tmp_path / "obs.tsv.gz")]
    args += ["--taxa", str(tmp_path / "taxa.csv.gz"), "--before", "2025-01-01"]
    assert main([*args, "--out", str(tmp_path / "s.parquet")]) == 0
    assert pd.read_parquet(tmp_path / "s.parquet").columns.tolist() == ["id", "surprise"]


def test_score_groups_by_key():
    ref = pd.DataFrame({"key": [7] * 200, "x": RNG.normal(size=200), "y": RNG.normal(size=200)})
    pool = pd.DataFrame({"key": [7, 7, 8, None], "x": [0.0, 5.0, 0.0, 0.0], "y": [0.0] * 4})
    got = score(pool, ref, ["x", "y"], h=0.5)
    assert got[0] < 0.3 and got[1] == 1.0 and got[2] == 1.0 and np.isnan(got[3])
