"""Per-record look-alike stats for the photo-space page, from the atlas's BioCLIP 12-NN.

    python -m what_to_id.page_lookalike --out SITE_DIR --data-url URL [--parts DIR]

The site directory holds the built map (map.html, its pool shards and pool-taxa.bin). The
neighbours are the atlas neighbour sets in high-dimensional BioCLIP space, never the 2D layout:
the manifest and parts come from ``--parts`` where present there, else from ``--data-url``, and
later sets override earlier ones per id (atlas_neighbors.merge_neighbors).

It writes pool-lookalike.bin: gzip of two planes of n bytes, records in the order of META.shards.
Plane A holds class agreement in the low nibble and order agreement in the high one, plane B family
agreement low and the look-alike level + 2 high. Agreement at a rank is the share of the record's
neighbours, among those in the site with a known ancestor there, that share its ancestor, in
twelfths (half up). The look-alike is the first neighbour in cosine order with another known
taxon, skipping pairs photographed together (host_pairs.load); its level is the rank of their
lowest common ancestor: 0 same family, 1 order, 2 class, 3 phylum, 4 kingdom, 5 other kingdom,
-1 undecidable, -2 no such neighbour. UNKNOWN (15) marks a nibble with nothing to say.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import NamedTuple

import numpy as np

from what_to_id import host_pairs
from what_to_id.atlas_index_io import read_manifest
from what_to_id.atlas_neighbors import merge_neighbors, record_dtype
from what_to_id.inat import USER_AGENT
from what_to_id.page_map import _decode_shard

OUT_NAME = "pool-lookalike.bin"
RANKS = ("kingdom", "phylum", "class", "order", "family")
KINGDOM, PHYLUM, CLASS, ORDER, FAMILY = range(5)
UNKNOWN = 15
NONE, UNDECIDABLE = -2, -1
LEVELS = {
    -2: "no look-alike",
    -1: "undecidable",
    0: "same family",
    1: "same order",
    2: "same class",
    3: "same phylum",
    4: "same kingdom",
    5: "other kingdom",
}


# ---- inputs -----------------------------------------------------------------------------
def site_records(site: Path) -> tuple[np.ndarray, np.ndarray, list[list], list[str]]:
    """Record ids and taxon rows in META.shards order, the taxa rows and META.ranks."""
    meta, rows = host_pairs.site_taxa(site)
    ids, tax = [], []
    for s in meta["shards"]:
        cols = _decode_shard(gzip.decompress((site / s["file"].split("?")[0]).read_bytes()), s["n"])
        ids.append(cols["id"].astype(np.int64))
        tax.append(cols["taxon"].astype(np.int64))
    return np.concatenate(ids), np.concatenate(tax), rows, meta["ranks"]


def ancestors(rows: list[list], ranks: list[str]) -> np.ndarray:
    """``(len(rows), 5)`` row of each taxon's kingdom .. family ancestor (itself included), -1."""
    n = len(rows)
    parent = np.array([r[4] if len(r) > 4 else -1 for r in rows] + [-1], dtype=np.int64)
    rank_of = {name: i for i, name in enumerate(ranks)}
    want = np.full(256, -1, dtype=np.int64)
    for k, name in enumerate(RANKS):
        if name in rank_of:
            want[rank_of[name]] = k
    rank = np.array([want[min(r[3], 255)] for r in rows] + [-1], dtype=np.int64)
    out = np.full((n, len(RANKS)), -1, dtype=np.int64)
    cur = np.arange(n)
    for _ in range(n + 1):
        live = cur >= 0
        if not live.any():
            break
        k = rank[np.where(live, cur, n)]
        hit = live & (k >= 0)
        out[hit, k[hit]] = np.where(out[hit, k[hit]] < 0, cur[hit], out[hit, k[hit]])
        cur = np.where(live, parent[np.where(live, cur, n)], -1)
    return out


def _fetch(url: str, path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as f:
        shutil.copyfileobj(resp, f, 1 << 20)


def load_neighbors(work: Path, data_url: str | None, parts: Path | None) -> np.ndarray:
    """Every neighbour set of the atlas merged into one record array, newest record per id."""
    if data_url is None and parts is None:
        raise ValueError("give --data-url, --parts or both")
    base = data_url.rstrip("/") + "/" if data_url else None
    local = parts / "manifest.json" if parts else None
    if local is not None and local.exists():
        shutil.copy(local, work / "manifest.json")
    elif base:
        _fetch(base + "manifest.json", work / "manifest.json")
    else:
        raise FileNotFoundError(f"no manifest.json in {parts} and no --data-url")
    entries = read_manifest(work).get("neighbors", [])
    if not entries:
        raise ValueError("the atlas manifest lists no neighbour sets")
    for e in entries:
        name = f"{e['name']}.bin"
        size = e["count"] * record_dtype(e.get("k", 12)).itemsize
        mine = parts / name if parts else None
        if mine is not None and mine.exists() and mine.stat().st_size == size:
            (work / name).symlink_to(mine.resolve())
        elif base:
            _fetch(base + name, work / name)
        else:
            raise FileNotFoundError(f"{mine} is missing or not {size} bytes, and no --data-url")
        if (work / name).stat().st_size != size:
            raise ValueError(f"{name} holds {(work / name).stat().st_size} bytes, expected {size}")
    entry = merge_neighbors(work, name="neighbors")
    return np.fromfile(work / "neighbors.bin", dtype=record_dtype(entry["k"]))


def neighbor_rows(ids: np.ndarray, rec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each record's neighbours as positions in ``ids`` (-1 outside the site), and coverage."""
    order = np.argsort(ids, kind="stable")
    sid = ids[order]

    def pos(q):
        k = np.clip(np.searchsorted(sid, q), 0, len(sid) - 1)
        return np.where(sid[k] == q, order[k], -1)

    src = pos(rec["id"].astype(np.int64))
    ok = src >= 0
    nb = np.full((len(ids), rec["nb"].shape[1]), -1, dtype=np.int64)
    nb[src[ok]] = pos(rec["nb"][ok].astype(np.int64).ravel()).reshape(-1, rec["nb"].shape[1])
    covered = np.zeros(len(ids), dtype=bool)
    covered[src[ok]] = True
    return nb, covered


# ---- stats ------------------------------------------------------------------------------
def _at(values: np.ndarray, nb: np.ndarray) -> np.ndarray:
    return np.where(nb >= 0, values[np.maximum(nb, 0)], -1)


def agreement(anc: np.ndarray, nb: np.ndarray, covered: np.ndarray) -> np.ndarray:
    """``(n, 3)`` class, order and family agreement in twelfths, UNKNOWN where undefined."""
    out = np.full((len(nb), 3), UNKNOWN, dtype=np.uint8)
    for c, r in enumerate((CLASS, ORDER, FAMILY)):
        mine, theirs = anc[:, r], _at(anc[:, r], nb)
        known = theirs >= 0
        cnt = known.sum(1)
        same = (known & (theirs == mine[:, None])).sum(1)
        twelfths = np.floor(12 * same / np.maximum(cnt, 1) + 0.5).astype(np.uint8)
        out[:, c] = np.where(covered & (mine >= 0) & (cnt > 0), twelfths, UNKNOWN)
    return out


def lca_level(anc: np.ndarray, other: np.ndarray) -> np.ndarray:
    """LCA level of each record and ``other`` (positions, same shape as a column of anc)."""
    lev = np.full(other.shape, UNDECIDABLE, dtype=np.int8)
    done = np.zeros(other.shape, dtype=bool)
    for d in range(len(RANKS)):
        a = anc[:, d].reshape((-1,) + (1,) * (other.ndim - 1))
        b = _at(anc[:, d], other)
        unk = (a < 0) | (b < 0)
        diff = ~unk & (a != b)
        lev[~done & diff] = len(RANKS) - d
        done |= diff | unk
    lev[~done] = 0
    return lev


def lookalike(lev: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    """The level of each record's first ``candidate`` neighbour, NONE when there is none."""
    first = np.argmax(candidate, 1)
    out = lev[np.arange(len(lev)), first]
    return np.where(candidate.any(1), out, NONE).astype(np.int8)


def together_flags(fam: np.ndarray, nb: np.ndarray, pairs: dict, rows: list[list], ranks) -> tuple:
    """``(n, k)`` True where record and neighbour are a flagged family pair, and the pair keys."""
    at = ranks.index("family") if "family" in ranks else -1
    by_name: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if r[3] == at:
            by_name.setdefault(r[0], []).append(i)
    big = len(rows)
    keys = {
        min(x, y) * big + max(x, y): pair
        for pair in pairs
        for x in by_name.get(pair[0], [])
        for y in by_name.get(pair[1], [])
    }
    mine, theirs = fam[:, None], _at(fam, nb)
    key = np.minimum(mine, theirs) * big + np.maximum(mine, theirs)
    cross = (mine >= 0) & (theirs >= 0) & (mine != theirs)
    flag = cross & np.isin(key, np.fromiter(keys, dtype=np.int64, count=len(keys)))
    return flag, cross, key, keys


def pack(agree: np.ndarray, level: np.ndarray, known: np.ndarray) -> bytes:
    """The gzipped two-plane file: class|order<<4, then family|(level+2)<<4."""
    hi = np.where(known, level.astype(np.int16) + 2, UNKNOWN).astype(np.uint8)
    plane_a = agree[:, 0] | (agree[:, 1] << 4)
    plane_b = agree[:, 2] | (hi << 4)
    return gzip.compress(plane_a.tobytes() + plane_b.tobytes(), mtime=0)


def unpack(blob: bytes) -> dict[str, np.ndarray]:
    """Read pool-lookalike.bin back: agreement in twelfths and look-alike level, UNKNOWN as 15."""
    raw = np.frombuffer(gzip.decompress(blob), dtype=np.uint8)
    a, b = raw[: len(raw) // 2], raw[len(raw) // 2 :]
    hi = (b >> 4).astype(np.int8)
    return {
        "class": a & 15,
        "order": a >> 4,
        "family": b & 15,
        "level": np.where(hi == UNKNOWN, UNKNOWN, hi - 2).astype(np.int8),
    }


# ---- build ------------------------------------------------------------------------------
def build(
    site: str | Path,
    *,
    data_url: str | None = None,
    parts: str | Path | None = None,
    pair_files=host_pairs.PAIR_FILES,
) -> dict:
    """Write ``site/pool-lookalike.bin`` and return the summary stats."""
    site = Path(site)
    ids, tax, rows, ranks = site_records(site)
    taxon_anc = ancestors(rows, ranks)
    tax = np.where(tax < len(rows), tax, -1)
    anc = np.where(tax[:, None] >= 0, taxon_anc[np.maximum(tax, 0)], -1)
    with tempfile.TemporaryDirectory(prefix="lookalike-") as work:
        rec = load_neighbors(Path(work), data_url, Path(parts) if parts else None)
    nb, covered = neighbor_rows(ids, rec)
    del rec
    agree = agreement(anc, nb, covered)
    pairs = host_pairs.load(pair_files)
    flag, cross, key, keys = together_flags(anc[:, FAMILY], nb, pairs, rows, ranks)
    edge_lev = lca_level(anc, nb)
    tnb = _at(tax, nb)
    candidate = (tnb >= 0) & (tnb != tax[:, None])
    before = lookalike(edge_lev, candidate)
    after = lookalike(edge_lev, candidate & ~flag)
    known = covered & (tax >= 0)
    (site / OUT_NAME).write_bytes(pack(agree, after, known))
    names = [r[0] for r in rows]
    edges = Edges(nb, edge_lev, flag, cross, key)
    return summarize(names, anc, edges, covered, known, before, after, keys, pairs)


class Edges(NamedTuple):
    """Per record and neighbour: position, LCA level, together flag, cross-family, pair key."""

    nb: np.ndarray
    level: np.ndarray
    flag: np.ndarray
    cross: np.ndarray
    key: np.ndarray


def _pair_counts(pair_key: np.ndarray, label, limit: int = 10) -> list[tuple]:
    uk, cnt = np.unique(pair_key, return_counts=True)
    top = np.argsort(-cnt, kind="stable")[:limit]
    return [(label(int(uk[t])), int(cnt[t])) for t in top]


def summarize(names, anc, e: Edges, covered, known, before, after, keys, pairs) -> dict:
    """Build summary: together-filter effect, look-alike levels, top cross-phylum class pairs."""
    big = len(names)

    def dist(lev):
        lev = lev[known]
        decided = max(int((lev >= 0).sum()), 1)
        out = {}
        for k, label in LEVELS.items():
            c = int((lev == k).sum())
            out[label] = f"{c} ({c / decided:.1%} of decided)" if k >= 0 else c
        return out

    def family_pair(k):
        p = pairs[keys[k]]
        where = f"GloBI rows {p['rows']}" if p["rows"] else f"hand: {p['source']}"
        return f"{' ~ '.join(sorted((names[k // big], names[k % big])))} [{p['types']}; {where}]"

    def clade(r):  # class, else phylum, else kingdom
        a = anc[r]
        return np.where(
            a[:, CLASS] >= 0,
            a[:, CLASS],
            np.where(a[:, PHYLUM] >= 0, a[:, PHYLUM], a[:, KINGDOM]),
        )

    def clade_pairs(mask):
        ci = clade(np.broadcast_to(np.arange(len(e.nb))[:, None], e.nb.shape)[mask])
        cj = clade(e.nb[mask])
        return _pair_counts(
            np.minimum(ci, cj) * big + np.maximum(ci, cj),
            lambda k: f"{names[k // big]} ~ {names[k % big]}",
        )

    far = (e.level >= 4) & (e.nb >= 0)
    flag, cross = e.flag, e.cross
    return {
        "records": int(len(known)),
        "with_neighbors": int(covered.sum()),
        "edges_dropped": int(flag.sum()),
        "cross_family_edges": int(cross.sum()),
        "dropped_share": round(float(flag.sum() / max(cross.sum(), 1)), 4),
        "flagged_pairs_in_file": len(pairs),
        "records_changed": int((known & (before != after)).sum()),
        "level_before": dist(before),
        "level_after": dist(after),
        "top_flagged_pairs": _pair_counts(e.key[flag], family_pair),
        "cross_phylum_class_pairs_before": clade_pairs(far),
        "cross_phylum_class_pairs_after": clade_pairs(far & ~flag),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_lookalike", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory holding map.html")
    p.add_argument("--data-url", help="atlas base URL holding manifest.json and the neighbour sets")
    p.add_argument("--parts", type=Path, help="local directory of neighbour sets to use first")
    a = p.parse_args(argv)
    try:
        stats = build(a.out, data_url=a.data_url, parts=a.parts)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"page_lookalike: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(stats, indent=1))
    print(f"page_lookalike: wrote {a.out / OUT_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
