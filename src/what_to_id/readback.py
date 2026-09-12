"""Outcome read-back for served records, meant to run at freeze plus 30 days.

``readback`` fetches the current state of served ids, ``outcomes`` joins that state to the
assignment arms and the pool and tallies per-arm shares. ``--dry-run`` skips the fetch and
reports the unengaged share per iconic group from the pool alone.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import inat

OBS_COLUMNS = (
    "id",
    "quality_grade",
    "community_rank",
    "taxon_rank",
    "ident_count",
    "n_identifiers",
    "last_ident_at",
)
IDENT_COLUMNS = ("id", "user_id", "created_at", "taxon_id")
OUTCOME_COLUMNS = (
    "arm",
    "n_served",
    "share_species",
    "share_engaged",
    "unengaged",
    "weighted_rg",
)


def summarise(obs: dict) -> dict:
    """Reduce one raw observation to its read-back fields plus its identification list."""
    idents = obs.get("identifications") or []
    taxon = obs.get("taxon") or {}
    community = obs.get("community_taxon") or {}
    flat = [
        {
            "user_id": (i.get("user") or {}).get("id"),
            "created_at": i.get("created_at"),
            "taxon_id": (i.get("taxon") or {}).get("id"),
        }
        for i in idents
    ]
    users = {f["user_id"] for f in flat if f["user_id"] is not None}
    stamps = [f["created_at"] for f in flat if f["created_at"]]
    return {
        "id": int(obs["id"]),
        "quality_grade": obs.get("quality_grade"),
        "community_rank": community.get("rank") or None,
        "taxon_rank": taxon.get("rank") if taxon else None,
        "ident_count": int(obs.get("identifications_count") or len(flat)),
        "n_identifiers": len(users),
        "last_ident_at": max(stamps) if stamps else None,
        "identifications": flat,
    }


def readback(
    ids: Sequence[int],
    *,
    fetch: Callable[..., list[dict]] = inat.fetch_by_ids,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch served ids and return (one row per id, long identification table)."""
    ids = [int(i) for i in ids]
    summaries = {s["id"]: s for s in map(summarise, fetch(ids))}
    obs_rows: list[dict] = []
    ident_rows: list[dict] = []
    for i in ids:
        s = summaries.get(i)
        if s is None:
            obs_rows.append({"id": i, **{c: None for c in OBS_COLUMNS[1:]}})
            continue
        obs_rows.append({c: s[c] for c in OBS_COLUMNS})
        ident_rows.extend({"id": i, **f} for f in s["identifications"])
    obs_df = pd.DataFrame(obs_rows, columns=list(OBS_COLUMNS))
    for c in ("ident_count", "n_identifiers"):
        obs_df[c] = obs_df[c].astype("Int64")
    idents_df = pd.DataFrame(ident_rows, columns=list(IDENT_COLUMNS))
    return obs_df, idents_df


def _arms(assign_df: pd.DataFrame | None, pool_df: pd.DataFrame) -> pd.DataFrame:
    if assign_df is None:
        return pd.DataFrame({"id": pool_df["id"].to_numpy(), "arm": "pool"})
    missing = [c for c in ("id", "arm") if c not in assign_df.columns]
    if missing:
        raise ValueError(f"assign_df missing columns {missing}")
    return assign_df[["id", "arm"]].drop_duplicates("id")


def outcomes(
    obs_df: pd.DataFrame | None,
    assign_df: pd.DataFrame | None,
    pool_df: pd.DataFrame,
) -> pd.DataFrame:
    """Per-arm outcome shares. ``obs_df=None`` falls back to the pool's own ident counts."""
    arms = _arms(assign_df, pool_df)
    if obs_df is None:
        obs_df = pd.DataFrame(
            {
                "id": pool_df["id"],
                "quality_grade": "needs_id",
                "community_rank": None,
                "ident_count": pool_df["ident_count"],
            }
        )
    df = arms.merge(obs_df, on="id", how="left")
    score_col = "cell_score" if "cell_score" in pool_df.columns else None
    if score_col:
        df = df.merge(pool_df[["id", score_col]].drop_duplicates("id"), on="id", how="left")
    ident = pd.to_numeric(df["ident_count"], errors="coerce").fillna(0).astype(float)
    is_rg = df["quality_grade"].eq("research")
    df = df.assign(
        _species=(df["community_rank"].eq("species") | is_rg).astype(float),
        _engaged=(ident >= 2).astype(float),
        _unengaged=(ident <= 1).astype(float),
        _rg_score=np.where(is_rg, df[score_col].fillna(0.0) if score_col else 0.0, 0.0),
    )
    g = df.groupby("arm", sort=True)
    out = pd.DataFrame(
        {
            "n_served": g.size(),
            "share_species": g["_species"].mean(),
            "share_engaged": g["_engaged"].mean(),
            "unengaged": g["_unengaged"].mean(),
            "weighted_rg": g["_rg_score"].sum() if score_col else np.nan,
        }
    ).reset_index()
    return out[list(OUTCOME_COLUMNS)]


def to_markdown(outcomes_df: pd.DataFrame) -> str:
    """Simple pipe table, shares as percentages."""
    cols = list(outcomes_df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in outcomes_df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if c == "n_served":
                cells.append(str(int(v)))
            elif c in ("share_species", "share_engaged", "unengaged"):
                cells.append(f"{100 * v:.1f}%")
            elif isinstance(v, float):
                cells.append("nan" if np.isnan(v) else f"{v:.3f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def dry_run(pool_df: pd.DataFrame) -> pd.DataFrame:
    """Unengaged share per iconic group from the pool alone, no API calls."""
    assign = pd.DataFrame({"id": pool_df["id"], "arm": pool_df["iconic_taxon"].fillna("unknown")})
    return outcomes(None, assign, pool_df)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read back outcomes for served records.")
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--assign", type=Path, help="assignment parquet with id and arm columns")
    ap.add_argument("--out", type=Path, help="outcomes parquet; idents written next to it")
    ap.add_argument("--dry-run", action="store_true", help="pool only, no fetch")
    a = ap.parse_args(argv)
    pool = inat.load_pool(a.pool)
    if a.dry_run:
        res = dry_run(pool)
        print(to_markdown(res))
        return 0
    if a.assign is None or a.out is None:
        ap.error("--assign and --out are required unless --dry-run")
    assign = pd.read_parquet(a.assign, engine="pyarrow")
    ids = assign["id"].drop_duplicates().tolist()
    obs_df, idents_df = readback(ids)
    res = outcomes(obs_df, assign, pool)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    res.to_parquet(a.out, engine="pyarrow", index=False)
    obs_df.to_parquet(a.out.with_name(a.out.stem + "_obs.parquet"), engine="pyarrow", index=False)
    idents_df.to_parquet(
        a.out.with_name(a.out.stem + "_idents.parquet"), engine="pyarrow", index=False
    )
    print(to_markdown(res))
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
