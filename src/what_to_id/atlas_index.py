"""Static IVF-PQ vector index for the browser atlas: build, search, append, compact.

The index is plain little-endian binary (see `atlas_index_io`) that a browser reads with HTTP
Range. Scoring for a unit query q is <q, c_l> + sum_j LUT[j][code_j] with
LUT[j][k] = <q_j, pq[j][k]>, centroids taken from float16 exactly as the browser reconstructs
them. `build` needs faiss (optional `index` extra) only for training; assignment and encoding
are numpy so `append` runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from what_to_id.atlas_index_io import (
    CHUNK,
    KSUB,
    NBITS,
    VERSION,
    check_ids,
    check_vectors,
    encode_stream,
    group_by_list,
    load_core,
    open_part,
    read_manifest,
    unit_rows,
    warn_normalized,
    write_array,
    write_manifest,
    write_part,
)
from what_to_id.atlas_neighbors import lookup_neighbors, neighbors

__all__ = [
    "append",
    "build",
    "compact",
    "lookup_neighbors",
    "neighbors",
    "recall_at_k",
    "search",
]

log = logging.getLogger("what_to_id")

PART_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _train(sample: np.ndarray, nlist: int, m: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Train coarse centroids and residual PQ codebooks with faiss; return float32 arrays."""
    try:
        import faiss
    except ImportError as exc:
        raise ImportError(
            "build needs faiss; install the optional extra: pip install 'what-to-id[index]'"
        ) from exc
    d = sample.shape[1]
    quantizer = faiss.IndexFlatIP(d)
    index = faiss.IndexIVFPQ(quantizer, d, nlist, m, NBITS, faiss.METRIC_INNER_PRODUCT)
    index.cp.seed = seed
    index.pq.cp.seed = seed
    index.train(np.ascontiguousarray(sample))
    centroids = quantizer.reconstruct_n(0, nlist)
    pq = faiss.vector_to_array(index.pq.centroids).reshape(m, KSUB, d // m)
    return centroids, pq.astype(np.float32)


def build(
    E,
    ids,
    out_dir: str | Path,
    *,
    nlist: int = 4096,
    m: int = 64,
    train_size: int = 262144,
    seed: int = 0,
    model: dict | None = None,
) -> dict:
    """Train IVF-PQ on a sample of ``E`` and write the index with a single part ``base``.

    ``E`` is an (n, dims) float array, typically a read-only ``np.load(mmap_mode="r")``; it is
    streamed in chunks and never copied whole. Returns the manifest.
    """
    check_vectors(E)
    n, d = E.shape
    ids = check_ids(ids, n)
    if d % m:
        raise ValueError(f"dims {d} not divisible by m={m}")
    if n < KSUB:
        raise ValueError(f"need at least {KSUB} rows to train 8-bit PQ, got {n}")
    train_n = min(train_size, n)
    if nlist > train_n:
        log.warning("nlist %d exceeds %d rows available for training; clamped", nlist, train_n)
        nlist = train_n
    rng = np.random.default_rng(seed)
    sample, fixed = unit_rows(E[np.sort(rng.choice(n, size=train_n, replace=False))])
    warn_normalized(fixed, "build training sample")
    centroids, pq = _train(sample, nlist, m, seed)
    del sample

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c16 = centroids.astype("<f2")
    lists, codes, fixed = encode_stream(E, c16.astype(np.float32), pq)
    warn_normalized(fixed, "build")
    offsets, ids_sorted, codes_sorted = group_by_list(lists, ids, codes, nlist)
    write_array(out / "centroids.f16", c16, "<f2")
    write_array(out / "pq.f32", pq, "<f4")
    write_part(out, "base", offsets, ids_sorted, codes_sorted)
    manifest = {
        "version": VERSION,
        "dims": d,
        "nlist": nlist,
        "m": m,
        "nbits": NBITS,
        "metric": "ip",
        "by_residual": True,
        "count": n,
        "model": model,
        "parts": [{"name": "base", "count": n, "built_at": _now()}],
        "neighbors": [],
        "text_encoder": None,
    }
    write_manifest(out, manifest)
    return manifest


def search(index_dir: str | Path, queries, k: int, nprobe: int) -> tuple[np.ndarray, np.ndarray]:
    """Reference ADC search over every part; returns ids (nq, k) int64 and scores (nq, k) float32.

    Rows with fewer than ``k`` candidates are padded with id -1 and score -inf. Queries are
    expected to be unit-norm (they are normalized with a warning otherwise).
    """
    manifest = read_manifest(index_dir)
    d, nlist, m = manifest["dims"], manifest["nlist"], manifest["m"]
    q = np.atleast_2d(np.asarray(queries))
    if q.ndim != 2 or q.shape[1] != d:
        raise ValueError(f"dims mismatch: queries {q.shape}, index dims {d}")
    if q.shape[0] == 0 or k < 1 or nprobe < 1:
        raise ValueError("need at least one query, k >= 1 and nprobe >= 1")
    q, fixed = unit_rows(q)
    warn_normalized(fixed, "search queries")
    nprobe = min(nprobe, nlist)
    centroids, pq = load_core(index_dir, manifest)
    parts = [
        open_part(index_dir, p["name"], nlist, m, p["count"])
        for p in manifest["parts"]
        if p["count"] > 0
    ]
    dsub = d // m
    cols = np.arange(m)
    out_ids = np.full((len(q), k), -1, dtype=np.int64)
    out_scores = np.full((len(q), k), -np.inf, dtype=np.float32)
    for qi, vec in enumerate(q):
        coarse = centroids @ vec
        probe = np.argsort(-coarse, kind="stable")[:nprobe]
        lut = np.einsum("jd,jkd->jk", vec.reshape(m, dsub), pq)
        cand_ids, cand_scores = [], []
        for offsets, ids, codes in parts:
            for lst in probe:
                lo, hi = int(offsets[lst]), int(offsets[lst + 1])
                if hi > lo:
                    cand_ids.append(np.asarray(ids[lo:hi]))
                    cand_scores.append(coarse[lst] + lut[cols, np.asarray(codes[lo:hi])].sum(1))
        if not cand_ids:
            continue
        cid, cs = np.concatenate(cand_ids), np.concatenate(cand_scores)
        top = np.argsort(-cs, kind="stable")[:k]
        out_ids[qi, : len(top)], out_scores[qi, : len(top)] = cid[top], cs[top]
    return out_ids, out_scores


def _existing_ids(index_dir, manifest) -> np.ndarray:
    parts = [
        np.asarray(open_part(index_dir, p["name"], manifest["nlist"], manifest["m"], p["count"])[1])
        for p in manifest["parts"]
    ]
    return np.concatenate(parts) if parts else np.empty(0, dtype=np.uint32)


def append(index_dir: str | Path, part_name: str, E_new, ids_new) -> dict:
    """Encode new vectors with the stored centroids and codebooks into a new part.

    Numpy only. Ids must be unique and absent from the index; the manifest is written last.
    """
    check_vectors(E_new, "E_new")
    manifest = read_manifest(index_dir)
    ids = check_ids(ids_new, len(E_new))
    if E_new.shape[1] != manifest["dims"]:
        raise ValueError(f"dims mismatch: E_new {E_new.shape[1]}, index {manifest['dims']}")
    if not PART_NAME.match(part_name):
        raise ValueError(f"invalid part name {part_name!r}")
    if any(p["name"] == part_name for p in manifest["parts"]):
        raise ValueError(f"part {part_name!r} already exists")
    clash = np.isin(ids, _existing_ids(index_dir, manifest))
    if clash.any():
        raise ValueError(f"{int(clash.sum())} ids already in the index (e.g. {ids[clash][0]})")
    centroids, pq = load_core(index_dir, manifest)
    lists, codes, fixed = encode_stream(E_new, centroids, pq)
    warn_normalized(fixed, "append")
    offsets, ids_sorted, codes_sorted = group_by_list(lists, ids, codes, manifest["nlist"])
    write_part(index_dir, part_name, offsets, ids_sorted, codes_sorted)
    manifest["parts"].append({"name": part_name, "count": len(ids), "built_at": _now()})
    manifest["count"] += len(ids)
    write_manifest(index_dir, manifest)
    return manifest


def compact(index_dir: str | Path, keep_ids=None, name: str = "base") -> dict:
    """Merge all parts into one part ``name`` grouped by list, optionally keeping only ``keep_ids``.

    Files are written to temp names and renamed, the manifest last, so a reader never sees a
    manifest that references files that were not yet written. Old part files are removed after.
    A published index passes a new ``name`` each time, so files a reader already holds a
    manifest for are never rewritten in place.
    """
    manifest = read_manifest(index_dir)
    nlist, m = manifest["nlist"], manifest["m"]
    lists, ids, codes = [], [], []
    for p in manifest["parts"]:
        offsets, p_ids, p_codes = open_part(index_dir, p["name"], nlist, m, p["count"])
        lists.append(np.repeat(np.arange(nlist, dtype=np.int32), np.diff(offsets.astype(np.int64))))
        ids.append(np.asarray(p_ids))
        codes.append(np.asarray(p_codes))
    lists, ids, codes = np.concatenate(lists), np.concatenate(ids), np.concatenate(codes)
    if keep_ids is not None:
        keep = np.isin(ids, np.asarray(keep_ids))
        lists, ids, codes = lists[keep], ids[keep], codes[keep]
    offsets, ids, codes = group_by_list(lists, ids, codes, nlist)
    old = [p["name"] for p in manifest["parts"] if p["name"] != name]
    write_part(index_dir, name, offsets, ids, codes)
    manifest["parts"] = [{"name": name, "count": len(ids), "built_at": _now()}]
    manifest["count"] = len(ids)
    write_manifest(index_dir, manifest)
    for name in old:
        for suffix in ("offsets.u32", "ids.u32", "codes.u8"):
            (Path(index_dir) / f"{name}.{suffix}").unlink(missing_ok=True)
    return manifest


def _exact_topk(E, ids, rows: np.ndarray, k: int) -> np.ndarray:
    """Exact cosine top-``k`` ids for the given rows of ``E``, excluding each row itself."""
    q, _ = unit_rows(E[rows])
    best_v = np.full((len(rows), 0), -np.inf, dtype=np.float32)
    best_i = np.zeros((len(rows), 0), dtype=np.int64)
    for lo in range(0, len(E), CHUNK):
        sims = q @ unit_rows(E[lo : lo + CHUNK])[0].T
        own = rows - lo
        ok = (own >= 0) & (own < sims.shape[1])
        sims[np.flatnonzero(ok), own[ok]] = -np.inf
        v = np.concatenate([best_v, sims], axis=1)
        i = np.concatenate(
            [best_i, np.broadcast_to(np.arange(lo, lo + sims.shape[1]), sims.shape)], 1
        )
        top = np.argpartition(-v, min(k, v.shape[1]) - 1, axis=1)[:, :k]
        best_v, best_i = np.take_along_axis(v, top, 1), np.take_along_axis(i, top, 1)
    return np.asarray(ids)[best_i]


def recall_at_k(
    index_dir: str | Path, E, ids, *, k: int = 10, nprobe: int = 32, n_queries: int = 1000, seed=0
) -> float:
    """Mean recall@k of `search` against exact brute force for sampled rows of ``E``.

    Each query is a data row; its own id is excluded from both sides.
    """
    check_vectors(E)
    ids = check_ids(ids, len(E))
    rows = np.sort(np.random.default_rng(seed).choice(len(E), min(n_queries, len(E)), False))
    truth = _exact_topk(E, ids, rows, k)
    found, _ = search(index_dir, np.asarray(E[rows]), k + 1, nprobe)
    hits = 0
    for r, f, t in zip(rows, found, truth, strict=True):
        f = f[f != ids[r]][:k]
        hits += len(np.intersect1d(f, t))
    return hits / (len(rows) * k)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m what_to_id.atlas_index", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, vectors=True):
        sp.add_argument("--index", "--out", dest="index", required=True, help="index directory")
        if vectors:
            sp.add_argument("--E", required=True, help="embeddings .npy (n x dims)")
            sp.add_argument("--ids", required=True, help="observation ids .npy (n,)")
        return sp

    sp = common(sub.add_parser("build"))
    sp.add_argument("--nlist", type=int, default=4096)
    sp.add_argument("--m", type=int, default=64)
    sp.add_argument("--train-size", type=int, default=262144)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--model-json", help="JSON object stored as manifest model")
    sp = common(sub.add_parser("neighbors"))
    sp.add_argument("--name", default="neighbors")
    sp.add_argument("--k", type=int, default=12)
    sp.add_argument("--block", type=int, default=1024)
    sp.add_argument("--device", default="auto", choices=["auto", "cuda", "numpy"])
    sp = common(sub.add_parser("append"))
    sp.add_argument("--part", required=True)
    sp = common(sub.add_parser("compact"), vectors=False)
    sp.add_argument("--keep-ids", help=".npy of ids to keep (default: keep all)")
    sp = common(sub.add_parser("search"), vectors=False)
    sp.add_argument("--queries", required=True, help=".npy (nq x dims)")
    sp.add_argument("--k", type=int, default=10)
    sp.add_argument("--nprobe", type=int, default=32)
    sp = common(sub.add_parser("recall"))
    sp.add_argument("--k", type=int, default=10)
    sp.add_argument("--nprobe", type=int, default=32)
    sp.add_argument("--n-queries", type=int, default=1000)
    sp.add_argument("--seed", type=int, default=0)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.cmd in ("build", "neighbors", "append", "recall"):
        E, ids = np.load(a.E, mmap_mode="r"), np.load(a.ids)
    if a.cmd == "build":
        model = json.loads(a.model_json) if a.model_json else None
        kw = {"nlist": a.nlist, "m": a.m, "train_size": a.train_size, "seed": a.seed}
        m = build(E, ids, a.index, model=model, **kw)
        print(json.dumps({k: m[k] for k in ("nlist", "m", "count")}))
    elif a.cmd == "neighbors":
        print(json.dumps(neighbors(E, ids, a.index, a.name, a.k, a.block, a.device)))
    elif a.cmd == "append":
        print(json.dumps(append(a.index, a.part, E, ids)["parts"][-1]))
    elif a.cmd == "compact":
        keep = np.load(a.keep_ids) if a.keep_ids else None
        print(json.dumps(compact(a.index, keep)["parts"]))
    elif a.cmd == "search":
        found, scores = search(a.index, np.load(a.queries), a.k, a.nprobe)
        print(json.dumps({"ids": found.tolist(), "scores": scores.tolist()}))
    else:
        r = recall_at_k(a.index, E, ids, k=a.k, nprobe=a.nprobe, n_queries=a.n_queries, seed=a.seed)
        print(json.dumps({"k": a.k, "nprobe": a.nprobe, "n_queries": a.n_queries, "recall": r}))


if __name__ == "__main__":
    main()
