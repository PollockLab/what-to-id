"""Rebuild each observation's state at a past freeze T from its identification history.

Used by the order backtest: the queue at T is every record that was needs-ID at T, and the
outcome is what happened to it afterwards (resolved, and how fast; corrected to another branch).

Rules follow iNaturalist's community taxon: a taxon's score is the IDs at or below it over those
IDs plus the IDs on another branch; the community taxon is the deepest taxon with at least two IDs
at or below it and a score above 2/3. A record is research grade when that taxon is at species
rank or below. Three things the pulled data cannot show are ignored: when an ID was withdrawn
(an ID that was later withdrawn counts as active at T unless the same person added a newer one
before T), explicit disagreements with an ancestor, and Data Quality votes.

Input is the JSONL from `pull_history.py`: API v2 observations with `identifications.*` fields.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

SPECIES = 10


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def lineage(taxon: Mapping) -> tuple[int, ...]:
    """Root-to-self taxon ids. API v2 lists the observation taxon's own id in `ancestor_ids`,
    and leaves it out for an identification's taxon; both shapes are handled."""
    anc = list(taxon.get("ancestor_ids") or [])
    if not anc or anc[-1] != taxon["id"]:
        anc.append(taxon["id"])
    return tuple(anc)


def active(idents: Iterable[Mapping], at: datetime | None) -> list[Mapping]:
    """Per person, their latest ID made before `at`. With `at=None`, the IDs current now."""
    if at is None:
        return [i for i in idents if i.get("current") and i.get("taxon")]
    latest: dict[int, Mapping] = {}
    for i in idents:
        if not i.get("taxon") or ts(i["created_at"]) >= at:
            continue
        u = i["user"]["id"]
        if u not in latest or ts(i["created_at"]) > ts(latest[u]["created_at"]):
            latest[u] = i
    return list(latest.values())


def community_taxon(lins: list[tuple[int, ...]], rank_level: Mapping[int, float]) -> int | None:
    if len(lins) < 2:
        return None
    below = Counter(t for lin in lins for t in lin)
    best, best_key = None, None
    for t, n in below.items():
        if n < 2:
            continue
        up = next(lin[: lin.index(t) + 1] for lin in lins if t in lin)
        other = sum(1 for lin in lins if t not in lin and lin[-1] not in up)
        if n / (n + other) <= 2 / 3:
            continue
        key = (-rank_level.get(t, 100 - len(up)), len(up))
        if best_key is None or key > best_key:
            best, best_key = t, key
    return best


def state(obs: Mapping, at: datetime | None, rank_level: Mapping[int, float]) -> dict:
    """Taxon, grade and ID count of `obs` at `at` (now when `at` is None)."""
    ids = active(obs.get("identifications") or [], at)
    lins = [lineage(i["taxon"]) for i in ids]
    ct = community_taxon(lins, rank_level)
    if ct is not None:
        taxon, lin = ct, next(lin[: lin.index(ct) + 1] for lin in lins if ct in lin)
    else:
        own = [i for i in ids if i.get("own_observation")]
        pick = max(own or ids, key=lambda i: ts(i["created_at"]), default=None)
        lin = lineage(pick["taxon"]) if pick else ()
        taxon = lin[-1] if lin else None
    rl = rank_level.get(taxon, float("nan")) if taxon is not None else float("nan")
    rg = ct is not None and rank_level.get(ct, 100) <= SPECIES
    return {"taxon": taxon, "lineage": lin, "rank_level": rl, "research": rg, "n_ids": len(ids)}


def days_to_research(obs: Mapping, t: datetime, rank_level: Mapping[int, float]) -> float:
    """Days after `t` until the record first reached research grade by the rules above, NaN if
    it never did. Replays the IDs made after `t` one at a time."""
    later = sorted(
        {ts(i["created_at"]) for i in obs.get("identifications") or [] if ts(i["created_at"]) >= t}
    )
    for when in later:
        if state(obs, when + timedelta(microseconds=1), rank_level)["research"]:
            return (when - t).total_seconds() / 86400
    return float("nan")


def first_touch_days(obs: Mapping, t: datetime) -> float:
    """Days after `t` until anyone but the observer added an ID, NaN if nobody did."""
    after = [
        ts(i["created_at"])
        for i in obs.get("identifications") or []
        if not i.get("own_observation") and ts(i["created_at"]) >= t
    ]
    return (min(after) - t).total_seconds() / 86400 if after else float("nan")


def relation(then: tuple[int, ...], now: tuple[int, ...]) -> str:
    """How the taxon now relates to the taxon at T: same, refined, coarsened, corrected, none."""
    if not then or not now:
        return "none"
    if then == now:
        return "same"
    if now[: len(then)] == then:
        return "refined"
    if then[: len(now)] == now:
        return "coarsened"
    return "corrected"


def row(obs: Mapping, t: datetime, rank_level: Mapping[int, float]) -> dict:
    lat, lon = (
        (float(x) for x in obs["location"].split(",")) if obs.get("location") else (None,) * 2
    )
    at_t, now = state(obs, t, rank_level), state(obs, None, rank_level)
    tx = obs.get("taxon") or {}
    photos = obs.get("photos") or []
    return {
        "id": obs["id"],
        "created_at": obs["created_at"],
        "observed_on": obs.get("observed_on"),
        "lat": lat,
        "lon": lon,
        "user_id": (obs.get("user") or {}).get("id"),
        "iconic_taxon": tx.get("iconic_taxon_name"),
        "photo_url": photos[0]["url"] if photos else None,
        "taxon_t": at_t["taxon"],
        "rank_level_t": at_t["rank_level"],
        "research_t": at_t["research"],
        "n_ids_t": at_t["n_ids"],
        "lineage_t": "/".join(map(str, at_t["lineage"])),
        "grade_now": obs.get("quality_grade"),
        "taxon_now": tx.get("id"),
        "rank_level_now": tx.get("rank_level"),
        "research_rebuilt_now": now["research"],
        "relation": relation(at_t["lineage"], lineage(tx) if tx else ()),
        "days_to_rg": days_to_research(obs, t, rank_level)
        if not at_t["research"]
        else float("nan"),
        "first_touch_days": first_touch_days(obs, t),
    }


def load_rank_levels(taxa_csv: Path | str) -> dict[int, float]:
    df = pd.read_csv(taxa_csv, sep="\t", usecols=["taxon_id", "rank_level"])
    return dict(zip(df.taxon_id.astype(int), df.rank_level.astype(float), strict=True))


def build(jsonl: Path | str, t: datetime, rank_level: Mapping[int, float]) -> pd.DataFrame:
    opener = gzip.open if str(jsonl).endswith(".gz") else open
    with opener(jsonl, "rt") as f:
        rows = [row(json.loads(line), t, rank_level) for line in f]
    df = pd.DataFrame(rows).drop_duplicates("id")
    return df[pd.to_datetime(df.created_at, utc=True) < pd.Timestamp(t)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("jsonl")
    ap.add_argument("--taxa", required=True, help="iNat Open Data taxa.csv.gz")
    ap.add_argument("--freeze", required=True, help="T, ISO time with offset")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    df = build(a.jsonl, ts(a.freeze), load_rank_levels(a.taxa))
    df.to_parquet(a.out, index=False)
    agree = (df.research_rebuilt_now == (df.grade_now == "research")).mean()
    print(
        f"{len(df)} records, {int((~df.research_t).sum())} needs-ID at T, "
        f"rebuilt grade now agrees with iNat on {agree:.1%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
