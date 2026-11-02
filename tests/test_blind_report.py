import pandas as pd
import pytest

from what_to_id.blind_report import (
    DETECT_COLUMNS,
    HARD_COLUMNS,
    LEVEL_COLUMNS,
    REPORT_COLUMNS,
    TEST_COLUMNS,
    collapse_refinements,
    cv_error,
    detection_rate,
    first_own_ids,
    hard_cases,
    hypothesis_tests,
    level_error,
    level_table,
    main,
    matched_error,
)


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
        {
            "record_id": 1,
            "group": "Aves",
            "taxon_id": 20,
            "vision": True,
            "age_days": 1,
            "age": "<30 d",
        }
    ]


def test_first_own_ids_bins_observer_experience():
    obs = pd.DataFrame(
        [(1, 7, "Aves", 0), (2, 8, "Aves", 50), (3, 9, "Aves", 100)],
        columns=["id", "user_id", "iconic_taxon", "observer_idents"],
    )
    idents = _idents(
        [(1, 7, "2024-01-01", 20, True, 7), (2, 8, "2024-01-01", 20, False, 8)]
        + [(3, 9, "2024-01-01", 20, False, 9)]
    )
    firsts = first_own_ids(obs, idents)
    assert firsts["experience"].tolist() == ["<10 ids", "10-99 ids", "100+ ids"]
    cons = _cons([(1, 20, 0.99), (2, 21, 0.99), (3, 20, 0.99)])
    out = cv_error(cons, firsts, by="experience").set_index(["experience", "source"])
    assert out.loc[("<10 ids", "cv"), ["n", "wrong"]].tolist() == [1, 0]
    assert out.loc[("10-99 ids", "typed"), ["n", "wrong"]].tolist() == [1, 1]
    assert out.loc[("all", "typed"), ["n", "wrong"]].tolist() == [2, 1]
    assert "group" not in out.columns


def test_first_own_ids_bins_age_against_the_latest_identification():
    obs = _obs([(1, 7, "Aves"), (2, 8, "Aves"), (3, 9, "Aves")])
    idents = _idents(
        [(1, 7, "2023-01-01", 20, True, 7), (2, 8, "2024-01-01", 20, False, 8)]
        + [(3, 9, "2024-06-01", 20, False, 9), (3, 5, "2024-06-20", 20, False, 9)]
    )
    assert first_own_ids(obs, idents)["age"].tolist() == ["365+ d", "30-364 d", "<30 d"]


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
    _cons([(1, 20, 0.99)]).assign(n_answers=4).to_parquet(tmp_path / "c.parquet")
    _obs([(1, 7, "Aves")]).to_parquet(tmp_path / "o.parquet")
    _idents([(1, 7, "2024-01-01", 20, True, 7)]).to_parquet(tmp_path / "i.parquet")
    argv = ["--threshold", "0.9", "--hard-cases", str(tmp_path / "hard.parquet")]
    for flag, name in [("consensus", "c"), ("obs", "o"), ("idents", "i")]:
        argv += [f"--{flag}", str(tmp_path / f"{name}.parquet")]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "Aves" in out and "cv" in out and "all" in out and "0 hard cases" in out
    assert list(pd.read_parquet(tmp_path / "hard.parquet").columns) == HARD_COLUMNS


def test_main_nowcast_d_from_correction_delays(tmp_path, capsys):
    _cons([(1, 21, 0.99), (2, 30, 0.99)]).to_parquet(tmp_path / "c.parquet")
    _obs([(1, 7, "Aves"), (2, 7, "Aves")]).to_parquet(tmp_path / "o.parquet")
    own = [(1, 7, "2024-01-01", 20, True, 7), (2, 7, "2024-01-01", 30, True, 7)]
    other = [(1, 9, "2024-01-11", 22, False, 7), (2, 9, "2024-01-11", 30, False, 7)]
    _idents(own + other).to_parquet(tmp_path / "i.parquet")
    pd.DataFrame({"id": [1, 2], "taxon_id": [22, 30]}).to_parquet(tmp_path / "p.parquet")
    pd.DataFrame({"source": "cv", "days": [5.0, 100.0]}).to_parquet(tmp_path / "d.parquet")
    argv = []
    for flag, name in [("consensus", "c"), ("obs", "o"), ("idents", "i"), ("public", "p")]:
        argv += [f"--{flag}", str(tmp_path / f"{name}.parquet")]
    assert main([*argv, "--delays", str(tmp_path / "d.parquet")]) == 0
    out = capsys.readouterr().out
    assert "nowcast d, overturn over completeness at age (2 delays)" in out


def test_main_consensus_error_from_held_out_planted(tmp_path, capsys):
    _cons([(1, 20, 0.99), (2, 30, 0.99)]).to_parquet(tmp_path / "c.parquet")
    _obs([(1, 7, "Aves"), (2, 7, "Aves")]).to_parquet(tmp_path / "o.parquet")
    _idents([(1, 7, "2024-01-01", 20, True, 7), (2, 7, "2024-01-01", 30, True, 7)]).to_parquet(
        tmp_path / "i.parquet"
    )
    ans = [(f"s{k}", "Aves", r, t) for k in range(4) for r, t in [(1, 20), (2, 30)]]
    pd.DataFrame(ans, columns=["login", "group", "record_id", "taxon_id"]).to_parquet(
        tmp_path / "a.parquet"
    )
    plant = {"record_id": [1, 2], "taxon_id": [20, 31], "kind": ["cv_hold", "cv_fail"]}
    pd.DataFrame(plant).to_parquet(tmp_path / "p.parquet")
    argv = []
    for flag, name in [
        ("consensus", "c"),
        ("obs", "o"),
        ("idents", "i"),
        ("answers", "a"),
        ("planted", "p"),
    ]:
        argv += [f"--{flag}", str(tmp_path / f"{name}.parquet")]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "consensus error c = 0.5000 on 2 held-out" in out
    # record 2: students agree with the observer's first name 30, the expert says 31
    assert "cv_fail" in out and "confirmed_first" in out


def test_cv_error_removes_consensus_error():
    cons = _cons([(i, 20 if i < 90 else 21, 0.99) for i in range(100)])
    firsts = _firsts([(i, "Aves", 20, True) for i in range(100)])
    raw, fixed = (
        t[t["group"] == "all"].set_index("source").loc["cv"]
        for t in (cv_error(cons, firsts), cv_error(cons, firsts, consensus_error=0.05))
    )
    assert raw["error"] == pytest.approx(0.10)
    assert fixed["error"] == pytest.approx((0.10 - 0.05) / 0.9)
    assert fixed["lo"] <= fixed["error"] <= fixed["hi"] and fixed["lo"] < raw["lo"]


def test_cv_error_interval_carries_consensus_uncertainty():
    # 200 cv records, 20 disagree; c = 1% measured on 300 planted vs on 10**7 (as good as exact)
    cons = _cons([(i, 1, 0.99) for i in range(200)])
    firsts = _firsts([(i, "Aves", 2 if i < 20 else 1, True) for i in range(200)])
    few, many = (
        cv_error(cons, firsts, consensus_error=0.01, consensus_n=n).iloc[0] for n in (300, 10**7)
    )
    assert few["error"] == many["error"] == pytest.approx((0.1 - 0.01) / 0.98)
    assert few["lo"] < few["error"] < few["hi"] and few["hi"] - few["lo"] > many["hi"] - many["lo"]
    # no disagreement at all still leaves an upper bound, as the Wilson interval does
    none = cv_error(cons, _firsts([(i, "Aves", 1, True) for i in range(200)]), consensus_n=50)
    assert none["error"].eq(0).all() and none["hi"].gt(0).all()


def test_matched_error_within_species():
    # first-ID species 7: typed wrong 2 of 2, cv wrong 1 of 2; species 2 and 8: cv only, no weight
    cons = _cons([(0, 7, 0.99)] + [(i, 1, 0.99) for i in (1, 2, 3)] + [(4, 2, 0.99), (5, 2, 0.99)])
    firsts = _firsts(
        [(0, "Aves", 7, True), (1, "Aves", 7, True), (2, "Aves", 7, False), (3, "Aves", 7, False)]
        + [(4, "Aves", 2, True), (5, "Aves", 8, True)]
    )
    assert matched_error(cons, firsts) == (2.0, 1)
    assert matched_error(_cons([]), _firsts([]))[1] == 0


def test_detection_rate_is_overturn_over_error():
    # 10 cv records: 4 wrong by consensus, the public caught 2 of them -> d = 0.5
    cons = _cons([(i, 1, 0.99) for i in range(1, 11)])
    firsts = _firsts([(i, "Aves", 2 if i <= 4 else 1, True) for i in range(1, 11)])
    public = pd.DataFrame({"record_id": range(1, 11), "taxon_id": [1, 1] + [2] * 2 + [1] * 6})
    out = detection_rate(cons, firsts, public, boot=200).set_index(["group", "source"])
    assert list(out.columns) == DETECT_COLUMNS[2:]
    row = out.loc[("all", "cv")]
    assert row["n"] == 10 and row["error"] == 0.4 and row["overturn"] == 0.2
    assert row["detection"] == 0.5 and row["lo"] <= 0.5 <= row["hi"]
    assert out.loc[("Aves", "cv"), "detection"] == 0.5


def test_detection_interval_widens_with_consensus_uncertainty():
    # 200 cv records, 20 wrong, 10 caught; c = 1% measured on 300 planted vs taken as exact
    cons = _cons([(i, 1, 0.99) for i in range(200)])
    firsts = _firsts([(i, "Aves", 2 if i < 20 else 1, True) for i in range(200)])
    public = pd.DataFrame({"record_id": range(200), "taxon_id": [1] * 10 + [2] * 10 + [1] * 180})
    kw = dict(boot=2000, consensus_error=0.01)
    fixed, drawn = (
        detection_rate(cons, firsts, public, **kw, consensus_n=n).iloc[0] for n in (0, 300)
    )
    assert fixed["detection"] == drawn["detection"] == pytest.approx(0.05 / ((0.1 - 0.01) / 0.98))
    assert drawn["hi"] - drawn["lo"] > fixed["hi"] - fixed["lo"]
    assert drawn["lo"] < drawn["detection"] < drawn["hi"]


def test_detection_rate_splits_by_experience():
    # novices: 4 wrong, 2 caught (d 0.5); experts: 4 wrong, 4 caught (d 1.0); same e in both
    cons = _cons([(i, 1, 0.99) for i in range(20)])
    firsts = _firsts([(i, "Aves", 2 if i % 10 < 4 else 1, True) for i in range(20)])
    firsts["experience"] = ["<10 ids"] * 10 + ["100+ ids"] * 10
    public = pd.DataFrame({"record_id": range(20), "taxon_id": [2, 2, 1, 1] + [1] * 16})
    out = detection_rate(cons, firsts, public, boot=100, by="experience")
    assert list(out.columns) == ["experience", *DETECT_COLUMNS[1:]]
    d = out.set_index(["experience", "source"])["detection"]
    assert (
        d[("<10 ids", "cv")] == 0.5
        and d[("100+ ids", "cv")] == 1.0
        and d[("all", "cv")] == pytest.approx(0.75)
    )


def test_detection_rate_nowcast_divides_by_completeness():
    # 4 of 10 wrong, 2 overturned so far; at every age half the corrections are in
    cons = _cons([(i, 1, 0.99) for i in range(10)])
    firsts = _firsts([(i, "Aves", 2 if i < 4 else 1, True) for i in range(10)])
    firsts["complete"] = 0.5
    public = pd.DataFrame({"record_id": range(10), "taxon_id": [1, 1] + [2, 2] + [1] * 6})
    kw = dict(boot=100, by="group")
    raw = detection_rate(cons, firsts, public, **kw).set_index(["group", "source"])
    now = detection_rate(cons, firsts, public, nowcast=True, **kw).set_index(["group", "source"])
    assert raw.loc[("all", "cv"), "detection"] == pytest.approx(0.5)
    assert now.loc[("all", "cv"), ["overturn", "detection"]].tolist() == pytest.approx([0.4, 1.0])


def test_nowcast_weights_error_by_completeness_when_error_changes_with_age():
    # young: 20 records at F 0.5, 8 wrong, 2 overturned; old: 20 at F 1, 2 wrong, 1 overturned;
    # true d 0.5 in both, but the young records hold most of the error
    young = [(i, "Aves", 2 if i < 8 else 1, True) for i in range(20)]
    old = [(i, "Aves", 2 if i < 22 else 1, True) for i in range(20, 40)]
    firsts = _firsts(young + old)
    firsts["complete"] = [0.5] * 20 + [1.0] * 20
    cons = _cons([(i, 1, 0.99) for i in range(40)])
    over = {0, 1, 20}
    public = pd.DataFrame(
        {
            "record_id": range(40),
            "taxon_id": [1 if i in over else 2 if i < 8 or 20 <= i < 22 else 1 for i in range(40)],
        }
    )
    out = detection_rate(cons, firsts, public, boot=50, nowcast=True).set_index(["group", "source"])
    assert out.loc[("all", "cv"), "detection"] == pytest.approx(0.5)


def test_collapse_refinements_keeps_the_first_taxon_for_descendants_only():
    firsts = _firsts([(1, "Aves", 10, True), (2, "Aves", 10, True), (3, "Aves", 10, True)])
    public = pd.DataFrame({"record_id": [1, 2, 3], "taxon_id": [11, 12, 1]})
    taxa = pd.DataFrame({"taxon_id": [11, 12, 1], "ancestry": ["1/10", "1/5", None]})
    assert collapse_refinements(public, firsts, taxa)["taxon_id"].tolist() == [10, 12, 1]


def test_detection_rate_handles_no_error_and_no_overlap():
    cons = _cons([(1, 1, 0.99), (2, 1, 0.99)])
    firsts = _firsts([(1, "Aves", 1, False), (2, "Aves", 1, False)])
    public = pd.DataFrame({"record_id": [1, 2], "taxon_id": [1, 1]})
    out = detection_rate(cons, firsts, public, boot=50)
    assert out["detection"].isna().all()  # 0/0: no errors to detect
    assert detection_rate(cons, firsts, public.iloc[:0]).empty


def test_hard_cases_overturned_and_unsettled_without_planted():
    cons = pd.DataFrame(
        {
            "record_id": [1, 2, 3, 4, 5],
            "taxon_id": pd.array([2, 1, None, 2, 1], dtype="Int64"),
            "posterior": [0.99, 0.99, 0.0, 0.6, 0.99],
            "n_answers": [4, 4, 0, 3, 4],
            "n_abstain": [0, 0, 4, 1, 0],
            "planted": [False, False, False, False, True],
        }
    )
    firsts = _firsts([(i, "Aves", 1, i % 2 == 1) for i in range(1, 6)])
    out = hard_cases(cons, firsts)
    assert list(out.columns) == HARD_COLUMNS
    assert out[["record_id", "why"]].values.tolist() == [[1, "overturned"], [4, "unsettled"]]
    assert out.loc[0, ["source", "first", "consensus"]].tolist() == ["cv", 1, 2]
    assert pd.isna(out.loc[1, "consensus"]) and out.loc[1, "n_answers"] == 3
    assert hard_cases(cons.iloc[:0], firsts).empty


def test_level_table_settled_and_abstain_per_level():
    cons = pd.DataFrame(
        {
            "record_id": [1, 2, 3, 4],
            "taxon_id": pd.array([1, 1, None, 1], dtype="Int64"),
            "posterior": [0.99, 0.95, 0.0, 0.6],
            "n_answers": [4, 4, 0, 3],
            "n_abstain": [0, 0, 4, 1],
        }
    )
    levels = pd.DataFrame({"record_id": [1, 2, 3, 4, 5], "level": [1, 1, 4, 4, 2]})
    out = level_table(cons, levels).set_index("level")
    assert list(out.columns) == LEVEL_COLUMNS[1:] and list(out.index) == [1, 4]  # 5: no answers
    assert out.loc[1, ["n", "settled", "abstain"]].tolist() == [2, 1.0, 0.0]
    assert out.loc[4, ["n", "settled", "abstain"]].tolist() == [2, 0.0, 0.625]
    assert level_table(cons, levels.iloc[:0]).empty


def test_level_error_per_level():
    held = pd.DataFrame({"record_id": [1, 2, 3, 4, 5], "wrong": [0, 1, 1, 1, 0]})
    held["level"] = [1, 1, 5, 5, None]  # a planted record outside the levels file is skipped
    out = level_error(held).set_index("level")
    assert list(out.index) == [1, 5] and out["n"].tolist() == [2, 2]
    assert out["c"].tolist() == [0.5, 1.0]


def test_hypothesis_tests_directions():
    # 40 cv records, 20 wrong, public caught 4; 40 typed, 4 wrong, public caught all 4
    n = 80
    cons = _cons([(i, 1, 0.99) for i in range(n)])
    first = [2 if i < 20 else 1 for i in range(40)] + [2 if i < 44 else 1 for i in range(40, n)]
    firsts = _firsts([(i, "Aves", first[i], i < 40) for i in range(n)])
    pub = [2 if 4 <= i < 20 else 1 for i in range(n)]  # cv misses 16 of 20 stay uncaught
    public = pd.DataFrame({"record_id": range(n), "taxon_id": pub})
    cons.loc[cons["record_id"] >= 40, "posterior"] = [0.95] * 20 + [0.5] * 20
    levels = pd.DataFrame({"record_id": range(n), "level": [1] * 40 + [2] * 20 + [4] * 20})
    out = hypothesis_tests(cons, firsts, public, levels, boot=500).set_index("hypothesis")
    assert list(out.columns) == TEST_COLUMNS[1:] and len(out) == 3
    h1, h2, h3 = out["p"].tolist()
    assert out["statistic"].iloc[0] == pytest.approx(0.3) and h1 < 0.05  # typed: 4 of 20 settled
    assert out["statistic"].iloc[1] == 0.2 - 1.0 and h2 < 0.01
    assert out["statistic"].iloc[2] < 0 and h3 < 0.01


def test_hypothesis_tests_h2_drops_undefined_resamples():
    # cv: 20 of 40 wrong, all caught (d 1); typed: 1 of 4 wrong, uncaught (d 0), and about a third
    # of typed resamples hold no wrong record, so d_typed is 0/0 there and must not count
    cons = _cons([(i, 1, 0.99) for i in range(44)])
    firsts = _firsts([(i, "Aves", 2 if i < 20 or i == 40 else 1, i < 40) for i in range(44)])
    public = pd.DataFrame({"record_id": range(44), "taxon_id": [1] * 40 + [2, 1, 1, 1]})
    levels = pd.DataFrame({"record_id": range(44), "level": [1] * 44})
    out = hypothesis_tests(cons, firsts, public, levels, boot=200).set_index("hypothesis")
    assert out.loc["H2 detection cv < typed", "p"] == 1.0


def test_hypothesis_tests_skip_untestable():
    cons = _cons([(1, 1, 0.99), (2, 1, 0.99)])
    firsts = _firsts([(1, "Aves", 1, True), (2, "Aves", 1, False)])
    public = pd.DataFrame({"record_id": [1, 2], "taxon_id": [1, 1]})
    levels = pd.DataFrame({"record_id": [1, 2], "level": [1, 1]})
    out = hypothesis_tests(cons, firsts, public, levels, boot=10)
    assert out["hypothesis"].tolist() == ["H1 error cv != typed"] and out["p"].item() == 1.0
