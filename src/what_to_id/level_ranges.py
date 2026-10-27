"""Range tables for the Close calls cards, from the repaired Open Range Map (H3 res-4 cells).

    python -m what_to_id.level_ranges --levels LEVELS --pool POOL --cells ORM_CELLS --out-dir DIR

Needs the optional ``geo`` extra (h3). A card is checked against the map: is the label taxon
expected in the record's cell, and is the look-alike? A note is written only when they disagree
or both are out. A taxon (or look-alike name) absent from ORM_CELLS is unknown and gives no note.
A look-alike name maps to taxon ids through the pool's taxon_name, as levels.py does.

It writes into DIR, for `levels --range-notes`:
``range-notes.parquet`` (``id``, ``range_note`` on Close calls rows only, ``lat``, ``lon`` float32
at 2 decimals, null when the record has no point, and ``out_km``: km from the point to the nearest
centre of the label's cells, 0 inside them, null when unknown), ``level-ranges.parquet`` (``name``,
``cells`` int16 indexes into the grid, one row per label or look-alike name with cells on it) and
``level-range-cells.parquet`` (the grid in index order: the sorted ORM cells holding a pool record,
i.e. BC land; ``lat``, ``lon`` float32 boundary vertices at 3 decimals).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h3
import numpy as np
import pandas as pd

BOTH_OUT = "Range: outside both ranges"
ONLY_LOOK = "Range: fits the look-alike, not the label"
ONLY_LABEL = "Range: fits the label, not the look-alike"
NOTES, RANGES, GRID = "range-notes.parquet", "level-ranges.parquet", "level-range-cells.parquet"


def note(label_in, look_in):
    """label_in, look_in: True, False or None (unknown)."""
    if label_in is None or look_in is None:
        return None
    if label_in == look_in:
        return None if label_in else BOTH_OUT
    return ONLY_LABEL if label_in else ONLY_LOOK


def km_to_cells(lat, lon, centres):
    """Great-circle km from each point (degrees) to the nearest of `centres` (n x 2, radians)."""
    p = np.radians(np.column_stack([lat, lon]))[:, None, :]
    dlat, dlon = centres[None, :, 0] - p[..., 0], centres[None, :, 1] - p[..., 1]
    h = np.sin(dlat / 2) ** 2 + np.cos(p[..., 0]) * np.cos(centres[:, 0]) * np.sin(dlon / 2) ** 2
    return (2 * 6371.0088 * np.arcsin(np.sqrt(h))).min(axis=1)


def build(levels: pd.DataFrame, pool: pd.DataFrame, orm: pd.DataFrame):
    """(notes, ranges, grid) frames for the rows of `levels`; notes only on taxonomist rows."""
    lv = levels[["id", "taxon_id", "taxon_name", "looks_like_name", "level"]]
    cells = orm.groupby("taxon_id")["cells"].agg(lambda x: {c for cs in x for c in cs})
    ids = pool[["taxon_name", "taxon_id"]].drop_duplicates().groupby("taxon_name")["taxon_id"]
    by_name = {n: {int(t) for t in g} for n, g in ids}

    def look_cells(name):
        sets = [cells[t] for t in by_name.get(name, ()) if t in cells.index]
        return set().union(*sets) if sets else None

    lv = lv.merge(pool.drop_duplicates("id")[["id", "lat", "lon"]], on="id", how="left")
    cell = [
        h3.latlng_to_cell(a, b, 4) if pd.notna(a) and pd.notna(b) else None
        for a, b in zip(lv["lat"], lv["lon"], strict=True)
    ]
    tax = lv["level"] == "taxonomist"
    look = {n: look_cells(n) for n in lv.loc[tax, "looks_like_name"].unique()}
    out, okm = [], np.full(len(lv), np.nan)
    for k, (r, c) in enumerate(zip(lv.itertuples(), cell, strict=True)):
        lab = cells.get(r.taxon_id)
        lk = look.get(r.looks_like_name) if r.level == "taxonomist" else None
        out.append(None if c is None or lab is None or lk is None else note(c in lab, c in lk))
        if c is not None and lab is not None and c in lab:
            okm[k] = 0
    for t, g in lv[np.isnan(okm) & pd.Series(cell, dtype=object).notna().to_numpy()].groupby(
        "taxon_id"
    ):
        if t in cells.index:
            ctr = np.radians([h3.cell_to_latlng(c) for c in cells[t]])
            okm[g.index.to_numpy()] = km_to_cells(g["lat"], g["lon"], ctr)
    notes = pd.DataFrame(
        {
            "id": lv["id"].astype("int64"),
            "range_note": pd.Series(out, dtype=object),
            "lat": lv["lat"].round(2).astype("float32"),
            "lon": lv["lon"].round(2).astype("float32"),
            "out_km": pd.Series(np.round(okm), dtype="float64").astype("Int32"),
        }
    )
    # the grid is the BC land mask: ORM cells that hold at least one pool record
    pts = pool[["lat", "lon"]].dropna().round(2).drop_duplicates()
    land = {h3.latlng_to_cell(a, b, 4) for a, b in zip(pts["lat"], pts["lon"], strict=True)}
    grid_ids = sorted({c for cs in orm["cells"] for c in cs} & land)
    ix = {c: i for i, c in enumerate(grid_ids)}
    lab = zip(lv["taxon_name"], lv["taxon_id"], strict=True)
    sets = {n: cells[t] for n, t in lab if t in cells.index}  # a label is its own taxon
    for n, s_ in look.items():
        if s_ and n not in sets:
            sets[n] = s_
    sets = {n: [ix[c] for c in s_ if c in ix] for n, s_ in sets.items()}
    rows = [(n, np.array(sorted(s_), np.int16)) for n, s_ in sets.items() if s_]
    ranges = pd.DataFrame(rows, columns=["name", "cells"])
    bounds = [h3.cell_to_boundary(c) for c in grid_ids]
    grid = pd.DataFrame(
        {
            k: [np.round([v[j] for v in b], 3).astype("float32") for b in bounds]
            for j, k in enumerate(("lat", "lon"))
        }
    )
    return notes, ranges, grid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m what_to_id.level_ranges", description=__doc__)
    ap.add_argument("--levels", required=True, help="levels.parquet")
    ap.add_argument("--pool", required=True, help="pool parquet with id, lat, lon, taxon_name")
    ap.add_argument("--cells", required=True, help="ORM parquet with taxon_id, cells")
    ap.add_argument("--out-dir", required=True, type=Path)
    a = ap.parse_args(argv)
    pool = pd.read_parquet(a.pool, columns=["id", "lat", "lon", "taxon_id", "taxon_name"])
    notes, ranges, grid = build(pd.read_parquet(a.levels), pool, pd.read_parquet(a.cells))
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in ((NOTES, notes), (RANGES, ranges), (GRID, grid)):
        df.to_parquet(a.out_dir / name, index=False)
    print(notes["range_note"].value_counts(dropna=False).to_string())
    print(f"{len(ranges)} species ranges over {len(grid)} cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
