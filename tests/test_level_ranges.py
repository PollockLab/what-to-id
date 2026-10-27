"""level_ranges: the note truth table and the three parquets on a tiny synthetic set."""

import numpy as np
import pandas as pd
import pytest

h3 = pytest.importorskip("h3")
lr = pytest.importorskip("what_to_id.level_ranges")


@pytest.mark.parametrize(
    "label,look,want",
    [
        (False, True, lr.ONLY_LOOK),
        (True, False, lr.ONLY_LABEL),
        (False, False, lr.BOTH_OUT),
        (True, True, None),
        (None, False, None),
        (True, None, None),
        (None, None, None),
    ],
)
def test_note_truth_table(label, look, want):
    assert lr.note(label, look) == want


def test_build_round_trips_notes_ranges_and_grid(tmp_path):
    a, b, c = (h3.latlng_to_cell(48.5 + k, -123.0, 4) for k in range(3))
    orm = pd.DataFrame({"taxon_id": [1, 2, 3, 3], "cells": [[a, b], [b, c], [a], [c]]})
    levels = pd.DataFrame(
        {
            "id": [10, 11, 12, 13],
            "taxon_id": [1, 1, 1, 9],
            "taxon_name": ["A a", "A a", "A a", "Z z"],
            "looks_like_name": ["B b", "B b", "C c", "B b"],
            "level": ["taxonomist", "taxonomist", "taxonomist", "easy"],
        }
    )
    pool = pd.DataFrame(
        {
            "id": [10, 11, 12, 13],
            "lat": [48.5004, None, 49.5, 48.5],
            "lon": [-123.0, -123.0, -123.0, -123.0],
            "taxon_id": [1, 1, 1, 2],
            "taxon_name": ["A a", "A a", "A a", "B b"],
        }
    )
    pool = pd.concat(
        [
            pool,
            pd.DataFrame(
                {"id": [14], "lat": [0.0], "lon": [0.0], "taxon_id": [3], "taxon_name": ["C c"]}
            ),
        ]
    )
    notes, ranges, grid = lr.build(levels, pool, orm)
    assert notes["id"].tolist() == [10, 11, 12]
    # id 10 sits in cell a, id 12 in b, and the label has both but C c lacks b; 11 has no point
    assert notes["range_note"].tolist() == [lr.ONLY_LABEL, None, lr.ONLY_LABEL]
    assert notes["lat"].round(2).tolist()[0] == 48.5 and np.isnan(notes["lat"][1])
    ids = sorted({a, b, c})
    assert len(grid) == 3 and len(grid["lat"][0]) == 6
    r = {n: [ids[i] for i in cs] for n, cs in zip(ranges["name"], ranges["cells"], strict=True)}
    assert r == {"A a": sorted([a, b]), "B b": sorted([b, c]), "C c": sorted([a, c])}
    assert all(cs.dtype == np.int16 for cs in ranges["cells"])
    assert "Z z" not in r
