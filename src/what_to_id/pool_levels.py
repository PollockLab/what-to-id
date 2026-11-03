"""Per-record Identify levels for every pool record, from identify.parquet (see `identify`).

    python -m what_to_id.pool_levels --out SITE_DIR (--data-url URL | --parquet FILE [--ranges DIR])

The site directory holds the built map (map.html, its pool shards and pool-taxa.bin). The atlas
manifest at ``--data-url`` names `identify.parquet` under ``"identify"``; ``--parquet`` reads a
local file instead. It writes two files, records in the order of META.shards, as pool-lookalike.bin,
and a third when the range tables are found, each under its content-hashed name in map.html's
META.files (`site_files.publish`):

``pool-levels.bin``: gzip of one plane of n bytes. The low nibble is the level (0 none, 1 easy,
2 taxonomist, 3 narrow, 4 weird, 5 mislabel; `identify.LEVEL_NAMES`), the high nibble the
record's score quantized to 16 steps within its level, 15 for the record to show first (the
highest score, the lowest for weird and mislabel). A record missing from identify.parquet, or
whose label changed since it was scored, is level 0.

``pool-levels-looks.bin``: the look-alike species of the taxonomist, narrow and mislabel records,
apart so the levels load first. A uint32 LE length and that many bytes of JSON
``{"names": [...]}``, then two planes of n bytes (low byte, high byte) of indexes into
``names``, 65535 for none; all gzipped.

``pool-levels-range.bin``: the range maps, from `level_ranges` output (range-notes.parquet,
level-ranges.parquet, level-range-cells.parquet): the manifest's identify entry names them under
``range_notes``, ``ranges`` and ``range_cells``, or ``--ranges DIR`` holds them. A uint32 LE length
and that many bytes of JSON ``{"grid": [[lon, lat, ...] per cell, integer thousandths of a degree],
"names": [...], "rng": [base64 bitset over the grid per name, bit i in byte i>>3 at 1<<(i&7), ""
for a known range off the grid], "notes": [...]}``, then two planes of n bytes: ``okm``, km from
the record to its label's range (`okm_code`: 0 inside, 255 unknown) and ``note``, an index into
``notes`` (255 none); all gzipped. A name not in ``names`` has no known range. Without the tables
the file is not written; the levels are.

``pool-levels-first.bin``: the first cards Identify draws while the pool shards load, the lists
`identify_app.js` builds for no filter (``""``) and for each one group (``"groups=Aves"``, as
MapFilter writes it), with no area, view or taxa and the range file's default (Clear matches leave
out records far outside). Gzipped JSON ``{"bbox": META.bbox, "taxa": [[latin, common, taxon id],
...], "looks": [...], "s": {state: {"total": [...], "n": [...], "rows": [...]}}}``, per level 0..5:
the records in it, the cards after the per-species cut, and the first FIRST_ROWS cards as ``[id,
taxa index (65535 none), looks index (65535 none), how many more of its taxon the cut left out]``.

``pool-levels-dates.json``: with ``--data-url``,
``{"photos": "2026-10-15", "scored": "2026-10-27"}``, the photo download the embeddings came from
(the date in the identify entry's ``emb`` path, else in ``model.source``) and the day
identify.parquet was built; `page_identify` writes them into the About. Either may be null.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

from what_to_id import site_files
from what_to_id.identify import MISLABEL, NARROW, NONE, TAXONOMIST, WEIRD
from what_to_id.page_identify import DATES_NAME, FIRST_NAME
from what_to_id.page_lookalike import _fetch, site_records
from what_to_id.page_map import _decode_shard
from what_to_id.tree_page import map_meta

OUT_NAME = "pool-levels.bin"
LOOKS_NAME = "pool-levels-looks.bin"
STEPS = 16
NO_LOOK = 0xFFFF
RANGE_NAME = "pool-levels-range.bin"
NO_BYTE = 0xFF
NOTAX = 0xFFFF
FIRST_ROWS = 200  # one iNaturalist batch, IdentifyLinks.MAX_IDS
PER_SPECIES = 3  # identify_app.js
FAR_CODE = 50  # identify_ranges.js OUT_KM: an okm_code of 50 and up is 50 km or more
# manifest key -> file name, as level_ranges writes them (not imported: it needs h3)
RANGE_FILES = {
    "range_notes": "range-notes.parquet",
    "ranges": "level-ranges.parquet",
    "range_cells": "level-range-cells.parquet",
}


def quantize(level: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Per record 0..STEPS-1: its rank among the records of its level, STEPS-1 to show first."""
    q = np.zeros(len(level), np.uint8)
    for lv in np.unique(level[level != NONE]):
        rows = np.flatnonzero(level == lv)
        s = np.nan_to_num(score[rows].astype(np.float64), nan=-np.inf)
        order = np.argsort(-s if lv in (WEIRD, MISLABEL) else s, kind="stable")
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
    """The gzipped look-alike file for `looks` (name or None per record), for levels 2, 3, 5."""
    keep = np.isin(level, (TAXONOMIST, NARROW, MISLABEL)) & pd.notna(looks)
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


def okm_code(km: np.ndarray) -> np.ndarray:
    """One byte per km (NaN unknown): 0..49 as is, then the km the page shows, rounded to 10 below
    500, 50 below 1000 and 100 beyond, so 50 and up stays far and the page's rounding is exact."""
    k = np.asarray(km, np.float64)
    known = ~np.isnan(k)
    k = np.floor(np.where(known, k, 0) + 0.5)
    s = np.where(k >= 1000, 100, np.where(k >= 500, 50, 10))
    d = np.floor(k / s + 0.5) * s  # Math.round, as the page rounds
    far = np.where(
        d <= 500,
        50 + (d - 50) / 10,
        np.where(d <= 1000, 95 + (d - 500) / 50, 105 + (d - 1000) / 100),
    )
    # shortcut: 254 (15,900 km) caps the far end, past any distance from BC to a range in reach
    code = np.where(k < 50, k, np.minimum(far, 254))
    return np.where(known, code, NO_BYTE).astype(np.uint8)


def okm_km(code: np.ndarray) -> np.ndarray:
    """The km of each `okm_code` byte, NaN for unknown."""
    c = np.asarray(code, np.float64)
    km = np.where(
        c < 50,
        c,
        np.where(
            c <= 95,
            50 + (c - 50) * 10,
            np.where(c <= 105, 500 + (c - 95) * 50, 1000 + (c - 105) * 100),
        ),
    )
    return np.where(c == NO_BYTE, np.nan, km)


def pack_range(km: np.ndarray, note: np.ndarray, ranges: pd.DataFrame, grid: pd.DataFrame) -> bytes:
    """The gzipped range file: km (NaN unknown) and note (str or None) per record, the range
    tables (`level_ranges`: ranges name, cells; grid lat, lon boundary arrays)."""
    has = pd.notna(note)
    notes, code = np.unique(np.asarray(note, dtype=object)[has].astype(str), return_inverse=True)
    if len(notes) >= NO_BYTE:
        raise ValueError(f"{len(notes)} range notes do not fit a byte")
    nb = np.full(len(km), NO_BYTE, np.uint8)
    nb[has] = code
    rng = []
    for name, cells in zip(ranges["name"], ranges["cells"], strict=True):
        cells = np.asarray(cells, np.int64)
        if len(cells) and (cells.min() < 0 or cells.max() >= len(grid)):
            raise ValueError(f"the range of {name} has a cell outside the {len(grid)}-cell grid")
        b = np.zeros(len(grid), bool)
        b[cells] = True
        bits = np.packbits(b, bitorder="little").tobytes() if len(cells) else b""
        rng.append(base64.b64encode(bits).decode())
    head = {
        "grid": [
            np.rint(np.column_stack([lo, la]).astype(np.float64) * 1000)
            .astype(int)
            .ravel()
            .tolist()
            for la, lo in zip(grid["lat"], grid["lon"], strict=True)
        ],
        "names": [str(n) for n in ranges["name"]],
        "rng": rng,
        "notes": notes.tolist(),
    }
    raw = json.dumps(head, separators=(",", ":")).encode()
    body = len(raw).to_bytes(4, "little") + raw + okm_code(km).tobytes() + nb.tobytes()
    return gzip.compress(body, mtime=0)


def unpack_range(blob: bytes, n: int) -> tuple[dict, np.ndarray, list[str | None]]:
    """(JSON head, km per record with NaN unknown, note per record or None) of a range file."""
    raw = gzip.decompress(blob)
    size = int.from_bytes(raw[:4], "little")
    head = json.loads(raw[4 : 4 + size])
    if len(raw) != 4 + size + 2 * n:
        raise ValueError(f"the range file holds {len(raw)} bytes, expected {4 + size + 2 * n}")
    okm, nb = np.frombuffer(raw, np.uint8, 2 * n, 4 + size).reshape(2, n)
    return head, okm_km(okm), [None if v == NO_BYTE else head["notes"][v] for v in nb]


def align(ids: np.ndarray, current: np.ndarray, scored: pd.DataFrame) -> np.ndarray:
    """Row of `scored` for each site record (id, current taxon id), -1 when it has none."""
    s = scored.reset_index(drop=True)
    key = pd.MultiIndex.from_arrays([s["id"].to_numpy(np.int64), s["taxon_id"].to_numpy(np.int64)])
    return key.get_indexer(pd.MultiIndex.from_arrays([ids, current]))


def build(
    site: str | Path,
    data_url: str | None = None,
    parquet: str | Path | None = None,
    ranges: str | Path | None = None,
) -> dict:
    """Write the files into ``site`` and return the record count per level."""
    site = Path(site)
    ids, tax, rows, _ = site_records(site)
    taxon_ids = np.array([r[2] for r in rows] + [-1], dtype=np.int64)
    current = taxon_ids[np.where(tax < len(rows), tax, len(rows))]
    tables, why = None, "no --ranges"
    parquet_from_manifest = parquet is None
    with tempfile.TemporaryDirectory(prefix="pool-levels-") as work:
        if parquet is None:
            if not data_url:
                raise ValueError("give --data-url or --parquet")
            base = data_url.rstrip("/") + "/"
            _fetch(base + "manifest.json", Path(work) / "manifest.json")
            manifest = json.loads((Path(work) / "manifest.json").read_text())
            entry = manifest.get("identify")
            if not entry:
                raise ValueError("the manifest has no identify table")
            parquet = Path(work) / "identify.parquet"
            _fetch(base + entry["name"], parquet)
            missing = [k for k in RANGE_FILES if not entry.get(k)]
            why = f"the manifest's identify entry has no {missing[0]!r}" if missing else None
            ranges = None if missing else Path(work)
            try:
                for k in () if missing else RANGE_FILES:
                    _fetch(base + entry[k], Path(work) / RANGE_FILES[k])
            except OSError as exc:
                ranges, why = None, f"could not fetch the range tables: {exc}"
        if ranges is not None:
            try:
                tables = [pd.read_parquet(Path(ranges) / f) for f in RANGE_FILES.values()]
            except (OSError, ValueError) as exc:
                why = f"could not read the range tables: {exc}"
        scored = pd.read_parquet(parquet)
    at = align(ids, current, scored)
    hit = at >= 0
    level = np.zeros(len(ids), np.int8)
    score = np.full(len(ids), np.nan, np.float32)
    looks = np.full(len(ids), None, dtype=object)
    level[hit] = scored["level"].to_numpy()[at[hit]]
    score[hit] = scored["score"].to_numpy(np.float32)[at[hit]]
    looks[hit] = scored["looks_like"].astype(object).to_numpy()[at[hit]]
    site_files.publish(site, "levels", OUT_NAME, pack(level, score))
    site_files.publish(site, "looks", LOOKS_NAME, pack_looks(level, looks))
    site_files.publish(site, "range", RANGE_NAME, None)  # a stale one would no longer line up
    far = None
    (site / DATES_NAME).unlink(missing_ok=True)
    if parquet_from_manifest:
        (site / DATES_NAME).write_text(json.dumps(scoring_dates(manifest)))
    try:
        if tables is not None:
            km, note = range_planes(ids, hit, tables[0])
            site_files.publish(site, "range", RANGE_NAME, pack_range(km, note, *tables[1:]))
            code = okm_code(km)
            far = (code >= FAR_CODE) & (code != NO_BYTE)
    except (KeyError, ValueError) as exc:
        why = f"the range tables do not fit: {exc}"
        far = None
        site_files.publish(site, "range", RANGE_NAME, None)
    first = pack_first(site, ids, tax, rows, level, quantize(level, score), looks, far)
    site_files.publish(site, "first", FIRST_NAME, first)
    if site_files.path(site, "range") is None:
        print(f"pool_levels: no {RANGE_NAME}, so no range maps: {why}", file=sys.stderr)
    return {int(lv): int(c) for lv, c in zip(*np.unique(level, return_counts=True), strict=True)}


def pack_first(site, ids, tax, taxa, level, q, looks, far) -> bytes:
    """The gzipped first lists (see the module doc), as `build()` in identify_app.js orders them:
    best score bucket first, newest id first within one, PER_SPECIES of a taxon unless the level
    holds one taxon only. `far` per record is far outside its label's range, None without ranges."""
    meta = map_meta(site, keys=("shards", "groups", "bbox"))
    grp = np.concatenate(
        [
            _decode_shard(gzip.decompress((site / s["file"].split("?")[0]).read_bytes()), s["n"])[
                "group"
            ]
            for s in meta["shards"]
        ]
    )
    on = (level > 0) & (grp < len(meta["groups"]))  # no group fails every group chip
    if far is not None:
        on &= (level != 1) | ~far
    shows = np.isin(level, (TAXONOMIST, NARROW, MISLABEL)) & pd.notna(looks)
    tx, nm, out = {}, {}, {}
    states = {"": on} | {
        "groups=" + quote(g, safe="!*'()"): on & (grp == k) for k, g in enumerate(meta["groups"])
    }
    for key, keep in states.items():
        st = out[key] = {"total": [0], "n": [0], "rows": [[]]}
        for lv in range(1, 6):
            i = np.flatnonzero(keep & (level == lv))
            i = i[np.lexsort((-ids[i], -q[i].astype(np.int64)))]
            _, inv, cnt = np.unique(tax[i], return_inverse=True, return_counts=True)
            cut = len(i) if len(cnt) == 1 else PER_SPECIES
            by = np.argsort(inv, kind="stable")
            rank = np.empty(len(i), np.int64)
            rank[by] = np.arange(len(i)) - np.r_[0, np.cumsum(cnt)[:-1]][inv[by]]
            left = np.maximum(np.where(rank == 0, cnt[inv] - cut, 0), 0)
            i, left = i[rank < cut], left[rank < cut]
            st["total"].append(len(rank))
            st["n"].append(len(i))
            st["rows"].append(
                [
                    [
                        int(ids[r]),
                        NOTAX if tax[r] == NOTAX else tx.setdefault(int(tax[r]), len(tx)),
                        nm.setdefault(str(looks[r]), len(nm)) if shows[r] else NO_LOOK,
                        int(m),
                    ]
                    for r, m in zip(i[:FIRST_ROWS], left[:FIRST_ROWS], strict=True)
                ]
            )
    head = {"bbox": meta["bbox"], "taxa": [taxa[t][:3] for t in tx], "looks": list(nm), "s": out}
    return gzip.compress(json.dumps(head, separators=(",", ":")).encode(), mtime=0)


def scoring_dates(manifest: dict) -> dict:
    """{"photos", "scored"} as YYYY-MM-DD (or None) from the atlas manifest, for the About."""
    entry = manifest.get("identify", {})
    source = entry.get("emb") or manifest.get("model", {}).get("source", "")
    photos = re.search(r"\d{4}-\d{2}-\d{2}", str(source))
    scored = str(entry.get("built_at", ""))[:10]
    return {
        "photos": photos.group() if photos else None,
        "scored": scored if re.fullmatch(r"\d{4}-\d{2}-\d{2}", scored) else None,
    }


def range_planes(ids: np.ndarray, hit: np.ndarray, notes: pd.DataFrame) -> tuple:
    """(km, note) per site record from range-notes.parquet by id; unknown and None where the
    record has no current level (missing, or its label changed since it was scored)."""
    notes = notes.drop_duplicates("id").set_index("id")
    j = np.where(hit, notes.index.get_indexer(ids), -1)
    km = np.full(len(ids), np.nan)
    note = np.full(len(ids), None, dtype=object)
    km[j >= 0] = notes["out_km"].astype("Float64").to_numpy(np.float64, na_value=np.nan)[j[j >= 0]]
    note[j >= 0] = notes["range_note"].astype(object).to_numpy()[j[j >= 0]]
    return km, note


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.pool_levels", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory holding map.html")
    p.add_argument("--data-url", help="atlas base URL holding manifest.json and identify.parquet")
    p.add_argument("--parquet", type=Path, help="read this local identify.parquet instead")
    p.add_argument("--ranges", type=Path, help="with --parquet: dir of `level_ranges` output")
    a = p.parse_args(argv)
    try:
        counts = build(a.out, a.data_url, a.parquet, a.ranges)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"pool_levels: {exc}", file=sys.stderr)
        return 1
    paths = [site_files.path(a.out, k) for k in ("levels", "looks", "range", "first")]
    sizes = ", ".join(f"{p.name} {p.stat().st_size / 1e6:.2f} MB" for p in paths if p)
    print(f"pool_levels: records per level {counts}; {sizes} gzipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
