"""BC's parks, reserves, protected areas and conservancies, as the map page's park list.

scripts/bc_park_places.py builds map_assets/bc_parks.json.gz from the BC Data Catalogue layers
and the iNaturalist places they match; the map build copies it next to the page as PARKS_NAME,
and the page reads it when the park search is first used or a link names a park (bcpark=<key>).

The file is gzipped JSON: {"source": ..., "kinds": [...], "parks": [row, ...]}, each row
    [key, name, kind, place_id, bbox, rings, alt]
key is the ORCS number, with "-" and ORCS_SECONDARY added for one site of a park in several;
the row without a site holds them all. kind indexes "kinds"; place_id is the matched iNaturalist
place, 0 for none; bbox is [west, south, east, north]; rings is the boundary as map_area.js codes
an area (encode_rings), "" for a matched park, whose boundary is its place's; alt is other names to
search by, "" for none.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from importlib.resources import files

PARKS_NAME = "bc-parks.bin"
_INDEX = files("what_to_id") / "map_assets" / "bc_parks.json.gz"
Q = 1e4
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def encode_rings(rings: list[list[float]]) -> str:
    """Rings of flat [lon, lat, ...] as map_area.js's encode(): zigzag varint steps on a 0.0001
    degree grid, 5 bits to a base64url character, rings joined by '.'."""
    out = []
    for r in rings:
        s, prev = [], [0, 0]
        for i, c in enumerate(r):
            v = math.floor(c * Q + 0.5)
            d, prev[i % 2] = v - prev[i % 2], v
            z = -2 * d - 1 if d < 0 else 2 * d
            while z >= 32:
                s.append(_B64[32 | z % 32])
                z //= 32
            s.append(_B64[z])
        out.append("".join(s))
    return ".".join(out)


def parks_blob() -> bytes:
    """The park list as the page reads it (gzipped JSON)."""
    return _INDEX.read_bytes()


def parks_version(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()[:12]


def read_parks(blob: bytes | None = None) -> dict:
    return json.loads(gzip.decompress(parks_blob() if blob is None else blob))
