"""Per-record Identify levels for every pool record, from identify.parquet (see `identify`).

    python -m what_to_id.pool_levels --out SITE_DIR (--data-url URL | --parquet FILE)

The site directory holds the built map (map.html, its pool shards and pool-taxa.bin). The atlas
manifest at ``--data-url`` names `identify.parquet` under ``"identify"``; ``--parquet`` reads a
local file instead. It writes two files, records in the order of META.shards, as pool-lookalike.bin:

``pool-levels.bin``: gzip of one plane of n bytes. The low nibble is the level (0 none, 1 easy,
2 taxonomist, 3 narrow, 4 weird; `identify.LEVEL_NAMES`), the high nibble the record's score
quantized to 16 steps within its level, 15 for the record to show first (the highest score, the
lowest for weird). A record missing from identify.parquet, or whose label changed since it was
scored, is level 0.

``pool-levels-looks.bin``: the look-alike species of the taxonomist and narrow records, apart so
the levels load first. A uint32 LE length and that many bytes of JSON ``{"names": [...]}``, then two
planes of n bytes (low byte, high byte) of indexes into ``names``, 65535 for none; all gzipped.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.identify import NARROW, NONE, TAXONOMIST, WEIRD
from what_to_id.page_lookalike import _fetch, site_records

OUT_NAME = "pool-levels.bin"
LOOKS_NAME = "pool-levels-looks.bin"
STEPS = 16
NO_LOOK = 0xFFFF


def quantize(level: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Per record 0..STEPS-1: its rank among the records of its level, STEPS-1 to show first."""
    q = np.zeros(len(level), np.uint8)
    for lv in np.unique(level[level != NONE]):
        rows = np.flatnonzero(level == lv)
        s = np.nan_to_num(score[rows].astype(np.float64), nan=-np.inf)
        order = np.argsort(-s if lv == WEIRD else s, kind="stable")
        rank = np.empty(len(rows), np.int64)
        rank[order] = np.arange(len(rows))
        q[rows] = rank * STEPS // len(rows)
    return q


def pack(level: np.ndarray, score: np.ndarray) -> bytes:
    """The gzipped levels file: level | quantized score << 4 per record."""
    return gzip.compress((level.astype(np.uint8) | quantize(level, score) << 4).tobytes(), mtime=0)


def unpack(blob: bytes) -> tuple[np.ndarray, np.ndarray]:
    """(level, quantized score) per record of a levels file."""
    raw = np.frombuffer(gzip.decompress(blob), dtype=np.uint8)
    return (raw & 15).astype(np.int8), raw >> 4


def pack_looks(level: np.ndarray, looks: np.ndarray) -> bytes:
    """The gzipped look-alike file for `looks` (name or None per record), kept at levels 2 and 3."""
    keep = np.isin(level, (TAXONOMIST, NARROW)) & pd.notna(looks)
    names, code = np.unique(np.asarray(looks, dtype=object)[keep].astype(str), return_inverse=True)
    if len(names) >= NO_LOOK:
        raise ValueError(f"{len(names)} look-alike names do not fit 16 bits")
    idx = np.full(len(level), NO_LOOK, np.uint16)
    idx[keep] = code
    head = json.dumps({"names": names.tolist()}, separators=(",", ":")).encode()
    planes = idx.view(np.uint8).reshape(-1, 2).T.tobytes()
    return gzip.compress(len(head).to_bytes(4, "little") + head + planes, mtime=0)


def unpack_looks(blob: bytes, n: int) -> list[str | None]:
    """The look-alike name per record of a looks file, None for none."""
    raw = gzip.decompress(blob)
    size = int.from_bytes(raw[:4], "little")
    names = json.loads(raw[4 : 4 + size])["names"]
    planes = np.frombuffer(raw, np.uint8, 2 * n, 4 + size).reshape(2, n)
    idx = planes[0].astype(np.uint16) | planes[1].astype(np.uint16) << 8
    return [None if i == NO_LOOK else names[i] for i in idx]


def align(ids: np.ndarray, current: np.ndarray, scored: pd.DataFrame) -> np.ndarray:
    """Row of `scored` for each site record (id, current taxon id), -1 when it has none."""
    s = scored.reset_index(drop=True)
    key = pd.MultiIndex.from_arrays([s["id"].to_numpy(np.int64), s["taxon_id"].to_numpy(np.int64)])
    return key.get_indexer(pd.MultiIndex.from_arrays([ids, current]))


def build(site: str | Path, data_url: str | None = None, parquet: str | Path | None = None) -> dict:
    """Write both files into ``site`` and return the record count per level."""
    site = Path(site)
    ids, tax, rows, _ = site_records(site)
    taxon_ids = np.array([r[2] for r in rows] + [-1], dtype=np.int64)
    current = taxon_ids[np.where(tax < len(rows), tax, len(rows))]
    with tempfile.TemporaryDirectory(prefix="pool-levels-") as work:
        if parquet is None:
            if not data_url:
                raise ValueError("give --data-url or --parquet")
            base = data_url.rstrip("/") + "/"
            _fetch(base + "manifest.json", Path(work) / "manifest.json")
            entry = json.loads((Path(work) / "manifest.json").read_text()).get("identify")
            if not entry:
                raise ValueError("the manifest has no identify table")
            parquet = Path(work) / "identify.parquet"
            _fetch(base + entry["name"], parquet)
        scored = pd.read_parquet(parquet)
    at = align(ids, current, scored)
    hit = at >= 0
    level = np.zeros(len(ids), np.int8)
    score = np.full(len(ids), np.nan, np.float32)
    looks = np.full(len(ids), None, dtype=object)
    level[hit] = scored["level"].to_numpy()[at[hit]]
    score[hit] = scored["score"].to_numpy(np.float32)[at[hit]]
    looks[hit] = scored["looks_like"].astype(object).to_numpy()[at[hit]]
    (site / OUT_NAME).write_bytes(pack(level, score))
    (site / LOOKS_NAME).write_bytes(pack_looks(level, looks))
    return {int(lv): int(c) for lv, c in zip(*np.unique(level, return_counts=True), strict=True)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.pool_levels", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory holding map.html")
    p.add_argument("--data-url", help="atlas base URL holding manifest.json and identify.parquet")
    p.add_argument("--parquet", type=Path, help="read this local identify.parquet instead")
    a = p.parse_args(argv)
    try:
        counts = build(a.out, a.data_url, a.parquet)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"pool_levels: {exc}", file=sys.stderr)
        return 1
    sizes = ", ".join(
        f"{n} {(a.out / n).stat().st_size / 1e6:.2f} MB" for n in (OUT_NAME, LOOKS_NAME)
    )
    print(f"pool_levels: records per level {counts}; {sizes} gzipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
