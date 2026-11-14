"""One row of Food web progress, appended to a CSV: how many BC observations carry iNaturalist's
Eating or Eaten by field, and how many name the other animal.

    PYTHONPATH=src python scripts/foodweb_progress.py --out foodweb-progress.csv

Reads the same public queries as what_to_id.foodweb_obs (place BC, field Eating, field Eaten by).
Columns: date, n_obs (observations with a field), n_named_species (the field names a species),
n_coarse (the field names a genus or higher), n_green_edges (distinct predator and prey species
pairs that observations name to species on both sides; not checked against the metaweb).
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from what_to_id import foodweb_obs

COLUMNS = ("date", "n_obs", "n_named_species", "n_coarse", "n_green_edges")


def row(obs: list[dict], today: str) -> dict:
    def pair(o: dict) -> tuple[str, str] | None:
        if "f" not in o or " " not in o["f"][0] or " " not in o["t"][0]:
            return None
        return (o["t"][0], o["f"][0]) if o["k"] == "eating" else (o["f"][0], o["t"][0])

    named = [o for o in obs if "f" in o]
    species = sum(" " in o["f"][0] for o in named)
    return {
        "date": today,
        "n_obs": len(obs),
        "n_named_species": species,
        "n_coarse": len(named) - species,
        "n_green_edges": len({p for p in map(pair, obs) if p}),
    }


def append(path: Path, r: dict) -> None:
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        if new:
            w.writeheader()
        w.writerow(r)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    obs = foodweb_obs.fetch("eating", pause=0) + foodweb_obs.fetch("by", pause=0)
    r = row(obs, date.today().isoformat())
    append(a.out, r)
    print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
