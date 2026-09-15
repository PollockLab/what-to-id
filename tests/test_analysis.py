import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import analysis, power

SERVED = pd.DataFrame({"id": [1, 2, 3, 4], "arm": ["c", "c", "t", "t"]})


def _idents(rows):
    return pd.DataFrame(rows, columns=["id", "user_id", "created_at", "taxon_rank"])


def test_identifier_counts_filters_and_dedupes():
    idents = _idents(
        [
            (1, 10, "2026-11-01T12:00:00Z", "species"),
            (1, 10, "2026-11-02T12:00:00Z", "subspecies"),
            (3, 10, "2026-11-01T12:00:00Z", "species"),
            (4, 10, "2026-11-01T12:00:00Z", "genus"),
            (2, 11, "2026-10-01T12:00:00Z", "species"),
            (9, 11, "2026-11-01T12:00:00Z", "species"),
            (3, None, "2026-11-01T12:00:00Z", "species"),
            (4, 11, "2026-11-03T12:00:00Z", "species"),
        ]
    )
    got = analysis.identifier_counts(idents, SERVED, start="2026-11-01", cutoff="2026-12-01")
    assert list(got.columns) == ["c", "t"]
    assert got.loc[10].tolist() == [1, 1]
    assert got.loc[11].tolist() == [0, 1]


def test_identifier_counts_empty_and_bad_input():
    empty = analysis.identifier_counts(_idents([]), SERVED, start="2026-11-01", cutoff="2026-12-01")
    assert empty.empty and list(empty.columns) == ["c", "t"]
    with pytest.raises(ValueError, match="taxon_rank"):
        analysis.identifier_counts(
            _idents([]).drop(columns="taxon_rank"), SERVED, start="2026-11-01", cutoff="2026-12-01"
        )
    with pytest.raises(ValueError, match="not after"):
        analysis.identifier_counts(_idents([]), SERVED, start="2026-12-01", cutoff="2026-12-01")
    with pytest.raises(ValueError, match="arm"):
        analysis.identifier_counts(
            _idents([]), SERVED[["id"]], start="2026-11-01", cutoff="2026-12-01"
        )


def test_sign_flip_exact_and_monte_carlo():
    assert analysis.sign_flip_p([0, 0]) == 1.0
    assert analysis.sign_flip_p([]) == 1.0
    assert analysis.sign_flip_p([1, 1, 1]) == pytest.approx(0.25)
    assert analysis.sign_flip_p([1, -1]) == 1.0
    big = np.full(40, 3.0)
    p = analysis.sign_flip_p(big, reps=2000, seed=1)
    assert p == pytest.approx(1 / 2001)
    assert analysis.sign_flip_p(big, reps=2000, seed=1) == p


def test_holm():
    got = analysis.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert got == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_analyse_rows_and_control():
    counts = pd.DataFrame({"c": [1, 2, 0], "t": [3, 4, 2], "u": [1, 2, 0]}, index=[10, 11, 12])
    res = analysis.analyse(counts, control="c")
    assert res["arm"].tolist() == ["t", "u"]
    assert res.loc[0, "mean_diff"] == pytest.approx(2.0)
    assert res.loc[1, "p"] == 1.0 and res.loc[1, "p_holm"] == 1.0
    assert res.loc[0, "p_holm"] == pytest.approx(min(1.0, 2 * res.loc[0, "p"]))
    with pytest.raises(ValueError, match="control"):
        analysis.analyse(counts, control="x")


def test_identifier_power_calibrated_and_rising():
    null = power.identifier_power(power.Scenario(50, 0.0, "rotation", n_arms=2), reps=300, seed=3)
    alt = power.identifier_power(power.Scenario(50, 0.3, "rotation", n_arms=2), reps=300, seed=3)
    assert 0.01 <= null <= 0.10
    assert alt > null + 0.3
    # Four arms test at alpha / 3, so alpha = 0.15 gives a 0.05 level.
    four = power.identifier_power(power.Scenario(50, 0.0, "rotation"), alpha=0.15, reps=300, seed=3)
    assert 0.01 <= four <= 0.10
    with pytest.raises(ValueError, match="rotation"):
        power.identifier_power(power.Scenario(50, 0.0, "sets"), reps=1)


def test_identifier_counts_users_filter():
    idents = _idents(
        [
            (1, 10, "2026-11-01T12:00:00Z", "species"),
            (3, 11, "2026-11-01T12:00:00Z", "species"),
        ]
    )
    got = analysis.identifier_counts(
        idents, SERVED, start="2026-11-01", cutoff="2026-12-01", users=[11]
    )
    assert got.index.tolist() == [11]


def test_cli_blitz_and_placebo(tmp_path, capsys):
    idents = _idents(
        [
            (1, 10, "2026-10-20T12:00:00Z", "species"),
            (3, 10, "2026-11-02T12:00:00Z", "species"),
            (4, 12, "2026-11-02T12:00:00Z", "species"),
        ]
    )
    idents.to_parquet(tmp_path / "i.parquet")
    SERVED.to_parquet(tmp_path / "s.parquet")
    (tmp_path / "u.txt").write_text("# participants\n10\n")
    args = ["--idents", str(tmp_path / "i.parquet"), "--served", str(tmp_path / "s.parquet")]
    args += ["--control", "c", "--start", "2026-11-01", "--cutoff", "2026-12-01"]
    args += ["--users", str(tmp_path / "u.txt"), "--placebo-start", "2026-10-01"]
    assert analysis.main(args) == 0
    out = capsys.readouterr().out
    assert "blitz: [2026-11-01, 2026-12-01)" in out and "placebo: [2026-10-01, 2026-11-01)" in out
    rows = [ln for ln in out.splitlines() if ln.startswith("| t |")]
    assert rows[0].split(" | ")[2:5] == ["1", "1", "0"]
    assert rows[1].split(" | ")[2:5] == ["1", "0", "1"]
    (tmp_path / "bad.txt").write_text("alice\n")
    with pytest.raises(SystemExit, match="one iNaturalist user id"):
        analysis.main(args[:-4] + ["--users", str(tmp_path / "bad.txt")])


def _obs(rows):
    return pd.DataFrame(rows, columns=["id", "reviewed_by"])


def test_exposure_counts_reviews_per_user_and_arm(tmp_path):
    obs = _obs([(1, [10, 11]), (2, [10]), (3, [10, 10]), (4, None), (9, [10])])
    p = tmp_path / "obs.parquet"
    obs.to_parquet(p)
    for frame in (obs, pd.read_parquet(p)):
        got = analysis.exposure(frame, SERVED)
        assert list(got.columns) == ["c", "t"]
        assert got.loc[10].tolist() == [2, 1]
        assert got.loc[11].tolist() == [1, 0]
    assert analysis.exposure(obs, SERVED, users=[11]).index.tolist() == [11]


def test_exposure_empty_and_bad_input():
    empty = analysis.exposure(_obs([(1, []), (2, None)]), SERVED)
    assert empty.empty and list(empty.columns) == ["c", "t"]
    with pytest.raises(ValueError, match="reviewed_by"):
        analysis.exposure(pd.DataFrame({"id": [1]}), SERVED)
    with pytest.raises(ValueError, match="served missing"):
        analysis.exposure(_obs([(1, [10])]), pd.DataFrame({"id": [1]}))


def test_exposure_summary_shares():
    expo = analysis.exposure(_obs([(1, [10, 11]), (2, [10]), (3, [10])]), SERVED)
    s = analysis.exposure_summary(expo)
    assert s["arm"].tolist() == ["c", "t"]
    assert s["n_users"].tolist() == [2, 1]
    assert s["reviewed"].tolist() == [3, 1]
    assert s["share"].tolist() == [0.75, 0.25]
    assert analysis.exposure_summary(expo.iloc[0:0])["share"].tolist() == [0.0, 0.0]


def test_served_arms_from_batches_frame():
    got = analysis.served_arms(SERVED)
    assert list(got.columns) == ["id", "arm", "cell_score"]
    assert got.set_index("id")["arm"].to_dict() == {1: "c", 2: "c", 3: "t", 4: "t"}
    assert got["cell_score"].isna().all()


def test_served_arms_from_log_repeated_ids_and_cell_score():
    log = pd.DataFrame(
        {
            "build_date": ["2026-11-01", "2026-11-01", "2026-11-02", "2026-11-02"],
            "label": ["A", "B", "A", "B"],
            "id": [1, 3, 1, 4],
            "cell_score": [float("nan"), 0.5, 0.9, 1.5],
        }
    )
    got = analysis.served_arms(log, {"A": "recency", "B": "gap_first"})
    got = got.set_index("id")
    assert got.loc[1, "arm"] == "recency"
    assert got.loc[1, "cell_score"] == pytest.approx(0.9)  # first non-null wins
    assert got.loc[3, "arm"] == "gap_first" and got.loc[3, "cell_score"] == pytest.approx(0.5)
    assert got.loc[4, "arm"] == "gap_first"
    assert sorted(got.index) == [1, 3, 4]


def test_served_arms_requires_label_map():
    log = pd.DataFrame({"label": ["A"], "id": [1]})
    with pytest.raises(ValueError, match="label_map"):
        analysis.served_arms(log)
    with pytest.raises(ValueError, match="labels not in label_map"):
        analysis.served_arms(log, {"B": "gap_first"})


def test_served_arms_conflict_raises():
    log = pd.DataFrame({"label": ["A", "B"], "id": [1, 1]})
    with pytest.raises(ValueError, match="more than one arm"):
        analysis.served_arms(log, {"A": "recency", "B": "gap_first"})


def test_identifier_counts_weighted_by_cell_score():
    served = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "arm": ["c", "c", "t", "t"],
            "cell_score": [0.5, float("nan"), 2.0, 1.0],
        }
    )
    idents = _idents(
        [
            (1, 10, "2026-11-01T12:00:00Z", "species"),
            (2, 10, "2026-11-01T12:00:00Z", "species"),
            (3, 10, "2026-11-01T12:00:00Z", "species"),
            (1, 10, "2026-11-02T12:00:00Z", "species"),  # duplicate (user, id), not double-counted
        ]
    )
    got = analysis.identifier_counts(
        idents, served, start="2026-11-01", cutoff="2026-12-01", weight="cell_score"
    )
    assert got["c"].dtype == np.float64
    assert got.loc[10].tolist() == pytest.approx([0.5, 2.0])  # NaN cell_score treated as 0


def test_sign_test_p_known_cases():
    assert analysis.sign_test_p([1] * 8) == pytest.approx(2 * 0.5**8)
    assert analysis.sign_test_p([0, 0]) == 1.0
    assert analysis.sign_test_p([]) == 1.0
    assert analysis.sign_test_p([1, -1]) == 1.0
    assert analysis.sign_test_p([1, 1, -1]) == pytest.approx(1.0)


def test_analyse_has_p_sign_column():
    counts = pd.DataFrame({"c": [1, 2, 0], "t": [3, 4, 2]}, index=[10, 11, 12])
    res = analysis.analyse(counts, control="c")
    assert "p_sign" in res.columns
    d = (counts["t"] - counts["c"]).to_numpy()
    assert res.loc[0, "p_sign"] == pytest.approx(analysis.sign_test_p(d))


def test_cli_multi_served_logs_with_label_map(tmp_path, capsys):
    idents = _idents(
        [
            (1, 10, "2026-11-01T12:00:00Z", "species"),
            (3, 10, "2026-11-02T12:00:00Z", "species"),
        ]
    )
    idents.to_parquet(tmp_path / "i.parquet")
    day1 = pd.DataFrame(
        {"build_date": ["2026-10-20"], "label": ["A"], "id": [1], "cell_score": [0.4]}
    )
    day2 = pd.DataFrame(
        {"build_date": ["2026-10-21"], "label": ["B"], "id": [3], "cell_score": [1.1]}
    )
    day1.to_parquet(tmp_path / "s1.parquet")
    day2.to_parquet(tmp_path / "s2.parquet")
    label_map = tmp_path / "labels.json"
    label_map.write_text(json.dumps({"A": "c", "B": "t"}))
    args = ["--idents", str(tmp_path / "i.parquet")]
    args += ["--served", str(tmp_path / "s1.parquet"), str(tmp_path / "s2.parquet")]
    args += ["--label-map", str(label_map), "--weight", "cell_score"]
    args += ["--control", "c", "--start", "2026-11-01", "--cutoff", "2026-12-01"]
    assert analysis.main(args) == 0
    out = capsys.readouterr().out
    assert "0 served record(s) with no cell_score" in out
    assert "blitz: [2026-11-01, 2026-12-01)" in out


def test_cli_exposure(tmp_path, capsys):
    _idents([(1, 10, "2026-11-02T12:00:00Z", "species")]).to_parquet(tmp_path / "i.parquet")
    _obs([(1, [10, 12]), (3, [10])]).to_parquet(tmp_path / "o.parquet")
    SERVED.to_parquet(tmp_path / "s.parquet")
    (tmp_path / "u.txt").write_text("10\n")
    args = ["--idents", str(tmp_path / "i.parquet"), "--served", str(tmp_path / "s.parquet")]
    args += ["--control", "c", "--start", "2026-11-01", "--cutoff", "2026-12-01"]
    args += ["--users", str(tmp_path / "u.txt"), "--obs", str(tmp_path / "o.parquet")]
    assert analysis.main(args) == 0
    out = capsys.readouterr().out
    assert "exposure: served records marked reviewed, participants" in out
    assert "| c | 1 | 1 | 0.5 |" in out and "| t | 1 | 1 | 0.5 |" in out


def test_record_totals_collapse_to_the_summed_paired_difference():
    idents = _idents(
        [
            (1, 10, "2026-11-01T12:00:00Z", "species"),
            (1, 11, "2026-11-01T12:00:00Z", "species"),
            (3, 10, "2026-11-01T12:00:00Z", "species"),
            (4, 11, "2026-11-01T12:00:00Z", "species"),
            (4, 11, "2026-11-02T12:00:00Z", "subspecies"),
            (2, 10, "2026-10-01T12:00:00Z", "species"),
        ]
    )
    kw = {"start": "2026-11-01", "cutoff": "2026-12-01"}
    totals = analysis.record_totals(idents, SERVED, **kw)
    assert sorted(totals.index) == [1, 2, 3, 4]
    assert totals.loc[1] == 2.0 and totals.loc[2] == 0.0
    counts = analysis.identifier_counts(idents, SERVED, **kw)
    paired = float((counts["t"] - counts["c"]).sum())
    arm_of = SERVED.set_index("id")["arm"]
    collapsed = float(totals[arm_of == "t"].sum() - totals[arm_of == "c"].sum())
    assert collapsed == paired


def test_record_totals_weighted_uses_the_cell_score():
    served = SERVED.assign(cell_score=[0.0, 0.5, 0.25, np.nan])
    idents = _idents(
        [
            (3, 10, "2026-11-01T12:00:00Z", "species"),
            (3, 11, "2026-11-01T12:00:00Z", "species"),
            (4, 10, "2026-11-01T12:00:00Z", "species"),
        ]
    )
    kw = {"start": "2026-11-01", "cutoff": "2026-12-01"}
    totals = analysis.record_totals(idents, served, weight="cell_score", **kw)
    assert totals.loc[3] == 0.5 and totals.loc[4] == 0.0
    with pytest.raises(ValueError, match="weight must be"):
        analysis.record_totals(idents, served, weight="nope", **kw)


def test_record_shuffle_p_is_large_with_no_signal_and_small_with_a_strong_one():
    served = pd.DataFrame({"id": range(200), "arm": ["c", "t"] * 100})
    flat = pd.Series(1.0, index=range(200))
    kw = {"arm": "t", "control": "c", "reps": 200, "seed": 0}
    assert analysis.record_shuffle_p(flat, served, **kw) > 0.2
    loaded = pd.Series([0.0 if a == "c" else 10.0 for a in served["arm"]], index=served["id"])
    assert analysis.record_shuffle_p(loaded, served, **kw) < 0.05


def test_record_shuffle_p_strata_permute_within_a_stratum_only():
    served = pd.DataFrame({"id": [1, 2, 3, 4], "arm": ["c", "t", "c", "t"]})
    strata = pd.Series({1: "a", 2: "a", 3: "b", 4: "b"})
    totals = pd.Series({1: 0.0, 2: 5.0, 3: 0.0, 4: 5.0})
    p = analysis.record_shuffle_p(
        totals, served, arm="t", control="c", strata=strata, reps=400, seed=1
    )
    assert 0.2 < p <= 1.0
    with pytest.raises(ValueError, match="strata is missing"):
        analysis.record_shuffle_p(
            totals, served, arm="t", control="c", strata=strata.drop(4), reps=10
        )


def test_cli_reports_p_record_next_to_the_primary_p(tmp_path, capsys):
    idents = _idents(
        [
            (1, 10, "2026-11-02T12:00:00Z", "species"),
            (3, 10, "2026-11-02T12:00:00Z", "species"),
            (4, 10, "2026-11-02T12:00:00Z", "species"),
            (4, 11, "2026-11-03T12:00:00Z", "species"),
        ]
    )
    idents.to_parquet(tmp_path / "i.parquet")
    SERVED.to_parquet(tmp_path / "s.parquet")
    args = ["--idents", str(tmp_path / "i.parquet"), "--served", str(tmp_path / "s.parquet")]
    args += ["--control", "c", "--start", "2026-11-01", "--cutoff", "2026-12-01"]
    args += ["--reps", "200", "--seed", "3"]
    assert analysis.main(args) == 0
    out = capsys.readouterr().out
    assert analysis.RECORD_NOTE in out
    head = next(ln for ln in out.splitlines() if ln.startswith("| arm |"))
    cols = [c.strip() for c in head.strip("|").split("|")]
    assert cols[-2:] == ["p_holm", "p_record"]
    row = next(ln for ln in out.splitlines() if ln.startswith("| t |"))
    got = float(row.strip("|").split("|")[-1])
    kw = {"start": "2026-11-01", "cutoff": "2026-12-01"}
    totals = analysis.record_totals(idents, SERVED, **kw)
    want = analysis.record_shuffle_p(totals, SERVED, arm="t", control="c", reps=200, seed=3)
    assert got == pytest.approx(want, abs=5e-4)


def test_cli_help_says_p_record_is_secondary_and_needs_no_binding_cap(capsys):
    with pytest.raises(SystemExit):
        analysis.main(["--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "secondary" in text and "not Holm-adjusted" in text
    assert "no cap on batches binds" in text and "cannot show this" in text
    assert "cannot check this" in analysis.__doc__


def test_record_shuffle_p_rejects_bad_arms_and_reps():
    flat = pd.Series(1.0, index=[1, 2, 3, 4])
    with pytest.raises(ValueError, match="not in"):
        analysis.record_shuffle_p(flat, SERVED, arm="zz", control="c", reps=10)
    with pytest.raises(ValueError, match="reps must be"):
        analysis.record_shuffle_p(flat, SERVED, arm="t", control="c", reps=0)
