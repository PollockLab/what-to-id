"""Served log: every daily build's served records by list letter, appended to one parquet.

The log never holds an arm name. Only the private list key maps letters to lists, so the log can
sit next to the pool state in public release assets, and the read-back is a join on it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

COLUMNS = ["build_date", "label", "group", "batch_index", "position", "id", "cell_score"]


def served_rows(
    batches_df: pd.DataFrame, labels: Mapping[str, str], pool: pd.DataFrame, build_date: str
) -> pd.DataFrame:
    """One row per served record of this build, with the list letter in place of the arm."""
    missing = set(batches_df["arm"]) - set(labels)
    if missing:
        raise ValueError(f"no list letter for arms {sorted(missing)}")
    out = batches_df[["arm", "group", "batch_id", "position", "id"]].copy()
    out["label"] = out["arm"].map(labels)
    out["batch_index"] = out["batch_id"].str.rsplit("-", n=1).str[-1].astype("int64")
    score = pool.set_index("id")["cell_score"] if "cell_score" in pool else pd.Series(dtype=float)
    out["id"] = out["id"].astype("int64")
    out["cell_score"] = out["id"].map(score).astype("float64")
    out["build_date"] = str(build_date)
    return out[COLUMNS].reset_index(drop=True)


def append_served(path: Path | str, rows: pd.DataFrame) -> pd.DataFrame:
    """Append rows to the log at path, replacing any earlier rows of the same build date.

    Refuses a record that changes list letter between builds: with a keyed assignment that only
    happens if the key changed, and a changed key would split one record's IDs over two lists.
    """
    path = Path(path)
    if list(rows.columns) != COLUMNS:
        raise ValueError(f"served rows must have columns {COLUMNS}, got {list(rows.columns)}")
    if path.exists():
        old = pd.read_parquet(path)
        if list(old.columns) != COLUMNS:
            raise ValueError(f"{path}: columns {list(old.columns)}, expected {COLUMNS}")
        old = old[~old["build_date"].isin(rows["build_date"].unique())]
        seen = old[["id", "label"]].drop_duplicates("id")
        both = rows[["id", "label"]].merge(seen, on="id", suffixes=("", "_before"))
        moved = both[both["label"] != both["label_before"]]
        if not moved.empty:
            raise ValueError(
                f"{len(moved)} records changed list letter since an earlier build "
                f"(e.g. id {int(moved['id'].iloc[0])}); was the list key changed?"
            )
        rows = pd.concat([old, rows], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    rows.to_parquet(tmp, index=False)
    tmp.replace(path)
    return rows
