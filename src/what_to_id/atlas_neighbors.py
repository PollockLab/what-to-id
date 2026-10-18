"""Exact cosine nearest neighbours for the static atlas, one fixed-size record per observation.

`<name>.bin` holds records sorted by id: id u32, k neighbour ids u32, k cosines f16
(76 bytes for k=12). `<name>.dir.u32` holds the first id of every `block` records, so a browser
binary-searches the directory and range-fetches one block.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from what_to_id.atlas_index_io import (
    check_ids,
    check_vectors,
    load_array,
    read_manifest,
    unit_rows,
    warn_normalized,
    write_array,
    write_manifest,
)

log = logging.getLogger("what_to_id")

QUERY_BLOCK = 1024
COL_CHUNK = 65536
GPU_QUERY_BLOCK = 4096
GPU_COL_CHUNK = 131072


def record_dtype(k: int) -> np.dtype:
    return np.dtype([("id", "<u4"), ("nb", "<u4", (k,)), ("cos", "<f2", (k,))])


def _topk_numpy(q: np.ndarray, cols, q0: int, k: int) -> tuple:
    """Running top-k of ``q @ cols.T`` streamed over column chunks, excluding self."""
    best_v = np.full((len(q), 0), -np.inf, dtype=np.float32)
    best_i = np.zeros((len(q), 0), dtype=np.int64)
    for c0 in range(0, len(cols), COL_CHUNK):
        sims = q @ unit_rows(cols[c0 : c0 + COL_CHUNK])[0].T
        rows = np.arange(len(q))
        selfcol = rows + q0 - c0
        ok = (selfcol >= 0) & (selfcol < sims.shape[1])
        sims[rows[ok], selfcol[ok]] = -np.inf
        kk = min(k, sims.shape[1])
        top = np.argpartition(-sims, kk - 1, axis=1)[:, :kk]
        v = np.concatenate([best_v, np.take_along_axis(sims, top, 1)], axis=1)
        i = np.concatenate([best_i, top + c0], axis=1)
        top = np.argpartition(-v, min(k, v.shape[1]) - 1, axis=1)[:, :k]
        best_v, best_i = np.take_along_axis(v, top, 1), np.take_along_axis(i, top, 1)
    order = np.argsort(-best_v, axis=1, kind="stable")
    return np.take_along_axis(best_v, order, 1), np.take_along_axis(best_i, order, 1)


def _all_topk_numpy(E, k: int) -> tuple:
    n = len(E)
    vals = np.empty((n, k), dtype=np.float32)
    idx = np.empty((n, k), dtype=np.int64)
    fixed = 0
    for q0 in range(0, n, QUERY_BLOCK):
        q, nf = unit_rows(E[q0 : q0 + QUERY_BLOCK])
        fixed += nf
        vals[q0 : q0 + len(q)], idx[q0 : q0 + len(q)] = _topk_numpy(q, E, q0, k)
    return vals, idx, fixed


def _all_topk_torch(E, k: int, device: str) -> tuple:
    """Blockwise on a GPU: E lives on the device as float16, accumulation is float32."""
    import torch

    n = len(E)
    store = torch.empty((n, E.shape[1]), dtype=torch.float16, device=device)
    fixed = 0
    for lo in range(0, n, 32768):
        x, nf = unit_rows(E[lo : lo + 32768])
        fixed += nf
        store[lo : lo + len(x)] = torch.from_numpy(x).to(device, torch.float16)
    vals = np.empty((n, k), dtype=np.float32)
    idx = np.empty((n, k), dtype=np.int64)
    for q0 in range(0, n, GPU_QUERY_BLOCK):
        q = store[q0 : q0 + GPU_QUERY_BLOCK]
        best_v = best_i = None
        for c0 in range(0, n, GPU_COL_CHUNK):
            sims = (q @ store[c0 : c0 + GPU_COL_CHUNK].T).float()
            rows = torch.arange(len(q), device=device)
            selfcol = rows + q0 - c0
            ok = (selfcol >= 0) & (selfcol < sims.shape[1])
            sims[rows[ok], selfcol[ok]] = -torch.inf
            v, i = sims.topk(min(k, sims.shape[1]), dim=1)
            i = i + c0
            if best_v is not None:
                v, i = torch.cat([best_v, v], 1), torch.cat([best_i, i], 1)
                v, pos = v.topk(k, dim=1)
                i = i.gather(1, pos)
            best_v, best_i = v, i
        vals[q0 : q0 + len(q)] = best_v.cpu().numpy()
        idx[q0 : q0 + len(q)] = best_i.cpu().numpy()
    return vals, idx, fixed


def neighbors(
    E,
    ids,
    out_dir: str | Path,
    name: str = "neighbors",
    k: int = 12,
    block: int = 1024,
    device: str = "auto",
) -> dict:
    """Write exact cosine top-``k`` neighbours (self excluded) for every row and register them.

    ``device`` is "auto" (CUDA via torch when available, else numpy), "cuda" or "numpy". The index
    in ``out_dir`` must already have a manifest.
    """
    check_vectors(E)
    ids = check_ids(ids, len(E))
    if k < 1 or block < 1:
        raise ValueError("k and block must be positive")
    if len(E) <= k:
        raise ValueError(f"need more than k={k} rows for neighbours, got {len(E)}")
    manifest = read_manifest(out_dir)
    if E.shape[1] != manifest["dims"]:
        raise ValueError(f"dims mismatch: E has {E.shape[1]}, index has {manifest['dims']}")
    if device not in ("auto", "cuda", "numpy"):
        raise ValueError(f"unknown device {device!r}")
    use_cuda = device == "cuda"
    if device == "auto":
        try:
            import torch

            use_cuda = torch.cuda.is_available()
        except ImportError:
            use_cuda = False
    vals, idx, fixed = _all_topk_torch(E, k, "cuda") if use_cuda else _all_topk_numpy(E, k)
    warn_normalized(fixed, "neighbors")

    order = np.argsort(ids)
    rec = np.empty(len(ids), dtype=record_dtype(k))
    rec["id"] = ids[order]
    rec["nb"] = ids[idx[order]]
    rec["cos"] = vals[order].astype("<f2")
    base = Path(out_dir)
    write_array(base / f"{name}.bin", rec.view(np.uint8), "u1")
    write_array(base / f"{name}.dir.u32", rec["id"][::block], "<u4")

    entry = {"name": name, "count": int(len(ids)), "block": int(block), "k": int(k)}
    manifest["neighbors"] = [e for e in manifest.get("neighbors", []) if e["name"] != name]
    manifest["neighbors"].append(entry)
    write_manifest(out_dir, manifest)
    return entry


def lookup_neighbors(index_dir: str | Path, obs_id: int, name: str = "neighbors"):
    """Return ``(neighbor_ids int64, cosines float32)`` for ``obs_id``, or None if absent."""
    manifest = read_manifest(index_dir)
    entry = next((e for e in manifest.get("neighbors", []) if e["name"] == name), None)
    if entry is None:
        raise KeyError(f"no neighbour set {name!r} in manifest")
    base = Path(index_dir)
    dtype = record_dtype(entry.get("k", 12))
    n_blocks = -(-entry["count"] // entry["block"])
    directory = load_array(base / f"{name}.dir.u32", "<u4", (n_blocks,))
    b = int(np.searchsorted(directory, obs_id, side="right")) - 1
    if b < 0:
        return None
    lo = b * entry["block"]
    hi = min(lo + entry["block"], entry["count"])
    raw = np.fromfile(base / f"{name}.bin", dtype=dtype, count=hi - lo, offset=lo * dtype.itemsize)
    pos = int(np.searchsorted(raw["id"], obs_id))
    if pos >= len(raw) or raw["id"][pos] != obs_id:
        return None
    return raw["nb"][pos].astype(np.int64), raw["cos"][pos].astype(np.float32)
