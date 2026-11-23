"""January identification blitz: three challenge scores per identifier, from the IDs they made.

Each challenge is coverage of a target space with saturating credit per unit: an identifier earns
`weight * min(n, cap) / cap` for each unit their IDs touch, so many IDs of one taxon or in one far
cell stop paying after `cap`, while breadth keeps paying.

- tree: units are every taxon on the lineage of each ID'd taxon, weight 1, so the score is a
  unit-branch Faith PD of what was identified, weighted by how often (Tree of Life challenge).
- climate: units are 25 km where-to-blitz cells, weighted by their `env` axis, the
  under-sampled-environment score (climate space challenge).
- checklist: units are the same cells weighted by `1 - discover`, cells closest to a species list.
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


def scores(ids: pd.DataFrame, taxa: Mapping[str, list], cells: pd.DataFrame) -> pd.DataFrame:
    """Challenge scores per `user` from IDs with `user`, `taxon_id`, `lat`, `lon`."""
    lin = lineages(taxa)
    tree = ids[["user"]].assign(unit=[lin(int(t)) for t in ids.taxon_id]).explode("unit").dropna()
    cell = ids[["user"]].assign(unit=cell_index(cells, ids.lat, ids.lon)).dropna()
    return pd.DataFrame(
        {
            "n_ids": ids.groupby("user").size(),
            "tree": unit_credit(tree),
            "climate": unit_credit(cell, cells["env"]),
            "checklist": unit_credit(cell, 1.0 - cells["discover"]),
        }
    ).fillna(0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Blitz challenge scores per identifier")
    ap.add_argument("ids", help="parquet with user, taxon_id, lat, lon (one row per ID)")
    ap.add_argument("taxonomy", help="taxonomy json with a `taxa` table")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ids = pd.read_parquet(a.ids).dropna(subset=["user", "taxon_id", "lat", "lon"])
    with open(a.taxonomy) as fh:
        taxa = json.load(fh)["taxa"]
    scores(ids, taxa, cells_mod.load_cells(cells_mod.FALLBACK_GROUP)).to_csv(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
