"""File layout, validation and encoding helpers for the static IVF-OPQ-PQ atlas index.

Layout v2 (little-endian, headerless so a browser can HTTP-Range any slice): `manifest.json`,
`centroids.f16` (nlist x dims), `opq.f16` (dims x dims rotation A, applied to residuals as
y = A r), `pq.f32` (m x 256 x dims/m, codebooks of the rotated residual), `refine.f32` (2 x dims:
lo, step of the refine grid, see `atlas_refine`), and per part `<part>.offsets.u32` (nlist+1 row
offsets, rows grouped by list), `<part>.ids.u32`, `<part>.codes.u8` (rows x m) and
`<part>.refine.u8` (rows x dims*bits/8, same row order as the codes).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import NamedTuple

import numpy as np

from what_to_id import atlas_refine

log = logging.getLogger("what_to_id")

VERSION = 2
NBITS = 8
KSUB = 1 << NBITS
NPROBE = 96
SHORTLIST = 500
MAX_ID = 2**32 - 1
CHUNK = 32768
UNIT_TOL = 1e-3


def read_manifest(index_dir: str | Path) -> dict:
    path = Path(index_dir) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"no manifest.json in {index_dir}; build the index first")
    manifest = json.loads(path.read_text())
    if manifest.get("version") != VERSION:
        raise ValueError(f"unsupported index version {manifest.get('version')!r}")
    return manifest


def write_array(path: Path, array: np.ndarray, dtype: str) -> None:
    """Write ``array`` as plain little-endian ``dtype`` via a temp file and rename."""
    tmp = path.with_name(path.name + ".tmp")
    np.ascontiguousarray(array, dtype=np.dtype(dtype)).tofile(tmp)
    os.replace(tmp, path)


def write_manifest(index_dir: str | Path, manifest: dict) -> None:
    path = Path(index_dir) / "manifest.json"
    tmp = path.with_name("manifest.json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(tmp, path)


def load_array(path: Path, dtype: str, shape: tuple) -> np.ndarray:
    """Memory-map a headerless array (zero-length files cannot be mapped)."""
    if int(np.prod(shape)) == 0:
        return np.empty(shape, dtype=dtype)
    return np.memmap(path, dtype=dtype, mode="r", shape=shape)


class Core(NamedTuple):
    """Everything shared by all parts, as the browser reconstructs it (f16 widened to f32)."""

    centroids: np.ndarray  # (nlist, dims)
    rot: np.ndarray  # (dims, dims)
    pq: np.ndarray  # (m, 256, dims/m)
    refine: np.ndarray  # (2, dims): lo, step
    bits: int


def load_core(index_dir: str | Path, manifest: dict) -> Core:
    d, nlist, m = manifest["dims"], manifest["nlist"], manifest["m"]
    base = Path(index_dir)
    centroids = load_array(base / "centroids.f16", "<f2", (nlist, d)).astype(np.float32)
    rot = load_array(base / "opq.f16", "<f2", (d, d)).astype(np.float32)
    pq = load_array(base / "pq.f32", "<f4", (m, KSUB, d // m))
    spec = manifest["refine"]
    sq = load_array(base / spec["params"], "<f4", (2, d))
    return Core(centroids, rot, np.asarray(pq), np.asarray(sq), spec["bits"])


def open_part(index_dir: str | Path, name: str, manifest: dict, count: int) -> tuple:
    """Memory-mapped (offsets, ids, codes, refine) of a part."""
    base = Path(index_dir)
    rb = atlas_refine.row_bytes(manifest["dims"], manifest["refine"]["bits"])
    offsets = load_array(base / f"{name}.offsets.u32", "<u4", (manifest["nlist"] + 1,))
    ids = load_array(base / f"{name}.ids.u32", "<u4", (count,))
    codes = load_array(base / f"{name}.codes.u8", "u1", (count, manifest["m"]))
    refine = load_array(base / f"{name}.refine.u8", "u1", (count, rb))
    return offsets, ids, codes, refine


def write_part(index_dir: str | Path, name: str, offsets, ids, codes, refine, order) -> None:
    """Write a part; ``refine[order]`` gives the refine rows in list order, gathered in blocks."""
    base = Path(index_dir)
    write_array(base / f"{name}.offsets.u32", offsets, "<u4")
    write_array(base / f"{name}.ids.u32", ids, "<u4")
    write_array(base / f"{name}.codes.u8", codes, "u1")
    path = base / f"{name}.refine.u8"
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        for lo in range(0, len(order), CHUNK):
            f.write(np.ascontiguousarray(refine[order[lo : lo + CHUNK]]).tobytes())
    os.replace(tmp, path)


def check_ids(ids, n: int) -> np.ndarray:
    """Validate observation ids as unique non-negative integers fitting uint32."""
    ids = np.asarray(ids)
    if ids.ndim != 1 or len(ids) != n:
        raise ValueError(f"ids must be 1-D with {n} entries, got shape {ids.shape}")
    if n == 0:
        raise ValueError("empty input")
    if ids.dtype.kind not in "iu":
        raise ValueError(f"ids must be integers, got {ids.dtype}")
    if ids.min() < 0 or ids.max() > MAX_ID:
        raise ValueError(f"ids must fit uint32 (0..{MAX_ID}), got range {ids.min()}..{ids.max()}")
    if len(np.unique(ids)) != n:
        raise ValueError("duplicate ids")
    return ids.astype(np.int64)


def check_vectors(E, what: str = "E") -> None:
    if E.ndim != 2:
        raise ValueError(f"{what} must be 2-D, got shape {E.shape}")
    if E.shape[0] == 0 or E.shape[1] == 0:
        raise ValueError(f"empty input: {what} has shape {E.shape}")
    if E.dtype.kind != "f":
        raise ValueError(f"{what} must be floating point, got {E.dtype}")


def unit_rows(x: np.ndarray) -> tuple[np.ndarray, int]:
    """Return float32 rows normalized to unit length and how many rows needed it."""
    x = np.asarray(x, dtype=np.float32)
    norms = np.linalg.norm(x, axis=1)
    if not np.all(norms > 0) or not np.all(np.isfinite(norms)):
        raise ValueError("vectors contain zero-length or non-finite rows")
    off = np.abs(norms - 1.0) > UNIT_TOL
    if off.any():
        x = x / norms[:, None]
    return x, int(off.sum())


def warn_normalized(n_fixed: int, what: str) -> None:
    if n_fixed:
        log.warning("%s: %d vectors were not unit-norm and were normalized", what, n_fixed)


def assign_encode(x: np.ndarray, core: Core) -> tuple:
    """Assign unit rows to the max-dot centroid; PQ-encode the rotated residual and its error.

    Returns lists, PQ codes and the packed refine codes of the PQ reconstruction error.
    """
    pq = core.pq
    m, _, dsub = pq.shape
    lists = np.argmax(x @ core.centroids.T, axis=1).astype(np.int32)
    resid = (x - core.centroids[lists]) @ core.rot.T
    cb_norm = np.einsum("mkd,mkd->mk", pq, pq)
    codes = np.empty((len(x), m), dtype=np.uint8)
    for j in range(m):
        dist = cb_norm[j] - 2.0 * (resid[:, j * dsub : (j + 1) * dsub] @ pq[j].T)
        codes[:, j] = dist.argmin(axis=1)
    recon = pq[np.arange(m)[None, :], codes].reshape(len(x), m * dsub)
    return lists, codes, atlas_refine.encode(resid - recon, core.refine, core.bits)


def group_by_list(lists, ids, codes, nlist: int) -> tuple:
    """Stable-sort rows by list; return offsets (nlist+1), ids, codes and the row order."""
    order = np.argsort(lists, kind="stable")
    counts = np.bincount(lists, minlength=nlist)
    offsets = np.zeros(nlist + 1, dtype=np.uint32)
    np.cumsum(counts, out=offsets[1:])
    return offsets, np.asarray(ids)[order], codes[order], order


def encode_stream(E, core: Core, chunk: int = CHUNK) -> tuple:
    """Assign and encode all rows of ``E`` in chunks; return lists, codes, refine, rows fixed."""
    n = len(E)
    lists = np.empty(n, dtype=np.int32)
    codes = np.empty((n, core.pq.shape[0]), dtype=np.uint8)
    refine = np.empty((n, atlas_refine.row_bytes(E.shape[1], core.bits)), dtype=np.uint8)
    fixed = 0
    for lo in range(0, n, chunk):
        x, nf = unit_rows(E[lo : lo + chunk])
        fixed += nf
        lists[lo : lo + chunk], codes[lo : lo + chunk], refine[lo : lo + chunk] = assign_encode(
            x, core
        )
    return lists, codes, refine, fixed
