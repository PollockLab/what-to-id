"""Who observed each map record, for the map's Observer filter (map_user.js).

The shards stay as they are (identify.html reads them); the observer's iNaturalist user id goes in
a side file, pool-observer.bin: gzipped, one uint32 little-endian per record in the order of the
shards (shard 0 first, each sorted by id), 0 for a record without an observer.
"""

from __future__ import annotations

import gzip

import numpy as np
import pandas as pd

OBSERVER_NAME = "pool-observer.bin"


def observer_users(df: pd.DataFrame, order: np.ndarray) -> np.ndarray | None:
    """Each record's observer in ``order`` (row positions of ``df`` in shard order); None when the
    pool has no user_id column. Ids that are missing or do not fit in uint32 are 0."""
    if "user_id" not in df:
        return None
    u = pd.to_numeric(df["user_id"], errors="coerce").to_numpy(dtype=np.float64)
    ok = np.isfinite(u) & (u > 0) & (u <= 0xFFFFFFFF)
    return np.where(ok, u, 0).astype("<u4")[order]


def decode_observer(blob: bytes) -> np.ndarray:
    """The file back to one uint32 per record."""
    raw = gzip.decompress(blob)
    if len(raw) % 4:
        raise ValueError("observer file size is not a multiple of 4")
    return np.frombuffer(raw, dtype="<u4")
