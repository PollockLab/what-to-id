"""The map's "One ID from Research Grade" choice (map_filter.js oneIds).

The flags byte is full, so no bit is stored: the page reads each record's ids byte (IDs by others in
the low nibble, agreements in the high one) and its taxon's rank. META.flags names "oneid" when the
pool has both counts.
"""

from __future__ import annotations

import pandas as pd

ONE_ID_COLUMNS = ("ident_count", "agree")


def with_one_id(df: pd.DataFrame, known: list[str]) -> list[str]:
    """The flag names with "oneid" added when the pool carries the ID counts."""
    return [*known, "oneid"] if all(c in df for c in ONE_ID_COLUMNS) else known
