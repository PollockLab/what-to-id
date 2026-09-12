import logging

import numpy as np
import pandas as pd
import pytest

from what_to_id.cells import DISCOVERY_W, cell_score, load_cells, nearest_cells, score_records

from .conftest import CELLS, write_webapp


def test_load_cells_columns(webapp_dir):
    df = load_cells("Aves", webapp_dir=webapp_dir)
    assert list(df.columns) == [
        "lat",
        "lon",
        "discover",
        "conservation",
        "env",
        "staleness",
        "urgency",
    ]
    assert len(df) == 3
    assert df.loc[1, "discover"] == 0.9


def test_load_cells_falls_back(webapp_dir, caplog):
    with caplog.at_level(logging.WARNING):
        df = load_cells("Mollusca", webapp_dir=webapp_dir)
    assert len(df) == 3
    assert "All_biodiversity" in caplog.text


def test_load_cells_missing_everything(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cells("Aves", webapp_dir=tmp_path)


def test_cell_score_blend_and_clip(webapp_dir):
    df = load_cells("Aves", webapp_dir=webapp_dir)
    s = cell_score(df, DISCOVERY_W)
    assert s[0] == pytest.approx(0.5 + 0.6 * 0.5)
    assert s[1] == 1.0  # 0.9 + 0.54 clipped
    assert s[2] == 0.0
    with pytest.raises(ValueError):
        cell_score(df, {"bogus": 1.0})


def test_score_records_nearest_and_far(webapp_dir):
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "lat": [49.0, 49.0, 50.0, np.nan],
            "lon": [-123.0, -122.5, -123.0, -123.0],
            "iconic_taxon": ["Aves", "Aves", "Aves", "Aves"],
        }
    )
    nc = nearest_cells(pool, webapp_dir=webapp_dir)
    assert nc.loc[0, "cell_score"] == pytest.approx(0.8)
    assert nc.loc[0, "cell_km"] == pytest.approx(0.0, abs=1e-6)
    assert (nc.loc[0, ["cell_lat", "cell_lon"]].to_numpy() == [49.0, -123.0]).all()
    assert nc.loc[1, "cell_score"] == 1.0
    assert np.isnan(nc.loc[2, "cell_score"])  # ~55 km north of the nearest centre
    assert np.isnan(nc.loc[3, "cell_score"])  # missing lat
    s = score_records(pool, webapp_dir=webapp_dir)
    assert s.name == "cell_score"
    assert s.tolist()[:2] == pytest.approx([0.8, 1.0])


def test_score_records_group_fallback(tmp_path):
    other = [[49.0, -123.0, 0.1, 0, 0, 0, 0, 0, 0]]
    d = write_webapp(tmp_path, groups=("Aves",), cells=CELLS)
    write_webapp(tmp_path, groups=("All_biodiversity",), cells=other)
    pool = pd.DataFrame(
        {"id": [1, 2], "lat": [49.0, 49.0], "lon": [-123.0, -123.0], "iconic_taxon": ["Aves", None]}
    )
    s = score_records(pool, webapp_dir=d)
    assert s.iloc[0] == pytest.approx(0.8)
    assert s.iloc[1] == pytest.approx(0.1)


def test_score_records_empty(webapp_dir):
    pool = pd.DataFrame({"id": [], "lat": [], "lon": [], "iconic_taxon": []})
    assert len(score_records(pool, webapp_dir=webapp_dir)) == 0
