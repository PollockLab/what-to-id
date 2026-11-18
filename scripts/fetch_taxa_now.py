"""The taxon now, for records that left a pool: the follow-up of levels_outcome.py's secondary
outcome and narrow_temp.py. Read-only GETs of the iNaturalist API (`inat.fetch_by_ids`, with its
retries and pause between pages); nothing is posted.

    PYTHONPATH=src python scripts/fetch_taxa_now.py --before pool-A.parquet \\
        --after pool-B.parquet [--after pool-C.parquet ...] [--only scores.parquet] \\
        --out now.parquet

The ids are those of `--before` missing from any `--after` pool (those that left by then, even if
back in a later one), narrowed to the ids of `--only` when given. The output has one row per
observation the API returned: id, user_id, taxon_id, taxon_name, quality_grade and `fetched_on`.
A record the API no longer returns (deleted, hidden) has no row. The taxon is the one on
`fetched_on`, not on the day a pool was taken.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from what_to_id.inat import fetch_by_ids


def left_ids(before: Path, after: list[Path], only: Path | None = None) -> list[int]:
    ids = set(pd.read_parquet(before, columns=["id"])["id"])
    gone: set[int] = set()
    for p in after:
        gone |= ids - set(pd.read_parquet(p, columns=["id"])["id"])
    ids = gone
    if only:
        ids &= set(pd.read_parquet(only, columns=["id"])["id"])
    return sorted(int(i) for i in ids)


def frame(obs: list[dict], fetched_on: str) -> pd.DataFrame:
    rows = [
        {
            "id": int(o["id"]),
            "user_id": (o.get("user") or {}).get("id"),
            "taxon_id": (o.get("taxon") or {}).get("id"),
            "taxon_name": (o.get("taxon") or {}).get("name"),
            "quality_grade": o.get("quality_grade"),
            "fetched_on": fetched_on,
        }
        for o in obs
    ]
    cols = ["id", "user_id", "taxon_id", "taxon_name", "quality_grade", "fetched_on"]
    return pd.DataFrame(rows, columns=cols).astype({"user_id": "Int64", "taxon_id": "Int64"})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, action="append", required=True)
    ap.add_argument("--only", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, help="fetch only the first N ids (a dry run)")
    a = ap.parse_args(argv)
    ids = left_ids(a.before, a.after, a.only)[: a.limit]
    print(f"{len(ids):,} ids to fetch")
    obs = fetch_by_ids(ids)
    out = frame(obs, datetime.now(UTC).date().isoformat())
    out.to_parquet(a.out, index=False)
    print(f"{len(out):,} observations returned, {len(ids) - len(out):,} not")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
