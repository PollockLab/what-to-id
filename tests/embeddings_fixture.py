"""Synthetic photo-space inputs: layout parts in the shared format, and a pool for the map shards.

Layout part (gzip of 8*n bytes, records sorted by id): id steps as byte-planar uint32, then x, then
y quantized to uint16 over the manifest bbox, byte-planar. Written independently of the readers.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

BBOX = [-40.0, -25.0, 60.0, 35.0]
GROUPS = ["Aves", "Insecta", "Plantae"]
# taxon id -> [parent, latin, common, rank]: species 1000-1002 sit in Genus A, 1003-1006 in Genus B
TREE = {
    **{1000 + k: [900 if k < 3 else 901, f"Taxon {k}", "", "species"] for k in range(7)},
    900: [800, "Genus A", "", "genus"],
    901: [800, "Genus B", "", "genus"],
    800: [None, "Family F", "", "family"],
}


def quantize(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.rint((np.asarray(v, dtype=np.float64) - lo) / (hi - lo) * 65535).astype("<u2")


def planes(a: np.ndarray) -> bytes:
    return a.view("u1").reshape(-1, a.itemsize).T.tobytes()


def layout_part_bytes(ids: np.ndarray, xy: np.ndarray, bbox: list[float] = BBOX) -> bytes:
    """The gzipped part file for ids (sorted ascending here) at xy positions, shape (n, 2)."""
    order = np.argsort(ids)
    ids = np.asarray(ids, dtype=np.int64)[order]
    xy = np.asarray(xy, dtype=np.float64)[order]
    steps = np.diff(ids, prepend=0).astype("<u4")
    body = planes(steps) + planes(quantize(xy[:, 0], bbox[0], bbox[2]))
    body += planes(quantize(xy[:, 1], bbox[1], bbox[3]))
    assert len(body) == 8 * len(ids)
    return gzip.compress(body, mtime=0)


def write_layout(
    atlas: Path, parts: dict[str, tuple[np.ndarray, np.ndarray]], manifest: dict
) -> dict:
    """Write each part as <name>.bin and add the "layout" key to the manifest on disk."""
    entries = []
    for name, (ids, xy) in parts.items():
        (atlas / f"{name}.bin").write_bytes(layout_part_bytes(ids, xy))
        entries.append({"name": name, "count": len(ids)})
    layout = {
        "version": 1,
        "method": "fixture",
        "bbox": BBOX,
        "fidelity": {"k": 12, "mean_neighbor_recall": 0.5},
        "parts": entries,
    }
    manifest["layout"] = layout
    (atlas / "manifest.json").write_text(json.dumps(manifest))
    return layout


def pool_frame(ids: np.ndarray) -> pd.DataFrame:
    """Pool rows for page_map.encode_points: a few BC points, three groups cycling by position."""
    n = len(ids)
    rng = np.random.default_rng(3)
    day = pd.Timestamp("2026-08-01") + pd.to_timedelta(rng.integers(0, 60, n), unit="D")
    return pd.DataFrame(
        {
            "id": np.asarray(ids, dtype="int64"),
            "lat": 49.0 + rng.uniform(-0.5, 0.5, n),
            "lon": -123.0 + rng.uniform(-0.5, 0.5, n),
            "observed_on": [d.date().isoformat() for d in day],
            "created_at": [d.isoformat() + "T00:00:00Z" for d in day],
            "iconic_taxon": [GROUPS[i % 3] for i in range(n)],
            "taxon_id": [1000 + i % 7 for i in range(n)],
            "taxon_name": [f"Taxon {i % 7}" for i in range(n)],
            "rank": ["species"] * n,
        }
    )
