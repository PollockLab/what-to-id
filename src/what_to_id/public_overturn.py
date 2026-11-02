"""Public-record pre-test of the blind track: overturn of first own species IDs, CV or typed.

    python -m what_to_id.public_overturn pull --out records.jsonl [--blocks 200] [--seed 0]
    python -m what_to_id.public_overturn tables records.jsonl [--levels identify.parquet]

``pull`` samples ``blocks`` runs of 200 consecutive ids from BC verifiable observations with photos
observed 2025 or later and writes one JSON line per record with its identifications and the
observer's lifetime counts. ``tables`` prints overturn by iconic group, by observer experience and
by creation quarter, the within-species Mantel-Haenszel ratio, and with ``--levels`` the public
contradiction share per Identify level.

Unit: the observer's earliest identification on their own non-casual record, at species rank,
with at least one other current identification. Overturned: the community taxon exists and is
neither that identification nor a descendant of it. Later identifiers saw the suggestion and the
first ID, so these rates carry the agreement bias the blind track is designed to remove; they
size and stratify the study, they do not answer it.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import inat

PARAMS = {
    "place_id": 7085,
    "verifiable": "true",
    "d1": "2025-01-01",
    "photos": "true",
    "order_by": "id",
    "order": "asc",
    "per_page": 200,
}
EXPERIENCE_CUTS = (10, 100, 1000)
EXPERIENCE = ("<10 ids", "10-99 ids", "100-999 ids", "1000+ ids")
LEVEL_NAMES = ("none", "easy", "taxonomist", "narrow", "weird", "mislabel")


def level_number(v) -> int:
    """Identify level as its number; ``identify_levels`` writes numbers or ``LEVEL_NAMES``."""
    return LEVEL_NAMES.index(v) if isinstance(v, str) else int(v)


TABLE_COLUMNS = ["stratum", "source", "n", "species", "tested", "overturned", "overturn"]


def summarise(o: dict) -> dict:
    """One raw observation to the record the tables read."""
    user = o.get("user") or {}
    taxon = o.get("taxon") or {}
    return {
        "id": o["id"],
        "quality_grade": o.get("quality_grade"),
        "created_at": o.get("created_at"),
        "community_taxon_id": o.get("community_taxon_id"),
        "user_id": user.get("id"),
        "observer_idents": user.get("identifications_count"),
        "taxon": taxon.get("id"),
        "iconic": taxon.get("iconic_taxon_name"),
        "idents": [
            {
                "user": (i.get("user") or {}).get("id"),
                "user_idents": (i.get("user") or {}).get("identifications_count"),
                "own": i.get("own_observation"),
                "vision": i.get("vision"),
                "current": i.get("current"),
                "taxon": i.get("taxon_id"),
                "rank": (i.get("taxon") or {}).get("rank"),
                "anc": (i.get("taxon") or {}).get("ancestor_ids") or [],
                "created": i.get("created_at"),
            }
            for i in o.get("identifications") or []
        ],
    }


def pull(blocks: int, seed: int, session=None, sleep: float = 1.0):
    """Yield summarised records from ``blocks`` uniform id blocks; one request per block."""
    session = session or inat.make_session()
    lo = inat._results(session, {**PARAMS, "per_page": 1})[0]["id"]
    hi = inat._results(session, {**PARAMS, "per_page": 1, "order": "desc"})[0]["id"]
    rng = random.Random(seed)
    for start in sorted(rng.randrange(lo, hi) for _ in range(blocks)):
        for o in inat._results(session, {**PARAMS, "id_above": start}):
            yield summarise(o)
        time.sleep(sleep)


def _first_own(r: dict) -> dict | None:
    own = [i for i in r["idents"] if i["own"] and i["created"]]
    return min(own, key=lambda i: i["created"]) if own else None


def _on_lineage(i: dict, ref: dict) -> bool:
    """Whether ID ``i`` names ``ref``'s taxon, a descendant of it or one of its ancestors."""
    return i["taxon"] == ref["taxon"] or ref["taxon"] in i["anc"] or i["taxon"] in ref["anc"]


def _upheld(first: dict, others: list[dict], ct) -> bool:
    if ct is None:
        return False
    return ct == first["taxon"] or any(
        first["taxon"] in i["anc"] + [i["taxon"]] for i in others if i["taxon"] == ct
    )


def scored(rows) -> pd.DataFrame:
    """One row per non-casual record whose first own ID carries a ``vision`` flag."""
    out, seen = [], set()
    for r in rows:
        first = _first_own(r)
        if r["id"] in seen or r["quality_grade"] == "casual" or not first:
            continue
        if first["vision"] is None:
            continue
        seen.add(r["id"])
        others = [i for i in r["idents"] if not i["own"] and i["current"]]
        ct = r["community_taxon_id"]
        species = first["rank"] == "species"
        tested = species and bool(others)
        month = int(r["created_at"][5:7]) if r["created_at"] else 1
        out.append(
            {
                "id": r["id"],
                "group": r["iconic"] or "unknown",
                "source": "cv" if first["vision"] else "typed",
                "species": species,
                "tested": tested,
                "overturned": tested and ct is not None and not _upheld(first, others, ct),
                "first_taxon": first["taxon"],
                "observer_idents": r.get("observer_idents"),
                "quarter": f"{(r['created_at'] or '')[:4]}Q{(month - 1) // 3 + 1}",
            }
        )
    df = pd.DataFrame(out)
    if len(df):
        bins = [-np.inf, *[c - 0.5 for c in EXPERIENCE_CUTS], np.inf]
        idents = pd.to_numeric(df["observer_idents"], errors="coerce").fillna(0)
        df["experience"] = pd.cut(idents, bins, labels=EXPERIENCE).astype(str)
    return df


def table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Per stratum and source: first IDs, species-rank share, tested records and overturn rate."""
    if df.empty:
        return pd.DataFrame(columns=TABLE_COLUMNS)
    g = df.groupby([by, "source"])
    out = g.agg(
        n=("id", "size"), species=("species", "mean"), tested=("tested", "sum")
    ).reset_index()
    out["overturned"] = g["overturned"].sum().to_numpy()
    out["overturn"] = out["overturned"] / out["tested"].where(out["tested"] > 0)
    return out.rename(columns={by: "stratum"})[TABLE_COLUMNS]


def within_species(df: pd.DataFrame) -> tuple[float, int]:
    """Mantel-Haenszel risk ratio of typed to CV overturn within first-ID species, and strata."""
    t = df[df["tested"]] if "tested" in df.columns else df
    num = den = 0.0
    strata = 0
    for _, s in t.groupby("first_taxon"):
        cv, ty = s[s["source"] == "cv"], s[s["source"] == "typed"]
        if cv.empty or ty.empty:
            continue
        strata += 1
        num += ty["overturned"].sum() * len(cv) / len(s)
        den += cv["overturned"].sum() * len(ty) / len(s)
    return (num / den if den else float("nan")), strata


def matched_table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Per stratum of ``by``: crude and species-matched (Mantel-Haenszel) typed/CV overturn
    ratios over tested records. The absolute gap can close across strata while the matched
    ratio does not, which says the closing is species composition, not a change in the gap."""
    rows = []
    for stratum, s in df[df["tested"]].groupby(by):
        rate = s.groupby("source")["overturned"].mean()
        if {"cv", "typed"} <= set(rate.index):
            crude = rate["typed"] / rate["cv"] if rate["cv"] else np.nan
            rows.append((stratum, len(s), crude, *within_species(s)))
    return pd.DataFrame(rows, columns=["stratum", "tested", "crude", "matched", "species"])


def other_ids(rows, df: pd.DataFrame) -> pd.DataFrame:
    """Other identifiers' current IDs on tested records: ``source`` of the first ID, ``same`` when
    the ID sits on the first taxon's lineage (the taxon, a refinement of it or an ancestor), as
    ``_upheld`` counts agreement, ``vision`` of that ID, and the identifier's ``experience`` bin."""
    src = df.drop_duplicates("id").set_index("id")
    out, seen = [], set()
    for r in rows:
        if r["id"] in seen or r["id"] not in src.index or not src.at[r["id"], "tested"]:
            continue
        seen.add(r["id"])
        first = _first_own(r)
        for i in r["idents"]:
            if not i["own"] and i["current"]:
                n = i.get("user_idents")
                same = _on_lineage(i, first)
                out.append((src.at[r["id"], "source"], same, i["vision"], n))
    o = pd.DataFrame(out, columns=["source", "same", "vision", "user_idents"])
    o["vision"] = o["vision"].fillna(False).astype(bool)
    bins = [-np.inf, *[c - 0.5 for c in EXPERIENCE_CUTS], np.inf]
    idents = pd.to_numeric(o["user_idents"], errors="coerce").fillna(0)
    o["experience"] = pd.cut(idents, bins, labels=EXPERIENCE).astype(str)
    return o


def identifier_cv_table(rows, df: pd.DataFrame) -> pd.DataFrame:
    """Per first-ID source: other identifiers' current IDs on tested records, split by whether they
    name the first taxon or another, and the share of each that was itself a CV suggestion.

    Public corrections are not all human: an identifier can accept a suggestion too. The blind
    page offers none, so this is the part of public detection d a blind consensus cannot carry.
    """
    o = other_ids(rows, df)
    g = o.groupby(["source", "same"])["vision"].agg(["size", "mean"]).unstack("same")
    g = g.reindex(columns=pd.MultiIndex.from_product([["size", "mean"], [True, False]]))
    out = pd.DataFrame(
        {
            "source": g.index,
            "same": g[("size", True)].fillna(0).astype(int).to_numpy(),
            "same_cv": g[("mean", True)].to_numpy(),
            "other": g[("size", False)].fillna(0).astype(int).to_numpy(),
            "other_cv": g[("mean", False)].to_numpy(),
        }
    )
    return out.reset_index(drop=True)


def corrector_table(rows, df: pd.DataFrame) -> pd.DataFrame:
    """Per first-ID source and identifier experience bin: other identifiers' current IDs on tested
    records and the share of them that name another taxon than the first ID.

    Who does the correcting: if disagreement with CV-accepted names comes from the most experienced
    identifiers, a blitz that wants CV errors caught has to recruit them. Identifiers whose count
    the read-back does not carry fall in the lowest bin.
    """
    o = other_ids(rows, df)
    g = o.groupby(["source", "experience"], observed=True)["same"]
    out = g.agg(ids="size", other=lambda s: int((~s).sum())).reset_index()
    out["other_share"] = out["other"] / out["ids"]
    order = {e: k for k, e in enumerate(EXPERIENCE)}
    out = out.sort_values(
        ["source", "experience"], key=lambda c: c.map(order) if c.name == "experience" else c
    )
    return out.reset_index(drop=True)


def latency_table(rows, df: pd.DataFrame) -> pd.DataFrame:
    """Per first-ID source and outcome: hours from the first own ID to the first other identifier's
    ID after it on tested records, withdrawn or not, as median and the share within a day.

    Public overturn is error times detection, and detection takes time: a first ID that ends up
    overturned waits far longer for its first other look than one that is upheld, so a pull of
    young records reads as fewer errors than there are. ``PARAMS`` keeps records months old.
    """
    src = df.drop_duplicates("id").set_index("id")
    out, seen = [], set()
    for r in rows:
        if r["id"] in seen or r["id"] not in src.index or not src.at[r["id"], "tested"]:
            continue
        seen.add(r["id"])
        t0 = pd.Timestamp(_first_own(r)["created"])
        hours = [
            (pd.Timestamp(i["created"]) - t0).total_seconds() / 3600
            for i in r["idents"]
            if not i["own"] and i["created"] and pd.Timestamp(i["created"]) >= t0
        ]
        if hours:
            out.append((src.at[r["id"], "source"], src.at[r["id"], "overturned"], min(hours)))
    o = pd.DataFrame(out, columns=["source", "overturned", "hours"])
    g = o.groupby(["source", "overturned"])["hours"]
    out = g.agg(n="size", median_hours="median", within_day=lambda s: (s <= 24).mean())
    return out.reset_index()


def level_table(rows, levels: pd.DataFrame) -> pd.DataFrame:
    """Per Identify level: records, share with another current ID, share of those contradicting
    the label the level was scored on (an ID off the label's lineage: not the label, a refinement
    of it or one of its ancestors)."""
    lab = levels.drop_duplicates("id").set_index("id")
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    seen = set()
    for r in rows:
        if r["id"] in seen or r["id"] not in lab.index:
            continue
        seen.add(r["id"])
        c = acc[LEVEL_NAMES[level_number(lab.at[r["id"], "level"])]]
        others = [i for i in r["idents"] if not i["own"] and i["current"]]
        c[0] += 1
        if others:
            c[1] += 1
            ref = {"taxon": lab.at[r["id"], "taxon_id"], "anc": []}
            ref["anc"] = next((i["anc"] for i in r["idents"] if i["taxon"] == ref["taxon"]), [])
            c[2] += any(not _on_lineage(i, ref) for i in others)
    out = pd.DataFrame(
        [(k, n, o / n if n else np.nan, d / o if o else np.nan) for k, (n, o, d) in acc.items()],
        columns=["level", "n", "has_other", "contradicted"],
    )
    return out.set_index("level").reindex([k for k in LEVEL_NAMES if k in acc]).reset_index()


def load(path: str | Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("--out", required=True)
    p.add_argument("--blocks", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    t = sub.add_parser("tables")
    t.add_argument("records")
    t.add_argument("--levels", help="identify.parquet from the atlas manifest")
    a = ap.parse_args(argv)
    if a.cmd == "pull":
        n = 0
        with open(a.out, "w") as f:
            for r in pull(a.blocks, a.seed):
                f.write(json.dumps(r) + "\n")
                n += 1
        print(f"{n} records -> {a.out}")
        return 0
    rows = load(a.records)
    df = scored(rows)
    for by in ("group", "experience", "quarter"):
        print(table(df, by).to_string(index=False, float_format="{:.3f}".format))
        print()
    rr, k = within_species(df)
    print(f"within-species Mantel-Haenszel ratio typed/cv = {rr:.2f} over {k} species")
    print(matched_table(df, "experience").to_string(index=False, float_format="{:.2f}".format))
    print()
    print(identifier_cv_table(rows, df).to_string(index=False, float_format="{:.3f}".format))
    print()
    print(corrector_table(rows, df).to_string(index=False, float_format="{:.3f}".format))
    print()
    print(latency_table(rows, df).to_string(index=False, float_format="{:.2f}".format))
    if a.levels:
        print()
        lv = level_table(rows, pd.read_parquet(a.levels, columns=["id", "taxon_id", "level"]))
        print(lv.to_string(index=False, float_format="{:.3f}".format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
