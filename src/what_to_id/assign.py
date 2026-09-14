"""Stratified random assignment of pool records to arms."""

from __future__ import annotations

import hashlib
import hmac
import zlib
from collections.abc import Sequence

import numpy as np
import pandas as pd

N_OBSERVER_BUCKETS = 3
UNKNOWN_GROUP = "Unknown"


def _bucket(uid) -> str:
    if pd.isna(uid):
        return "na"
    return str(zlib.crc32(str(int(uid)).encode()) % N_OBSERVER_BUCKETS)


def strata(pool: pd.DataFrame) -> pd.Series:
    """iconic_taxon + "|" + observer bucket (crc32(user_id) mod 3, "na" when missing)."""
    group = pool["iconic_taxon"].fillna(UNKNOWN_GROUP).astype(str)
    bucket = (
        pool["user_id"].map(_bucket) if "user_id" in pool else pd.Series("na", index=pool.index)
    )
    return (group + "|" + bucket).rename("stratum")


def _stratum_rng(seed: int, stratum: str) -> np.random.Generator:
    # Derive from (seed, stratum) so adding a stratum does not reshuffle the others.
    return np.random.default_rng([int(seed), zlib.crc32(stratum.encode())])


def assign(pool: pd.DataFrame, arms: Sequence[str], *, seed: int) -> pd.DataFrame:
    """Per stratum: shuffle ids, deal round-robin over arms with a rotating start offset.

    Returns columns id, arm, stratum, seed, one row per pool record.
    """
    arms = list(arms)
    if not arms:
        raise ValueError("arms must be non-empty")
    if len(set(arms)) != len(arms):
        raise ValueError(f"arms must be unique, got {arms}")
    if pool["id"].duplicated().any():
        raise ValueError("pool ids must be unique")
    st = strata(pool)
    ids = pool["id"].to_numpy(dtype=np.int64)
    out_id, out_arm, out_st = [], [], []
    for i, stratum in enumerate(sorted(st.unique())):
        rows = np.flatnonzero(st.to_numpy() == stratum)
        shuffled = _stratum_rng(seed, stratum).permutation(ids[rows])
        offset = i % len(arms)
        out_id.append(shuffled)
        out_arm.append([arms[(offset + j) % len(arms)] for j in range(len(shuffled))])
        out_st.append([stratum] * len(shuffled))
    df = pd.DataFrame(
        {
            "id": np.concatenate(out_id) if out_id else np.empty(0, dtype=np.int64),
            "arm": np.concatenate(out_arm) if out_arm else np.empty(0, dtype=object),
            "stratum": np.concatenate(out_st) if out_st else np.empty(0, dtype=object),
        }
    )
    df["id"] = df["id"].astype("int64")
    df["arm"] = df["arm"].astype(str)
    df["stratum"] = df["stratum"].astype(str)
    df["seed"] = np.int64(seed)
    return df.sort_values("id", kind="stable").reset_index(drop=True)


def _keyed_arm(uid: int, arms: Sequence[str], key: bytes) -> str:
    digest = hmac.new(key, str(int(uid)).encode(), hashlib.sha256).digest()
    return arms[int.from_bytes(digest[:8], "big") % len(arms)]


def assign_keyed(pool: pd.DataFrame, arms: Sequence[str], *, key: bytes) -> pd.DataFrame:
    """Per record: arm = HMAC-SHA256(key, id) mod len(arms), stable across pool changes.

    A record's arm depends only on its id and the key, never on the rest of the pool,
    so it stays on the same list across builds as the pool grows or shrinks. Returns
    columns id, arm, stratum, seed (seed is always -1, marking a keyed assignment;
    stratum is still filled in, for information, via the same strata helper as `assign`).
    """
    arms = list(arms)
    if not arms:
        raise ValueError("arms must be non-empty")
    if len(set(arms)) != len(arms):
        raise ValueError(f"arms must be unique, got {arms}")
    if not key:
        raise ValueError("key must be non-empty")
    if pool["id"].duplicated().any():
        raise ValueError("pool ids must be unique")
    st = strata(pool)
    df = pd.DataFrame(
        {
            "id": pool["id"].to_numpy(dtype=np.int64),
            "arm": [_keyed_arm(uid, arms, key) for uid in pool["id"]],
            "stratum": st.to_numpy(dtype=object),
        }
    )
    df["arm"] = df["arm"].astype(str)
    df["stratum"] = df["stratum"].astype(str)
    df["seed"] = np.int64(-1)
    return df.sort_values("id", kind="stable").reset_index(drop=True)
