"""where-to-blitz cell score: nearest 25 km cell centre per record, Species discovery blend.

The where-to-blitz webapp JSON is a dict whose first value is a list of rows in the order
[lat, lon, discover, conservation, env, staleness, urgency, travel_min, n_train]. One file per
iconic taxon group; records whose group has no file fall back to All_biodiversity.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

log = logging.getLogger(__name__)

WEBAPP_DIR = Path(
    os.environ.get(
        "WHERE_TO_BLITZ_CA", "/Users/w/Documents/Github/where-to-blitz/cluster_results/ca"
    )
)
FALLBACK_GROUP = "All_biodiversity"
AXES = ["discover", "conservation", "env", "staleness", "urgency"]
# Row layout of the app JSON. Columns 7 and 8 (travel_min, n_train) are not used here.
AX = {"lat": 0, "lon": 1, "discover": 2, "conservation": 3, "env": 4, "staleness": 5, "urgency": 6}
# where-to-blitz "Species discovery" preset: w=[1.0, 0, 0, 0.6, 0] over AXES.
DISCOVERY_W: Mapping[str, float] = {"discover": 1.0, "staleness": 0.6}
EARTH_KM = 6371.0088


def _group_path(group: str, webapp_dir: Path) -> Path:
    return Path(webapp_dir) / f"webapp_data_{group}.json"


def load_cells(group: str, *, webapp_dir: Path = WEBAPP_DIR) -> pd.DataFrame:
    """Cell centres and axis values for one group; falls back to All_biodiversity."""
    path = _group_path(group, webapp_dir)
    if not path.exists():
        fallback = _group_path(FALLBACK_GROUP, webapp_dir)
        if not fallback.exists():
            raise FileNotFoundError(
                f"no webapp JSON for {group!r} or {FALLBACK_GROUP!r} in {webapp_dir}"
            )
        log.warning("no cell file for group %r, falling back to %s", group, FALLBACK_GROUP)
        path = fallback
    with open(path) as fh:
        d = json.load(fh)
    if not isinstance(d, dict) or not d:
        raise ValueError(f"{path}: expected a non-empty dict of rows")
    rows = np.asarray(d[next(iter(d))], dtype=float)
    if rows.ndim != 2 or rows.shape[1] < 7:
        raise ValueError(f"{path}: expected rows with at least 7 columns, got shape {rows.shape}")
    return pd.DataFrame({k: rows[:, i] for k, i in AX.items()})


def cell_score(cells: pd.DataFrame, w: Mapping[str, float] = DISCOVERY_W) -> np.ndarray:
    """Weighted axis blend, clipped to [0, 1] like the webapp colour ramp."""
    unknown = set(w) - set(AXES)
    if unknown:
        raise ValueError(f"unknown axes in weights: {sorted(unknown)}")
    blend = np.zeros(len(cells), dtype=float)
    for axis, weight in w.items():
        blend += weight * cells[axis].to_numpy(dtype=float)
    return np.clip(blend, 0.0, 1.0)


def _xyz(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def _chord_to_km(chord: np.ndarray) -> np.ndarray:
    # Unit-sphere chord length to great-circle distance (equivalent to haversine).
    return 2.0 * EARTH_KM * np.arcsin(np.clip(chord / 2.0, 0.0, 1.0))


def nearest_cells(
    pool: pd.DataFrame,
    *,
    webapp_dir: Path = WEBAPP_DIR,
    max_km: float = 20.0,
    w: Mapping[str, float] = DISCOVERY_W,
) -> pd.DataFrame:
    """Per record: nearest cell centre of its iconic_taxon group and that cell's score.

    Columns cell_lat, cell_lon, cell_km, cell_score, aligned to pool.index. NaN throughout when
    lat/lon is missing or the nearest centre is farther than max_km (outside the grid).
    """
    out = pd.DataFrame(
        {c: np.full(len(pool), np.nan) for c in ["cell_lat", "cell_lon", "cell_km", "cell_score"]},
        index=pool.index,
    )
    if pool.empty:
        return out
    lat = pd.to_numeric(pool["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(pool["lon"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(lat) & np.isfinite(lon)
    groups = pool["iconic_taxon"].fillna(FALLBACK_GROUP).astype(str).to_numpy()
    for group in np.unique(groups):
        rows = np.flatnonzero((groups == group) & ok)
        if rows.size == 0:
            continue
        cells = load_cells(group, webapp_dir=webapp_dir)
        scores = cell_score(cells, w)
        tree = cKDTree(_xyz(cells["lat"].to_numpy(), cells["lon"].to_numpy()))
        chord, idx = tree.query(_xyz(lat[rows], lon[rows]), k=1)
        km = _chord_to_km(np.asarray(chord, dtype=float))
        within = km <= max_km
        hit = rows[within]
        cell_idx = idx[within]
        out.iloc[hit, out.columns.get_loc("cell_lat")] = cells["lat"].to_numpy()[cell_idx]
        out.iloc[hit, out.columns.get_loc("cell_lon")] = cells["lon"].to_numpy()[cell_idx]
        out.iloc[hit, out.columns.get_loc("cell_km")] = km[within]
        out.iloc[hit, out.columns.get_loc("cell_score")] = scores[cell_idx]
    return out


def score_records(
    pool: pd.DataFrame,
    *,
    webapp_dir: Path = WEBAPP_DIR,
    max_km: float = 20.0,
    w: Mapping[str, float] = DISCOVERY_W,
) -> pd.Series:
    """Species-discovery score of each record's nearest cell, named "cell_score"."""
    return nearest_cells(pool, webapp_dir=webapp_dir, max_km=max_km, w=w)["cell_score"].rename(
        "cell_score"
    )
