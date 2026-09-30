"""Find every BC record iNaturalist changed since a time, for the map pool's daily sync."""

from __future__ import annotations

import datetime
import time

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
)


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
