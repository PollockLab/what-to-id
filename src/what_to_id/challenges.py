"""January identification blitz: three challenge scores per identifier, from the IDs they made.

Each challenge is coverage of a target space with saturating credit per unit: an identifier earns
`weight * min(n, cap) / cap` for each unit their IDs touch, so many IDs of one taxon or in one far
cell stop paying after `cap`, while breadth keeps paying.

- tree: units are every taxon on the lineage of each ID'd taxon, weight 1, so the score is a
  unit-branch Faith PD of what was identified, weighted by how often (Tree of Life challenge).
- climate: units are the top fifth of 25 km where-to-blitz cells by their `env` axis, the
  under-sampled-environment score (climate space challenge).
- checklist: the top fifth of cells by `1 - discover`, cells closest to a species list.
- id_gap: the top fifth of cells by needs-ID over research-grade records there, as a
  percentile, so any constant sampling fraction of either input cancels.
- unique: taxon-by-cell units only this identifier covers, what the pool would lose without them;
  ranks people apart from raw count (Spearman 0.62 on the BC sample), so it picks whom to invite.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from what_to_id import cells as cells_mod

CAP = 5
# Cell challenges count only their top fifth of cells: with graded weights every cell score ranks
# people by how many cells they touched (Spearman 0.81 to 0.92 on the BC sample), with a top fifth
# they rank them apart (0.17 to 0.45).
TOP = 0.8


def unit_credit(ids: pd.DataFrame, weight: Mapping | None = None, cap: int = CAP) -> pd.Series:
    """Per `user`, the sum over `unit` of weight * min(n, cap) / cap. Units missing from `weight`
    score 0; no `weight` means every unit weighs 1."""
    n = ids.groupby(["user", "unit"]).size().clip(upper=cap) / cap
    w = 1.0 if weight is None else n.index.get_level_values("unit").map(weight).fillna(0.0)
    return (n * np.asarray(w, dtype=float)).groupby(level="user").sum()


def lineages(taxa: Mapping[str, list]) -> callable:
    """Lineage of a taxon id (itself included) from the taxonomy json's `taxa` table of
    id -> [parent, name, common, rank]."""
    memo: dict[int, tuple[int, ...]] = {}

    def lin(t: int) -> tuple[int, ...]:
        chain = []
        while t not in memo and str(t) in taxa:
            chain.append(t)
            t = taxa[str(t)][0]
        out = memo.get(t, ())
        for x in reversed(chain):
            out = memo[x] = (*out, x)
        return out

    return lin


def cell_index(cells: pd.DataFrame, lat, lon, max_km: float = 20.0) -> np.ndarray:
    """Row of the nearest cell centre per point, NaN past `max_km` (outside the grid)."""
    tree = cKDTree(cells_mod._xyz(cells["lat"].to_numpy(), cells["lon"].to_numpy()))
    chord, idx = tree.query(cells_mod._xyz(np.asarray(lat, float), np.asarray(lon, float)), k=1)
    return np.where(cells_mod._chord_to_km(chord) <= max_km, idx, np.nan)


def id_gap(
    cells: pd.DataFrame, needs_id: pd.DataFrame, research: pd.DataFrame, min_n: int = 20
) -> pd.Series:
    """Per cell row with at least `min_n` records, the percentile of (needs-ID + 0.5) over
    (research grade + 0.5), from two record tables with `lat`, `lon`."""
    n = pd.DataFrame(
        {
            k: pd.Series(cell_index(cells, d.lat, d.lon)).dropna().astype(int).value_counts()
            for k, d in (("nid", needs_id), ("rg", research))
        }
    ).fillna(0.0)
    n = n[n.nid + n.rg >= min_n]
    return ((n.nid + 0.5) / (n.rg + 0.5)).rank(pct=True)


def top_cells(w: pd.Series, q: float = TOP) -> pd.Series:
    """1 for cells at or above the `q` quantile of `w`, else 0."""
    return (w >= w.quantile(q)).astype(float)


def scores(
    ids: pd.DataFrame,
    taxa: Mapping[str, list],
    cells: pd.DataFrame,
    gap: Mapping | None = None,
) -> pd.DataFrame:
    """Challenge scores per `user` from IDs with `user`, `taxon_id`, `lat`, `lon`; `id_gap` only
    when `gap` (from `id_gap`) is given."""
    lin = lineages(taxa)
    tree = ids[["user"]].assign(unit=[lin(int(t)) for t in ids.taxon_id]).explode("unit").dropna()
    cell = (
        ids[["user", "taxon_id"]]
        .assign(unit=cell_index(cells, ids.lat, ids.lon))
        .dropna()
        .astype({"unit": int})
    )
    out = pd.DataFrame(
        {
            "n_ids": ids.groupby("user").size(),
            "tree": unit_credit(tree),
            "climate": unit_credit(cell, top_cells(cells["env"])),
            "checklist": unit_credit(cell, top_cells(1.0 - cells["discover"])),
        }
    )
    units = cell.drop_duplicates()
    solo = units.groupby(["taxon_id", "unit"]).user.transform("size") == 1
    out["unique"] = units[solo].groupby("user").size()
    if gap is not None:
        out["id_gap"] = unit_credit(cell, top_cells(pd.Series(gap)))
    return out.fillna(0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Blitz challenge scores per identifier")
    ap.add_argument("ids", help="parquet with user, taxon_id, lat, lon (one row per ID)")
    ap.add_argument("taxonomy", help="taxonomy json with a `taxa` table")
    ap.add_argument("--gap", nargs=2, metavar=("NEEDS_ID", "RESEARCH"), help="record parquets")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ids = pd.read_parquet(a.ids).dropna(subset=["user", "taxon_id", "lat", "lon"])
    with open(a.taxonomy) as fh:
        taxa = json.load(fh)["taxa"]
    cells = cells_mod.load_cells(cells_mod.FALLBACK_GROUP)
    gap = None
    if a.gap:
        nid, rg = (pd.read_parquet(f).dropna(subset=["lat", "lon"]) for f in a.gap)
        gap = id_gap(cells, nid, rg)
    scores(ids, taxa, cells, gap).to_csv(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
