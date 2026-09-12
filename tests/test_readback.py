import pandas as pd
import pytest

from what_to_id import analysis, readback


def _ident(user, ts, taxon, rank="species", current=True):
    return {
        "user": {"id": user},
        "created_at": ts,
        "taxon": {"id": taxon, "rank": rank},
        "current": current,
    }


OBS = {
    "id": 11,
    "quality_grade": "research",
    "community_taxon": {"id": 1, "rank": "species"},
    "taxon": {"id": 1, "rank": "species"},
    "identifications_count": 3,
    "identifications": [
        _ident(1, "2026-09-12T00:00:00Z", 1),
        _ident(2, "2026-09-20T00:00:00Z", 2, rank="genus", current=False),
        _ident(2, "2026-09-25T00:00:00Z", 1),
    ],
}


def test_summarise():
    s = readback.summarise(OBS)
    assert s["id"] == 11
    assert s["quality_grade"] == "research"
    assert s["community_rank"] == "species"
    assert s["taxon_rank"] == "species"
    assert s["ident_count"] == 3
    assert s["n_identifiers"] == 2
    assert s["last_ident_at"] == "2026-09-25T00:00:00Z"
    assert len(s["identifications"]) == 3
    assert s["identifications"][0] == {
        "user_id": 1,
        "created_at": "2026-09-12T00:00:00Z",
        "taxon_id": 1,
        "taxon_rank": "species",
        "current": True,
    }
    assert s["identifications"][1]["taxon_rank"] == "genus"
    assert s["identifications"][1]["current"] is False


def test_summarise_sparse():
    s = readback.summarise({"id": 5, "quality_grade": "needs_id", "community_taxon": None})
    assert s["community_rank"] is None and s["taxon_rank"] is None
    assert s["ident_count"] == 0 and s["n_identifiers"] == 0
    assert s["last_ident_at"] is None
    assert s["identifications"] == []


def test_readback_missing_ids_get_none_row():
    obs_df, idents_df = readback.readback([11, 99], fetch=lambda ids: [OBS])
    assert list(obs_df.columns) == list(readback.OBS_COLUMNS)
    assert obs_df["id"].tolist() == [11, 99]
    assert pd.isna(obs_df.loc[1, "quality_grade"])
    assert pd.isna(obs_df.loc[1, "ident_count"])
    assert obs_df.loc[0, "n_identifiers"] == 2
    assert list(idents_df.columns) == list(readback.IDENT_COLUMNS)
    assert len(idents_df) == 3
    assert (idents_df["id"] == 11).all()


@pytest.fixture
def tiny():
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "iconic_taxon": ["Aves", "Aves", "Insecta", "Insecta"],
            "ident_count": [1, 0, 2, 1],
            "cell_score": [0.5, float("nan"), 2.0, 1.0],
        }
    )
    assign = pd.DataFrame({"id": [1, 2, 3, 4], "arm": ["A", "A", "B", "B"]})
    obs = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "quality_grade": ["research", "research", "needs_id", None],
            "community_rank": ["species", None, "species", None],
            "ident_count": [3, 2, 2, None],
        }
    )
    return pool, assign, obs


def test_outcomes(tiny):
    pool, assign, obs = tiny
    out = readback.outcomes(obs, assign, pool).set_index("arm")
    assert list(out.columns) == list(readback.OUTCOME_COLUMNS[1:])
    assert out.loc["A", "n_served"] == 2 and out.loc["B", "n_served"] == 2
    assert out.loc["A", "share_species"] == 1.0
    assert out.loc["B", "share_species"] == 0.5
    assert out.loc["A", "share_engaged"] == 1.0
    assert out.loc["B", "share_engaged"] == 0.5
    assert out.loc["B", "unengaged"] == 0.5
    assert out.loc["A", "weighted_rg"] == 0.5
    assert out.loc["B", "weighted_rg"] == 0.0


def test_outcomes_without_cell_score(tiny):
    pool, assign, obs = tiny
    out = readback.outcomes(obs, assign, pool.drop(columns="cell_score"))
    assert out["weighted_rg"].isna().all()


def test_outcomes_no_assign_single_arm(tiny):
    pool, _, obs = tiny
    out = readback.outcomes(obs, None, pool)
    assert out["arm"].tolist() == ["pool"]
    assert out.loc[0, "n_served"] == 4


def test_dry_run_per_group(tiny):
    pool, _, _ = tiny
    out = readback.dry_run(pool).set_index("arm")
    assert out.loc["Aves", "unengaged"] == 1.0
    assert out.loc["Insecta", "unengaged"] == 0.5
    assert out["share_species"].eq(0.0).all()


def test_to_markdown(tiny):
    pool, assign, obs = tiny
    md = readback.to_markdown(readback.outcomes(obs, assign, pool))
    lines = md.splitlines()
    assert lines[0].startswith("| arm |")
    assert "| A |" in lines[2] and "| B |" in lines[3]
    assert "100.0%" in lines[2]


def test_cli_dry_run(tmp_path, capsys):
    from what_to_id import inat

    pool = pd.DataFrame({c: [None] for c in inat.COLUMNS}).assign(
        id=[1], lat=[0.0], lon=[0.0], ident_count=[0], agree=[0], iconic_taxon=["Aves"]
    )
    p = tmp_path / "pool.parquet"
    pool.to_parquet(p)
    assert readback.main(["--pool", str(p), "--dry-run"]) == 0
    assert "| Aves |" in capsys.readouterr().out


def test_readback_idents_feed_analysis():
    _, idents_df = readback.readback([11], fetch=lambda ids: [OBS])
    served = pd.DataFrame({"id": [11], "arm": ["A"]})
    counts = analysis.identifier_counts(idents_df, served, start="2026-09-01", cutoff="2026-10-01")
    assert counts["A"].to_dict() == {1: 1, 2: 1}
