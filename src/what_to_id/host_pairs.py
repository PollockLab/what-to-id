"""Parasite, pathogen, epiphyte and host family pairs from GloBI, for the look-alike stats.

A smut photographed on its grass, a rust on its rose, a gall on its oak or a mistletoe on its pine
shares the photo with its host, so BioCLIP puts the two side by side although neither looks like
the other. page_lookalike skips such neighbour pairs. This module lifts the Global Biotic
Interactions (GloBI) dump to unordered family pairs:

    python -m what_to_id.host_pairs --site SITE_DIR [--dump PATH_OR_URL] \\
        --out src/what_to_id/lookalike_assets/host_pairs.tsv

It keeps only the interaction types in TYPES, only pairs of two site families (pool-taxa.bin) in
different phyla, and only pairs with at least MIN_ROWS GloBI rows. Within a phylum the GloBI rows
are mostly parasitoids reared from their hosts and genuine look-alikes (polypores, jelly fungi,
cuckoo bees), so flagging them would hide real confusions. lookalike_assets/host_pairs_extra.tsv
adds by hand the few same-phylum pairs that are photographed together, each with its reason.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from what_to_id.inat import USER_AGENT
from what_to_id.tree_page import map_meta

DUMP = "https://depot.globalbioticinteractions.org/snapshot/target/data/tsv/interactions.tsv.gz"
ASSETS = Path(__file__).parent / "lookalike_assets"
PAIR_FILES = (ASSETS / "host_pairs.tsv", ASSETS / "host_pairs_extra.tsv")
COLUMNS = ("family_a", "family_b", "types", "globi_rows", "source")
# Living on or in the other, so photographed with it. Not eats, visits, pollinates or mycorrhiza.
TYPES = frozenset(
    [
        "parasiteOf",
        "hasParasite",
        "endoparasiteOf",
        "hasEndoparasite",
        "ectoparasiteOf",
        "hasEctoparasite",
        "parasitoidOf",
        "hasParasitoid",
        "hostOf",
        "hasHost",
        "pathogenOf",
        "hasPathogen",
        "rootparasiteOf",
        "hemiparasiteOf",
        "epiphyteOf",
        "hasEpiphyte",
        "kleptoparasiteOf",
    ]
)
# Every kept type holds one of these, so most of the dump is skipped before it is split.
_HINTS = (b"arasit", b"ostOf", b"asHost", b"athogen", b"piphyte")
MIN_ROWS = 2
_FIELDS = ("sourceTaxonFamilyName", "interactionTypeName", "targetTaxonFamilyName")
_REFS = ("referenceDoi", "sourceCitation")


def site_taxa(site: Path) -> tuple[dict, list[list]]:
    """The META ranks, taxa and shards of the site built in ``site``, and its pool-taxa.bin rows."""
    meta = map_meta(site, keys=("ranks", "taxa", "shards"))
    rows = json.loads(gzip.decompress((site / meta["taxa"].split("?")[0]).read_bytes()))
    return meta, rows


def family_phyla(ranks: list[str], rows: list[list]) -> dict[str, int]:
    """Each site family's phylum row in ``rows``, -1 when it has none."""
    fam = ranks.index("family") if "family" in ranks else -1
    phy = ranks.index("phylum") if "phylum" in ranks else -1
    out = {}
    for r in rows:
        if r[3] == fam:
            up = r[4]
            while up is not None and up >= 0 and rows[up][3] != phy:
                up = rows[up][4]
            out[r[0]] = up if up is not None else -1
    return out


def lift(lines, phyla: dict[str, int], min_rows: int = MIN_ROWS) -> dict[tuple[str, str], dict]:
    """Unordered cross-phylum pairs of the families in ``phyla`` from GloBI tsv ``lines``."""
    header = next(lines).rstrip(b"\r\n").split(b"\t")
    try:
        cols = [header.index(name.encode()) for name in _FIELDS + _REFS]
    except ValueError as exc:
        raise ValueError(f"GloBI header lacks a column: {exc}") from None
    width = max(cols) + 1
    pairs: dict[tuple[str, str], dict] = {}
    for line in lines:
        if not any(h in line for h in _HINTS):
            continue
        f = line.rstrip(b"\r\n").decode("utf-8", "replace").split("\t")
        if len(f) < width or f[cols[1]] not in TYPES:
            continue
        a, b = f[cols[0]], f[cols[2]]
        if a not in phyla or b not in phyla or phyla[a] == phyla[b]:
            continue
        key = (a, b) if a < b else (b, a)
        p = pairs.setdefault(key, {"types": set(), "rows": 0, "refs": Counter()})
        p["types"].add(f[cols[1]])
        p["rows"] += 1
        ref = f[cols[3]] or f[cols[4]]
        if ref:
            p["refs"][ref] += 1
    return {
        k: {
            "types": ",".join(sorted(p["types"])),
            "rows": p["rows"],
            "source": p["refs"].most_common(1)[0][0] if p["refs"] else "",
        }
        for k, p in sorted(pairs.items())
        if p["rows"] >= min_rows
    }


def _clean(text: str) -> str:
    return " ".join(text.split())[:120]


def write(path: Path, pairs: dict, header: list[str]) -> None:
    lines = [f"# {h}" for h in header] + ["\t".join(COLUMNS)]
    for (a, b), p in pairs.items():
        lines.append("\t".join([a, b, p["types"], str(p["rows"]), _clean(p["source"])]))
    path.write_text("\n".join(lines) + "\n")


def load(paths=PAIR_FILES) -> dict[tuple[str, str], dict]:
    """The flagged pairs of every file in ``paths``; later files add to earlier ones."""
    out: dict[tuple[str, str], dict] = {}
    for path in paths:
        rows = [ln for ln in Path(path).read_text().splitlines() if ln and not ln.startswith("#")]
        if not rows or tuple(rows[0].split("\t")) != COLUMNS:
            raise ValueError(f"{path} must start with the columns {', '.join(COLUMNS)}")
        for ln in rows[1:]:
            f = ln.split("\t")
            if len(f) != len(COLUMNS) or not f[0] or not f[1] or f[0] == f[1]:
                raise ValueError(f"{path}: bad row {ln!r}")
            key = tuple(sorted(f[:2]))
            out[key] = {"types": f[2], "rows": int(f[3]), "source": f[4]}
    return out


def _open(dump: str):
    """The decompressed dump as a byte stream, and the snapshot day (Last-Modified or mtime)."""
    if dump.startswith(("http://", "https://")):
        req = urllib.request.Request(dump, headers={"User-Agent": USER_AGENT})
        resp = urllib.request.urlopen(req, timeout=120)
        stamp = parsedate_to_datetime(resp.headers["Last-Modified"])
        return gzip.GzipFile(fileobj=resp), stamp.date().isoformat()
    stamp = datetime.fromtimestamp(Path(dump).stat().st_mtime, UTC)
    return gzip.open(dump, "rb"), stamp.date().isoformat()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.host_pairs", description=__doc__)
    p.add_argument("--site", type=Path, required=True, help="built site holding map.html")
    p.add_argument("--dump", default=DUMP, help="GloBI interactions.tsv.gz, a path or URL")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--min-rows", type=int, default=MIN_ROWS)
    a = p.parse_args(argv)
    meta, rows = site_taxa(a.site)
    phyla = family_phyla(meta["ranks"], rows)
    stream, day = _open(a.dump)
    with stream:
        pairs = lift(iter(stream), phyla, a.min_rows)
    write(
        a.out,
        pairs,
        [
            f"Generated from the GloBI interactions dump of {day} ({a.dump}); do not edit.",
            "Regenerate: python -m what_to_id.host_pairs --site SITE_DIR --out "
            "src/what_to_id/lookalike_assets/host_pairs.tsv",
            f"Kept: {', '.join(sorted(TYPES))}; families of the site's taxa in different "
            f"phyla; at least {a.min_rows} GloBI rows per pair.",
        ],
    )
    print(f"host_pairs: {len(pairs)} family pairs from {len(phyla)} site families to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
