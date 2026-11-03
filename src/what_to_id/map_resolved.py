"""The records that left needs-ID, for the map's "left needs-ID" layer.

Each map.yml run logs the pool rows that left (``left_rows``, ``append_log``) into resolved.parquet
on the map-state release: the pool's own columns plus ``left``, the run's UTC time, and ``reason``,
a code from REASON. The log keeps KEEP_DAYS days; a record that is back in the pool is not in it.

``build`` turns the log into the site's pool-resolved.bin (hashed, in META.files.resolved;
`site_files`), gzipped, little-endian, n records sorted by id, only those that left in the last
SITE_DAYS days:
    uint16 start | uint16 build | uint16 live | uint16 0 | uint32 id[n]
    | float32 lon[n] | float32 lat[n]
    | uint16 obs[n] | uint16 up[n] | uint16 left[n] | uint16 taxon[n]
    | uint8 group[n] | uint8 flags[n] | uint8 reason[n]
Days count from 1900-01-01 (not META.day0), NO_DAY for none; start is the day of the log's oldest
row and build the day of the build, so the page can say the log is younger than its window. live is
the day of the log's oldest row that is not a BACKFILL one (a backfill only knows Research Grade
leavers), so rows before it are Research Grade only; it equals start when nothing was backfilled.
taxon
is a row of pool-taxa.bin (the taxon, else its nearest ancestor in that table, else NO_TAXON), group
an index of META.groups and flags as the shards' flags byte. Records of a group no pool record
carries are left out. ``check`` compares the log with two pool snapshots.
"""

from __future__ import annotations

import argparse
import gzip
import json
import struct
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import site_files
from what_to_id.inat import BC_PLACE_ID, PER_PAGE, SLEEP, _frame, _results, flatten, make_session
from what_to_id.page_map import DAY_FLOOR, EARLY_OBS, EARLY_UP, NO_DAY, _dates, _flags, _gz
from what_to_id.taxonomy import NO_TAXON, load_tree, taxa_table

NAME = "pool-resolved.bin"
KEEP_DAYS = 60
SITE_DAYS = 30
# the quality grade a record had when it left; reconcile cannot know it
REASON = {"research": 1, "casual": 2, "needs_id": 3}
UNKNOWN = 4
# Research Grade, found by the iNaturalist backfill rather than seen leaving; counts as research
BACKFILL = 5
_LAYOUT = [("id", "<u4"), ("lon", "<f4"), ("lat", "<f4")]
_LAYOUT += [(k, "<u2") for k in ("obs", "up", "left", "taxon")] + [
    (k, "u1") for k in ("group", "flags", "reason")
]
_BYTES = sum(np.dtype(dt).itemsize for _, dt in _LAYOUT)


def left_rows(
    before: pd.DataFrame, after: pd.DataFrame, grades: dict[int, str], at: pd.Timestamp
) -> pd.DataFrame:
    """The rows of ``before`` whose id is not in ``after``, stamped ``at`` with a reason code."""
    gone = before[~before["id"].isin(after["id"])]
    reason = [REASON.get(grades.get(int(i)), UNKNOWN) for i in gone["id"]]
    return gone.assign(left=at, reason=np.array(reason, dtype="uint8"))


def append_log(
    path: Path,
    rows: pd.DataFrame,
    pool_ids: pd.Series,
    now: pd.Timestamp,
    keep_days: int = KEEP_DAYS,
) -> pd.DataFrame:
    """The log at ``path`` (none yet is empty) with ``rows`` added, the newest row per id kept.

    Records in ``pool_ids`` (back in the pool) and rows older than ``keep_days`` are dropped.
    """
    frames = [f for f in (pd.read_parquet(path) if path.exists() else None, rows) if f is not None]
    return _tidy(
        pd.concat([f for f in frames if len(f)] or [rows], ignore_index=True),
        pool_ids,
        now,
        keep_days,
    )


def _tidy(
    log: pd.DataFrame, pool_ids: pd.Series, now: pd.Timestamp, keep_days: int
) -> pd.DataFrame:
    log = log.drop_duplicates("id", keep="last")
    fresh = pd.to_datetime(log["left"], utc=True) >= now - pd.Timedelta(days=keep_days)
    return log[fresh & ~log["id"].isin(pool_ids)].reset_index(drop=True)


def merge_backfill(
    back: pd.DataFrame, path: Path, pool_ids: pd.Series, now: pd.Timestamp
) -> pd.DataFrame:
    """The log at ``path`` with ``back`` under it: the newest row per id wins, so a live row."""
    live = pd.read_parquet(path) if path.exists() else back.iloc[:0]
    return _tidy(pd.concat([back, live], ignore_index=True), pool_ids, now, KEEP_DAYS)


def _days(col: pd.Series) -> pd.Series:
    """Days since 1900-01-01, NaN for no date."""
    return (_dates(col) - DAY_FLOOR).dt.days


def _u16(d: pd.Series) -> np.ndarray:
    return d.clip(lower=0).fillna(NO_DAY).to_numpy().astype("<u2")


def _taxon_rows(rows: pd.DataFrame, pool: pd.DataFrame, tree: dict | None) -> np.ndarray:
    table = taxa_table(pool, tree or None)[0]
    at = {r[2]: i for i, r in enumerate(table)}

    def row(t) -> int:
        t = None if pd.isna(t) else int(t)
        while t is not None and t not in at:
            t = tree[t][0] if tree and t in tree else None
        return NO_TAXON if t is None else at[t]

    cache = {t: row(t) for t in rows["taxon_id"].unique()} if "taxon_id" in rows else {}
    return np.array([cache.get(t, NO_TAXON) for t in rows.get("taxon_id", [])], dtype="<u2")


def encode_left(
    log: pd.DataFrame | None,
    pool: pd.DataFrame,
    tree: dict | None,
    now: pd.Timestamp,
    days: int = SITE_DAYS,
) -> bytes:
    """pool-resolved.bin for the records of ``log`` that left in the ``days`` days to ``now``."""
    build = (now.tz_convert(None).normalize() - DAY_FLOOR).days
    if log is None or log.empty:
        return _gz(struct.pack("<HHHH", build, build, build, 0))
    log = log[~log["id"].isin(pool["id"])]  # a write that failed can leave a record that is back
    start = int(_days(log["left"]).min()) if len(log) else build
    full = log[log["reason"] != BACKFILL]
    live = int(_days(full["left"]).min()) if len(full) else start
    groups = sorted(pool["iconic_taxon"].fillna("Unknown").astype(str).unique())
    g = log["iconic_taxon"].fillna("Unknown").astype(str).map({k: i for i, k in enumerate(groups)})
    left = _days(log["left"])
    df = log[g.notna() & (left > build - days) & (left <= build)].sort_values("id")
    g, left = g[df.index].to_numpy("u1"), _days(df["left"])
    obs, up = _dates(df["observed_on"]), _dates(df["created_at"])
    flags = _flags(df)[1] | np.where(obs < DAY_FLOOR, EARLY_OBS, 0).astype("u1")
    flags = flags | np.where(up < DAY_FLOOR, EARLY_UP, 0).astype("u1")
    cols = {
        "id": df["id"].to_numpy("<u4"),
        "lon": df["lon"].to_numpy("<f4"),
        "lat": df["lat"].to_numpy("<f4"),
        "obs": _u16((obs - DAY_FLOOR).dt.days),
        "up": _u16((up - DAY_FLOOR).dt.days),
        "left": _u16(left),
        "taxon": _taxon_rows(df, pool, tree),
        "group": g,
        "flags": flags,
        "reason": df["reason"].to_numpy("u1"),
    }
    body = b"".join(np.ascontiguousarray(cols[k], dtype=dt).tobytes() for k, dt in _LAYOUT)
    return _gz(struct.pack("<HHHH", start, build, live, 0) + body)


def decode_left(blob: bytes) -> dict[str, np.ndarray | int]:
    """A pool-resolved.bin as the page reads it: its columns, ``start``, ``build`` and ``live``."""
    raw = gzip.decompress(blob)
    n, rest = divmod(len(raw) - 8, _BYTES)
    if len(raw) < 8 or rest:
        raise ValueError(f"pool-resolved.bin holds {len(raw)} bytes, not 8 + {_BYTES} per record")
    start, build, live, _ = struct.unpack_from("<HHHH", raw)
    out: dict[str, np.ndarray | int] = {"start": start, "build": build, "live": live}
    off = 8
    for name, dt in _LAYOUT:
        out[name] = np.frombuffer(raw, dt, n, off)
        off += n * np.dtype(dt).itemsize
    return out


def check(
    before: pd.DataFrame,
    after: pd.DataFrame,
    log: pd.DataFrame,
    since: pd.Timestamp,
    site: bytes | None = None,
    tol: float = 0.02,
) -> dict:
    """Whether the log accounts for the records that left the pool between two snapshots.

    ``since`` is when ``before`` was taken (sync.json's ran_at). The log rows after it that were in
    ``before`` must number exactly the records ``before`` has and ``after`` lacks, and all its rows
    after it within ``tol`` of that (records added in one run and gone by the next were never in
    ``before``). With ``site``, the deployed file's last 7 days must count the log's own, exactly.
    """
    gone = set(before["id"]) - set(after["id"])
    logged = log[pd.to_datetime(log["left"], utc=True) > since]
    seen = set(logged["id"])
    out = {
        "left_pool": len(gone),
        "logged": len(seen),
        "logged_in_before": len(seen & set(before["id"])),
        "ratio": len(seen) / len(gone) if gone else None,
    }
    out["pool_ok"] = out["logged_in_before"] == len(gone) and (
        not gone or abs(out["ratio"] - 1) <= tol
    )
    if site is not None:
        s = decode_left(site)
        day = _days(log["left"])
        out["site_7d"] = int((s["left"] > s["build"] - 7).sum())
        out["log_7d"] = int(((day > s["build"] - 7) & ~log["id"].isin(after["id"])).sum())
        out["site_ok"] = out["site_7d"] == out["log_7d"]
    return out


def _lineage(taxon: dict) -> set[int]:
    return set(taxon.get("ancestor_ids") or []) | {taxon["id"]}


def research_time(obs: dict) -> pd.Timestamp | None:
    """When a Research Grade observation reached it, from its identifications; None if they say no.

    The first identification (by time) at which at least 2 agree with the community taxon and more
    than 2/3 of the agreeing and disagreeing ones do. A taxon swap re-creates every identification
    with a new time, so one that carries ``taxon_change`` is dated by the same user's latest earlier
    identification, the one it replaced.
    """
    ct = obs.get("community_taxon_id") or (obs.get("taxon") or {}).get("id")
    allids = obs.get("identifications") or []
    ids = []
    for i in allids:
        if not (i.get("current") and i.get("taxon")):
            continue
        t = i["created_at"]
        if i.get("taxon_change"):
            uid = (i.get("user") or {}).get("id")
            prev = [
                j["created_at"]
                for j in allids
                if (j.get("user") or {}).get("id") == uid
                and not j.get("current")
                and j["created_at"] < t
            ]
            t = max(prev, default=t)
        ids.append((pd.Timestamp(t), i["taxon"]))
    ids.sort(key=lambda x: x[0])
    if ct is None:
        return None
    exact = [t for _, t in ids if t["id"] == ct and ct in _lineage(t)]
    own = _lineage(exact[-1]) if exact else None
    agree = disagree = 0
    for t, taxon in ids:
        if ct in _lineage(taxon):
            agree += 1
        elif not (own and taxon["id"] in own):
            disagree += 1  # neither the community taxon, a descendant nor an ancestor of it
        if agree >= 2 and agree / (agree + disagree) > 2 / 3:
            return t
    return None


def backfill_rows(
    observations: Iterable[dict], runs: pd.DatetimeIndex, since: pd.Timestamp
) -> pd.DataFrame:
    """BACKFILL log rows for observations that reached Research Grade in a window of ``runs``.

    A window is (previous run, run]; ``left`` is the run's time, as the live log stamps it. Only
    records uploaded before the window opened count, as a stand-in for having been in the pool,
    and only those that reached Research Grade after ``since``.
    """
    rows = []
    for obs in observations:
        t = research_time(obs)
        row = flatten(obs)
        if t is None or row is None or t <= since:
            continue
        k = int(runs.searchsorted(t, side="left"))
        if k == 0 or k == len(runs) or pd.Timestamp(row["created_at"]) > runs[k - 1]:
            continue  # before the first window, after the last run (the live log has it), or new
        rows.append({**row, "left": runs[k], "reason": BACKFILL})
    out = _frame([{k: v for k, v in r.items() if k not in ("left", "reason")} for r in rows])
    left = pd.Series([r["left"] for r in rows], dtype="datetime64[ns, UTC]")
    return out.assign(left=left, reason=np.full(len(rows), BACKFILL, dtype="uint8"))


def fetch_research(
    since: pd.Timestamp,
    d1: str,
    fetch: Callable[[dict], list[dict]] | None = None,
    sleep: float = SLEEP,
):
    """Every Research Grade BC observation with a photo that iNaturalist updated since ``since``."""
    if fetch is None:
        session = make_session()

        def fetch(p):
            return _results(session, p)

    params = {
        "place_id": BC_PLACE_ID,
        "quality_grade": "research",
        "photos": "true",
        "d1": d1,
        "updated_since": since.isoformat(),
        "per_page": PER_PAGE,
        "order_by": "id",
        "order": "desc",
    }
    pages = 0
    while True:
        res = fetch(params)
        yield from res
        pages += 1
        if pages % 25 == 0:
            print(f"backfill: {pages} pages", file=sys.stderr, flush=True)
        if len(res) < PER_PAGE:
            return
        params = {**params, "id_below": res[-1]["id"]}
        if sleep:
            time.sleep(sleep)


def read_runs(text: str) -> pd.DatetimeIndex:
    """Run times, sorted, from ``gh run list --json createdAt,conclusion`` or one ISO time a line.

    A run whose conclusion is given and is not success never saved its sync, so it is skipped.
    """
    text = text.strip()
    if text.startswith("["):
        got = [
            r["createdAt"] for r in json.loads(text) if r.get("conclusion", "success") == "success"
        ]
    else:
        got = [x.strip() for x in text.splitlines() if x.strip()]
    return pd.DatetimeIndex(pd.to_datetime(got, utc=True)).sort_values()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build or check the left-needs-ID layer.")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help=f"write {NAME} from the log")
    b.add_argument("--log", required=True, type=Path, help="resolved.parquet; none is an empty log")
    b.add_argument("--pool", required=True, type=Path)
    b.add_argument("--tree", type=Path, help="taxon tree cache, as page_map's")
    b.add_argument("--out", required=True, type=Path, help="site folder holding map.html")
    c = sub.add_parser("check", help="compare the log with two pool snapshots")
    c.add_argument("--before", required=True, type=Path)
    c.add_argument("--after", required=True, type=Path)
    c.add_argument("--log", required=True, type=Path)
    c.add_argument("--since", required=True, help="when --before was taken, ISO, UTC")
    c.add_argument("--site", type=Path, help="the deployed pool-resolved.bin")
    k = sub.add_parser("backfill", help="add Research Grade leavers from the iNaturalist API")
    k.add_argument("--log", required=True, type=Path, help="resolved.parquet; none is an empty log")
    k.add_argument("--pool", required=True, type=Path)
    k.add_argument("--runs", type=Path, help="gh run list JSON, or a time a line")
    k.add_argument("--since", help="earliest time to backfill, ISO, UTC")
    k.add_argument("--from", dest="saved", type=Path, help="backfill rows saved before: no fetch")
    k.add_argument("--save", type=Path, help="also write the backfill rows alone here")
    k.add_argument("--d1", default="1900-01-01", help="the pool's earliest observed_on")
    k.add_argument("--out", required=True, type=Path, help="the merged resolved.parquet")
    a = ap.parse_args(argv)
    if a.command == "backfill":
        if a.saved:
            back = pd.read_parquet(a.saved)
        elif a.runs and a.since:
            since = pd.to_datetime(a.since, utc=True)
            back = backfill_rows(fetch_research(since, a.d1), read_runs(a.runs.read_text()), since)
            if a.save:
                back.to_parquet(a.save, index=False)
        else:
            ap.error("backfill needs --from, or --runs and --since")
        merge_backfill(
            back, a.log, pd.read_parquet(a.pool, columns=["id"])["id"], pd.Timestamp.now("UTC")
        ).to_parquet(a.out, index=False)
        return 0
    if a.command == "build":
        log = pd.read_parquet(a.log) if a.log.exists() else None
        blob = encode_left(
            log, pd.read_parquet(a.pool), load_tree(a.tree) or None, pd.Timestamp.now("UTC")
        )
        site_files.publish(a.out, "resolved", NAME, blob)
        return 0
    got = check(
        pd.read_parquet(a.before),
        pd.read_parquet(a.after),
        pd.read_parquet(a.log),
        pd.to_datetime(a.since, utc=True),
        a.site.read_bytes() if a.site else None,
    )
    print(json.dumps(got))
    return 0 if got["pool_ok"] and got.get("site_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
