"""Predator-prey pairs for BC from GloBI, as the small static file Identify's Food web filter reads.

    python -m what_to_id.foodweb --out SITE_DIR/foodweb.json

Reads GloBI's interaction API (eats and preysOn in a BC bounding box; GloBI returns each record
once per direction, so the inverse types add nothing) and writes
{"eats": {name: [[partner, records], ...]}, "eatenBy": {...}, "n": records}. Names are GloBI taxon
names, each record filed under its own two names only (a record labelled at genus stays at genus;
nothing is rolled up from species, but a subspecies or form is its species). Only animal-on-animal
pairs are kept (both paths name Animalia or Metazoa): GloBI's eats also holds grazing and fungus
eating. Every partner is kept, most records first.

`--kind pollination` reads pollinates and visitsFlowersOf instead and keeps animal-on-plant pairs,
writing pollination.json in the same shape: "eats" maps a pollinator to its plants, "eatenBy" a
plant to its pollinators. Each pair carries a third element, "pollinates" when any record says so,
else "visits" (only visitsFlowersOf), and the pollinates pairs sort before the visits ones. The
records count covers both types. GloBI's json.v2 rows hold no study citation for these types, so
sources cannot be counted.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict

API = "https://api.globalbioticinteractions.org/interaction"
BC_BBOX = "-139.06,48.30,-114.03,60.00"  # w,s,e,n around British Columbia
TYPES = ("eats", "preysOn")
FILE = "foodweb.json"  # beside identify.html; page_identify turns the filter on when it is there
POLLINATION = ("pollinates", "visitsFlowersOf")
POLLINATION_FILE = "pollination.json"
# GloBI paths name the plant kingdom as Plantae, Viridiplantae or only by a clade below it
PLANT = (
    "Plantae",
    "Viridiplantae",
    "Streptophyta",
    "Embryophyt",
    "Tracheophyt",
    "Spermatophyt",
    "Angiosperm",
)
PAGE = 4096


def _name(r: dict, side: str) -> str | None:
    """The taxon's own name: the last element of its path (GloBI's name can carry a common name)."""
    path = (r.get(f"{side}_taxon_path") or "").split(" | ")
    n = (path[-1] or r.get(f"{side}_taxon_name") or "").strip()
    return " ".join(n.split()[:2]) or None  # a subspecies or form (Feral Pigeon) is its species


def _animal(r: dict, side: str) -> bool:
    path = r.get(f"{side}_taxon_path") or ""
    return "Animalia" in path or "Metazoa" in path


def _plant(r: dict, side: str) -> bool:
    path = r.get(f"{side}_taxon_path") or ""
    return any(k in path for k in PLANT)


def pairs(rows: list[dict], kind: str = "predation") -> dict:
    """The eats / eatenBy tables out of GloBI rows; skips other types and nameless rows.
    Predation keeps animal-on-animal rows, pollination animal-on-plant rows."""
    types = POLLINATION if kind == "pollination" else TYPES
    eats: dict[str, Counter] = defaultdict(Counter)
    by: dict[str, Counter] = defaultdict(Counter)
    real: set[tuple[str, str]] = set()  # pollination pairs with a pollinates record
    n = 0
    for r in rows:
        if r.get("interaction_type") not in types:
            continue
        a, b = _name(r, "source"), _name(r, "target")
        if not a or not b or a == b or not _animal(r, "source"):
            continue
        if not (_plant(r, "target") if kind == "pollination" else _animal(r, "target")):
            continue
        n += 1
        eats[a][b] += 1
        by[b][a] += 1
        if r["interaction_type"] == "pollinates":
            real.add((a, b))

    def cut(t: dict[str, Counter], flip: bool = False) -> dict:
        if kind != "pollination":
            return {
                k: [[p, c] for p, c in sorted(v.items(), key=lambda x: (-x[1], x[0]))]
                for k, v in sorted(t.items())
            }
        out = {}
        for k, v in sorted(t.items()):
            rows = [[p, c, "pollinates" if ((p, k) if flip else (k, p)) in real else "visits"]
                    for p, c in v.items()]  # fmt: skip
            out[k] = sorted(rows, key=lambda x: (x[2] != "pollinates", -x[1], x[0]))
        return out

    return {"eats": cut(eats), "eatenBy": cut(by, True), "n": n}


def fetch(bbox: str = BC_BBOX, pause: float = 1.0, types: tuple = TYPES) -> list[dict]:
    import requests

    fields = [
        "interaction_type",
        "source_taxon_name",
        "source_taxon_path",
        "target_taxon_name",
        "target_taxon_path",
    ]
    rows, off = [], 0
    while True:
        p = [("bbox", bbox), ("type", "json.v2"), ("limit", PAGE), ("offset", off)]
        p += [("interactionType", t) for t in types] + [("field", f) for f in fields]
        r = requests.get(API, params=p, timeout=180)
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < PAGE:
            return rows
        off += PAGE
        time.sleep(pause)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--kind", choices=("predation", "pollination"), default="predation")
    ap.add_argument("--rows", help="a saved GloBI JSON response instead of the API")
    a = ap.parse_args(argv)
    if a.rows:
        with open(a.rows) as f:
            rows = json.load(f)
    else:
        rows = fetch(types=POLLINATION if a.kind == "pollination" else TYPES)
    t = pairs(rows, a.kind)
    if not t["n"]:
        print(f"no {a.kind} records read", file=sys.stderr)
        return 1
    with open(a.out, "w") as f:
        json.dump(t, f, separators=(",", ":"))
    print(f"{t['n']} records, {len(t['eats'])} predators, {len(t['eatenBy'])} prey -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
