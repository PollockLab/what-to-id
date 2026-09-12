"""Pull the BC needs-ID pool from the iNaturalist API and read it back from parquet.

The pool is frozen by ``created_d2`` so a rerun with the same freeze date reproduces the same
set of observations (iNat keeps regrading and backfilling, so a pull without it keeps growing).
"""

from __future__ import annotations

import argparse
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
import requests

INAT = "https://api.inaturalist.org/v1/observations"
BC_PLACE_ID = 7085
PER_PAGE = 200
SLEEP = 0.5
TIMEOUT = 60
USER_AGENT = "what-to-id (17180130+wietzesuijker@users.noreply.github.com)"
GROUPS = (
    "Actinopterygii",
    "Amphibia",
    "Arachnida",
    "Aves",
    "Fungi",
    "Insecta",
    "Mammalia",
    "Mollusca",
    "Plantae",
    "Reptilia",
)

COLUMNS = (
    "id",
    "created_at",
    "observed_on",
    "lat",
    "lon",
    "iconic_taxon",
    "taxon_id",
    "taxon_name",
    "rank",
    "user_id",
    "ident_count",
    "agree",
    "photo_url",
)
DTYPES = {
    "id": "int64",
    "created_at": "object",
    "observed_on": "object",
    "lat": "float64",
    "lon": "float64",
    "iconic_taxon": "object",
    "taxon_id": "Int64",
    "taxon_name": "object",
    "rank": "object",
    "user_id": "Int64",
    "ident_count": "int64",
    "agree": "int64",
    "photo_url": "object",
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(name: str, value: object) -> str:
    if not isinstance(value, str) or not _DATE.match(value):
        raise ValueError(f"{name} must be a YYYY-MM-DD string, got {value!r}")
    return value


QUALITY_GRADES = ("needs_id", "research")


def pool_params(group: str, *, d1: str, freeze: str, quality: str = "needs_id") -> dict:
    """Query parameters for one iconic group of the BC pool.

    ``quality="needs_id"`` is the pool identifiers work on; ``quality="research"`` pulls the
    verified reference pool the novelty arm measures distance from.
    """
    if quality not in QUALITY_GRADES:
        raise ValueError(f"quality must be one of {QUALITY_GRADES}, got {quality!r}")
    return {
        "place_id": BC_PLACE_ID,
        "quality_grade": quality,
        "photos": "true",
        "iconic_taxa": group,
        "d1": _check_date("d1", d1),
        "created_d2": _check_date("freeze", freeze),
        "per_page": PER_PAGE,
        "order_by": "id",
        "order": "desc",
    }


def flatten(obs: dict) -> dict | None:
    """One API observation to a flat row. None if it has no coordinates or no photos."""
    geo = obs.get("geojson") or {}
    coords = geo.get("coordinates")
    photos = obs.get("photos") or []
    if not coords or len(coords) < 2 or not photos:
        return None
    taxon = obs.get("taxon") or {}
    user = obs.get("user") or {}
    lon, lat = coords[0], coords[1]
    return {
        "id": int(obs["id"]),
        "created_at": obs.get("created_at"),
        "observed_on": obs.get("observed_on"),
        "lat": float(lat),
        "lon": float(lon),
        "iconic_taxon": taxon.get("iconic_taxon_name") or obs.get("iconic_taxon_name"),
        "taxon_id": taxon.get("id"),
        "taxon_name": taxon.get("name"),
        "rank": taxon.get("rank"),
        "user_id": user.get("id"),
        "ident_count": int(obs.get("identifications_count") or 0),
        "agree": int(obs.get("num_identification_agreements") or 0),
        "photo_url": str(photos[0].get("url", "")).replace("/square.", "/medium."),
    }


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    return df.astype(DTYPES)


def pull_group(
    group: str,
    *,
    d1: str,
    freeze: str,
    session: requests.Session | None = None,
    cap_pages: int | None = None,
    sleep: float = SLEEP,
    log: Callable[[str], None] = print,
    quality: str = "needs_id",
) -> pd.DataFrame:
    """Page through one iconic group with an ``id_below`` cursor."""
    session = session or make_session()
    params = pool_params(group, d1=d1, freeze=freeze, quality=quality)
    rows: list[dict] = []
    id_below = None
    pages = 0
    while cap_pages is None or pages < cap_pages:
        p = dict(params)
        if id_below is not None:
            p["id_below"] = id_below
        r = session.get(INAT, params=p, timeout=TIMEOUT)
        r.raise_for_status()
        res = r.json().get("results", [])
        if not res:
            break
        pages += 1
        kept = [row for row in map(flatten, res) if row is not None]
        rows.extend(kept)
        log(f"{group} page {pages}: {len(res)} results, {len(kept)} kept, total {len(rows)}")
        id_below = res[-1]["id"]
        if len(res) < PER_PAGE:
            break
        if sleep:
            time.sleep(sleep)
    return _frame(rows)


def pull_pool(
    groups: Sequence[str] = GROUPS,
    *,
    d1: str,
    freeze: str,
    out: Path,
    **kw,
) -> pd.DataFrame:
    """Pull every group, dedupe on id, write parquet to ``out`` and return the frame."""
    frames = [pull_group(g, d1=d1, freeze=freeze, **kw) for g in groups]
    df = pd.concat(frames, ignore_index=True) if frames else _frame([])
    df = df.drop_duplicates("id").reset_index(drop=True)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    return df


def load_pool(path: Path) -> pd.DataFrame:
    """Read a pool parquet and check the required columns are present."""
    df = pd.read_parquet(path, engine="pyarrow")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    return df


def fetch_by_ids(
    ids: Sequence[int],
    *,
    session: requests.Session | None = None,
    chunk: int = 200,
    sleep: float = SLEEP,
) -> list[dict]:
    """Fetch raw observation dicts by id, in chunks of at most 200."""
    if not 1 <= chunk <= 200:
        raise ValueError(f"chunk must be between 1 and 200, got {chunk}")
    session = session or make_session()
    ids = [int(i) for i in ids]
    out: list[dict] = []
    for start in range(0, len(ids), chunk):
        batch = ids[start : start + chunk]
        r = session.get(
            INAT,
            params={"id": ",".join(map(str, batch)), "per_page": chunk},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        out.extend(r.json().get("results", []))
        if sleep and start + chunk < len(ids):
            time.sleep(sleep)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pull the BC needs-ID pool to parquet.")
    ap.add_argument("--d1", required=True, help="earliest observed_on, YYYY-MM-DD")
    ap.add_argument("--freeze", required=True, help="created_d2 freeze date, YYYY-MM-DD")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--groups", default=",".join(GROUPS), help="comma-separated iconic groups")
    ap.add_argument("--cap-pages", type=int, default=None)
    ap.add_argument(
        "--quality",
        default="needs_id",
        choices=QUALITY_GRADES,
        help="needs_id for the ID pool, research for the novelty arm's reference pool",
    )
    a = ap.parse_args(argv)
    groups = [g.strip() for g in a.groups.split(",") if g.strip()]
    unknown = sorted(set(groups) - set(GROUPS))
    if unknown:
        ap.error(f"unknown groups {unknown}; choose from {list(GROUPS)}")
    df = pull_pool(
        groups, d1=a.d1, freeze=a.freeze, out=a.out, cap_pages=a.cap_pages, quality=a.quality
    )
    print(f"{len(df)} rows -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
