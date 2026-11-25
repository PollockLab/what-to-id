"""The metaweb the Eating page reads: predator, prey and a probability per pair, in one swappable
file.

    python -m what_to_id.metaweb --foodweb foodweb.json --taxa TAXA --meta META --out OUT

{"source": text, "rule": text, "pairs": [[predator, prey, p], ...]}. Names are Latin names, at
species or a higher rank (a predator named at genus covers its species). A predicted food web in
this format replaces the file; nothing else changes. The stand-in builds it from GloBI's BC
pairs (foodweb.py): p = 1 - 0.5^records, so one record is 0.5 and each further one halves the
doubt, and a pair is dropped when a mollusc is the predator of a vertebrate: GloBI's eats holds
slugs on carcasses (Black Slug eats American Robin), which is scavenging, not predation. The
group of a name is its taxa-table ancestor that is an iconic group; a name the table lacks keeps
its pairs.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import json
import re
import sys
from pathlib import Path

VERTEBRATES = {"Actinopterygii", "Amphibia", "Aves", "Mammalia", "Reptilia"}
RULE = "p = 1 - 0.5^records; drop a mollusc predator of a vertebrate (scavenging)"
RULE_PLAIN = "p = 1 - 0.5^records"  # pollination: no scavenging to drop


def groups(taxa: list, group_ids: dict) -> dict[str, str]:
    """Group name by taxon name, from the taxa table rows."""
    # a group may be several taxa (Bryophytes and Algae are lists of phyla)
    by_id = {i: k for k, v in group_ids.items() for i in (v if isinstance(v, list) else [v])}
    out = {}
    for t in taxa:
        j, hops = t, 0
        while hops < 64:
            if j[2] in by_id:
                out[t[0]] = by_id[j[2]]
                break
            if j[4] is None or j[4] < 0:
                break
            j, hops = taxa[j[4]], hops + 1
    return out


def build(
    web: dict,
    group: dict[str, str] | None = None,
    taxa: list | None = None,
    ranks: list[str] | None = None,
    labels: dict[str, str] | None = None,
    scavenging: bool = True,
) -> dict:
    """The metaweb out of foodweb.py's tables; `group` maps a name to its iconic group and `taxa`
    (the taxa table rows) gives the names in the pairs their common names. `ranks` (the table's
    rank names) puts a rank on each ancestor and `labels` (iconic group taxon to its display name)
    lets the Eating picker open on the groups. `scavenging=False` keeps the mollusc pairs."""
    group = group or {}
    pairs = []
    for pred, preys in sorted(web["eats"].items()):
        for prey, n in preys:
            if scavenging and group.get(pred) == "Mollusca" and group.get(prey) in VERTEBRATES:
                continue
            pairs.append([pred, prey, round(1 - 0.5**n, 3)])
    named = {n for p in pairs for n in p[:2]}
    common = {t[0]: t[1] for t in taxa or [] if t[1] and t[0] in named}
    parent: dict[str, str] = {}  # each name's parent, for the ancestors of the names in the pairs
    at = {t[0]: i for i, t in enumerate(taxa or [])}
    for n in named:
        row = at.get(n)
        while row is not None and taxa[row][4] is not None and taxa[row][4] >= 0:
            up = taxa[taxa[row][4]][0]
            if taxa[row][0] in parent:
                break
            parent[taxa[row][0]] = up
            row = taxa[row][4]
    rank = {n: ranks[taxa[at[n]][3]] for n in {*parent, *parent.values()} if ranks and n in at}
    return {
        "source": "GloBI, British Columbia (stand-in)",
        "rule": RULE if scavenging else RULE_PLAIN,
        "pairs": pairs,
        "common": common,
        "parent": parent,
        "rank": rank,
        "groups": labels or {},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("foodweb", "taxa", "meta", "out"):
        ap.add_argument("--" + k, required=k in ("foodweb", "out"))
    ap.add_argument("--no-scavenging", action="store_true", help="keep every pair (pollination)")
    a = ap.parse_args(argv)
    web = json.loads(Path(a.foodweb).read_text())
    group, taxa = {}, None
    if a.taxa and a.meta:
        raw = Path(a.taxa).read_bytes()
        with contextlib.suppress(OSError):
            raw = gzip.decompress(raw)
        meta = json.loads(Path(a.meta).read_text())
        taxa = json.loads(raw)
        group = groups(taxa, meta["group_ids"])
    ranks = meta["ranks"] if taxa else None
    labels = (
        {k: re.sub(r" \(.*\)$", "", meta["names"].get(k, k)) for k in meta["group_ids"]}
        if taxa
        else None
    )
    m = build(web, group, taxa, ranks, labels, not a.no_scavenging)
    with open(a.out, "w") as f:
        json.dump(m, f, separators=(",", ":"))
    print(f"{len(m['pairs'])} pairs of {sum(len(v) for v in web['eats'].values())} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
