import numpy as np
import pandas as pd

from what_to_id.surprise import score, tail_prob, taxon_key

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


def test_score_groups_by_key():
    ref = pd.DataFrame({"key": [7] * 200, "x": RNG.normal(size=200), "y": RNG.normal(size=200)})
    pool = pd.DataFrame({"key": [7, 7, 8, None], "x": [0.0, 5.0, 0.0, 0.0], "y": [0.0] * 4})
    got = score(pool, ref, ["x", "y"], h=0.5)
    assert got[0] < 0.3 and got[1] == 1.0 and got[2] == 1.0 and np.isnan(got[3])
