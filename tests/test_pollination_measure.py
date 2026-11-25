"""The pollination measurement script: identification replay, cohort and gap. No network."""

import numpy as np
import pandas as pd
import pollination_measure as pm

GENUS = {"id": 5, "rank_level": 20, "ancestor_ids": [1, 2]}
SP_A = {"id": 6, "rank_level": 10, "ancestor_ids": [1, 2, 5], "min_species_taxon_id": 6}
SP_B = {"id": 7, "rank_level": 10, "ancestor_ids": [1, 2, 5], "min_species_taxon_id": 7}


def ids(*taxa):
    return [{"taxon": t} for t in taxa]


def test_community_needs_two_and_a_two_thirds_majority():
    assert pm.community([]) == (None, 99, False)
    assert pm.community(ids(SP_A)) == (6, 10, False)  # one identification is only the shown taxon
    assert pm.community(ids(SP_A, SP_A)) == (6, 10, True)
    # a genus identification agrees with the species under it, at the genus
    assert pm.community(ids(SP_A, GENUS)) == (5, 20, True)
    # two species disagree: the community falls back to the genus (rank 99, never named)
    assert pm.community(ids(SP_A, SP_B)) == (5, 99, True)
    # 2 for A, 1 for B is 2/3, not more than 2/3, so genus
    assert pm.community(ids(SP_A, SP_A, SP_B))[:1] == (5,)
    assert pm.community(ids(SP_A, SP_A, SP_A, SP_B))[0] == 6


def test_mde_shrinks_with_n_and_is_zero_at_p_zero():
    assert pm.mde(0.2, 800, 800) < pm.mde(0.2, 200, 200)
    assert pm.mde(0.0, 100, 100) == 0.0


def snap(rows):
    return pd.DataFrame(
        [{"id": i, "quality_grade": q, "taxon_rank_level": lv, "group": g, "user_id": u}
         for i, q, lv, g, u in rows]
    )  # fmt: skip


def test_report_gap_is_treated_change_minus_control_change(tmp_path, capsys):
    t0 = snap([(i, "needs_id", 20, "bee", i) for i in range(40)])
    c0 = snap([(100 + i, "needs_id", 20, "bee", 100 + i) for i in range(40)])
    t1 = t0.copy()
    t1.loc[:19, "quality_grade"] = "research"  # 50% of treated reach research grade
    t1.loc[:19, "taxon_rank_level"] = 10
    c1 = c0.copy()
    c1.loc[:9, "quality_grade"] = "research"  # 25% of control
    c1.loc[:9, "taxon_rank_level"] = 10
    paths = []
    for n, d in zip(["t0", "t1", "c0", "c1"], (t0, t1, c0, c1), strict=True):
        paths.append(str(tmp_path / f"{n}.parquet"))
        d.to_parquet(paths[-1])
    assert pm.report([paths]) == 0
    out = capsys.readouterr().out
    assert "research grade" in out and "50.0" in out and "25.0" in out
    g = pm.gap_table(pm.cohort(t0, t1), pm.cohort(c0, c1), reps=50)
    assert np.isclose(g["est"][2], 25.0) and g["lo"][2] <= 25.0 <= g["hi"][2]


def test_cohort_drops_records_that_were_not_needs_id_or_are_gone():
    a = snap(
        [
            (1, "needs_id", 20, "bee", 1),
            (2, "research", 10, "bee", 2),
            (3, "needs_id", 20, "bee", 3),
        ]
    )
    b = snap([(1, "research", 10, "bee", 1), (2, "research", 10, "bee", 2)])
    c = pm.cohort(a, b)
    assert c.id.tolist() == [1] and c.rg1.tolist() == [1.0] and c.sp1.tolist() == [1.0]
