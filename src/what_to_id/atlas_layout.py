"""2D layout of the atlas pool: gzip column-planar parts next to the index, listed under the
manifest's ``layout`` key (the daily update places new observations, compaction folds the deltas).

    python -m what_to_id.atlas_layout base --xy xy.f32.npy --ids ids.npy --out DIR \\
        --method STR --fidelity fidelity.json

Part ``<name>.bin`` is gzip of ``8*n`` bytes, records sorted by id: the id steps (first id, then
differences) as uint32, then x and y quantized to uint16 over the manifest ``bbox``, each column
byte-planar (all low bytes, then all high bytes, as the map shards in `page_map`).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

from what_to_id.atlas_index_io import MAX_ID, read_manifest, write_array, write_manifest

VERSION = 1
Q = 65535


def quantize(v, lo: float, hi: float) -> np.ndarray:
    """uint16 grid over ``lo..hi``; values outside are clamped."""
    q = np.rint((np.asarray(v, dtype=np.float64) - lo) / ((hi - lo) or 1.0) * Q)
    return np.clip(q, 0, Q).astype("<u2")


def dequantize(q, lo: float, hi: float) -> np.ndarray:
    return (lo + np.asarray(q, dtype=np.float64) / Q * ((hi - lo) or 1.0)).astype(np.float32)


def _planes(v: np.ndarray) -> bytes:
    return v.view("u1").reshape(-1, v.itemsize).T.tobytes()


def _unplanes(buf: bytes, off: int, n: int, dt: str) -> np.ndarray:
    w = np.dtype(dt).itemsize
    return np.frombuffer(buf, "u1", w * n, off).reshape(w, n).T.copy().view(dt).ravel()


def write_part(path, ids, xy, bbox) -> int:
    """Write ``ids`` (any order, unique) with their ``xy`` (n, 2) as one part; return the count."""
    ids, xy = np.asarray(ids, dtype=np.int64), np.asarray(xy)
    if xy.shape != (len(ids), 2) or ids.ndim != 1:
        raise ValueError(f"xy must have shape ({len(ids)}, 2), got {xy.shape}")
    if len(ids) and (ids.min() < 0 or ids.max() > MAX_ID):
        raise ValueError(f"ids must fit uint32 (0..{MAX_ID})")
    order = np.argsort(ids, kind="stable")
    ids, xy = ids[order], xy[order]
    if (np.diff(ids) == 0).any():
        raise ValueError("duplicate ids")
    x0, y0, x1, y1 = bbox
    body = (
        _planes(np.diff(ids, prepend=0).astype("<u4"))
        + _planes(quantize(xy[:, 0], x0, x1))
        + _planes(quantize(xy[:, 1], y0, y1))
    )
    write_array(Path(path), np.frombuffer(gzip.compress(body, 6, mtime=0), "u1"), "u1")
    return len(ids)


def read_part(path, n: int, bbox) -> tuple[np.ndarray, np.ndarray]:
    """``(ids int64 (n,), xy float32 (n, 2))`` of a part."""
    body = gzip.decompress(Path(path).read_bytes())
    if len(body) != 8 * n:
        raise ValueError(f"{path} holds {len(body)} bytes, expected {8 * n}")
    x0, y0, x1, y1 = bbox
    ids = np.cumsum(_unplanes(body, 0, n, "<u4"), dtype=np.int64)
    x = dequantize(_unplanes(body, 4 * n, n, "<u2"), x0, x1)
    y = dequantize(_unplanes(body, 6 * n, n, "<u2"), y0, y1)
    return ids, np.stack([x, y], axis=1)


def place(new_ids, nb_ids, nb_cos, known_ids, known_xy) -> tuple[np.ndarray, np.ndarray]:
    """Cosine-weighted mean of the neighbours that have coordinates: ``(placed_ids, xy)``.

    Weights are max(cos, 0); if all are 0 the plain mean of the known neighbours is used. Rows
    without a known neighbour are not placed.
    """
    new_ids, nb_ids = np.asarray(new_ids, dtype=np.int64), np.asarray(nb_ids, dtype=np.int64)
    known_ids, known_xy = np.asarray(known_ids, dtype=np.int64), np.asarray(known_xy, "f8")
    if not len(new_ids) or not len(known_ids):
        return new_ids[:0], np.empty((0, 2), dtype=np.float32)
    order = np.argsort(known_ids)
    sorted_ids = known_ids[order]
    pos = np.minimum(np.searchsorted(sorted_ids, nb_ids), len(sorted_ids) - 1)
    have = sorted_ids[pos] == nb_ids
    xy = known_xy[order[pos]]  # (n, k, 2)
    w = np.where(have, np.maximum(np.asarray(nb_cos, dtype=np.float64), 0.0), 0.0)
    flat = have.astype(np.float64)
    w = np.where(w.sum(axis=1, keepdims=True) > 0, w, flat)
    total = w.sum(axis=1)
    ok = total > 0
    out = (xy * w[..., None]).sum(axis=1)[ok] / total[ok, None]
    return new_ids[ok], out.astype(np.float32)


def part_file(index_dir, name: str) -> Path:
    return Path(index_dir) / f"{name}.bin"


def read_all(index_dir, layout: dict) -> tuple[np.ndarray, np.ndarray]:
    """All parts concatenated; for an id in several parts the latest part wins."""
    got = [
        read_part(part_file(index_dir, p["name"]), p["count"], layout["bbox"])
        for p in layout["parts"]
    ]
    if not got:
        return np.empty(0, dtype=np.int64), np.empty((0, 2), dtype=np.float32)
    ids, xy = np.concatenate([g[0] for g in got]), np.concatenate([g[1] for g in got])
    last = len(ids) - 1 - np.unique(ids[::-1], return_index=True)[1]
    return ids[np.sort(last)], xy[np.sort(last)]


def add_part(index_dir, name: str, ids, xy) -> int:
    """Write part ``name`` and append it to the manifest's layout parts (replacing a same name)."""
    manifest = read_manifest(index_dir)
    layout = manifest["layout"]
    n = write_part(part_file(index_dir, name), ids, xy, layout["bbox"])
    layout["parts"] = [p for p in layout["parts"] if p["name"] != name] + [
        {"name": name, "count": n}
    ]
    write_manifest(index_dir, manifest)
    return n


def compact(index_dir, keep_ids, name: str) -> int:
    """Fold every layout part into ``name``, keeping only ``keep_ids``; remove the old files."""
    manifest = read_manifest(index_dir)
    layout = manifest["layout"]
    ids, xy = read_all(index_dir, layout)
    keep = np.isin(ids, np.asarray(keep_ids))
    old = [p["name"] for p in layout["parts"] if p["name"] != name]
    n = write_part(part_file(index_dir, name), ids[keep], xy[keep], layout["bbox"])
    layout["parts"] = [{"name": name, "count": n}]
    write_manifest(index_dir, manifest)
    for o in old:
        part_file(index_dir, o).unlink(missing_ok=True)
    return n


def write_base(index_dir, ids, xy, method: str, fidelity: dict | None = None) -> dict:
    """Write ``layout-base`` and set the manifest's ``layout`` key; every other key is kept."""
    ids, xy = np.asarray(ids), np.asarray(xy, dtype=np.float32)
    if not len(ids):
        raise ValueError("empty layout")
    if not np.isfinite(xy).all():
        raise ValueError("xy contains non-finite values")
    manifest = read_manifest(index_dir)
    bbox = [float(v) for v in (*xy.min(axis=0), *xy.max(axis=0))]
    n = write_part(part_file(index_dir, "layout-base"), ids, xy, bbox)
    manifest["layout"] = {
        "version": VERSION,
        "method": method,
        "bbox": bbox,
        "fidelity": fidelity or {},
        "parts": [{"name": "layout-base", "count": n}],
    }
    write_manifest(index_dir, manifest)
    return manifest["layout"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.atlas_layout", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("base")
    sp.add_argument("--xy", required=True, help=".npy (n, 2) float32")
    sp.add_argument("--ids", required=True, help=".npy (n,) observation ids")
    sp.add_argument("--out", required=True, help="index directory with manifest.json")
    sp.add_argument("--method", required=True)
    sp.add_argument("--fidelity", help="JSON file stored under layout.fidelity")
    a = p.parse_args(argv)
    try:
        fid = json.loads(Path(a.fidelity).read_text()) if a.fidelity else None
        layout = write_base(a.out, np.load(a.ids), np.load(a.xy), a.method, fid)
    except (ValueError, FileNotFoundError) as exc:
        print(f"atlas_layout {a.cmd}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"bbox": layout["bbox"], "parts": layout["parts"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
