"""Sample the blind page's ``records.json`` from the pool, stratified by group and Identify level.

    python -m what_to_id.blind_sample --pool pool.parquet --per-stratum 20 --seed 1 \\
        [--levels identify.parquet] [--planted planted.json] --out records.json

Takes up to ``--per-stratum`` records from each group, or from each group and level when
``--levels`` is given (``id`` and ``level`` columns as ``identify_levels`` writes them, numbers or
names; level 0 or ``none`` is skipped). ``--planted`` is ``[{"id", "group", "photos", "taxon_id"},
...]``, expert-settled records mixed in; their ``taxon_id`` goes to ``planted.parquet`` next to
``--out`` (``record_id``, ``taxon_id``, the frame ``blind_skill.fit`` takes) and never into
``records.json``. Records without a group are skipped. Output order is shuffled with the seed; the
page reorders per login.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

POOL_COLUMNS = ["id", "iconic_taxon", "photo_url"]
STRATA_COLUMNS = ["group", "level", "n"]


def sample(
    pool: pd.DataFrame, per_stratum: int, seed: int, levels: pd.DataFrame | None = None
) -> pd.DataFrame:
    """``id, group, level, photo_url`` rows, at most ``per_stratum`` per group (and level)."""
    df = pool.loc[pool["iconic_taxon"].notna() & (pool["iconic_taxon"] != ""), POOL_COLUMNS]
    df = df.rename(columns={"iconic_taxon": "group"})
    if levels is not None:
        keep = levels["level"].notna() & ~levels["level"].isin([0, "none"])
        lv = levels.loc[keep, ["id", "level"]].drop_duplicates("id")
        df = df.merge(lv, on="id")
    else:
        df = df.assign(level=0)
    rng = np.random.default_rng(seed)
    df = df.iloc[rng.permutation(len(df))]
    out = df.groupby(["group", "level"], sort=True).head(per_stratum)
    return out.iloc[rng.permutation(len(out))].reset_index(drop=True)


def strata(records: pd.DataFrame) -> pd.DataFrame:
    """Count per group and level, for the console."""
    return records.groupby(["group", "level"]).size().rename("n").reset_index()[STRATA_COLUMNS]


def to_records(sampled: pd.DataFrame, planted: list[dict], seed: int) -> list[dict]:
    """The page's records, sampled and planted mixed, planted ``taxon_id`` dropped."""
    recs = [
        {"id": int(r.id), "group": r.group, "photos": [r.photo_url], "planted": False}
        for r in sampled.itertuples()
    ]
    ids = {r["id"] for r in recs}
    for p in planted:
        if int(p["id"]) in ids:
            raise ValueError(f"planted record {p['id']} is also in the sample")
        recs.append(
            {"id": int(p["id"]), "group": p["group"], "photos": p["photos"], "planted": True}
        )
    rng = np.random.default_rng(seed)
    return [recs[i] for i in rng.permutation(len(recs))]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.blind_sample", description=__doc__)
    p.add_argument("--pool", type=Path, required=True)
    p.add_argument("--levels", type=Path, help="identify parquet with id and level")
    p.add_argument("--planted", type=Path, help="expert-settled records JSON")
    p.add_argument("--per-stratum", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True, help="records.json for page_blind")
    a = p.parse_args(argv)
    if a.per_stratum < 1:
        p.error("--per-stratum must be at least 1")
    pool = pd.read_parquet(a.pool, columns=POOL_COLUMNS)
    levels = pd.read_parquet(a.levels, columns=["id", "level"]) if a.levels else None
    planted = json.loads(a.planted.read_text()) if a.planted else []
    sampled = sample(pool, a.per_stratum, a.seed, levels)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(to_records(sampled, planted, a.seed)))
    truth = pd.DataFrame(
        {
            "record_id": [int(x["id"]) for x in planted],
            "taxon_id": [int(x["taxon_id"]) for x in planted],
        }
    )
    truth.to_parquet(a.out.with_name("planted.parquet"), index=False)
    print(strata(sampled).to_string(index=False))
    print(f"blind_sample: {len(sampled)} sampled + {len(planted)} planted -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
