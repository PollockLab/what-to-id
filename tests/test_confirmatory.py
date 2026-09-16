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
KW = {"start": "2026-11-01", "cutoff": "2026-12-01"}


def _idents():
    rows = []
    for user in range(10, 16):
        for rec in (1, 3, 4, 5, 7):
            if (user + rec) % 3:
                rows.append((rec, user, "2026-11-02T12:00:00Z", "species"))
    return pd.DataFrame(rows, columns=["id", "user_id", "created_at", "taxon_rank"])


def test_each_tested_list_has_its_pinned_primary_outcome():
    assert confirmatory.PRIMARY == {
        "gap_first": "cell_score",
        "similarity": "none",
        "novelty": "none",
    }
    assert confirmatory.primary_outcome("gap_first") == "cell_score"
    res = confirmatory.confirmatory(_idents(), SERVED, control="recency", reps=200, **KW)
    prim = res[res["role"] == "primary"].set_index("arm")["outcome"].to_dict()
    assert prim == {"gap_first": "weighted", "novelty": "plain", "similarity": "plain"}
    sec = res[res["role"] == "secondary"].set_index("arm")["outcome"].to_dict()
    assert sec == {"gap_first": "plain", "novelty": "weighted", "similarity": "weighted"}
    weighted = analysis.identifier_counts(_idents(), SERVED, weight="cell_score", **KW)
    want = analysis.analyse(weighted, control="recency", reps=200).set_index("arm")
    got = res[res["role"] == "primary"].set_index("arm")
    assert got.loc["gap_first", "p"] == want.loc["gap_first", "p"]
    assert got.loc["gap_first", "mean_diff"] == pytest.approx(want.loc["gap_first", "mean_diff"])


def test_holm_runs_over_the_three_primary_p_values_only():
    def frame(ps):
        rows = [
            {c: 0 for c in analysis.RESULT_COLUMNS} | {"arm": a, "control": "recency", "p": p}
            for a, p in ps.items()
        ]
        return pd.DataFrame(rows).assign(p_holm=1.0)

    plain = frame({"gap_first": 0.001, "similarity": 0.02, "novelty": 0.04})
    weighted = frame({"gap_first": 0.01, "similarity": 0.0001, "novelty": 0.0002})
    res = confirmatory.family({"none": plain, "cell_score": weighted}).set_index(["role", "arm"])
    prim = res.loc["primary"]
    assert len(prim) == 3
    assert prim.loc["gap_first", "p_holm"] == pytest.approx(0.03)
    assert prim.loc["similarity", "p_holm"] == pytest.approx(0.04)
    assert prim.loc["novelty", "p_holm"] == pytest.approx(0.04)
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
    assert analysis.main([*args, "--reps", "100"]) == 0
    lines = capsys.readouterr().out.splitlines()
    head = next(ln for ln in lines if ln.startswith("| arm |"))
    cols = [c.strip() for c in head.strip("|").split("|")]
    assert cols[2:4] == ["outcome", "role"] and cols[-2:] == ["p_holm", "p_record"]
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines if ln.startswith("| ")]
    body = [r for r in rows if r[0] in ARMS]
    assert [r[:4] for r in body if r[3] == "primary"] == [
        ["gap_first", "recency", "weighted", "primary"],
        ["novelty", "recency", "plain", "primary"],
        ["similarity", "recency", "plain", "primary"],
    ]
    assert all(r[cols.index("p_holm")] == "nan" for r in body if r[3] == "secondary")
    assert np.isfinite([float(r[-1]) for r in body]).all()
