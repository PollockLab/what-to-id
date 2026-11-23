import pandas as pd

from what_to_id import challenges

TAXA = {
    "1": [0, "A", "", "kingdom"],
    "2": [1, "B", "", "genus"],
    "3": [2, "C", "", "species"],
    "4": [1, "D", "", "genus"],
    "5": [4, "E", "", "species"],
}
CELLS = pd.DataFrame(
    {"lat": [49.0, 55.0], "lon": [-123.0, -125.0], "env": [0.1, 0.9], "discover": [0.2, 0.9]}
)


def _ids(user, taxon, lat, lon, n):
    return pd.DataFrame(
        {"user": [user] * n, "taxon_id": [taxon] * n, "lat": [lat] * n, "lon": [lon] * n}
    )


def test_spam_saturates_and_breadth_wins():
    spam = _ids("spammer", 3, 55.0, -125.0, 200)
    broad = pd.concat([_ids("broad", 3, 49.0, -123.0, 5), _ids("broad", 5, 55.0, -125.0, 5)])
    s = challenges.scores(pd.concat([spam, broad]), TAXA, CELLS)
    assert s.loc["spammer", "n_ids"] > s.loc["broad", "n_ids"]
    assert s.loc["broad", "tree"] > s.loc["spammer", "tree"]
    assert s.loc["spammer", "tree"] == 3.0  # three lineage nodes, each capped at full credit
    assert s.loc["broad", "climate"] == s.loc["spammer", "climate"] == 1.0  # only cell 1 is top


def test_off_grid_and_unknown_taxon_score_zero():
    s = challenges.scores(_ids("u", 999, 0.0, 0.0, 3), TAXA, CELLS)
    assert s.loc["u", ["tree", "climate", "checklist"]].tolist() == [0.0, 0.0, 0.0]


def test_id_gap_ranks_the_under_identified_cell_first():
    nid = pd.concat([_ids("x", 3, 55.0, -125.0, 15), _ids("x", 3, 49.0, -123.0, 5)])
    rg = pd.concat([_ids("x", 3, 55.0, -125.0, 10), _ids("x", 3, 49.0, -123.0, 30)])
    gap = challenges.id_gap(CELLS, nid, rg)
    assert gap.idxmax() == 1 and gap.loc[1] == 1.0
    s = challenges.scores(_ids("u", 3, 55.0, -125.0, 5), TAXA, CELLS, gap)
    assert s.loc["u", "id_gap"] == 1.0


def test_unique_counts_units_no_one_else_covers():
    ids = pd.concat(
        [
            _ids("a", 3, 49.0, -123.0, 4),
            _ids("b", 3, 49.0, -123.0, 1),
            _ids("b", 5, 55.0, -125.0, 1),
        ]
    )
    s = challenges.scores(ids, TAXA, CELLS)
    assert s.loc["a", "unique"] == 0.0 and s.loc["b", "unique"] == 1.0
