"""Assemble the day's embedding bundle from a base release and the atlas raw deltas.

The base release holds float16 `base_{group}.npz` files (keys `ids`, `E`) and
`base_manifest.json`; the atlas job's `raw-delta-*.npz` files (same keys, no group) add the
records embedded since. For each group in the pool the vectors of its ids are taken from the base,
then from the deltas in name order (a later file wins over an earlier one and over the base),
cast to float32 and renormalised, and packed with the frozen reference by `artifacts.pack_bundle`.

Pool rows with no vector anywhere are uncovered. They are listed in `uncovered.json` beside the
bundle and left out of its pool, but they are not excluded from the study: they enter on a later
day, once the atlas has embedded them. If a group's uncovered share exceeds --max-uncovered-share
the atlas is behind and the build fails; re-preparing on the cluster is the fallback.

    python -m what_to_id.assemble_bundle --pool POOL.parquet --base DIR --deltas DIR \
      --reference-embeddings 'data/ref_sample_2026-09-11/emb_{group}_bioclip25.npz' --out BUNDLE
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.artifacts import pack_bundle
from what_to_id.embed import save_embeddings
from what_to_id.manifest import sha256_file

BACKBONE = "bioclip25"


def _load_vectors(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        ids, E = np.asarray(z["ids"], dtype=np.int64), np.asarray(z["E"])
    if ids.ndim != 1 or E.ndim != 2 or E.shape[0] != len(ids):
        raise ValueError(f"{path}: E shape {E.shape} does not match {len(ids)} ids")
    return ids, E


def _load_deltas(paths: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    """All delta rows as (ids, float16 E), one row per id, the latest file's row kept."""
    parts = [_load_vectors(p) for p in paths]
    if not parts:
        return np.empty(0, dtype=np.int64), np.empty((0, 0), dtype=np.float16)
    ids = np.concatenate([p[0] for p in parts])
    E = np.concatenate([p[1] for p in parts])
    _, first_in_reverse = np.unique(ids[::-1], return_index=True)
    keep = np.sort(len(ids) - 1 - first_in_reverse)
    return ids[keep], E[keep]


def _fill(out, have, pool_ids, ids, E, source) -> None:
    """Write the rows of E whose id is in the sorted pool_ids into out; mark them in have."""
    if not len(ids):
        return
    if E.shape[1] != out.shape[1]:
        raise ValueError(f"{source}: {E.shape[1]} dimensions, expected {out.shape[1]}")
    at = np.minimum(np.searchsorted(pool_ids, ids), len(pool_ids) - 1)
    hit = pool_ids[at] == ids
    out[at[hit]] = E[hit]
    have[at[hit]] = True


def _normalise(E: np.ndarray, group: str) -> None:
    for start in range(0, len(E), 8192):
        rows = E[start : start + 8192]
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        if not (np.isfinite(rows).all() and (norms > 0).all()):
            raise ValueError(f"{group}: vectors must be finite and nonzero")
        rows /= norms


def assemble(
    pool_path: Path,
    base: Path,
    deltas: Path,
    reference: str,
    out: Path,
    max_uncovered_share: float = 0.01,
) -> dict[str, int]:
    """Pack the bundle at `out`; return the uncovered count per group."""
    pool = pd.read_parquet(pool_path)
    if not pool["id"].is_unique:
        raise ValueError(f"{pool_path}: duplicate ids")
    manifest = base / "base_manifest.json"
    delta_files = sorted(deltas.glob("raw-delta-*.npz"), key=lambda p: p.name)
    delta_ids, delta_E = _load_deltas(delta_files)
    out.parent.mkdir(parents=True, exist_ok=True)
    uncovered: dict[str, list[int]] = {}
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=".assemble-") as tmp:
        candidates = Path(tmp) / "candidates"
        for group, rows in pool.dropna(subset=["iconic_taxon"]).groupby("iconic_taxon"):
            rows = rows.sort_values("id")
            pool_ids = rows["id"].to_numpy(dtype=np.int64)
            base_file = base / f"base_{group}.npz"
            base_ids, base_E = _load_vectors(base_file) if base_file.exists() else (None, None)
            dim = (base_E if base_E is not None else delta_E).shape[1]
            vectors = np.zeros((len(rows), dim), dtype=np.float32)
            have = np.zeros(len(rows), dtype=bool)
            if base_ids is not None:
                _fill(vectors, have, pool_ids, base_ids, base_E, base_file)
            del base_ids, base_E
            _fill(vectors, have, pool_ids, delta_ids, delta_E, "raw deltas")
            uncovered[group] = pool_ids[~have].tolist()
            if not have.any():
                continue
            kept = np.flatnonzero(have)
            for s in range(0, len(kept), 8192):  # compact in place: never a second float32 copy
                chunk = kept[s : s + 8192]
                vectors[s : s + len(chunk)] = vectors[chunk]
            vectors = vectors[: len(kept)]
            _normalise(vectors, group)
            rows = rows[have]
            save_embeddings(
                candidates / f"emb_{group}_{BACKBONE}.npz",
                ids=rows["id"].to_numpy(),
                E=vectors,
                lat=rows["lat"].to_numpy(dtype=float),
                lon=rows["lon"].to_numpy(dtype=float),
                backbone=BACKBONE,
                emb_device="assembled",
                failed_ids=[],
            )
            del vectors
        gone = {i for ids in uncovered.values() for i in ids}
        report = {
            "schema_version": 1,
            "ids": sorted(gone),
            "by_group": {g: len(ids) for g, ids in uncovered.items() if ids},
        }
        (out.parent / "uncovered.json").write_text(json.dumps(report) + "\n")
        sizes = pool.groupby("iconic_taxon").size()
        for group, ids in uncovered.items():
            if len(ids) / sizes[group] > max_uncovered_share:
                raise SystemExit(
                    f"assemble_bundle: {group} has {len(ids)} of {sizes[group]} pool rows without "
                    f"an embedding ({len(ids) / sizes[group]:.2%} > {max_uncovered_share:.2%}); "
                    "the atlas is behind, re-prepare on the cluster"
                )
        covered = Path(tmp) / "pool.parquet"
        pool[~pool["id"].isin(gone)].to_parquet(covered, index=False)
        preparation = Path(tmp) / "preparation.json"
        preparation.write_text(
            json.dumps(
                {
                    "source": "assemble_bundle",
                    "backbone": BACKBONE,
                    "base_manifest_sha256": sha256_file(manifest),
                    "deltas": {p.name: sha256_file(p) for p in delta_files},
                },
                indent=1,
                sort_keys=True,
            )
        )
        pack_bundle(
            covered,
            str(candidates / f"emb_{{group}}_{BACKBONE}.npz"),
            reference,
            out,
            preparation=preparation,
            move_embeddings=True,
        )
    return {g: len(ids) for g, ids in uncovered.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    for flag in ("pool", "base", "deltas", "reference-embeddings", "out"):
        ap.add_argument("--" + flag, required=True)
    ap.add_argument("--max-uncovered-share", type=float, default=0.01)
    a = ap.parse_args(argv)
    try:
        assemble(
            Path(a.pool),
            Path(a.base),
            Path(a.deltas),
            a.reference_embeddings,
            Path(a.out),
            a.max_uncovered_share,
        )
    except (OSError, ValueError, KeyError) as exc:
        ap.exit(1, f"assemble_bundle: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
