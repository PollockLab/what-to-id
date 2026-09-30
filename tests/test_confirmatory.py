import numpy as np
import pandas as pd
import pytest

from what_to_id import analysis, confirmatory

ARMS = ["recency", "gap_first", "similarity", "novelty"]
SERVED = pd.DataFrame(
    {
        "id": list(range(1, 9)),
        "arm": [a for a in ARMS for _ in range(2)],
        "cell_score": [0.1, 0.2, 0.9, 0.8, 0.3, 0.4, 0.5, 0.6],
    }
)
USERS = list(range(10, 16))
KW = {"start": "2026-11-01", "cutoff": "2026-12-01", "users": USERS}


def _idents():
    """Participant IDs on records observed by user 99, who is not a participant."""
    rows = []
    for user in USERS:
        for rec in (1, 3, 4, 5, 7):
            if (user + rec) % 3:
                rows.append((rec, user, "2026-11-02T12:00:00Z", "species", 99))
    return pd.DataFrame(rows, columns=["id", "user_id", "created_at", "taxon_rank", "observer_id"])


def test_each_tested_list_has_its_pinned_primary_outcome():
    assert confirmatory.PRIMARY == {
        "gap_first": "cell_score",
        "similarity": "none",
        "novelty": "none",
    }
    assert confirmatory.primary_outcome("gap_first") == "cell_score"
    res = confirmatory.confirmatory(_idents(), SERVED, control="recency", reps=200, **KW)
    prim = res[res["role"] == "primary"].set_index("arm")["outcome"].to_dict()
    assert prim == {"gap_first": "weighted", "similarity": "plain"}
    explo = res[res["role"] == "exploratory"].set_index("arm")["outcome"].to_dict()
    assert explo == {"novelty": "plain"}
    sec = res[res["role"] == "secondary"].set_index("arm")["outcome"].to_dict()
    assert sec == {"gap_first": "plain", "novelty": "weighted", "similarity": "weighted"}
    weighted = analysis.identifier_counts(_idents(), SERVED, weight="cell_score", **KW)
    want = analysis.analyse(weighted, control="recency", reps=200).set_index("arm")
    got = res[res["role"] == "primary"].set_index("arm")
    assert got.loc["gap_first", "p_signflip"] == want.loc["gap_first", "p"]
    assert got.loc["gap_first", "p_sign"] == want.loc["gap_first", "p_sign"]
    assert got.loc["gap_first", "mean_diff"] == pytest.approx(want.loc["gap_first", "mean_diff"])


def _record_p(arm, weight, alternative):
    w = None if weight == "none" else weight
    totals = analysis.record_totals(_idents(), SERVED, weight=w, **KW)
    return analysis.record_shuffle_p(
        totals, SERVED, arm=arm, control="recency", reps=200, seed=7, alternative=alternative
    )


def test_primary_p_is_the_one_sided_record_level_p_and_holm_runs_over_h1_and_h2():
    res = confirmatory.confirmatory(_idents(), SERVED, control="recency", reps=200, seed=7, **KW)
    assert list(res["role"]) == ["primary"] * 2 + ["exploratory"] + ["secondary"] * 3
    prim = res[res["role"] == "primary"].set_index("arm")
    assert confirmatory.HOLM_FAMILY == ("gap_first", "similarity")
    want = {
        arm: _record_p(arm, confirmatory.PRIMARY[arm], "greater")
        for arm in ("gap_first", "similarity")
    }
    assert prim["p"].to_dict() == pytest.approx(want)
    assert prim["p_holm"].to_dict() == pytest.approx(analysis.holm(want))
    assert list(res.columns) == list(confirmatory.COLUMNS)


def test_h3_is_exploratory_two_sided_and_unadjusted():
    res = confirmatory.confirmatory(_idents(), SERVED, control="recency", reps=200, seed=7, **KW)
    h3 = res[res["role"] == "exploratory"].set_index("arm")
    assert list(h3.index) == ["novelty"] and h3.loc["novelty", "outcome"] == "plain"
    assert h3.loc["novelty", "p"] == pytest.approx(_record_p("novelty", "none", "two-sided"))
    assert np.isnan(h3.loc["novelty", "p_holm"])
    sec = res[res["role"] == "secondary"].set_index("arm")
    for arm in confirmatory.PRIMARY:
        other = "none" if confirmatory.PRIMARY[arm] == "cell_score" else "cell_score"
        assert sec.loc[arm, "p"] == pytest.approx(_record_p(arm, other, "two-sided"))


def test_an_id_on_the_identifiers_own_record_does_not_count():
    idents = _idents()
    own = pd.DataFrame(
        [(2, 10, "2026-11-02T12:00:00Z", "species", 10)], columns=list(idents.columns)
    )
    with_own = pd.concat([idents, own], ignore_index=True)
    for weight in (None, "cell_score"):
        base = analysis.identifier_counts(idents, SERVED, weight=weight, **KW)
        got = analysis.identifier_counts(with_own, SERVED, weight=weight, **KW)
        pd.testing.assert_frame_equal(got, base)
        base_totals = analysis.record_totals(idents, SERVED, weight=weight, **KW)
        got_totals = analysis.record_totals(with_own, SERVED, weight=weight, **KW)
        pd.testing.assert_series_equal(got_totals, base_totals)
    # The same ID on someone else's record counts.
    other = with_own.assign(observer_id=with_own["observer_id"].where(with_own["id"] != 2, 99))
    assert analysis.identifier_counts(other, SERVED, **KW).loc[10, "recency"] == 2
    with pytest.raises(ValueError, match="observer_id"):
        analysis.identifier_counts(idents.drop(columns="observer_id"), SERVED, **KW)


def test_the_family_needs_participants():
    kw = {k: v for k, v in KW.items() if k != "users"}
    for users in (None, []):
        with pytest.raises(ValueError, match="participants only"):
            confirmatory.confirmatory(_idents(), SERVED, control="recency", users=users, **kw)


def test_a_list_with_nothing_served_stops_the_family():
    served = SERVED[SERVED["arm"] != "novelty"]
    with pytest.raises(ValueError, match=r"no served records: \['novelty'\]"):
        confirmatory.confirmatory(_idents(), served, control="recency", reps=10, **KW)


def test_holm_runs_over_the_h1_and_h2_p_values_only():
    def frame(ps):
        # p_signflip is set to 1 so a Holm over it instead of p would show.
        rows = [
            {c: 0 for c in analysis.RESULT_COLUMNS}
            | {"arm": a, "control": "recency", "p": p, "p_signflip": 1.0}
            for a, p in ps.items()
        ]
        return pd.DataFrame(rows).assign(p_holm=1.0)

    plain = frame({"gap_first": 0.001, "similarity": 0.02, "novelty": 0.04})
    weighted = frame({"gap_first": 0.01, "similarity": 0.0001, "novelty": 0.0002})
    res = confirmatory.family({"none": plain, "cell_score": weighted}).set_index(["role", "arm"])
    prim = res.loc["primary"]
    assert sorted(prim.index) == ["gap_first", "similarity"]
    # Holm over two: 0.01 * 2 and max(0.02, 0.02 * 1). Over three it would be 0.03 and 0.04.
    assert prim.loc["gap_first", "p_holm"] == pytest.approx(0.02)
    assert prim.loc["similarity", "p_holm"] == pytest.approx(0.02)
    assert res.loc["exploratory"].loc["novelty", "p"] == 0.04
    assert np.isnan(res.loc["exploratory"].loc["novelty", "p_holm"])
    assert res.loc["secondary", "p_holm"].isna().all()
    assert res.loc["secondary"].loc["similarity", "p"] == 0.0001
    with pytest.raises(ValueError, match="missing weightings"):
        confirmatory.family({"none": plain})


def test_a_list_with_no_pinned_outcome_fails_and_names_the_list():
    served = SERVED.assign(arm=SERVED["arm"].replace({"novelty": "surprise"}))
    with pytest.raises(ValueError, match="no primary outcome pinned for list 'surprise'"):
        confirmatory.confirmatory(_idents(), served, control="recency", reps=10, **KW)
    with pytest.raises(ValueError, match="'surprise'"):
        confirmatory.primary_outcome("surprise")
    with pytest.raises(ValueError, match="control arm"):
        confirmatory.confirmatory(_idents(), SERVED, control="nope", reps=10, **KW)


def test_cli_default_is_the_confirmatory_family(tmp_path, capsys):
    _idents().to_parquet(tmp_path / "i.parquet")
    SERVED.to_parquet(tmp_path / "s.parquet")
    args = ["--idents", str(tmp_path / "i.parquet"), "--served", str(tmp_path / "s.parquet")]
    args += ["--control", "recency", "--start", KW["start"], "--cutoff", KW["cutoff"]]
    with pytest.raises(SystemExit):
        analysis.main([*args, "--reps", "100"])
    assert "give --users" in capsys.readouterr().err
    (tmp_path / "u.txt").write_text("\n".join(map(str, USERS)))
    args += ["--users", str(tmp_path / "u.txt")]
    assert analysis.main([*args, "--reps", "100"]) == 0
    out = capsys.readouterr().out
    assert analysis.PRIMARY_NOTE in out and analysis.RECORD_NOTE not in out
    lines = out.splitlines()
    head = next(ln for ln in lines if ln.startswith("| arm |"))
    cols = [c.strip() for c in head.strip("|").split("|")]
    assert cols == list(confirmatory.COLUMNS)
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines if ln.startswith("| ")]
    body = [r for r in rows if r[0] in ARMS]
    assert [r[:4] for r in body if r[3] != "secondary"] == [
        ["gap_first", "recency", "weighted", "primary"],
        ["similarity", "recency", "plain", "primary"],
        ["novelty", "recency", "plain", "exploratory"],
    ]
    assert all(r[cols.index("p_holm")] == "nan" for r in body if r[3] != "primary")
    assert np.isfinite([float(r[cols.index("p")]) for r in body]).all()
