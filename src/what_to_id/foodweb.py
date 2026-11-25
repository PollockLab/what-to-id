"""Predator-prey pairs for BC from GloBI, as the small static file Identify's Food web filter reads.

    python -m what_to_id.foodweb --out SITE_DIR/foodweb.json

Reads GloBI's interaction API (eats and preysOn in a BC bounding box; GloBI returns each record
once per direction, so the inverse types add nothing) and writes
{"eats": {name: [[partner, records], ...]}, "eatenBy": {...}, "n": records}. Names are GloBI taxon
names, each record filed under its own two names only (a record labelled at genus stays at genus;
nothing is rolled up from species, but a subspecies or form is its species). Only animal-on-animal
pairs are kept (both paths name Animalia or Metazoa): GloBI's eats also holds grazing and fungus
eating. Every partner is kept, most records first.
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
PAGE = 4096


def _name(r: dict, side: str) -> str | None:
    """The taxon's own name: the last element of its path (GloBI's name can carry a common name)."""
    path = (r.get(f"{side}_taxon_path") or "").split(" | ")
    n = (path[-1] or r.get(f"{side}_taxon_name") or "").strip()
    return " ".join(n.split()[:2]) or None  # a subspecies or form (Feral Pigeon) is its species


def _animal(r: dict, side: str) -> bool:
    path = r.get(f"{side}_taxon_path") or ""
    return "Animalia" in path or "Metazoa" in path


def pairs(rows: list[dict]) -> dict:
    """The eats / eatenBy tables out of GloBI rows; skips other types and nameless rows."""
    eats: dict[str, Counter] = defaultdict(Counter)
    by: dict[str, Counter] = defaultdict(Counter)
    n = 0
    for r in rows:
        if r.get("interaction_type") not in TYPES:
            continue
        a, b = _name(r, "source"), _name(r, "target")
        if not a or not b or a == b or not (_animal(r, "source") and _animal(r, "target")):
            continue
        n += 1
        eats[a][b] += 1
        by[b][a] += 1

    def cut(t: dict[str, Counter]) -> dict:
        return {
            k: [[p, c] for p, c in sorted(v.items(), key=lambda x: (-x[1], x[0]))]
            for k, v in sorted(t.items())
        }

    return {"eats": cut(eats), "eatenBy": cut(by), "n": n}


def fetch(bbox: str = BC_BBOX, pause: float = 1.0) -> list[dict]:
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
        p += [("interactionType", t) for t in TYPES] + [("field", f) for f in fields]
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
    ap.add_argument("--rows", help="a saved GloBI JSON response instead of the API")
    a = ap.parse_args(argv)
    if a.rows:
        with open(a.rows) as f:
            rows = json.load(f)
    else:
        rows = fetch()
    t = pairs(rows)
    if not t["n"]:
        print("no predator-prey records read", file=sys.stderr)
        return 1
    with open(a.out, "w") as f:
        json.dump(t, f, separators=(",", ":"))
    print(f"{t['n']} records, {len(t['eats'])} predators, {len(t['eatenBy'])} prey -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
