import numpy as np
from scipy import stats

from what_to_id.blind_power import COLUMNS, level_power, main, power_two_prop, table


def test_table_shape_and_monotone():
    t = table([1000, 2000, 3000], draws=500, seed=1)
    assert list(t.columns) == COLUMNS and len(t) == 3
    assert t["half_cv"].is_monotonic_decreasing and t["half_typed"].is_monotonic_decreasing
    assert t["power_e_small"].is_monotonic_increasing and t["power_d"].is_monotonic_increasing
    assert (t["d_lo_cv"] < 0.75).all() and (t["d_hi_cv"] > 0.75).all()
    assert ((t["d_hi_cv"] - t["d_lo_cv"]) < (t["d_hi_typed"] - t["d_lo_typed"])).all()


def test_consensus_error_widens_d_and_keeps_it_centred():
    exact = table([2000], c=0.0, draws=3000, seed=2)
    noisy = table([2000], c=0.005, planted=600, draws=3000, seed=2)
    few = table([2000], c=0.005, planted=150, draws=3000, seed=2)
    width = lambda t: (t["d_hi_cv"] - t["d_lo_cv"]).item()  # noqa: E731
    assert width(exact) < width(noisy) < width(few)
    assert noisy["d_lo_cv"].item() < 0.75 < noisy["d_hi_cv"].item()
    assert noisy["power_d"].item() < exact["power_d"].item()


def test_power_two_prop_limits():
    assert abs(power_two_prop(0.06, 0.06, 1000, 1000) - 0.05) < 1e-6
    assert power_two_prop(0.06, 0.12, 1200, 400) > power_two_prop(0.06, 0.09, 1200, 400)
    two = power_two_prop(0.06, 0.09, 1200, 400)
    assert power_two_prop(0.06, 0.09, 1200, 400, one_sided=True) > two


def test_level_power_matches_spearman_and_orders():
    rng = np.random.default_rng(0)
    assert abs(level_power(1000, 0.8, 0.0, 4000, rng) - 0.05) < 0.02  # size under no gradient
    small, large = (level_power(2000, 0.8, s, 2000, rng) for s in (0.02, 0.05))
    assert small < large and large > 0.95
    # the closed form agrees with scipy on one draw
    x = np.repeat(np.arange(5), 40)
    y = (rng.random(x.size) < 0.8 - 0.05 * (np.arange(5).repeat(40) - 2)).astype(int)
    p = stats.spearmanr(x, y, alternative="less").pvalue
    r = stats.pearsonr(stats.rankdata(x), stats.rankdata(y))[0]
    t = r * np.sqrt((x.size - 2) / (1 - r * r))
    assert abs(stats.t.cdf(t, x.size - 2) - p) < 1e-9


def test_main_prints_table(capsys):
    main(["--records", "500", "--draws", "50"])
    out = capsys.readouterr().out
    assert "power_d" in out and "500" in out
