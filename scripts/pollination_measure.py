"""Does the Pollination page help pollinators get identified? Snapshots, a control and a baseline.

    export PYTHONPATH=src; P="python scripts/pollination_measure.py"
    $P snapshot --obs pollination-obs.json --out t0.parquet
    $P control --out c0.parquet --per-group 400
    $P snapshot --from t0.parquet --out t1.parquet    # later
    $P snapshot --from c0.parquet --out c1.parquet    # later
    $P report --window t0.parquet t1.parquet c0.parquet c1.parquet
    $P baseline --d1 2025-04-01 --d2 2025-10-31

Treated: the records of pollination-obs.json (BC, field "Interaction->Visited flower of"); the page
lists all of them, so there is no untreated group inside it. Control: BC needs_id observations of
the same broad groups that lack the field, so the page cannot list them. `snapshot --from` re-reads
the ids of an earlier snapshot, which is how both arms are followed over time. `report` takes the
records that were needs_id at the first snapshot of each arm, weights the control to the treated
group mix, and prints the change in research-grade and species-rank share per arm and the gap
(treated minus control) with an observer-clustered bootstrap interval. Two `--window`s print the
change of the gap (the second, post page change, minus the first, the pre-period gap).
`baseline` replays identification histories from iNaturalist: of records not research grade one
day after creation, the share that reached research grade or species rank within 30 and 60 days.
Public GETs only, 1 s pause, User-Agent what-to-id.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.foodweb_obs import API, BC_PLACE_ID, FIELDS, PER_PAGE

FIELD_ID = FIELDS["visit"][1]
SPECIES = 10  # rank_level of species; subspecies and below are smaller
GROUPS = [  # first match wins: (name, iNat taxon id)
    ("bee", 630955),
    ("syrphid", 49995),
    ("diptera", 47822),
    ("lepidoptera", 47157),
    ("coleoptera", 47208),
    ("hymenoptera", 47201),
]
COLS = [
    "id", "taxon_id", "taxon_rank", "taxon_rank_level", "quality_grade", "identifications_count",
    "fetched_on", "created_at", "observed_on", "user_id", "group", "has_field",
]  # fmt: skip


def get(params: dict, pause: float = 1.0) -> dict:
    import requests

    r = requests.get(API, params=params, timeout=120, headers={"User-Agent": "what-to-id"})
    r.raise_for_status()
    time.sleep(pause)
    return r.json()


def group_of(t: dict | None) -> str:
    anc = set(((t or {}).get("ancestor_ids") or []) + [(t or {}).get("id")])
    return next((n for n, i in GROUPS if i in anc), "other")


def row(o: dict, fetched_on: str) -> dict:
    t = o.get("taxon") or {}
    return {
        "id": o["id"],
        "taxon_id": t.get("id"),
        "taxon_rank": t.get("rank"),
        "taxon_rank_level": t.get("rank_level"),
        "quality_grade": o.get("quality_grade"),
        "identifications_count": o.get("identifications_count"),
        "fetched_on": fetched_on,
        "created_at": o.get("created_at"),
        "observed_on": o.get("observed_on"),
        "user_id": (o.get("user") or {}).get("id"),
        "group": group_of(t),
        "has_field": any(f.get("field_id") == FIELD_ID for f in o.get("ofvs") or []),
    }


def fetch_ids(ids: list[int]) -> list[dict]:
    out = []
    for i in range(0, len(ids), PER_PAGE):
        p = {"id": ",".join(map(str, ids[i : i + PER_PAGE])), "per_page": PER_PAGE}
        out += get(p)["results"]
    return out


def snapshot(ids: list[int]) -> pd.DataFrame:
    if not ids:
        raise SystemExit("no ids to snapshot")
    today = date.today().isoformat()
    return pd.DataFrame([row(o, today) for o in fetch_ids(ids)], columns=COLS)


def control(per_group: int, d1: str, d2: str, seed: int) -> pd.DataFrame:
    """Random BC needs_id observations without the field, up to per_group in each group."""
    today, out = date.today().isoformat(), []
    for _, tid in GROUPS:
        got = 0
        for page in range(1, 1 + -(-per_group * 2 // PER_PAGE)):  # x2: some carry the field
            p = {"place_id": BC_PLACE_ID, "taxon_id": tid, "quality_grade": "needs_id",
                 "d1": d1, "d2": d2, "order_by": "random", "page": page,
                 "per_page": PER_PAGE, "only_id": "false", "random_seed": seed}  # fmt: skip
            res = [row(o, today) for o in get(p)["results"] if o.get("taxon")]
            out += [r for r in res if not r["has_field"]]
            got += len(res)
            if len(res) < PER_PAGE:
                break
    df = pd.DataFrame(out, columns=COLS).drop_duplicates("id")
    # one record sits in several top groups (bee in hymenoptera): keep it once, in its own group
    return df.groupby("group", group_keys=False).head(per_group)


# ---- report ----


def cohort(first: pd.DataFrame, last: pd.DataFrame) -> pd.DataFrame:
    """Records needs_id at the first snapshot, with their state at the last (gone ones dropped)."""
    f = first[first.quality_grade == "needs_id"]
    d = f.merge(last, on="id", suffixes=("0", "1"))
    d["rg0"], d["rg1"] = 0.0, (d.quality_grade1 == "research").astype(float)
    d["sp0"] = (d.taxon_rank_level0 <= SPECIES).astype(float)
    d["sp1"] = (d.taxon_rank_level1 <= SPECIES).astype(float)
    return d.rename(columns={"group0": "group", "user_id0": "user"})[
        ["id", "group", "user", "rg0", "rg1", "sp0", "sp1"]
    ]


def weights(t: pd.DataFrame, c: pd.DataFrame) -> pd.Series:
    """Control weights so its group mix equals the treated mix (groups absent from control drop)."""
    share = t.group.value_counts(normalize=True) / c.group.value_counts(normalize=True)
    return c.group.map(share).fillna(0.0)


def _changes(t: pd.DataFrame, c: pd.DataFrame, wc: np.ndarray) -> np.ndarray:
    """rg change, sp change for treated, control, then the gaps."""
    out = []
    for m in ("rg", "sp"):
        dt = (t[m + "1"] - t[m + "0"]).mean()
        dc = np.average(c[m + "1"] - c[m + "0"], weights=wc) if wc.sum() else np.nan
        out += [dt, dc, dt - dc]
    return np.array(out)


def gap_table(t: pd.DataFrame, c: pd.DataFrame, reps: int = 1000, seed: int = 0) -> dict:
    """Changes (percentage points) per arm and gap, with observer-clustered bootstrap intervals."""
    wc = weights(t, c).to_numpy()
    est = _changes(t, c, wc)
    rng = np.random.default_rng(seed)
    ut, uc = t.user.unique(), c.user.unique()
    gt, gc = dict(tuple(t.groupby("user"))), dict(tuple(c.groupby("user")))
    boots = []
    for _ in range(reps):
        bt = pd.concat([gt[u] for u in rng.choice(ut, len(ut))])
        bc = pd.concat([gc[u] for u in rng.choice(uc, len(uc))])
        boots.append(_changes(bt, bc, weights(bt, bc).to_numpy()))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5], axis=0)
    return {
        "n_treated": len(t),
        "n_control": len(c),
        "est": est * 100,
        "lo": lo * 100,
        "hi": hi * 100,
        "boots": np.array(boots) * 100,
    }


def print_window(name: str, g: dict) -> None:
    print(f"\nwindow {name}: treated n={g['n_treated']}, control n={g['n_control']}")
    print(f"{'measure':<14}{'treated':>9}{'control':>9}{'gap':>9}  gap 95% CI (pp)")
    for i, m in enumerate(("research grade", "species rank")):
        e, lo, hi = g["est"][3 * i : 3 * i + 3], g["lo"][3 * i + 2], g["hi"][3 * i + 2]
        print(f"{m:<14}{e[0]:>9.1f}{e[1]:>9.1f}{e[2]:>9.1f}  [{lo:.1f}, {hi:.1f}]")


def report(windows: list[list[str]]) -> int:
    gaps = []
    for w in windows:
        t0, t1, c0, c1 = (pd.read_parquet(p) for p in w)
        t, c = cohort(t0, t1), cohort(c0, c1)
        if t.empty or c.empty:
            print(f"empty cohort for {w}", file=sys.stderr)
            return 1
        gaps.append(gap_table(t, c))
        print_window(" ".join(Path(x).stem for x in w), gaps[-1])
    if len(gaps) == 2:
        d = gaps[1]["est"] - gaps[0]["est"]
        # the arms and windows are disjoint samples, so the bootstrap differences are independent
        b = gaps[1]["boots"] - gaps[0]["boots"]
        lo, hi = np.nanpercentile(b, [2.5, 97.5], axis=0)
        print("\nchange of the gap, window 2 minus window 1 (pp)")
        for i, m in enumerate(("research grade", "species rank")):
            print(f"{m:<14}{d[3 * i + 2]:>9.1f}  [{lo[3 * i + 2]:.1f}, {hi[3 * i + 2]:.1f}]")
    return 0


# ---- baseline ----


def community(ids: list[dict]) -> tuple[int | None, int, bool]:
    """(taxon id, rank_level, agreed) from one identification per user.

    One identification is the shown taxon. From two on, the deepest node with at least two
    identifications at or below it and more than 2/3 of the identifications that are not on an
    ancestor of it (an ancestor identification neither agrees nor disagrees).
    """
    if not ids:
        return None, 99, False
    taxa = [i["taxon"] for i in ids]
    if len(taxa) == 1:
        return taxa[0]["id"], taxa[0]["rank_level"], False
    path = {}  # node -> its ancestors
    level = {}  # node -> rank_level (species for the species of a subspecies)
    for t in taxa:
        a = t["ancestor_ids"]
        level[t["id"]] = t["rank_level"]
        if t["rank_level"] <= SPECIES and t.get("min_species_taxon_id"):
            level.setdefault(t["min_species_taxon_id"], SPECIES)
        for k, n in enumerate(a + [t["id"]]):
            path.setdefault(n, set(a[:k]))
    best = None
    for n, anc in path.items():
        agree = sum(n == t["id"] or n in t["ancestor_ids"] for t in taxa)
        neutral = sum(t["id"] in anc for t in taxa)
        if (
            agree >= 2
            and agree / (len(taxa) - neutral) > 2 / 3
            and (best is None or len(anc) > best[0])
        ):
            best = (len(anc), n)
    return (best[1], level.get(best[1], 99), True) if best else (None, 99, False)


def state(idents: list[dict], at: pd.Timestamp) -> tuple[bool, bool]:
    """(research grade, species rank) as the identifications up to `at` would show it."""
    last = {}
    for i in sorted(idents, key=lambda i: i["created_at"]):
        if pd.Timestamp(i["created_at"]).tz_convert("UTC") <= at:
            last[i["user"]["id"]] = i
    # a user whose latest identification is not current withdrew it
    use = [i for i in last.values() if i["current"] and i.get("taxon") and not i.get("hidden")]
    _, rank, agreed = community(use)
    return agreed and rank <= SPECIES, rank <= SPECIES


def mde(p: float, n1: int, n2: int, deff: float = 1.0, z: float = 1.96 + 0.84) -> float:
    """Smallest true difference in a share detected at 5% two-sided and 80% power."""
    return z * float(np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2) * deff))


def replay(o: dict) -> dict | None:
    """Share-relevant states at day 1, 30, 60, 90 after creation, or None (casual, no photo)."""
    if o["quality_grade"] == "casual":
        return None
    c = pd.Timestamp(o["created_at"]).tz_convert("UTC")
    r = {"id": o["id"], "user": o["user"]["id"], "group": group_of(o.get("taxon"))}
    for d in (1, 30, 60, 90, 9999):
        r[f"rg{d}"], r[f"sp{d}"] = state(o["identifications"], c + pd.Timedelta(days=d))
    r["now_ok"] = r["rg9999"] == (o["quality_grade"] == "research")
    return r


def baseline_fetch(d1: str, d2: str, per_month: int) -> pd.DataFrame:
    """Field records in the window (all) and random no-field ones of the same groups per month."""
    out = []
    p = {"place_id": BC_PLACE_ID, f"field:{FIELDS['visit'][0]}": "", "d1": d1, "d2": d2,
         "per_page": 100, "page": 1}  # fmt: skip
    while True:
        res = get(p)["results"]
        out += [(o, True) for o in res]
        if len(res) < 100:
            break
        p["page"] += 1
    months = pd.period_range(d1, d2, freq="M")
    for m in months:
        a, b = (
            max(m.start_time.date(), date.fromisoformat(d1)),
            min(m.end_time.date(), date.fromisoformat(d2)),
        )
        for _, tid in GROUPS:
            q = {"place_id": BC_PLACE_ID, "taxon_id": tid, "d1": a.isoformat(), "d2": b.isoformat(),
                 "order_by": "random", "per_page": per_month, "random_seed": 1}  # fmt: skip
            out += [(o, False) for o in get(q)["results"]]
    seen, rows = set(), []
    for o, f in out:
        if o["id"] in seen or not o.get("taxon"):
            continue
        seen.add(o["id"])
        has = f or any(x.get("field_id") == FIELD_ID for x in o.get("ofvs") or [])
        r = replay(o)
        if r:
            rows.append({**r, "has_field": has, "month": o["observed_on"][:7]})
    return pd.DataFrame(rows)


def _wmean(x: pd.Series, w: pd.Series) -> float:
    return float(np.average(x, weights=w)) if w.sum() else float("nan")


def baseline_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per arm, among records not research grade at day 1: share research grade / species rank.

    The no-field arm is weighted to the field arm's group mix (bees dominate the field records).
    """
    d = df[~df.rg1].copy()
    mix = d[d.has_field].group.value_counts(normalize=True)
    d["w"] = np.where(
        d.has_field, 1.0, d.group.map(mix / d[~d.has_field].group.value_counts(normalize=True))
    )
    d["w"] = d.w.fillna(0.0)
    rows = []
    for name, g in d.groupby("has_field"):
        late = g[~g.rg30]  # still needs ID after 30 days: the age mix the live snapshot has
        rows.append({"arm": "field (page)" if name else "no field", "n": len(g)}
                    | {k: _wmean(g[k], g.w) for k in ("rg30", "rg60", "sp1", "sp30", "sp60")}
                    | {"n_late": len(late), "late_rg60": _wmean(late.rg60, late.w),
                       "late_rg90": _wmean(late.rg90, late.w)})  # fmt: skip
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--obs", help="pollination-obs.json")
    s.add_argument("--from", dest="src", help="an earlier snapshot parquet: re-read its ids")
    s.add_argument("--out", required=True)
    c = sub.add_parser("control")
    c.add_argument("--out", required=True)
    c.add_argument("--per-group", type=int, default=400)
    c.add_argument("--d1", default="2026-03-01")
    c.add_argument("--d2", default="2026-10-31")
    c.add_argument("--seed", type=int, default=1)
    r = sub.add_parser("report")
    r.add_argument("--window", nargs=4, action="append", required=True,
                   metavar=("T0", "T1", "C0", "C1"))  # fmt: skip
    b = sub.add_parser("baseline")
    b.add_argument("--d1", required=True)
    b.add_argument("--d2", required=True)
    b.add_argument("--per-month", type=int, default=100)
    b.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        if bool(a.obs) == bool(a.src):
            ap.error("give exactly one of --obs and --from")
        if a.obs:
            with open(a.obs) as fh:
                ids = [o["id"] for o in json.load(fh)["obs"]]
        else:
            ids = pd.read_parquet(a.src).id.tolist()
        df = snapshot(ids)
    elif a.cmd == "control":
        df = control(a.per_group, a.d1, a.d2, a.seed)
    elif a.cmd == "report":
        return report(a.window)
    else:
        df = baseline_fetch(a.d1, a.d2, a.per_month)
        print(
            f"replay agrees with iNaturalist's grade on {df.now_ok.mean():.1%} of {len(df)} records"
        )
        t = baseline_table(df)
        print(t.round(3).to_string(index=False))
        if len(t) == 2:
            f, n = t.iloc[0], t.iloc[1]
            print(f"MDE (pp) on rg60 at n={int(f.n)} vs {int(n.n)}: "
                  f"{100 * mde(float(n.rg60), int(f.n), int(n.n)):.1f}")  # fmt: skip
        if a.out:
            df.to_parquet(a.out)
        return 0
    df.to_parquet(a.out)
    print(f"{len(df)} records -> {a.out}; {df.quality_grade.value_counts().to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
