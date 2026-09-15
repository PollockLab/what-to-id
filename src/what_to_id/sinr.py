"""Range-model score for a pool (--sinr-scores), with numpy only.

SINR (Cole et al., ICML 2023, MIT licence) predicts where a species is present from location
alone. A record's `sinr_rel` is the model's presence at the record over the species' highest
presence on a 0.5 degree global grid, so values near 0 mean "far outside where this species
lives". Only species (or lower, climbed to the species) in the model's class list get a score.

The model is read from an npz export of the 2023 checkpoint
(`model_an_full_input_enc_sin_cos_hard_cap_num_per_class_1000.pt`): its `state_dict` with dots
written as `__`, plus `class_to_taxa` and `depth`. The export needs torch once; scoring does not.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from what_to_id.surprise import SPECIES, _lineage_fns

GRID_STEP = 0.5
CHUNK = 50000
SPECIES_CHUNK = 200


def load(path: str) -> dict[str, np.ndarray]:
    """The npz arrays, checked for the residual net's keys."""
    z = dict(np.load(path))
    need = {"class_emb__weight", "class_to_taxa", "depth", "feats__0__weight", "feats__0__bias"}
    need |= {
        f"feats__{i}__{w}__{p}"
        for i in range(2, 2 + int(z.get("depth", 0)))
        for w in ("w1", "w2")
        for p in ("weight", "bias")
    }
    missing = need - set(z)
    if missing:
        raise ValueError(f"{path}: not a SINR residual-net export, missing {sorted(missing)[:3]}")
    return z


def features(z: dict[str, np.ndarray], lonlat: np.ndarray) -> np.ndarray:
    """Location embedding: sin/cos of lon/180 and lat/90, one layer, then residual layers."""
    x = np.asarray(lonlat, dtype=np.float32) / np.array([180.0, 90.0], dtype=np.float32)
    x = np.concatenate([np.sin(np.pi * x), np.cos(np.pi * x)], axis=1)
    h = np.maximum(x @ z["feats__0__weight"].T + z["feats__0__bias"], 0)
    for i in range(2, 2 + int(z["depth"])):
        y = np.maximum(h @ z[f"feats__{i}__w1__weight"].T + z[f"feats__{i}__w1__bias"], 0)
        h = h + np.maximum(y @ z[f"feats__{i}__w2__weight"].T + z[f"feats__{i}__w2__bias"], 0)
    return h


def _embed(z: dict[str, np.ndarray], lonlat: np.ndarray) -> np.ndarray:
    parts = [features(z, lonlat[s : s + CHUNK]) for s in range(0, len(lonlat), CHUNK)]
    return np.concatenate(parts) if parts else np.empty((0, z["class_emb__weight"].shape[1]))


def _sigmoid(v: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-v))


def sinr_scores(pool: pd.DataFrame, taxa: pd.DataFrame, z: dict[str, np.ndarray]) -> pd.DataFrame:
    """id, sinr_rel for pool rows whose species is in the model; other rows are left out."""
    _, _, at = _lineage_fns(taxa)
    cls_of = {int(t): i for i, t in enumerate(z["class_to_taxa"])}
    sp = pool["taxon_id"].map(lambda t: at(int(t), SPECIES) if pd.notna(t) else None)
    cls = sp.map(lambda s: cls_of.get(int(s)) if s is not None and pd.notna(s) else None)
    rows = pool[cls.notna() & pool["lat"].notna() & pool["lon"].notna()]
    c = cls[rows.index].astype("int64").to_numpy()
    w = z["class_emb__weight"]
    here = _sigmoid(np.einsum("ij,ij->i", _embed(z, rows[["lon", "lat"]].to_numpy()), w[c]))
    lon, lat = np.meshgrid(
        np.arange(-180.0, 180.0, GRID_STEP), np.arange(-90.0, 90.0 + GRID_STEP / 2, GRID_STEP)
    )
    grid = _embed(z, np.column_stack([lon.ravel(), lat.ravel()]))
    species = np.unique(c)
    peak = [
        (grid @ w[species[s : s + SPECIES_CHUNK]].T).max(0)
        for s in range(0, len(species), SPECIES_CHUNK)
    ]
    top = pd.Series(_sigmoid(np.concatenate(peak)) if peak else [], index=species, dtype="float64")
    return pd.DataFrame({"id": rows["id"].to_numpy(), "sinr_rel": here / top[c].to_numpy()})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Range-model scores for a pool (--sinr-scores)")
    ap.add_argument("pool", help="pool parquet with id, lat, lon, taxon_id")
    ap.add_argument("--weights", required=True, help="npz export of the SINR 2023 checkpoint")
    ap.add_argument("--taxa", required=True, help="iNat Open Data taxa.csv.gz")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    pool = pd.read_parquet(a.pool, columns=["id", "lat", "lon", "taxon_id"])
    taxa = pd.read_csv(a.taxa, sep="\t", usecols=["taxon_id", "ancestry", "rank_level"])
    s = sinr_scores(pool, taxa, load(a.weights))
    s.to_parquet(a.out, index=False)
    print(f"{len(pool)} records, {len(s)} scored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
