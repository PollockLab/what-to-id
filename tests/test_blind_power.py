from what_to_id.blind_power import COLUMNS, main, power_two_prop, table


def test_table_shape_and_monotone():
    t = table([1000, 2000, 3000], draws=500, seed=1)
    assert list(t.columns) == COLUMNS and len(t) == 3
    assert t["half_cv"].is_monotonic_decreasing and t["half_typed"].is_monotonic_decreasing
    assert t["power_e_small"].is_monotonic_increasing and t["power_d"].is_monotonic_increasing
    assert (t["d_lo_cv"] < 0.75).all() and (t["d_hi_cv"] > 0.75).all()
    assert ((t["d_hi_cv"] - t["d_lo_cv"]) < (t["d_hi_typed"] - t["d_lo_typed"])).all()


def test_power_two_prop_limits():
    assert abs(power_two_prop(0.06, 0.06, 1000, 1000) - 0.05) < 1e-6
    assert power_two_prop(0.06, 0.12, 1200, 400) > power_two_prop(0.06, 0.09, 1200, 400)
    two = power_two_prop(0.06, 0.09, 1200, 400)
    assert power_two_prop(0.06, 0.09, 1200, 400, one_sided=True) > two


def test_main_prints_table(capsys):
    main(["--records", "500", "--draws", "50"])
    out = capsys.readouterr().out
    assert "power_d" in out and "500" in out
