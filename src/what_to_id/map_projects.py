"""Which of a few iNaturalist projects each map record sits in, so the map can combine them.

For each project in PROJECTS this keeps the ids of the BC records in it that the map pool holds
(needs an ID, has a photo, observed from d1), and writes them to pool-projects.bin next to the
map's shards, which stay as they are. The page turns the lists into a per-record bitmask.

pool-projects.bin, gzipped, little-endian: uint32 header length, the header (UTF-8 JSON,
``{"projects": [{"id", "n", "since"}, ...]}``), then each project's n ids, sorted, as uint32 steps
from the previous id (the first is the id itself), stored byte by byte like the shards' columns.
``since`` is when that project's list was last brought up to date.

The same file is the daily state. A full listing pages through a project with ``id_above``, 200
ids a request; that is cheap for a small project but not for a big one (the BC Biodiversity
Program holds over 500,000 BC needs-ID records, about 2,700 requests), so a big project is seeded
once with a high ``--max-requests`` and then kept up to date: ids that left the pool are dropped,
ids iNaturalist updated since the last run are added, and the id-range count check that
reconciles the pool repairs what is left (records that left the project, members added later).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import struct
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from what_to_id.inat import PER_PAGE, SLEEP, _results, make_session, pool_params, total_results
from what_to_id.inat_sync import reconcile_ids

# iNaturalist project ids, found with /v1/projects?q=: 86886 is the umbrella of the BC Parks iNat
# Team Big Summer projects (2019 on); 90486 is the collection of species listed S1 to S3 in BC.
PROJECTS = (
    {"id": 86886, "title": "BC Biodiversity Program"},
    {"id": 90486, "title": "BC Rarities"},
)
PROJECTS_NAME = "pool-projects.bin"
MAX_REQUESTS = 600
# updated_since starts this much before the last run, so a slow clock cannot skip an update
SINCE_MARGIN = pd.Timedelta(hours=1)


def encode_projects(state: dict[int, dict]) -> bytes:
    """``{project id: {"ids": ids, "since": iso time}}`` to the gzipped file."""
    head, body = [], []
    for pid, p in state.items():
        ids = np.unique(np.asarray(p["ids"], dtype=np.int64))
        if len(ids) and (ids[0] < 0 or ids[-1] > 0xFFFFFFFF):
            raise ValueError(f"project {pid}: record ids do not fit in uint32")
        steps = np.diff(ids, prepend=0).astype("<u4")
        head.append({"id": int(pid), "n": len(ids), "since": p["since"]})
        body.append(steps.view("u1").reshape(-1, 4).T.tobytes())
    h = json.dumps({"projects": head}, separators=(",", ":")).encode()
    return gzip.compress(struct.pack("<I", len(h)) + h + b"".join(body), compresslevel=9, mtime=0)


def decode_projects(blob: bytes) -> dict[int, dict]:
    """The file back to ``{project id: {"ids": sorted int64 ids, "since": iso time}}``."""
    raw = gzip.decompress(blob)
    if len(raw) < 4:
        raise ValueError("project file is too short")
    (hn,) = struct.unpack_from("<I", raw)
    head = json.loads(raw[4 : 4 + hn])["projects"]
    off = 4 + hn
    if len(raw) != off + 4 * sum(int(p["n"]) for p in head):
        raise ValueError("project file size does not match its header")
    out = {}
    for p in head:
        n = int(p["n"])
        planes = np.frombuffer(raw, "u1", 4 * n, off).reshape(4, n)
        steps = planes.T.copy().view("<u4").ravel()
        out[int(p["id"])] = {"ids": np.cumsum(steps, dtype=np.int64), "since": p["since"]}
        off += 4 * n
    return out


def list_ids(params: dict, *, session, sleep: float = SLEEP, max_requests: int = MAX_REQUESTS):
    """Every record id the query matches, paging up by ``id_above``; and the requests used."""
    ids: list[int] = []
    used, above = 0, 0
    while True:
        if used >= max_requests:
            raise RuntimeError(f"listing needs more than {max_requests} requests; raise the cap")
        if used and sleep:
            time.sleep(sleep)
        q = {**params, "only_id": "true", "per_page": PER_PAGE, "order_by": "id", "order": "asc"}
        res = _results(session, {**q, "id_above": above})
        used += 1
        ids += [int(o["id"]) for o in res]
        if len(res) < PER_PAGE:
            return np.unique(np.asarray(ids, dtype=np.int64)), used
        above = ids[-1]


def update_projects(
    state: dict[int, dict],
    pool_ids,
    *,
    d1: str,
    now: pd.Timestamp,
    session=None,
    sleep: float = SLEEP,
    max_requests: int = MAX_REQUESTS,
    projects=PROJECTS,
) -> tuple[dict[int, dict], dict[int, dict]]:
    """Bring each project's list in line with iNaturalist; returns the new state and per-project
    counts. A project that fails keeps its old list, cut to the pool, and its old ``since``; a
    project with no list yet is listed in full, or skipped if that takes over ``max_requests``.
    """
    session = session or make_session()
    pool = np.unique(np.asarray(pool_ids, dtype=np.int64))
    tomorrow = (now + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    stamp = now.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict[int, dict] = {}
    stats: dict[int, dict] = {}
    for p in projects:
        pid = int(p["id"])
        params = {**pool_params(None, d1=d1, freeze=tomorrow), "project_id": pid}
        old = state.get(pid)
        st = stats[pid] = {"requests": 0}
        try:
            if old is None:
                n = total_results(params, session=session)
                st["requests"] = 1
                if n // PER_PAGE + 1 > max_requests - 1:
                    raise RuntimeError(
                        f"{n:,} records need about {n // PER_PAGE + 1} requests to list, over the "
                        f"cap of {max_requests}; seed it with a higher --max-requests"
                    )
                ids, used = list_ids(
                    params, session=session, sleep=sleep, max_requests=max_requests
                )
                st.update(requests=1 + used, listed=len(ids))
            else:
                kept = np.intersect1d(old["ids"], pool)
                since = pd.Timestamp(old["since"]) - SINCE_MARGIN
                new, used = list_ids(
                    {**params, "updated_since": since.strftime("%Y-%m-%dT%H:%M:%SZ")},
                    session=session,
                    sleep=sleep,
                    max_requests=max_requests,
                )
                ids = np.union1d(kept, new)
                gone, missing, used2 = reconcile_ids(
                    ids,
                    d1=d1,
                    session=session,
                    sleep=sleep,
                    max_requests=max_requests - used,
                    extra={"project_id": pid},
                )
                gone_a, missing_a = (np.array(sorted(x), dtype=np.int64) for x in (gone, missing))
                ids = np.union1d(np.setdiff1d(ids, gone_a), missing_a)
                st.update(
                    requests=used + used2,
                    left_pool=len(old["ids"]) - len(kept),
                    updated=len(new),
                    gone=len(gone),
                    missing=len(missing),
                )
            out[pid] = {"ids": ids, "since": stamp}
        except (requests.RequestException, RuntimeError, KeyError, ValueError) as e:
            _warn(f"project {pid} ({p['title']}): {e}; keeping its last list")
            if old is not None:
                out[pid] = {"ids": np.intersect1d(old["ids"], pool), "since": old["since"]}
        if pid in out:
            st["n"] = len(out[pid]["ids"])
    return out, stats


def load_projects(path: Path | None) -> bytes | None:
    """The project file for the map, or None (with a warning) if it is missing or unreadable."""
    if path is None:
        return None
    try:
        blob = Path(path).read_bytes()
        decode_projects(blob)
    except (OSError, ValueError, KeyError, EOFError, gzip.BadGzipFile) as e:
        _warn(f"building the map without project filters: {e}")
        return None
    return blob


def project_meta(blob: bytes, projects=PROJECTS) -> dict | None:
    """What the page needs to read the file: its versioned name and the configured projects in
    it, in PROJECTS order. None when the file holds none of them."""
    have = decode_projects(blob)
    rows = [
        {"id": p["id"], "title": p["title"], "n": len(have[p["id"]]["ids"])}
        for p in projects
        if p["id"] in have
    ]
    if not rows:
        return None
    v = hashlib.sha256(blob).hexdigest()[:12]
    return {"file": f"{PROJECTS_NAME}?v={v}", "list": rows}


def add_projects(blobs: dict, meta: dict, path: Path | None) -> None:
    """Add the project file and its page meta to the map's files, if the file is readable."""
    if (blob := load_projects(path)) and (pm := project_meta(blob)):
        blobs[PROJECTS_NAME], meta["projects"] = blob, pm


def _warn(msg: str) -> None:
    from what_to_id.page_map import _warn as warn

    warn(msg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Update the map's project lists (pool-projects.bin).")
    ap.add_argument("--pool", required=True, type=Path, help="the map pool parquet")
    ap.add_argument("--state", required=True, type=Path, help="pool-projects.bin, read and written")
    ap.add_argument("--d1", required=True)
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS, help="per project")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("what_to_id")
    state = decode_projects(a.state.read_bytes()) if a.state.exists() else {}
    pool_ids = pd.read_parquet(a.pool, columns=["id"])["id"]
    new, stats = update_projects(
        state, pool_ids, d1=a.d1, now=pd.Timestamp.now("UTC"), max_requests=a.max_requests
    )
    for pid, st in stats.items():
        log.info("project %d: %s", pid, json.dumps(st))
    if not new:
        _warn("no project list could be built")
        return 1
    blob = encode_projects(new)
    tmp = a.state.with_suffix(".tmp")
    tmp.write_bytes(blob)
    tmp.replace(a.state)
    log.info("wrote %s (%d bytes)", a.state, len(blob))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
