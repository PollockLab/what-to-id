"""Daily update of the static atlas index: plan what to encode, encode a shard, apply the result.

    python -m what_to_id.atlas_update plan --pool pool.parquet --index DIR --out todo.json
    python -m what_to_id.atlas_update encode --todo todo.json --shard 0 --shards 4 --out vec-0.npz
    python -m what_to_id.atlas_update apply --index DIR --vectors 'vec-*.npz' --pool pool.parquet \\
        --part delta-20260101 [--compact]

`plan` lists pool observations the index does not hold. `encode` embeds its slice on CPU with
BioCLIP 2.5 and saves after every chunk, so a timeout keeps the finished work. `apply` appends a
delta part and a neighbour delta, and with `--compact` also folds deltas into the base and drops
observations that left the pool. The raw 3M-row vectors are not on the runner, so the neighbours of
new observations are approximate (see `delta_neighbors`). Nothing here needs torch except the real
encoder in `atlas_update_encoder`.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import atlas_index
from what_to_id.atlas_index_io import check_ids, read_manifest, unit_rows
from what_to_id.atlas_neighbors import _topk_numpy, merge_neighbors, write_neighbor_records
from what_to_id.atlas_update_encoder import Encoder

log = logging.getLogger("what_to_id")

CHUNK = 32  # photos per save: about 90 s on a free runner, so a deadline stops within minutes
NEIGHBOR_K = 12
DEFAULT_NPROBE = 64
MAX_DROP = 0.2  # refuse to compact away more than this share of the index (a truncated pool)

EncoderFactory = Callable[[Path, int], Encoder]


def _load_encoder(work: Path, threads: int) -> Encoder:
    from what_to_id.atlas_update_encoder import load_encoder

    return load_encoder(work, threads)


def _pool_ids(pool: str | Path) -> np.ndarray:
    return pd.read_parquet(pool, columns=["id"])["id"].to_numpy(dtype=np.int64)


# ---- plan -------------------------------------------------------------------------------
def plan(pool: str | Path, index: str | Path, out: str | Path, max_new: int | None = None) -> dict:
    """Write ``out`` with the pool observations missing from the index, oldest first, capped."""
    if max_new is not None and max_new < 1:
        raise ValueError("--max-new must be positive")
    df = pd.read_parquet(pool)
    if "photo_url" not in df.columns:
        raise ValueError(f"{pool} has no photo_url column")
    if df["id"].duplicated().any():
        raise ValueError("duplicate ids in the pool")
    manifest = read_manifest(index)
    indexed = atlas_index._existing_ids(index, manifest)
    new = df[~df["id"].isin(indexed)]
    has_photo = new["photo_url"].astype("string").str.len().fillna(0) > 0
    sort_cols = ["created_at", "id"] if "created_at" in new.columns else ["id"]
    new = new[has_photo].sort_values(sort_cols, kind="stable")
    planned = new if max_new is None else new.head(max_new)
    summary = {
        "pool": int(len(df)),
        "indexed": int(len(indexed)),
        "new": int(len(new)),
        "planned": int(len(planned)),
        "no_photo": int((~has_photo).sum()),
        "removed": int((~np.isin(indexed, df["id"].to_numpy())).sum()),
    }
    todo = {
        **summary,
        "ids": planned["id"].astype(int).tolist(),
        "urls": planned["photo_url"].tolist(),
    }
    Path(out).write_text(json.dumps(todo))
    return summary


# ---- encode -----------------------------------------------------------------------------
def _save_vectors(path: Path, ids, E, failed, info: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        np.savez(
            f,
            ids=np.asarray(ids, dtype=np.int64),
            E=np.asarray(E, dtype=np.float32),
            failed=np.asarray(failed, dtype=np.int64),
            model=np.array(json.dumps(info, sort_keys=True)),
        )
    os.replace(tmp, path)


def _load_vectors(path: str | Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        if "model" not in z.files:
            raise ValueError(f"{path} has no model record; not an atlas_update vector file")
        return {
            "ids": z["ids"].astype(np.int64),
            "E": z["E"].astype(np.float32),
            "failed": z["failed"].astype(np.int64),
            "info": json.loads(str(z["model"])),
        }


def encode(
    todo: str | Path,
    shard: int,
    shards: int,
    out: str | Path,
    *,
    deadline_minutes: float | None = None,
    resume: str | Path | None = None,
    factory: EncoderFactory = _load_encoder,
    work: str | Path = "atlas-work",
    threads: int = 4,
    chunk: int = CHUNK,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Embed this shard's slice (``id % shards == shard``); stop cleanly at the deadline."""
    if shards < 1 or not 0 <= shard < shards:
        raise ValueError(f"shard must satisfy 0 <= shard < shards, got {shard}/{shards}")
    if chunk < 1:
        raise ValueError("chunk must be positive")
    started = clock()
    out = Path(out)
    spec = json.loads(Path(todo).read_text())
    ids = np.asarray(spec["ids"], dtype=np.int64)
    urls = np.asarray(spec["urls"], dtype=object)
    if len(ids) != len(urls):
        raise ValueError("todo ids and urls differ in length")
    mine = (ids % shards) == shard
    ids, urls = ids[mine], urls[mine]

    done_ids = np.empty(0, dtype=np.int64)
    done_E = None
    failed = np.empty(0, dtype=np.int64)
    info = None
    if resume is not None and Path(resume).exists():
        prior = _load_vectors(resume)
        done_ids, done_E, failed, info = prior["ids"], prior["E"], prior["failed"], prior["info"]
        log.info("resuming from %d vectors and %d failures", len(done_ids), len(failed))
    todo_rows = ~np.isin(ids, np.concatenate([done_ids, failed]))
    ids, urls = ids[todo_rows], urls[todo_rows]
    summary = {"shard": shard, "slice": int(mine.sum()), "pending": int(len(ids))}
    if not len(ids):
        if info is not None and Path(resume) != out:
            _save_vectors(out, done_ids, done_E, failed, info)
        return {**summary, "encoded": 0, "failed": 0, "stopped": "complete"}

    enc = factory(Path(work), threads)
    if info is not None and info != enc.info:
        raise ValueError(f"resume file was encoded with {info}, this run uses {enc.info}")
    E_parts = [done_E if done_E is not None else np.empty((0, enc.dims), dtype=np.float32)]
    id_parts, fail_parts = [done_ids], [failed]
    stopped, n_ok, n_bad = "complete", 0, 0
    for lo in range(0, len(ids), chunk):
        if deadline_minutes is not None and clock() - started >= deadline_minutes * 60:
            stopped = "deadline"
            break
        ok_ids, E, bad = enc.encode(ids[lo : lo + chunk].tolist(), urls[lo : lo + chunk].tolist())
        E = np.asarray(E, dtype=np.float32).reshape(len(ok_ids), enc.dims)
        id_parts.append(np.asarray(ok_ids, dtype=np.int64))
        E_parts.append(E)
        fail_parts.append(np.asarray([i for i, _ in bad], dtype=np.int64))
        n_ok, n_bad = n_ok + len(ok_ids), n_bad + len(bad)
        _save_vectors(
            out,
            np.concatenate(id_parts),
            np.concatenate(E_parts),
            np.concatenate(fail_parts),
            enc.info,
        )
        log.info(
            "[encode %d] %d/%d done (%d failed)",
            shard,
            lo + len(ids[lo : lo + chunk]),
            len(ids),
            n_bad,
        )
    if stopped == "deadline" and not out.exists():
        _save_vectors(out, id_parts[0], E_parts[0], fail_parts[0], enc.info)
    return {**summary, "encoded": n_ok, "failed": n_bad, "stopped": stopped}


# ---- apply ------------------------------------------------------------------------------
def delta_neighbors(index_dir, E, ids, *, k: int = NEIGHBOR_K, nprobe: int = DEFAULT_NPROBE):
    """Approximate top-``k`` neighbours of the new rows: ``(ids (n, k), cosines (n, k))``.

    Raw vectors of the existing index are not available, so candidates are the exact cosines
    among the new rows plus an IVF-PQ search (``nprobe`` lists) of the index as it is now. The
    search scores are ADC estimates of the cosine, so they carry PQ quantisation error and are
    only comparable to the exact scores within that error. Rows with fewer than ``k`` candidates
    are padded with id 0 and cosine -1. Call before appending the rows to the index.
    """
    E, _ = unit_rows(E)
    n = len(E)
    cand_ids = [np.empty(0, dtype=np.int64)] * n
    cand_cos = [np.empty(0, dtype=np.float32)] * n
    if n > 1:
        vals, idx = _topk_numpy(E, E, 0, min(k, n - 1))
        cand_ids = [np.asarray(ids)[row] for row in idx]
        cand_cos = list(vals)
    if read_manifest(index_dir)["count"]:
        found, scores = atlas_index.search(index_dir, E, k, nprobe)
        cand_ids = [np.concatenate([a, f[f >= 0]]) for a, f in zip(cand_ids, found, strict=True)]
        cand_cos = [
            np.concatenate([a, s[f >= 0]]) for a, s, f in zip(cand_cos, scores, found, strict=True)
        ]
    out_ids = np.zeros((n, k), dtype=np.int64)
    out_cos = np.full((n, k), -1.0, dtype=np.float32)
    for r, (ci, cc) in enumerate(zip(cand_ids, cand_cos, strict=True)):
        top = np.argsort(-cc, kind="stable")[:k]
        out_ids[r, : len(top)], out_cos[r, : len(top)] = ci[top], np.clip(cc[top], -1.0, 1.0)
    return out_ids, out_cos


def _check_model(manifest: dict, info: dict, where: str) -> None:
    want = manifest.get("model") or {}
    for key in ("id", "revision"):
        if key in want and info.get(key) != want[key]:
            raise ValueError(
                f"model mismatch in {where}: {key} {info.get(key)!r}, index {want[key]!r}"
            )


def apply(
    index: str | Path,
    vectors: list[str],
    pool: str | Path,
    part: str,
    *,
    compact: bool = False,
    raw_out: str | Path | None = None,
    nprobe: int = DEFAULT_NPROBE,
    max_drop: float = MAX_DROP,
) -> dict:
    """Append ``vectors`` as part ``part`` with a neighbour delta; optionally compact."""
    manifest = read_manifest(index)
    parts = [(v, _load_vectors(v)) for v in vectors]
    for v, p in parts:
        if p["E"].shape[1:] != (manifest["dims"],):
            raise ValueError(f"dims mismatch: {v} has {p['E'].shape[1:]}, index {manifest['dims']}")
        _check_model(manifest, p["info"], v)
    ids = np.concatenate([p["ids"] for _, p in parts]) if parts else np.empty(0, dtype=np.int64)
    E = (
        np.concatenate([p["E"] for _, p in parts])
        if parts
        else np.empty((0, manifest["dims"]), "f4")
    )
    if len(ids):
        check_ids(ids, len(ids))  # duplicates across or within files, ids beyond uint32
    live = _pool_ids(pool)
    indexed = atlas_index._existing_ids(index, manifest)
    keep = np.isin(ids, live) & ~np.isin(ids, indexed)
    result = {"vectors": int(len(ids)), "added": int(keep.sum())}
    if not keep.all():
        log.warning(
            "skipping %d vectors already indexed or no longer in the pool", int((~keep).sum())
        )
    ids, E = ids[keep], E[keep]
    if len(ids):
        nb_ids, nb_cos = delta_neighbors(index, E, ids, nprobe=nprobe)
        atlas_index.append(index, part, E, ids)
        write_neighbor_records(index, f"neighbors-{part}", ids, nb_ids, nb_cos, 1024)
        raw = Path(raw_out) if raw_out else Path(index).resolve().parent / f"raw-{part}.npz"
        with open(raw, "wb") as f:
            np.savez(f, ids=ids, E=E.astype(np.float16))
        result["raw"] = str(raw)
    if compact:
        total = read_manifest(index)["count"]
        dropped = int(
            (~np.isin(atlas_index._existing_ids(index, read_manifest(index)), live)).sum()
        )
        if total and dropped > max_drop * total:
            raise ValueError(
                f"compaction would drop {dropped} of {total} ids; is the pool truncated?"
            )
        atlas_index.compact(index, keep_ids=live)
        merge_neighbors(index, keep_ids=live)
        result.update(compacted=True, dropped=dropped)
    result["count"] = read_manifest(index)["count"]
    return result


# ---- cli --------------------------------------------------------------------------------
def main(argv: list[str] | None = None, *, factory: EncoderFactory = _load_encoder) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.atlas_update", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("plan")
    sp.add_argument("--pool", required=True)
    sp.add_argument("--index", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--max-new", type=int)
    sp = sub.add_parser("encode")
    sp.add_argument("--todo", required=True)
    sp.add_argument("--shard", type=int, required=True)
    sp.add_argument("--shards", type=int, required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--deadline-minutes", type=float)
    sp.add_argument("--resume")
    sp.add_argument("--work", default="atlas-work", help="scratch dir for photos and model cache")
    sp.add_argument("--threads", type=int, default=4)
    sp.add_argument("--chunk", type=int, default=CHUNK)
    sp = sub.add_parser("apply")
    sp.add_argument("--index", required=True)
    sp.add_argument("--vectors", nargs="*", default=[], help="vec-*.npz files or glob patterns")
    sp.add_argument("--pool", required=True)
    sp.add_argument("--part", required=True, help="new part name, e.g. delta-20260101")
    sp.add_argument("--compact", action="store_true")
    sp.add_argument("--raw-out", help="float16 npz of the new vectors (default: next to --index)")
    sp.add_argument("--nprobe", type=int, default=DEFAULT_NPROBE)
    sp.add_argument("--max-drop", type=float, default=MAX_DROP)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if a.cmd == "plan":
            result = plan(a.pool, a.index, a.out, a.max_new)
        elif a.cmd == "encode":
            result = encode(
                a.todo, a.shard, a.shards, a.out, deadline_minutes=a.deadline_minutes,
                resume=a.resume, factory=factory, work=a.work, threads=a.threads, chunk=a.chunk,
            )  # fmt: skip
        else:
            files = sorted({f for pat in a.vectors for f in (glob.glob(pat) or [pat])})
            result = apply(
                a.index, files, a.pool, a.part, compact=a.compact, raw_out=a.raw_out,
                nprobe=a.nprobe, max_drop=a.max_drop,
            )  # fmt: skip
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"atlas_update {a.cmd}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
