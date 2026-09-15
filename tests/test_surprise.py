import numpy as np
import pandas as pd
import pytest

from what_to_id.surprise import geo_scores, main, prior_scores, score, tail_prob, taxon_key

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
    # id 1 and 2 share key 30, with 98 qualifying references (100 rows minus one needs_id and
    # one observed after the freeze); id 3's key (31) has no reference rows; id 4 has no key.
    n_ref = s.n_ref.to_numpy()
    assert n_ref[0] == 98 and n_ref[1] == 98 and n_ref[2] == 0 and np.isnan(n_ref[3])


def test_main_writes_id_and_surprise(tmp_path):
    pool, ref, taxa = _geo_inputs()
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    ref.to_csv(tmp_path / "obs.tsv.gz", sep="\t", index=False)
    taxa.to_csv(tmp_path / "taxa.csv.gz", sep="\t", index=False)
    args = [str(tmp_path / "pool.parquet"), "--ref", str(tmp_path / "obs.tsv.gz")]
    args += ["--taxa", str(tmp_path / "taxa.csv.gz"), "--before", "2025-01-01"]
    assert main([*args, "--out", str(tmp_path / "s.parquet")]) == 0
    assert pd.read_parquet(tmp_path / "s.parquet").columns.tolist() == ["id", "surprise", "n_ref"]


def test_score_groups_by_key():
    ref = pd.DataFrame({"key": [7] * 200, "x": RNG.normal(size=200), "y": RNG.normal(size=200)})
    pool = pd.DataFrame({"key": [7, 7, 8, None], "x": [0.0, 5.0, 0.0, 0.0], "y": [0.0] * 4})
    got = score(pool, ref, ["x", "y"], h=0.5)
    assert got[0] < 0.3 and got[1] == 1.0 and got[2] == 1.0 and np.isnan(got[3])


# taxon 300/301 and 310/311 are two genus/species pairs under family 200, itself under order 100.
# 320/321 is a second genus/species pair, also under family 210 under order 100.
def _prior_taxa():
    return pd.DataFrame(
        {
            "taxon_id": [100, 200, 300, 301, 310, 311, 210, 320, 321],
            "ancestry": [
                None,
                "100",
                "100/200",
                "100/200/300",
                "100/200",
                "100/200/310",
                "100",
                "100/210",
                "100/210/320",
            ],
            "rank_level": [40, 30, 20, 10, 20, 10, 30, 20, 10],
        }
    )


def _prior_ref(taxon_ids, grades, lat=49.0, lon=-123.0, when="2020-01-01"):
    n = len(taxon_ids)
    return pd.DataFrame(
        {
            "latitude": pd.array([lat] * n, dtype="float64"),
            "longitude": pd.array([lon] * n, dtype="float64"),
            "quality_grade": pd.array(grades, dtype="object"),
            "observed_on": pd.array([when] * n, dtype="object"),
            "taxon_id": taxon_ids,
        }
    )


def test_prior_uses_genus_when_it_has_enough_rows():
    ref = _prior_ref([301, 301, 301, 301, 311], ["research"] * 3 + ["needs_id"] * 2)
    pool = pd.DataFrame({"lat": [49.0], "lon": [-123.0], "taxon_id": [301]})
    got = prior_scores(pool, ref, _prior_taxa(), before="2025-01-01", min_n=3)
    assert got.iloc[0] == pytest.approx(0.75)  # genus 300: 3 research of 4 rows


def test_prior_falls_back_to_family_when_genus_is_too_small():
    # genus 300 and genus 310 each carry 2 rows (below min_n); their shared family 200 has 4.
    ref = _prior_ref([301, 301, 311, 311], ["research", "needs_id", "research", "needs_id"])
    pool = pd.DataFrame({"lat": [49.0], "lon": [-123.0], "taxon_id": [301]})
    got = prior_scores(pool, ref, _prior_taxa(), before="2025-01-01", min_n=3)
    assert got.iloc[0] == pytest.approx(0.5)  # family 200: 2 research of 4 rows


def test_prior_falls_back_to_order_when_family_is_too_small():
    # family 200 (2 rows) and family 210 (2 rows) are each below min_n; order 100 pools both.
    ref = _prior_ref([301, 311, 321, 321], ["research", "needs_id", "research", "needs_id"])
    pool = pd.DataFrame({"lat": [49.0], "lon": [-123.0], "taxon_id": [321]})
    got = prior_scores(pool, ref, _prior_taxa(), before="2025-01-01", min_n=3)
    assert got.iloc[0] == pytest.approx(0.5)  # order 100: 2 research of 4 rows


def test_prior_is_nan_when_no_level_reaches_min_n():
    ref = _prior_ref([301, 301], ["research", "needs_id"])
    pool = pd.DataFrame({"lat": [49.0], "lon": [-123.0], "taxon_id": [301]})
    got = prior_scores(pool, ref, _prior_taxa(), before="2025-01-01", min_n=3)
    assert np.isnan(got.iloc[0])


def test_prior_respects_min_n_boundary():
    taxa, before = _prior_taxa(), "2025-01-01"
    ref29 = _prior_ref([301] * 29, ["research"] * 29)
    ref30 = _prior_ref([301] * 30, ["research"] * 30)
    pool = pd.DataFrame({"lat": [49.0], "lon": [-123.0], "taxon_id": [301]})
    assert np.isnan(prior_scores(pool, ref29, taxa, before, min_n=30).iloc[0])
    assert prior_scores(pool, ref30, taxa, before, min_n=30).iloc[0] == 1.0


def test_prior_is_nan_for_missing_taxon_id_and_empty_reference():
    taxa = _prior_taxa()
    pool = pd.DataFrame({"lat": [49.0, 49.0], "lon": [-123.0, -123.0], "taxon_id": [None, 301]})
    empty_ref = _prior_ref([], [])
    got = prior_scores(pool, empty_ref, taxa, before="2025-01-01", min_n=3)
    assert np.isnan(got.iloc[0]) and np.isnan(got.iloc[1])


def test_prior_ignores_rows_observed_after_before_or_outside_the_pool_box():
    ref = _prior_ref([301] * 4, ["research"] * 4)
    late = _prior_ref([301] * 4, ["needs_id"] * 4, when="2026-01-01")
    far = _prior_ref([301] * 4, ["needs_id"] * 4, lat=10.0, lon=10.0)
    pool = pd.DataFrame({"lat": [49.0], "lon": [-123.0], "taxon_id": [301]})
    got = prior_scores(pool, pd.concat([ref, late, far]), _prior_taxa(), "2025-01-01", min_n=3)
    assert got.iloc[0] == 1.0  # only the 4 in-box, pre-`before` rows count


def _skip_inputs():
    taxa = _prior_taxa()
    low = _prior_ref([301] * 27 + [301] * 3, ["needs_id"] * 27 + ["research"] * 3)  # prior 0.10
    high = _prior_ref([311] * 3 + [311] * 27, ["needs_id"] * 3 + ["research"] * 27)  # prior 0.90
    ref = pd.concat([low, high], ignore_index=True)
    ref["positional_accuracy"] = 10.0
    pool = pd.DataFrame({"id": [1, 2], "lat": [49.0, 49.0], "lon": [-123.0, -123.0]})
    pool = pool.assign(taxon_id=pd.array([301, 311], dtype="Int64"))
    return pool, ref, taxa


def test_main_skip_below_writes_prior_and_skip_and_nans_low_prior_surprise(tmp_path):
    pool, ref, taxa = _skip_inputs()
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    ref.to_csv(tmp_path / "obs.tsv.gz", sep="\t", index=False)
    taxa.to_csv(tmp_path / "taxa.csv.gz", sep="\t", index=False)
    args = [str(tmp_path / "pool.parquet"), "--ref", str(tmp_path / "obs.tsv.gz")]
    args += ["--taxa", str(tmp_path / "taxa.csv.gz"), "--before", "2025-01-01"]
    args += ["--skip-below", "0.2", "--out", str(tmp_path / "s.parquet")]
    assert main(args) == 0
    s = pd.read_parquet(tmp_path / "s.parquet").set_index("id")
    assert s.columns.tolist() == ["surprise", "n_ref", "prior", "skip"]
    assert s.loc[1, "prior"] == pytest.approx(0.1) and bool(s.loc[1, "skip"])
    assert s.loc[2, "prior"] == pytest.approx(0.9) and not bool(s.loc[2, "skip"])
    assert np.isnan(s.loc[1, "surprise"])


def test_main_without_skip_below_output_is_unchanged(tmp_path):
    pool, ref, taxa = _skip_inputs()
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    ref.to_csv(tmp_path / "obs.tsv.gz", sep="\t", index=False)
    taxa.to_csv(tmp_path / "taxa.csv.gz", sep="\t", index=False)
    args = [str(tmp_path / "pool.parquet"), "--ref", str(tmp_path / "obs.tsv.gz")]
    args += ["--taxa", str(tmp_path / "taxa.csv.gz"), "--before", "2025-01-01"]
    assert main([*args, "--out", str(tmp_path / "s.parquet")]) == 0
    assert pd.read_parquet(tmp_path / "s.parquet").columns.tolist() == ["id", "surprise", "n_ref"]
