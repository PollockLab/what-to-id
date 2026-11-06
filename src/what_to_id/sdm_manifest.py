"""The ECCC 1 km species distribution models (habitat suitability 0-99 %) of North American
vertebrates, matched to the map's taxa so the range popover can read the model at a record's point.

The manifest maps a slug to {"Species": [latin name], "IUCN.Synonoms": ["Name a~Name b" or None],
"files": [...]}; every slug has COG beside the manifest, bytes 0-99, nodata 255.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from what_to_id.inat import TIMEOUT

BASE = (
    "https://object-arbutus.alliancecan.ca/swift/v1/4903c6264e0c4191a74a54c93b6fe1d9"
    "/def-pollock-eckert/vertebrates_NA/ECCC_2026"
)
COG = "{slug}_sdm-ensemble-clipped_1km_na_1980-2010_sett1.tif"


def load(src: str | Path) -> dict:
    """The manifest from a URL or a local file."""
    if str(src).startswith(("http://", "https://")):
        r = requests.get(str(src), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    return json.loads(Path(src).read_text())


def _key(name: str) -> str:
    return name.strip().lower()


def match(manifest: dict, names: list[str | None]) -> dict[int, str]:
    """Taxa-table index -> slug, by latin name against each slug's species and synonyms.

    A name two slugs claim goes to the one whose species it is, or to none."""
    own: dict[str, str] = {}
    seen: dict[str, set[str]] = {}
    for slug, v in manifest.items():
        sp = _key(v["Species"][0])
        own[sp] = slug
        syn = (v.get("IUCN.Synonoms") or [None])[0] or ""
        for s in [sp, *syn.split("~")]:
            if s.strip():
                seen.setdefault(_key(s), set()).add(slug)
    out = {}
    for i, name in enumerate(names):
        k = _key(name or "")
        slugs = seen.get(k, ())
        if len(slugs) == 1:
            out[i] = next(iter(slugs))
        elif k in own:
            out[i] = own[k]
    return out


def sdm_meta(src: str | Path, names: list[str | None]) -> dict:
    """META.sdm: the COG URL with a {slug} placeholder, and each matched taxon's slug.

    The COGs sit beside a manifest read from a URL; a local copy stands for the ECCC one at BASE."""
    s = str(src)
    base = s.rsplit("/", 1)[0] if s.startswith(("http://", "https://")) else BASE
    taxa = match(load(src), names)
    return {"cog": f"{base}/{COG}", "taxa": {str(i): slug for i, slug in taxa.items()}}
