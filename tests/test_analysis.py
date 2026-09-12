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
    null = power.identifier_power(power.Scenario(50, 0.0, "rotation"), reps=300, seed=3)
    alt = power.identifier_power(power.Scenario(50, 0.3, "rotation"), reps=300, seed=3)
    assert 0.01 <= null <= 0.10
    assert alt > null + 0.3
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
