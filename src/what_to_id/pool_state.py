"""Incremental updates to the on-disk BC needs-ID pool.

Instead of pulling the pool from scratch (thousands of requests, hours), a daily run
pulls only what changed: `update` fetches records created since the pool's newest
observation, and `refresh` drops observations that already got an ID or lost their photo.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from what_to_id.inat import COLUMNS, DTYPES, closed_since, load_pool, pull_pool, still_open
from what_to_id.manifest import sha256_file

log = logging.getLogger("what_to_id")

DEFAULT_OVERLAP_HOURS = 24.0
DEFAULT_D1 = "2000-01-01"


def merge_new(pool: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append ``new`` rows into ``pool``, deduping by id with the new row winning.

    Both frames must carry the pool's standard columns; the result has the same columns,
    dtypes, and is sorted by id.
    """
    for name, df in (("pool", pool), ("new", new)):
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{name} frame missing columns {missing}")
    combined = pd.concat([pool[list(COLUMNS)], new[list(COLUMNS)]], ignore_index=True)
    combined = combined.drop_duplicates("id", keep="last")
    combined = combined.sort_values("id").reset_index(drop=True)
    return combined.astype(DTYPES)


def drop_closed(pool: pd.DataFrame, checked: Iterable[int], open_ids: set[int]) -> pd.DataFrame:
    """Drop rows whose id was checked and is no longer open; unchecked ids are kept."""
    checked_ids = {int(i) for i in checked}
    open_ids = {int(i) for i in open_ids}
    closed = checked_ids - open_ids
    if not closed:
        return pool.reset_index(drop=True)
    return pool[~pool["id"].isin(closed)].reset_index(drop=True)


def last_created(pool: pd.DataFrame) -> pd.Timestamp:
    """Max ``created_at`` (UTC) in the pool, for the next incremental pull's ``created_d1``."""
    if pool.empty:
        raise ValueError("pool is empty; cannot determine last_created")
    return pd.to_datetime(pool["created_at"], utc=True).max()


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, engine="pyarrow", index=False)
    tmp.replace(path)


def _eligibility(path: Path) -> dict:
    saved = json.loads(path.read_text())
    if (
        not isinstance(saved, dict)
        or saved.get("schema_version") != 1
        or not isinstance(saved.get("pool_sha256"), str)
        or len(saved["pool_sha256"]) != 64
        or not isinstance(saved.get("closed_ids"), list)
        or any(type(oid) is not int for oid in saved["closed_ids"])
    ):
        raise ValueError(f"invalid bundle eligibility state: {path}")
    return saved


def _write_eligibility(path: Path, saved: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(saved, sort_keys=True) + "\n")
    temporary.replace(path)


def _cmd_prepared(a: argparse.Namespace) -> int:
    """Reuse closures only for the same prepared snapshot; new snapshots supersede them."""
    digest = sha256_file(a.prepared_pool)
    saved = _eligibility(a.eligibility) if a.eligibility.exists() else None
    if saved is None or saved["pool_sha256"] != digest:
        saved = {"schema_version": 1, "pool_sha256": digest, "closed_ids": []}
    pool = load_pool(a.prepared_pool)
    updated = drop_closed(pool, saved["closed_ids"], set())
    _atomic_write(updated, a.pool)
    _write_eligibility(a.eligibility, saved)
    return 0


def _cmd_update(a: argparse.Namespace) -> int:
    pool = load_pool(a.pool)
    since = last_created(pool) - pd.Timedelta(hours=a.overlap_hours)
    freeze = pd.Timestamp.now(tz="UTC").date().isoformat()
    d1 = a.d1 or DEFAULT_D1
    incoming = a.pool.with_name(a.pool.name + ".incoming.parquet")
    new = pull_pool(d1=d1, freeze=freeze, out=incoming, created_d1=since)
    merged = merge_new(pool, new)
    _atomic_write(merged, a.pool)
    parts = incoming.with_name(incoming.name + ".parts")
    if incoming.exists():
        incoming.unlink()
    if parts.exists():
        for f in parts.iterdir():
            f.unlink()
        parts.rmdir()
    log.info(
        "update: %d existing, %d pulled since %s, %d after merge",
        len(pool),
        len(new),
        since,
        len(merged),
    )
    return 0


def _cmd_refresh(a: argparse.Namespace) -> int:
    pool = load_pool(a.pool)
    served = pd.read_parquet(a.ids, engine="pyarrow")
    checked = served["id"].astype("int64").tolist()
    eligibility = _eligibility(a.eligibility) if a.eligibility is not None else None
    open_ids = still_open(checked)
    updated = drop_closed(pool, checked, open_ids)
    log.info(
        "refresh: %d checked, %d dropped, %d kept",
        len(set(checked)),
        len(pool) - len(updated),
        len(updated),
    )
    _atomic_write(updated, a.pool)
    if eligibility is not None:
        eligibility["closed_ids"] = sorted(
            set(eligibility["closed_ids"]) | (set(checked) - open_ids)
        )
        _write_eligibility(a.eligibility, eligibility)
    return 0


def _cmd_prune(a: argparse.Namespace) -> int:
    pool = load_pool(a.pool)
    closed = closed_since(a.since, d1=a.d1 or DEFAULT_D1)
    updated = pool[~pool["id"].isin(closed)].reset_index(drop=True)
    log.info(
        "prune: %d left needs-ID since %s, %d dropped, %d kept",
        len(closed),
        a.since,
        len(pool) - len(updated),
        len(updated),
    )
    _atomic_write(updated, a.pool)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Incrementally update the BC needs-ID pool.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="pull records created since the pool's newest one")
    p_update.add_argument("--pool", required=True, type=Path)
    p_update.add_argument("--overlap-hours", type=float, default=DEFAULT_OVERLAP_HOURS)
    p_update.add_argument("--d1", default=None, help="earliest observed_on, YYYY-MM-DD")
    p_update.set_defaults(func=_cmd_update)

    p_refresh = sub.add_parser("refresh", help="drop pool ids that are no longer needs-ID")
    p_refresh.add_argument("--pool", required=True, type=Path)
    p_refresh.add_argument("--ids", required=True, type=Path, help="parquet with an id column")
    p_refresh.add_argument("--eligibility", type=Path, help="prepared snapshot exclusion state")
    p_refresh.set_defaults(func=_cmd_refresh)

    p_prune = sub.add_parser("prune", help="drop records that left needs-ID since a time")
    p_prune.add_argument("--pool", required=True, type=Path)
    p_prune.add_argument("--since", required=True, help="ISO date or datetime, UTC")
    p_prune.add_argument("--d1", default=None, help="earliest observed_on, YYYY-MM-DD")
    p_prune.set_defaults(func=_cmd_prune)

    prepared = sub.add_parser("prepared", help="load a prepared snapshot retaining known closures")
    prepared.add_argument("--pool", required=True, type=Path)
    prepared.add_argument("--prepared-pool", required=True, type=Path)
    prepared.add_argument("--eligibility", required=True, type=Path)
    prepared.set_defaults(func=_cmd_prepared)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
