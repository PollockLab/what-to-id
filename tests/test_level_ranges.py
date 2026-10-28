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
    d = h3.latlng_to_cell(58.0, -130.0, 4)  # in a range but holds no record: not land
    orm = pd.DataFrame({"taxon_id": [1, 2, 3, 3], "cells": [[a, b], [b, c], [a, d], [c]]})
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
                {"id": [14], "lat": [50.5], "lon": [-123.0], "taxon_id": [3], "taxon_name": ["C c"]}
            ),
        ]
    )
    notes, ranges, grid = lr.build(levels, pool, orm)
    assert notes["id"].tolist() == [10, 11, 12, 13]
    # id 10 sits in cell a, id 12 in b, and the label has both but C c lacks b; 11 has no point
    assert notes["range_note"].tolist() == [lr.ONLY_LABEL, None, lr.ONLY_LABEL, None]
    assert notes["lat"].round(2).tolist()[0] == 48.5 and np.isnan(notes["lat"][1])
    ids = sorted({a, b, c})
    assert len(grid) == 3 and len(grid["lat"][0]) == 6
    r = {n: [ids[i] for i in cs] for n, cs in zip(ranges["name"], ranges["cells"], strict=True)}
    assert r == {"A a": sorted([a, b]), "B b": sorted([b, c]), "C c": sorted([a, c])}
    assert all(cs.dtype == np.int16 for cs in ranges["cells"])
    assert "Z z" not in r
    # a known range wholly off the grid stays, empty, so the card still gets its map
    orm.loc[1, "cells"] = [d]
    _, ranges, _ = lr.build(levels, pool, orm)
    assert ranges.set_index("name")["cells"]["B b"].tolist() == []


def test_out_km_is_zero_inside_and_the_distance_to_the_nearest_cell_outside():
    a, b, c = (h3.latlng_to_cell(48.5 + k, -123.0, 4) for k in range(3))
    orm = pd.DataFrame({"taxon_id": [1, 2], "cells": [[a, b], [b, c]]})
    levels = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "taxon_id": [1, 2, 2, 7],
            "taxon_name": ["A a", "B b", "B b", "X x"],
            "looks_like_name": ["B b"] * 4,
            "level": ["easy", "easy", "weird", "weird"],
        }
    )
    lat = [48.5, 48.5, None, 48.5]
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "lat": lat,
            "lon": -123.0,
            "taxon_id": [1, 2, 2, 7],
            "taxon_name": ["A a", "B b", "B b", "X x"],
        }
    )
    notes, ranges, _ = lr.build(levels, pool, orm)
    k = notes["out_km"]
    assert k[0] == 0 and 100 <= k[1] <= 125  # one degree of latitude is about 111 km
    assert k[2] is pd.NA and k[3] is pd.NA  # no point; no known range
    assert notes["range_note"].isna().all()
    cells = ranges.set_index("name")["cells"]
    assert len(cells["A a"]) == 1 and len(cells["B b"]) == 0  # B b lies off the land mask


def test_km_to_cells_in_blocks_matches_one_pass():
    rng = np.random.default_rng(0)
    lat, lon = rng.uniform(48, 60, 50), rng.uniform(-139, -114, 50)
    centres = np.radians(np.column_stack([rng.uniform(48, 60, 7), rng.uniform(-139, -114, 7)]))
    one = lr.km_to_cells(lat, lon, centres)
    assert np.allclose(lr.km_to_cells(lat, lon, centres, pairs=10), one)
    assert np.allclose(lr.km_to_cells(lat, lon, centres, pairs=1), one)


def test_identify_rows_build_the_same_tables_as_level_rows():
    a, b, c = (h3.latlng_to_cell(48.5 + k, -123.0, 4) for k in range(3))
    orm = pd.DataFrame({"taxon_id": [1, 2, 3], "cells": [[a, b], [b, c], [a]]})
    pool = pd.DataFrame(
        {
            "id": [10, 11, 12, 13],
            "lat": [48.5, 50.5, 49.5, 48.5],
            "lon": -123.0,
            "taxon_id": [1, 1, 2, 3],
            "taxon_name": ["A a", "A a", "B b", "C c"],
        }
    )
    ident = pd.DataFrame(
        {
            "id": [10, 11, 12, 13, 99],  # 99 has a taxon the pool does not know
            "taxon_id": [1, 1, 2, 3, 8],
            "level": np.array([2, 2, 1, 0, 2], np.int8),
            "looks_like": pd.Categorical(["B b", "C c", "A a", None, "A a"]),
        }
    )
    levels = lr.from_identify(ident, pool)
    assert levels["level"].tolist() == ["taxonomist", "taxonomist", "easy", "none", "taxonomist"]
    assert levels["taxon_name"].tolist()[:4] == ["A a", "A a", "B b", "C c"]
    notes, ranges, _ = lr.build(levels, pool, orm)
    assert notes["range_note"].tolist() == [lr.ONLY_LABEL, lr.BOTH_OUT, None, None, None]
    assert notes["out_km"].tolist()[:4] == [0, pytest.approx(111, abs=15), 0, 0]
    assert sorted(ranges["name"]) == ["A a", "B b", "C c"]


def test_a_likely_mislabel_gets_the_range_note_a_close_call_gets():
    a, b = (h3.latlng_to_cell(48.5 + k, -123.0, 4) for k in range(2))
    orm = pd.DataFrame({"taxon_id": [1, 2], "cells": [[a], [b]]})
    pool = pd.DataFrame(
        {"id": [10, 11, 12], "lat": [48.5, 48.5, 49.5], "lon": [-123.0] * 3}
        | {"taxon_id": [1, 1, 2], "taxon_name": ["A a", "A a", "B b"]}
    )
    levels = (
        pool[["id", "taxon_id", "taxon_name"]]
        .iloc[:2]
        .assign(looks_like_name="B b", level=["taxonomist", "mislabel"])
    )
    notes, _, _ = lr.build(levels, pool, orm)
    assert notes["range_note"].tolist() == [lr.ONLY_LABEL, lr.ONLY_LABEL]
