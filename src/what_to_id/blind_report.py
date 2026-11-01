"""Usage: python -m what_to_id.blind_report --consensus consensus.parquet --obs obs.parquet
--idents idents.parquet [--threshold 0.9]

The table is the error of CV-accepted versus typed first identifications, measured against a
blind consensus, which a public record cannot give because later identifiers see the suggestion.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

REPORT_COLUMNS = ["group", "source", "n", "wrong", "error", "lo", "hi"]
FIRST_COLUMNS = ["record_id", "group", "taxon_id", "vision"]
Z = 1.959964


def first_own_ids(obs: pd.DataFrame, idents: pd.DataFrame) -> pd.DataFrame:
    """Earliest identification by each observation's own observer. Needs ``iconic_taxon`` in obs."""
    if "iconic_taxon" not in obs.columns:
        raise ValueError("obs needs an iconic_taxon column (readback obs frames do not carry it)")
    own = idents[idents["user_id"] == idents["observer_id"]]
    first = own.sort_values("created_at", kind="stable").drop_duplicates("id")
    out = first.merge(obs[["id", "iconic_taxon"]].drop_duplicates("id"), on="id")
    out = out.rename(columns={"id": "record_id", "iconic_taxon": "group"})
    return out[FIRST_COLUMNS].reset_index(drop=True)


def _wilson(wrong, n):
    p = wrong / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return np.clip(c - h, 0, 1), np.clip(c + h, 0, 1)


def cv_error(consensus: pd.DataFrame, firsts: pd.DataFrame, threshold: float = 0.9):
    """Error of first own IDs against the blind consensus, by group and CV/typed source."""
    keep = consensus[(consensus["posterior"] >= threshold) & consensus["taxon_id"].notna()]
    j = keep[["record_id", "taxon_id"]].merge(firsts, on="record_id", suffixes=("_c", ""))
    if j.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    j["source"] = np.where(j["vision"].fillna(False).astype(bool), "cv", "typed")
    j["wrong"] = (j["taxon_id"] != j["taxon_id_c"]).astype(int)
    j = pd.concat([j, j.assign(group="all")])
    out = j.groupby(["group", "source"]).agg(n=("wrong", "size"), wrong=("wrong", "sum"))
    out = out.reset_index()
    out["error"] = out["wrong"] / out["n"]
    out["lo"], out["hi"] = _wilson(out["wrong"].to_numpy(float), out["n"].to_numpy(float))
    return out.sort_values(["group", "source"], ignore_index=True)[REPORT_COLUMNS]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CV versus typed first-ID error vs blind consensus")
    ap.add_argument("--consensus", required=True)
    ap.add_argument("--obs", required=True)
    ap.add_argument("--idents", required=True)
    ap.add_argument("--threshold", type=float, default=0.9)
    a = ap.parse_args(argv)
    firsts = first_own_ids(pd.read_parquet(a.obs), pd.read_parquet(a.idents))
    table = cv_error(pd.read_parquet(a.consensus), firsts, a.threshold)
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
