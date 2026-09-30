"""Find every BC record iNaturalist changed since a time, for the map pool's daily sync."""

from __future__ import annotations

import datetime
import time
from collections.abc import Iterable

import numpy as np
import pandas as pd
import requests

from what_to_id.inat import (
    BC_PLACE_ID,
    PER_PAGE,
    SLEEP,
    _check_created_d1,
    _check_date,
    _frame,
    _results,
    flatten,
    make_session,
    pool_params,
    total_results,
)

ID_CEILING = 2**31 - 1


def changed_since(
    since: str | datetime.date | pd.Timestamp,
    *,
    d1: str,
    session: requests.Session | None = None,
    sleep: float = SLEEP,
) -> tuple[pd.DataFrame, set[int], str | None]:
    """Every BC record observed from ``d1`` that iNaturalist updated since ``since``.

    Asks for all quality grades and does not filter on photos, so one query sees every way a
    record enters or leaves the pool: a new upload, a record reaching or dropping back from
    Research Grade, a casual record reopened, a changed ID, a removed photo. Returns the rows
    now in the pool (needs-ID with a photo and coordinates), the ids of the others, and the
    newest ``updated_at`` seen, which is the next run's ``since``. A record deleted from
    iNaturalist, moved out of BC or redated before ``d1`` is not returned.
    """
    params = {
        "place_id": BC_PLACE_ID,
        "quality_grade": "needs_id,research,casual",
        "d1": _check_date("d1", d1),
        "updated_since": _check_created_d1(since),
        "per_page": PER_PAGE,
        "order_by": "id",
        "order": "desc",
    }
    session = session or make_session()
    rows: list[dict] = []
    gone: set[int] = set()
    newest: pd.Timestamp | None = None
    id_below = None
    while True:
        p = dict(params)
        if id_below is not None:
            p["id_below"] = id_below
        res = _results(session, p)
        for obs in res:
            row = flatten(obs) if obs.get("quality_grade") == "needs_id" else None
            if row is None:
                gone.add(int(obs["id"]))
            else:
                rows.append(row)
            if obs.get("updated_at"):
                t = pd.Timestamp(obs["updated_at"]).tz_convert("UTC")
                newest = t if newest is None else max(newest, t)
        if len(res) < PER_PAGE:
            return _frame(rows), gone, None if newest is None else newest.isoformat()
        id_below = res[-1]["id"]
        if sleep:
            time.sleep(sleep)


def reconcile_ids(
    pool_ids: Iterable[int],
    *,
    d1: str,
    session: requests.Session | None = None,
    sleep: float = SLEEP,
    max_requests: int = 2000,
) -> tuple[set[int], set[int], int]:
    """Find pool ids iNaturalist no longer holds and ids it holds that the pool lacks.

    Compares counts of the pool query over id ranges, both sides, and splits a range where they
    differ at the median pool id until the API holds at most one page of it, then lists that page.
    Returns ``(gone, missing, requests used)``: ``gone`` are pool ids the API no longer returns
    (deleted, moved out of BC, redated, no longer needs-ID), ``missing`` are API ids not in the
    pool. Costs about one request per differing record times the log of the pool size, instead of
    a walk of every page. A range where one record went missing and another was never added keeps
    equal counts and is not inspected; running daily after the sync keeps that rare. Raises
    ``RuntimeError`` past ``max_requests``.
    """
    ids = np.unique(np.asarray(list(pool_ids), dtype=np.int64))
    tomorrow = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)).date().isoformat()
    params = pool_params(None, d1=d1, freeze=tomorrow)
    session = session or make_session()
    used = 0

    def ask(lo: int, hi: int, *, only_id: bool) -> int | list[dict]:
        nonlocal used
        if used >= max_requests:
            raise RuntimeError(f"reconcile needs more than {max_requests} requests; raise the cap")
        if used and sleep:
            time.sleep(sleep)
        used += 1
        bounds = {**params, "id_above": lo, "id_below": hi}
        if not only_id:
            return total_results(bounds, session=session)
        return _results(session, {**bounds, "only_id": "true", "per_page": PER_PAGE})

    gone: set[int] = set()
    missing: set[int] = set()
    # iNaturalist's search index answers 500 for an id bound past a signed 32-bit int
    ranges = [(0, ID_CEILING)]
    while ranges:
        lo, hi = ranges.pop()
        i = int(np.searchsorted(ids, lo, side="right"))
        j = int(np.searchsorted(ids, hi, side="left"))
        api = ask(lo, hi, only_id=False)
        if api == j - i:
            continue
        if api <= PER_PAGE:
            listed = {int(o["id"]) for o in ask(lo, hi, only_id=True)} if api else set()
            local = set(ids[i:j].tolist())
            gone |= local - listed
            missing |= listed - local
            continue
        mid = int(ids[(i + j) // 2]) if j - i >= 2 else (lo + hi) // 2
        if not lo < mid < hi - 1:
            # the median pool id sits on a bound, so that split would give back the same range
            mid = (lo + hi) // 2
        ranges += [(lo, mid + 1), (mid, hi)]
    return gone, missing, used
