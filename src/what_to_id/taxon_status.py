"""Conservation status and establishment means for each pool taxon, a sidecar for the read-back.

The table (state/taxon_status.parquet) has one row per taxon id, joined from served.id through
pool.taxon_id: taxon_id, lookup_date (YYYY-MM-DD of the fetch), natureserve_bc_srank,
natureserve_n_rank, sara_status, establishment_means and geoprivacy. A value iNaturalist does not
give is null. geoprivacy is that of the BC NatureServe row, else any BC row, else the SARA row,
and the most restrictive one when a taxon has several.

``update_status`` asks iNaturalist only for taxa the table lacks, and never asks again: the first
lookup stands for the whole study, so a rank changed later does not move the analysis. The table
holds no list or arm name. The list endpoint (/taxa?id=) returns one status per taxon, not all, so
this reads /taxa/<id,id,...> (preferred_place_id=BC), which iNaturalist caps at MAX_IDS ids.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from what_to_id.inat import SLEEP, TIMEOUT, make_session
from what_to_id.taxonomy import TAXA_API

PER_REQUEST = 30  # the path endpoint answers 422 "Too many IDs" above this
BC, CANADA = 7085, 6712  # iNaturalist place ids, checked against a live response
COLUMNS = [
    "taxon_id",
    "lookup_date",
    "natureserve_bc_srank",
    "natureserve_n_rank",
    "sara_status",
    "establishment_means",
    "geoprivacy",
]
_RESTRICTIVENESS = {"open": 0, "obscured": 1, "private": 2}

log = logging.getLogger("what_to_id")


def _rows(statuses: list[dict], authority_ok, place_id=None) -> list[dict]:
    return [
        c
        for c in statuses
        if authority_ok(c.get("authority") or "")
        and (place_id is None or (c.get("place") or {}).get("id") == place_id)
    ]


def _first(rows: list[dict]) -> str | None:
    return next((r["status"] for r in rows if r.get("status")), None)


def _geoprivacy(*groups: list[dict]) -> str | None:
    for rows in groups:
        found = [r["geoprivacy"] for r in rows if r.get("geoprivacy")]
        if found:
            return max(found, key=lambda g: _RESTRICTIVENESS.get(g, 0))
    return None


def fetch_status(ids: Iterable[int], *, session=None) -> dict[int, dict]:
    """The status fields for each of at most PER_REQUEST ids iNaturalist knows."""
    ids = sorted({int(i) for i in ids})
    if len(ids) > PER_REQUEST:
        raise ValueError(f"at most {PER_REQUEST} ids a request, got {len(ids)}")
    session = session or make_session()
    url = f"{TAXA_API}/{','.join(map(str, ids))}"
    r = session.get(url, params={"preferred_place_id": BC}, timeout=TIMEOUT)
    r.raise_for_status()
    out: dict[int, dict] = {}
    for t in r.json()["results"]:
        cs = t.get("conservation_statuses") or []
        ns = _rows(cs, lambda a: a == "NatureServe", BC)
        # observed authority string: "Canadian Species at Risk Act"
        sara = _rows(cs, lambda a: "Species at Risk Act" in a or "SARA" in a)
        bc_any = _rows(cs, lambda a: True, BC)
        means = (t.get("establishment_means") or {}).get("establishment_means")
        out[int(t["id"])] = {
            "natureserve_bc_srank": _first(ns),
            "natureserve_n_rank": _first(_rows(cs, lambda a: a == "NatureServe", CANADA)),
            "sara_status": _first(sara),
            "establishment_means": means or None,
            "geoprivacy": _geoprivacy(ns, bc_any, sara),
        }
    return out


def update_status(
    path: Path | str,
    taxon_ids: Iterable[int],
    *,
    session=None,
    sleep: float = SLEEP,
    today: str | None = None,
) -> int:
    """Add the taxa in ``taxon_ids`` the table at ``path`` lacks. Returns how many it added.

    The table is written even when a request fails midway, so the next run asks only for the rest.
    """
    path = Path(path)
    old = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=COLUMNS)
    need = sorted({int(i) for i in taxon_ids} - set(old["taxon_id"].astype(int)))
    today = today or datetime.now(UTC).date().isoformat()
    session = session or make_session()
    new: list[dict] = []
    try:
        for start in range(0, len(need), PER_REQUEST):
            if sleep and start:
                time.sleep(sleep)
            got = fetch_status(need[start : start + PER_REQUEST], session=session)
            new += [{"taxon_id": k, "lookup_date": today, **v} for k, v in got.items()]
    finally:
        if new or not path.exists():
            table = pd.concat([old, pd.DataFrame(new, columns=COLUMNS)], ignore_index=True)
            table = table.astype({"taxon_id": "int64"}).sort_values("taxon_id")
            tmp = path.with_name(path.name + ".tmp")
            table[COLUMNS].to_parquet(tmp, index=False)
            tmp.replace(path)
    return len(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fill the taxon status table for a pool's taxa.")
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="parquet, created if missing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ids = pd.read_parquet(a.pool, columns=["taxon_id"])["taxon_id"].dropna().astype(int).unique()
    added = update_status(a.out, ids)
    log.info("taxon status: %d new of %d pool taxa", added, len(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
