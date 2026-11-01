import pandas as pd
import pytest

from what_to_id.blind_report import REPORT_COLUMNS, cv_error, first_own_ids, main


def _obs(rows):
    return pd.DataFrame(rows, columns=["id", "user_id", "iconic_taxon"])


def _idents(rows):
    cols = ["id", "user_id", "created_at", "taxon_id", "vision", "observer_id"]
    return pd.DataFrame(rows, columns=cols)


def _cons(rows):
    cols = ["record_id", "taxon_id", "posterior"]
    return pd.DataFrame(rows, columns=cols).astype({"taxon_id": "Int64"})


def _firsts(rows):
    return pd.DataFrame(rows, columns=["record_id", "group", "taxon_id", "vision"])


def test_first_own_id_picks_earliest_own():
    obs = _obs([(1, 7, "Aves"), (2, 8, "Aves")])
    idents = _idents(
        [
            (1, 9, "2024-01-01", 99, False, 7),  # other's, earliest overall
            (1, 7, "2024-01-03", 30, False, 7),  # own, later
            (1, 7, "2024-01-02", 20, True, 7),  # own, first
            (2, 9, "2024-01-01", 5, False, 8),  # observer never identified
        ]
    )
    out = first_own_ids(obs, idents)
    assert out.to_dict("records") == [
        {"record_id": 1, "group": "Aves", "taxon_id": 20, "vision": True}
    ]


def test_first_own_ids_needs_group_column():
    with pytest.raises(ValueError, match="iconic_taxon"):
        first_own_ids(pd.DataFrame({"id": [1]}), _idents([]))


def test_cv_typed_split_and_all_rows():
    cons = _cons([(i, 1, 0.99) for i in range(1, 5)])
    firsts = _firsts(
        [
            (1, "Aves", 1, True),
            (2, "Aves", 2, True),
            (3, "Aves", 1, False),
            (4, "Plantae", 3, False),
        ]
    )
    out = cv_error(cons, firsts).set_index(["group", "source"])
    assert out.loc[("Aves", "cv"), ["n", "wrong"]].tolist() == [2, 1]
    assert out.loc[("Aves", "typed"), ["n", "wrong"]].tolist() == [1, 0]
    assert out.loc[("Plantae", "typed"), "error"] == 1.0
    assert out.loc[("all", "cv"), ["n", "wrong"]].tolist() == [2, 1]
    assert out.loc[("all", "typed"), ["n", "wrong"]].tolist() == [2, 1]
    assert list(out.index) == sorted(out.index)


def test_threshold_and_na_exclusion():
    cons = _cons([(1, 1, 0.95), (2, 1, 0.5), (3, None, 1.0)])
    firsts = _firsts([(i, "Aves", 1, False) for i in (1, 2, 3)])
    out = cv_error(cons, firsts, threshold=0.9)
    assert out["n"].tolist() == [1, 1]
    assert cv_error(cons, firsts, threshold=0.4)["n"].max() == 2


def test_wilson_interval():
    cons = _cons([(i, 1, 1.0) for i in range(10)])
    firsts = _firsts([(i, "Aves", 1, False) for i in range(10)])
    row = cv_error(cons, firsts).iloc[0]
    assert row["error"] == 0 and row["lo"] == 0
    assert row["hi"] == pytest.approx(0.278, abs=1e-3)
    firsts.loc[:2, "taxon_id"] = 2
    for _, r in cv_error(cons, firsts).iterrows():
        assert 0 <= r["lo"] <= r["error"] <= r["hi"] <= 1


def test_empty_inputs():
    out = cv_error(_cons([]), _firsts([]))
    assert out.empty and list(out.columns) == REPORT_COLUMNS
    assert first_own_ids(_obs([]), _idents([])).empty


def test_main(tmp_path, capsys):
    _cons([(1, 20, 0.99)]).to_parquet(tmp_path / "c.parquet")
    _obs([(1, 7, "Aves")]).to_parquet(tmp_path / "o.parquet")
    _idents([(1, 7, "2024-01-01", 20, True, 7)]).to_parquet(tmp_path / "i.parquet")
    argv = ["--threshold", "0.9"]
    for flag, name in [("consensus", "c"), ("obs", "o"), ("idents", "i")]:
        argv += [f"--{flag}", str(tmp_path / f"{name}.parquet")]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "Aves" in out and "cv" in out and "all" in out
