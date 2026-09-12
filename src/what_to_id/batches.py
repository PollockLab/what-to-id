"""Cut arm orderings into fixed-size batches and build iNaturalist Identify URLs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urlencode

import numpy as np
import pandas as pd

from what_to_id.arms import Arm

IDENTIFY_URL = "https://www.inaturalist.org/observations/identify"
EXPLORE_URL = "https://www.inaturalist.org/observations"
BC_PLACE_ID = "7085"
MAX_URL_LEN = 8000
UNKNOWN_GROUP = "Unknown"


def cut_batches(ordered_ids: Sequence[int], size: int) -> list[list[int]]:
    if size < 1:
        raise ValueError("batch size must be >= 1")
    ids = [int(i) for i in ordered_ids]
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def identify_url(ids: Sequence[int], *, extra: Mapping[str, str] | None = None) -> str:
    if len(ids) == 0:
        raise ValueError("identify_url needs at least one id")
    params: dict[str, str] = {"id": ",".join(str(int(i)) for i in ids), "place_id": BC_PLACE_ID}
    if extra:
        params.update({str(k): str(v) for k, v in extra.items()})
    url = f"{IDENTIFY_URL}?{urlencode(params, safe=',')}"
    if len(url) >= MAX_URL_LEN:
        raise ValueError(
            f"identify URL is {len(url)} chars (limit {MAX_URL_LEN}); use a smaller batch"
        )
    return url


def build_batches(
    pool: pd.DataFrame,
    assign_df: pd.DataFrame,
    arms: Mapping[str, Arm],
    *,
    size: int,
    seed: int,
    max_batches: int | None = None,
) -> pd.DataFrame:
    """One row per (batch, position, id); batch_id is f"{arm}-{group}-{i:03d}".

    max_batches keeps only the first max_batches batches of each (arm, group) cut, i.e. the
    highest-priority records of that arm's ordering. None (the default) keeps every batch.
    """
    if size < 1:
        raise ValueError("batch size must be >= 1")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be >= 1")
    missing = set(assign_df["arm"].unique()) - set(arms)
    if missing:
        raise ValueError(f"assignment references arms without an Arm object: {sorted(missing)}")
    arm_of = assign_df.set_index("id")["arm"]
    unassigned = ~pool["id"].isin(arm_of.index)
    if unassigned.any():
        raise ValueError(f"{int(unassigned.sum())} pool ids have no assignment")
    pool = pool.reset_index(drop=True)
    pool_arm = pool["id"].map(arm_of).to_numpy()
    groups = pool["iconic_taxon"].fillna(UNKNOWN_GROUP).astype(str).to_numpy()
    rows: list[tuple[str, str, str, int, int]] = []
    for arm_name in sorted(arms):
        arm = arms[arm_name]
        for group in sorted(np.unique(groups[pool_arm == arm_name])):
            sub = pool[(pool_arm == arm_name) & (groups == group)].reset_index(drop=True)
            order = np.asarray(arm.order(sub, seed=seed), dtype=np.int64)
            if sorted(order.tolist()) != list(range(len(sub))):
                raise ValueError(f"arm {arm_name!r} returned an invalid permutation for {group}")
            ordered_ids = sub["id"].to_numpy(dtype=np.int64)[order]
            cut = cut_batches(ordered_ids, size)
            if max_batches is not None:
                cut = cut[:max_batches]
            for i, batch in enumerate(cut):
                bid = f"{arm_name}-{group}-{i:03d}"
                rows.extend((bid, arm_name, group, pos, oid) for pos, oid in enumerate(batch))
    df = pd.DataFrame(rows, columns=["batch_id", "arm", "group", "position", "id"])
    df["position"] = df["position"].astype("int64")
    df["id"] = df["id"].astype("int64")
    return df
