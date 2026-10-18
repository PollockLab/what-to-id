"""Deterministic atlas-index fixture: a tiny IVF-PQ index plus reference queries for parity tests.

Run as `PYTHONPATH=src python tests/atlas_index_fixture.py OUT_DIR` (needs faiss) to write an index
(`base` plus one delta part, neighbours) and `reference.json` with queries and the expected
top-k from `atlas_index.search`; the JS reader tests compare against that file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from what_to_id import atlas_index

FIXTURE_DIMS = 1024
FIXTURE_ROWS = 2000
FIXTURE_DELTA = 200
FIXTURE_NLIST = 16
FIXTURE_M = 64
FIXTURE_K = 10
FIXTURE_NPROBES = (1, 4, 16)


def clustered_unit(n: int, d: int, n_clusters: int, seed: int, noise: float = 0.5) -> np.ndarray:
    """Float32 unit vectors drawn around ``n_clusters`` random unit centres."""
    rng = np.random.default_rng(seed)
    centres = rng.standard_normal((n_clusters, d))
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    x = centres[rng.integers(0, n_clusters, n)] + noise * rng.standard_normal((n, d)) / np.sqrt(d)
    return (x / np.linalg.norm(x, axis=1, keepdims=True)).astype(np.float32)


def write_fixture(out_dir: str | Path) -> dict:
    """Write the fixture index into ``out_dir`` and return (and save) the reference dict."""
    out = Path(out_dir)
    total = FIXTURE_ROWS + FIXTURE_DELTA
    E = clustered_unit(total, FIXTURE_DIMS, 24, seed=0)
    # Spread over the whole uint32 range so readers cannot get away with signed 32-bit ids.
    ids = np.random.default_rng(1).choice(2**32 - 2, total, replace=False) + 1
    atlas_index.build(
        E[:FIXTURE_ROWS],
        ids[:FIXTURE_ROWS],
        out,
        nlist=FIXTURE_NLIST,
        m=FIXTURE_M,
        train_size=FIXTURE_ROWS,
        model={"id": "fixture", "revision": "0", "sha256": "0" * 64},
    )
    atlas_index.append(out, "delta-20260101", E[FIXTURE_ROWS:], ids[FIXTURE_ROWS:])
    atlas_index.neighbors(E, ids, out, k=12, block=256, device="numpy")

    rng = np.random.default_rng(2)
    rows = rng.choice(total, 6, replace=False)
    jitter = E[rows[:2]] + 0.02 * rng.standard_normal((2, FIXTURE_DIMS)).astype(np.float32)
    jitter /= np.linalg.norm(jitter, axis=1, keepdims=True)
    queries = np.vstack([E[rows], jitter]).astype(np.float32)
    searches = []
    for nprobe in FIXTURE_NPROBES:
        found, scores = atlas_index.search(out, queries, FIXTURE_K, nprobe)
        searches.append({"nprobe": nprobe, "ids": found.tolist(), "scores": scores.tolist()})
    lookups = []
    for obs_id in [*ids[rows[:3]].tolist(), 0]:  # id 0 is absent (ids start at 1)
        got = atlas_index.lookup_neighbors(out, obs_id)
        lookups.append(
            {"id": obs_id, "neighbors": None if got is None else [got[0].tolist(), got[1].tolist()]}
        )
    reference = {
        "k": FIXTURE_K,
        "queries": queries.tolist(),
        "searches": searches,
        "lookups": lookups,
    }
    (out / "reference.json").write_text(json.dumps(reference))
    return reference


if __name__ == "__main__":
    write_fixture(sys.argv[1])
