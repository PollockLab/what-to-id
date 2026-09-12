"""Score backbone embeddings by leave-one-out species separability, per iconic group.

Usage: .venv/bin/python scripts/bakeoff_score.py --pool data/pool_sample_2026-09-11.parquet \
    --emb-dir data/pool_sample_2026-09-11 --backbones bioclip25,dinov3,bioclip25+dinov3@0.5 \
    --out out/bakeoff.json

Labels are the observer-proposed species names (rank == species) from the pool; rows at coarser
rank are unlabelled and ignored by the score. The score is labelfirst's 1-NN cosine agreement in
percent, so higher means same-species photos sit closer together in that backbone's space.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.arms import load_embeddings
from what_to_id.embed import emb_cache_path, separability_report


def species_labels(pool: pd.DataFrame, ids: np.ndarray) -> list[str | None]:
    sub = pool.set_index("id").reindex(ids)
    is_species = sub["rank"].astype("string") == "species"
    names = sub["taxon_name"]
    return [str(n) if ok and pd.notna(n) else None for ok, n in zip(is_species, names, strict=True)]


def _unit(E: np.ndarray) -> np.ndarray:
    return E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-12)


def load_spec(emb_dir: Path, group: str, spec: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Load one backbone or a weighted concat like ``bioclip25+dinov3@0.5``.

    Each block is unit-normed, scaled by its weight (default 1), and the blocks are joined on the
    ids they share. Returns None when any block's npz is missing.
    """
    blocks = []
    for part in spec.split("+"):
        name, _, w = part.partition("@")
        path = emb_cache_path(emb_dir, group, name)
        if not path.exists():
            return None
        ids, E, _ = load_embeddings(path)
        blocks.append((ids, _unit(E) * (float(w) if w else 1.0)))
    ids = blocks[0][0]
    for b_ids, _ in blocks[1:]:
        ids = np.intersect1d(ids, b_ids)
    parts = [E[pd.Index(b_ids).get_indexer(ids)] for b_ids, E in blocks]
    return ids, _unit(np.hstack(parts))


def score(pool: pd.DataFrame, emb_dir: Path, backbones: list[str]) -> pd.DataFrame:
    rows = []
    for group in sorted(pool["iconic_taxon"].dropna().astype(str).unique()):
        for bb in backbones:
            loaded = load_spec(emb_dir, group, bb)
            if loaded is None:
                rows.append({"group": group, "backbone": bb, "separability_pct": np.nan, "n": 0})
                continue
            ids, E = loaded
            rep = separability_report(E, species_labels(pool, ids))
            rows.append({"group": group, "backbone": bb, **rep, "rows": int(len(ids))})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--emb-dir", required=True, type=Path)
    ap.add_argument("--backbones", default="bioclip25,bioclip2,dinov2")
    ap.add_argument("--out", type=Path, default=None, help="optional JSON path for the table")
    a = ap.parse_args(argv)
    pool = pd.read_parquet(a.pool)
    backbones = [b.strip() for b in a.backbones.split(",") if b.strip()]
    df = score(pool, a.emb_dir, backbones)
    wide = df.pivot(index="group", columns="backbone", values="separability_pct").round(1)
    wide["n_labelled"] = df.groupby("group")["n"].max()
    print(wide.to_string())
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(df.to_dict(orient="records"), indent=1))
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
