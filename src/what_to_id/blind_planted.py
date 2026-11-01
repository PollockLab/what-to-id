"""Usage: python -m what_to_id.blind_planted --obs obs.parquet --idents idents.parquet
--pool pool.parquet [--per-kind 25] [--min-others 2] [--seed 0] --out planted-candidates.json

Candidate planted records for the blind track: research-grade records whose settled name at least
``min_others`` identifiers other than the observer currently share, tagged by whether the
observer's first species-rank ID was CV-accepted or typed and whether it held or failed. A coarser
first ID is a refinement, not a failure, and is skipped, as in the vision-flag pilot. An expert
confirms the names, then the file is the ``--planted`` input of ``blind_sample``. The community can
be wrong, so these are candidates, not truth; the expert step is what makes them planted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

KINDS = ("cv_fail", "cv_hold", "typed_fail", "typed_hold")
COLUMNS = ["id", "group", "taxon_id", "kind", "photo_url"]


def candidates(obs, idents, pool, min_others: int = 2) -> pd.DataFrame:
    """Research-grade records with ``min_others`` agreeing outside identifiers, one row each."""
    settled = pool[["id", "iconic_taxon", "taxon_id", "photo_url"]].drop_duplicates("id")
    rg = obs.loc[obs["quality_grade"] == "research", ["id", "user_id"]].merge(settled, on="id")
    others = idents[(idents["user_id"] != idents["observer_id"]) & idents["current"].astype(bool)]
    agree = others.merge(rg[["id", "taxon_id"]], on=["id", "taxon_id"])
    n_agree = agree.groupby("id")["user_id"].nunique()
    rg = rg[rg["id"].isin(n_agree[n_agree >= min_others].index)]
    own = idents[idents["user_id"] == idents["observer_id"]]
    first = own.sort_values("created_at", kind="stable").drop_duplicates("id")
    first = first[first["taxon_rank"] == "species"].rename(columns={"taxon_id": "first"})
    out = rg.merge(first[["id", "first", "vision"]], on="id")
    out = out[out["first"].notna() & out["taxon_id"].notna()]
    src = np.where(out["vision"].fillna(False).astype(bool), "cv", "typed")
    fate = np.where(out["first"] == out["taxon_id"], "hold", "fail")
    out["kind"] = [f"{s}_{f}" for s, f in zip(src, fate, strict=True)]
    out = out.rename(columns={"iconic_taxon": "group"})
    return out[COLUMNS].astype({"taxon_id": int}).reset_index(drop=True)


def pick(cands: pd.DataFrame, per_kind: int, seed: int) -> list[dict]:
    """Up to ``per_kind`` shuffled records per kind, in blind_sample's planted JSON shape."""
    rng = np.random.default_rng(seed)
    rows = []
    for kind in KINDS:
        c = cands[cands["kind"] == kind]
        for r in c.iloc[rng.permutation(len(c))[:per_kind]].itertuples():
            rows.append(
                {
                    "id": int(r.id),
                    "group": r.group,
                    "photos": [r.photo_url],
                    "taxon_id": int(r.taxon_id),
                    "kind": kind,
                }
            )
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="planted record candidates for the blind track")
    for name in ("--obs", "--idents", "--pool"):
        p.add_argument(name, type=Path, required=True)
    p.add_argument("--per-kind", type=int, default=25)
    p.add_argument("--min-others", type=int, default=2)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    cands = candidates(
        pd.read_parquet(a.obs), pd.read_parquet(a.idents), pd.read_parquet(a.pool), a.min_others
    )
    rows = pick(cands, a.per_kind, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rows, indent=1) + "\n")
    counts = cands["kind"].value_counts().reindex(KINDS, fill_value=0).to_dict()
    print(f"blind_planted: candidates {counts}, wrote {len(rows)} -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
