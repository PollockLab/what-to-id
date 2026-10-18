"""File layout, validation and encoding helpers for the static IVF-PQ atlas index.

Layout v1 (little-endian, headerless so a browser can HTTP-Range any slice): `manifest.json`,
`centroids.f16` (nlist x dims), `pq.f32` (m x 256 x dims/m), and per part `<part>.offsets.u32`
(nlist+1 row offsets, rows grouped by list), `<part>.ids.u32`, `<part>.codes.u8` (rows x m).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np

log = logging.getLogger("what_to_id")

VERSION = 1
NBITS = 8
KSUB = 1 << NBITS
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


def load_core(index_dir: str | Path, manifest: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return float32 centroids (as the browser reconstructs them from f16) and codebooks."""
    d, nlist, m = manifest["dims"], manifest["nlist"], manifest["m"]
    base = Path(index_dir)
    centroids = load_array(base / "centroids.f16", "<f2", (nlist, d)).astype(np.float32)
    pq = load_array(base / "pq.f32", "<f4", (m, KSUB, d // m))
    return centroids, np.asarray(pq)


def open_part(index_dir: str | Path, name: str, nlist: int, m: int, count: int) -> tuple:
    base = Path(index_dir)
    offsets = load_array(base / f"{name}.offsets.u32", "<u4", (nlist + 1,))
    ids = load_array(base / f"{name}.ids.u32", "<u4", (count,))
    codes = load_array(base / f"{name}.codes.u8", "u1", (count, m))
    return offsets, ids, codes


def write_part(index_dir: str | Path, name: str, offsets, ids, codes) -> None:
    base = Path(index_dir)
    write_array(base / f"{name}.offsets.u32", offsets, "<u4")
    write_array(base / f"{name}.ids.u32", ids, "<u4")
    write_array(base / f"{name}.codes.u8", codes, "u1")


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


def assign_encode(x: np.ndarray, centroids: np.ndarray, pq: np.ndarray) -> tuple:
    """Assign unit rows to the max-dot centroid and PQ-encode their residuals."""
    lists = np.argmax(x @ centroids.T, axis=1).astype(np.int32)
    m, ksub, dsub = pq.shape
    resid = (x - centroids[lists]).reshape(len(x), m, dsub)
    cb_norm = np.einsum("mkd,mkd->mk", pq, pq)
    codes = np.empty((len(x), m), dtype=np.uint8)
    for j in range(m):
        dist = cb_norm[j] - 2.0 * (resid[:, j] @ pq[j].T)
        codes[:, j] = dist.argmin(axis=1)
    return lists, codes


def group_by_list(lists, ids, codes, nlist: int) -> tuple:
    """Stable-sort rows by list; return offsets (nlist+1), ids and codes in that order."""
    order = np.argsort(lists, kind="stable")
    counts = np.bincount(lists, minlength=nlist)
    offsets = np.zeros(nlist + 1, dtype=np.uint32)
    np.cumsum(counts, out=offsets[1:])
    return offsets, np.asarray(ids)[order], codes[order]


def encode_stream(E, centroids, pq, chunk: int = CHUNK) -> tuple:
    """Assign and encode all rows of ``E`` chunk by chunk; return lists, codes, rows fixed."""
    n = len(E)
    lists = np.empty(n, dtype=np.int32)
    codes = np.empty((n, pq.shape[0]), dtype=np.uint8)
    fixed = 0
    for lo in range(0, n, chunk):
        x, nf = unit_rows(E[lo : lo + chunk])
        fixed += nf
        lists[lo : lo + chunk], codes[lo : lo + chunk] = assign_encode(x, centroids, pq)
    return lists, codes, fixed
