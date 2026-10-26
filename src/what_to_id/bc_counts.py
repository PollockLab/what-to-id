"""Verifiable iNat observations per taxon over all of British Columbia, any quality grade.

`levels --bc-counts` reads this table so a look-alike's rarity is judged over everything an
identifier can meet, not over a pool that may hold only Needs ID records.

    python -m what_to_id.bc_counts --out bc-verifiable-counts.parquet
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import requests

from what_to_id.inat import BC_PLACE_ID, TIMEOUT, make_session

URL = "https://api.inaturalist.org/v1/observations/species_counts"
PER_PAGE = 500


def fetch_bc_counts(*, session: requests.Session | None = None, sleep: float = 1.0) -> pd.DataFrame:
    """`taxon_id, name, count` for every taxon with a verifiable BC record, one request a second."""
    session = session or make_session()
    rows: list[dict] = []
    page = 1
    while True:
        params = {"place_id": BC_PLACE_ID, "verifiable": "true", "per_page": PER_PAGE, "page": page}
        r = session.get(URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        body = r.json()
        rows += [
            {
                "taxon_id": int(x["taxon"]["id"]),
                "name": x["taxon"]["name"],
                "count": int(x["count"]),
            }
            for x in body["results"]
        ]
        if not body["results"] or len(rows) >= body["total_results"]:
            break
        page += 1
        time.sleep(sleep)
    return pd.DataFrame(rows, columns=["taxon_id", "name", "count"])


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    out = ap.parse_args(argv).out
    df = fetch_bc_counts()
    df.to_parquet(out, index=False)
    print(f"{len(df)} taxa -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
