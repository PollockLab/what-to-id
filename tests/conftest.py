"""Shared synthetic fixtures: a 3-cell webapp dir and a pool generator."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# [lat, lon, discover, conservation, env, staleness, urgency, travel_min, n_train]
CELLS = [
    [49.0, -123.0, 0.5, 0.0, 0.1, 0.5, 0.0, 10.0, 3],
    [49.0, -122.5, 0.9, 0.2, 0.3, 0.9, 0.1, 20.0, 5],
    [49.5, -123.0, 0.0, 0.0, 0.0, 0.0, 0.0, 30.0, 0],
]
GROUPS = ["Aves", "Insecta", "Plantae"]


def write_webapp(tmp: Path, groups=("Aves", "All_biodiversity"), cells=CELLS) -> Path:
    d = tmp / "ca"
    d.mkdir(parents=True, exist_ok=True)
    for g in groups:
        (d / f"webapp_data_{g}.json").write_text(json.dumps({g: cells}))
    return d


@pytest.fixture
def webapp_dir(tmp_path: Path) -> Path:
    return write_webapp(tmp_path)


def make_pool(n: int = 200, seed: int = 1, groups=GROUPS, n_users: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2026-08-01", tz="UTC")
    created = t0 + pd.to_timedelta(rng.integers(0, 30 * 86400, n), unit="s")
    lat = 49.0 + rng.uniform(-0.05, 0.05, n)
    lon = np.where(rng.random(n) < 0.5, -123.0, -122.5) + rng.uniform(-0.05, 0.05, n)
    return pd.DataFrame(
        {
            "id": np.arange(1000, 1000 + n, dtype="int64"),
            "created_at": [t.isoformat() for t in created],
            "observed_on": [t.date().isoformat() for t in created],
            "lat": lat,
            "lon": lon,
            "iconic_taxon": rng.choice(groups, n),
            "taxon_id": pd.array(rng.integers(1, 500, n), dtype="Int64"),
            "taxon_name": ["Taxon"] * n,
            "rank": ["genus"] * n,
            "user_id": pd.array(rng.integers(1, n_users + 1, n), dtype="Int64"),
            "ident_count": np.zeros(n, dtype="int64"),
            "agree": np.zeros(n, dtype="int64"),
            "photo_url": [f"https://example.org/{i}.jpg" for i in range(n)],
        }
    )


@pytest.fixture
def pool() -> pd.DataFrame:
    return make_pool()
