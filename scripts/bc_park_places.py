"""Match BC's parks, reserves, protected areas and conservancies to iNaturalist places.

Usage: uv run --with geopandas --with shapely python scripts/bc_park_places.py \
    --gpkg bc_parks.gpkg --cache <dir> --out park_inat_places.csv \
    --index src/what_to_id/map_assets/bc_parks.json.gz

The BC layers (bc_parks, bc_conservancies) come from the BC Data Catalogue; see PROVENANCE.md
next to the GeoPackage. iNaturalist keeps no BC Parks (ORCS) id on its places, so a place matches
an area by name and by geometry, among places under British Columbia:

- First, place searches by designation ("provincial park", "ecological reserve", ...) gather most
  BC park places in a few dozen paged requests. Areas still without a name match then get one
  search each, by their own name and each of its other forms ("A / B", "[a.k.a. C]", "(D)").
- name+geometry: the names agree once the designation words are dropped and the place's
  polygon overlaps the area's (IoU at least MIN_IOU_NAMED).
- geometry: the place's polygon matches the area's both ways (two_way) and its name says it is a
  park, so a park renamed in BC since the place was made still matches; unless that name is
  another area's, which means the place's polygon is wrong.
- A pair scores the mean of its name likeness (name_score, 0 to 1) and its IoU. A name+geometry
  pair scoring under MIN_SCORE_ONE_WAY must also match both ways: a wrong place is worse than
  none, since an unmatched park still filters by its own boundary.
- The CSV gives each match's score and overlap: iou, r_bc (the share of the BC area inside the
  place's polygon) and r_inat (the share of the place's polygon inside the BC area).
- A place matches at most one area, the one it scores best with. A park in several sites
  (one ORCS, several ORCS_SECONDARY) also gets a row for the whole park, with an empty
  orcs_secondary, matched the same way against the sites' union.

Requests keep at least SLEEP seconds apart and back off on 429; every response is cached, so a
rerun asks nothing it has asked before.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

BC_PLACE_ID = 7085
SEARCH = "https://api.inaturalist.org/v1/search"
USER_AGENT = "what-to-id (+https://github.com/PollockLab/what-to-id)"
SLEEP = 1.6
HARVEST = ("provincial park", "ecological reserve", "protected area", "marine park")
MIN_NAME = 0.86
MIN_IOU_NAMED = 0.2
MIN_TWO_WAY = 0.9
MIN_SCORE_ONE_WAY = 0.85
KINDS = {
    "PROVINCIAL PARK": "park",
    "RECREATION AREA": "recreation area",
    "ECOLOGICAL RESERVE": "ecological reserve",
    "PROTECTED AREA": "protected area",
    "CONSERVANCY": "conservancy",
}
# words that say what kind of area a name is, not which one
_DESIG = re.compile(
    r"\b(provincial|marine|parks?|ecological|eco|reserves?|protected|areas?|conservancy|"
    r"recreation|heritage|site|class [abc]|pp|er|pa)\b"
)
_KIND_WORDS = (
    ("ecological reserve", r"\becological reserve|\beco ?reserve"),
    ("protected area", r"\bprotected area"),
    ("conservancy", r"\bconservancy"),
    ("recreation area", r"\brecreation area"),
    ("park", r"\bpark\b"),
)
FIELDS = (
    "orcs", "layer", "name", "designation", "inat_place_id", "match_method", "score",
    "orcs_secondary", "iou", "r_bc", "r_inat",
)  # fmt: skip


def fold(s: str) -> str:
    """Lower case ASCII: accents and glottal marks dropped, '?' (a lost character) a space."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s.replace("&", " and ")).strip()


def forms(name: str) -> list[str]:
    """The name and its other forms: a.k.a. and bracketed names, and each side of a '/'."""
    out = [name]
    inner = re.findall(r"[\[(]([^\])]*)[\])]?", name)
    bare = re.sub(r"[\[(][^\])]*([\])]|$)", " ", name)
    out.append(bare)
    for x in inner:
        out.append(re.sub(r"^\s*a\.?\s*k\.?\s*a\.?\s*", "", x, flags=re.I))
    for x in list(out):
        if "/" in x:
            out.extend(x.split("/"))
    seen, keep = set(), []
    for x in out:
        k = core(x)
        if k and k not in seen:
            seen.add(k)
            keep.append(x.strip())
    return keep


def core(name: str) -> str:
    """The part of a name that says which area it is."""
    s = fold(name)
    s = re.sub(r"\b(no|number) ?\d+\b", " ", s)
    s = re.sub(r"\ba ?k ?a\b.*", " ", s)
    return re.sub(r"\s+", " ", _DESIG.sub(" ", s)).strip()


def kind(name: str) -> str | None:
    """The designation a place's name states, if any."""
    s = fold(name)
    for k, rx in _KIND_WORDS:
        if re.search(rx, s):
            return k
    return None


def name_score(bc: str, inat: str) -> float:
    """How alike two names are, from 0 to 1, over each form of both."""
    best = 0.0
    for a in {core(x) for x in forms(bc)} - {""}:
        for b in {core(x) for x in forms(inat)} - {""}:
            best = max(best, SequenceMatcher(None, a, b).ratio())
    return best


def kind_ok(desig: str, inat_name: str) -> bool:
    """A place named for another designation is another area (a park and a protected area
    often share a name); a place that names none can be any."""
    k = kind(inat_name)
    want = KINDS[desig]
    return k is None or k == want or (want == "recreation area" and k == "park")


class Client:
    """GETs one at a time, SLEEP apart, backing off on 429 and 5xx, cached on disk."""

    def __init__(self, cache: Path):
        import requests

        self.errors = requests.exceptions
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.last = 0.0
        self.calls = 0

    def get(self, url: str, params: dict) -> dict:
        key = json.dumps([url, sorted(params.items())])
        f = self.cache / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")
        if f.exists():
            return json.loads(f.read_text())
        wait = 30.0
        for _ in range(8):
            time.sleep(max(0.0, self.last + SLEEP - time.monotonic()))
            try:
                r = self.s.get(url, params=params, timeout=90)
            except (self.errors.ConnectionError, self.errors.Timeout):
                r = None
            self.last = time.monotonic()
            self.calls += 1
            if r is None or r.status_code == 429 or r.status_code >= 500:
                retry = r.headers.get("Retry-After", "") if r is not None else ""
                time.sleep(float(retry) if retry.isdigit() else wait)
                wait = min(wait * 2, 600)
                continue
            r.raise_for_status()
            f.write_text(r.text)
            return r.json()
        raise RuntimeError(f"gave up on {url} {params}")

    def search(self, q: str, page: int = 1, per_page: int = 100) -> dict:
        p = {"q": q, "sources": "places", "per_page": per_page, "page": page}
        return self.get(SEARCH, p)


def bc_places(results: list[dict]) -> dict[int, dict]:
    """The places among search results that sit under British Columbia, with a polygon."""
    out = {}
    for r in results:
        p = r.get("record", r)
        under = BC_PLACE_ID in (p.get("ancestor_place_ids") or []) and p["id"] != BC_PLACE_ID
        if under and p.get("geometry_geojson") and p.get("admin_level") is None:
            out[p["id"]] = p
    return out


def harvest(client: Client) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for q in HARVEST:
        page = 1
        while True:
            j = client.search(q, page)
            out.update(bc_places(j["results"]))
            if page * 100 >= min(j["total_results"], 10_000) or not j["results"]:
                break
            page += 1
    return out


def load_areas(gpkg: Path):
    """One row per BC feature, plus one per multi-site park for the sites together."""
    import geopandas as gpd
    import pandas as pd
    from shapely import make_valid
    from shapely.ops import unary_union

    p = gpd.read_file(gpkg, layer="bc_parks")
    c = gpd.read_file(gpkg, layer="bc_conservancies")
    p = p.rename(columns={"PROTECTED_LANDS_NAME": "name", "PROTECTED_LANDS_DESIGNATION": "desig"})
    c = c.rename(columns={"CONSERVANCY_AREA_NAME": "name"}).assign(desig="CONSERVANCY")
    p["layer"], c["layer"] = "bc_parks", "bc_conservancies"
    cols = ["ORCS_PRIMARY", "ORCS_SECONDARY", "layer", "name", "desig", "geometry"]
    a = pd.concat([p[cols], c[cols]], ignore_index=True)
    a = a.rename(columns={"ORCS_PRIMARY": "orcs", "ORCS_SECONDARY": "orcs_secondary"})
    a["orcs_secondary"] = a["orcs_secondary"].fillna("")
    multi = a[a.duplicated("orcs", keep=False)]
    whole = []
    for orcs, g in multi.groupby("orcs"):
        name = re.split(r"\s*-\s*", g["name"].iloc[0], maxsplit=1)[0].strip()
        whole.append(
            {"orcs": orcs, "orcs_secondary": "", "layer": g["layer"].iloc[0], "name": name,
             "desig": g["desig"].iloc[0], "geometry": unary_union(list(g.geometry))}
        )  # fmt: skip
    a = pd.concat([a, gpd.GeoDataFrame(whole, crs=a.crs)], ignore_index=True)
    a["geometry"] = [make_valid(g) for g in a.geometry]
    return gpd.GeoDataFrame(a, crs=p.crs)


def score_pairs(areas, places: dict[int, dict]) -> list[tuple]:
    """(score, area index, place id, method, (iou, r_bc, r_inat)) for every pair that passes a
    rule."""
    from shapely import STRtree, make_valid
    from shapely.geometry import shape

    ids = list(places)
    geoms = [make_valid(shape(places[i]["geometry_geojson"])) for i in ids]
    tree = STRtree(geoms)
    out = []
    for ai, row in enumerate(areas.itertuples()):
        g = row.geometry
        for k in tree.query(g):
            p, pg = places[ids[k]], geoms[k]
            inter = g.intersection(pg).area
            iou = inter / (g.area + pg.area - inter) if inter else 0.0
            ns = name_score(row.name, p["name"])
            s = round(0.5 * ns + 0.5 * iou, 3)
            both = two_way(iou, inter, g.area, pg.area)
            overlap = (round(iou, 3), round(inter / g.area, 3), round(inter / pg.area, 3))
            if (ns >= MIN_NAME and iou >= MIN_IOU_NAMED and kind_ok(row.desig, p["name"])
                    and (s >= MIN_SCORE_ONE_WAY or both)):  # fmt: skip
                out.append((s, ai, ids[k], "name+geometry", overlap))
            elif (both and kind(p["name"]) and kind_ok(row.desig, p["name"])
                  and not names_other(areas, row.orcs, p["name"])):  # fmt: skip
                out.append((s, ai, ids[k], "geometry", overlap))
    return out


def two_way(iou: float, inter: float, a: float, b: float) -> bool:
    """Whether two polygons are one area: IoU at least MIN_TWO_WAY, or each covering at least
    MIN_TWO_WAY of the other. A place covering only part of an area, or much more, is not it."""
    return iou >= MIN_TWO_WAY or (inter >= MIN_TWO_WAY * a and inter >= MIN_TWO_WAY * b)


def names_other(areas, orcs: str, place_name: str) -> bool:
    """Whether a place is named for another BC area of its kind: its polygon is then wrong."""
    named = zip(areas.orcs, areas.name, areas.desig, strict=True)
    return any(
        name_score(n, place_name) >= MIN_NAME and kind_ok(d, place_name)
        for o, n, d in named
        if o != orcs
    )


def assign(pairs: list[tuple]) -> dict[int, tuple]:
    """Best pairs first, each area and each place used once."""
    got: dict[int, tuple] = {}
    used: set[int] = set()
    for s, ai, pid, how, overlap in sorted(pairs, key=lambda t: (-t[0], t[2])):
        if ai not in got and pid not in used:
            got[ai] = (pid, how, s, *overlap)
            used.add(pid)
    return got


def match(areas, client: Client) -> tuple[dict[int, tuple], dict[int, dict]]:
    places = harvest(client)
    got = assign(score_pairs(areas, places))
    # each unmatched area's own names, until one turns up a candidate that matches
    for ai, row in enumerate(areas.itertuples()):
        if ai in got:
            continue
        for f in forms(row.name):
            q = core(f)
            if len(q) < 3:
                continue
            found = bc_places(client.search(f"{q} {KINDS[row.desig]}", per_page=30)["results"])
            if not found:
                found = bc_places(client.search(q, per_page=30)["results"])
            places.update(found)
            if any(name_score(row.name, p["name"]) >= MIN_NAME for p in found.values()):
                break
    return assign(score_pairs(areas, places)), places


def write_csv(areas, got: dict[int, tuple], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for ai, row in enumerate(areas.itertuples()):
            pid, how, s, iou, r_bc, r_inat = got.get(ai, ("",) * 6)
            w.writerow(
                [row.orcs, row.layer, row.name, row.desig, pid, how or "none", s,
                 row.orcs_secondary, iou, r_bc, r_inat]
            )  # fmt: skip


_SMALL = {"and", "of", "the", "de", "la"}
# the catalogue cuts names at 50 characters; a cut word that starts one of these is completed
_ENDINGS = ("PROVINCIAL PARK", "ECOLOGICAL RESERVE", "PROTECTED AREA", "RECREATION AREA",
            "CONSERVANCY", "PARK", "SITE")  # fmt: skip


def display(name: str) -> str:
    """The catalogue's upper-case name in title case, with a cut-off end mended."""
    s = re.sub(r"\s+", " ", name).strip()
    if len(name) >= 49:
        o = max(s.rfind("["), s.rfind("("))
        if o > max(s.rfind("]"), s.rfind(")")):
            s = s[:o].strip()  # an a.k.a. cut short says too little to keep
        elif not any(s.upper().endswith(e) for e in _ENDINGS):
            cut = [(e, k) for e in _ENDINGS for k in range(len(e) - 1, 2, -1)
                   if s.upper().endswith(" " + e[:k])]  # fmt: skip
            s = s[: len(s) - cut[0][1]] + cut[0][0] if cut else s + "…"
    s = re.sub(r"\[\s*a\.?\s*k\.?\s*a\.?\s*", "(a.k.a. ", s, flags=re.I).replace("]", ")")

    def word(m: re.Match) -> str:
        w = m.group(0)
        if not w.isupper() or re.fullmatch(r"(?:[A-Z]\.)+", w):
            return w
        w = w.lower()
        return w if w in _SMALL and m.start() else w[0].upper() + w[1:]

    return re.sub(r"[^\s\-/(\[]+", word, s)


def ring_list(geom, tol: float) -> list[list[float]]:
    """The polygons' rings, simplified by tol degrees, on the page's grid, as flat lists."""
    from shapely import get_parts, simplify

    g = simplify(geom, tol, preserve_topology=False) if tol else geom
    out = []
    for p in get_parts(g):
        if p.geom_type == "MultiPolygon":
            polys = list(p.geoms)
        elif p.geom_type == "Polygon":
            polys = [p]
        else:
            continue
        for poly in polys:
            for ring in [poly.exterior, *poly.interiors]:
                r: list[float] = []
                for x, y in ring.coords:
                    x, y = round(x, 4), round(y, 4)
                    if r[-2:] != [x, y]:
                        r += [x, y]
                if len(r) >= 4 and r[:2] == r[-2:]:
                    r = r[:-2]
                if len(r) >= 6:
                    out.append(r)
    return out


def shape_rings(geom, max_corners: int, min_tol: float) -> list[list[float]]:
    """The boundary in at most max_corners corners: the least simplification that fits."""
    rings = ring_list(geom, min_tol)
    if sum(len(r) for r in rings) // 2 <= max_corners:
        return rings
    lo, hi = max(min_tol, 1e-6), 1.0
    for _ in range(30):
        mid = (lo * hi) ** 0.5
        if sum(len(r) for r in ring_list(geom, mid)) // 2 <= max_corners:
            hi = mid
        else:
            lo = mid
    return ring_list(geom, hi)


def write_index(areas, got, places, out: Path, max_corners: int, min_tol: float) -> None:
    import gzip
    import math

    from what_to_id.map_parks import encode_rings

    kinds = ["Park", "Ecological reserve", "Protected area", "Recreation area", "Conservancy"]
    kind_of = {"PROVINCIAL PARK": "Park", "ECOLOGICAL RESERVE": "Ecological reserve",
               "PROTECTED AREA": "Protected area", "RECREATION AREA": "Recreation area",
               "CONSERVANCY": "Conservancy"}  # fmt: skip
    multi = set(areas.loc[areas["orcs_secondary"] == "", "orcs"])
    rows = []
    for ai, row in enumerate(areas.itertuples()):
        site = row.orcs in multi and row.orcs_secondary != ""
        key = f"{row.orcs}-{row.orcs_secondary}" if site else row.orcs
        pid = got[ai][0] if ai in got else 0
        w, s, e, n = row.geometry.bounds
        bbox = [math.floor(w * 1e4) / 1e4, math.floor(s * 1e4) / 1e4,
                math.ceil(e * 1e4) / 1e4, math.ceil(n * 1e4) / 1e4]  # fmt: skip
        # a matched park's boundary comes from its iNaturalist place
        rings = "" if pid else encode_rings(shape_rings(row.geometry, max_corners, min_tol))
        alt = places[pid]["name"] if pid else ""
        name = display(row.name)
        rows.append([key, name, kinds.index(kind_of[row.desig]), pid, bbox, rings,
                     alt if fold(alt) != fold(name) else ""])  # fmt: skip
    rows.sort(key=lambda r: (fold(r[1]), r[0]))
    doc = {
        "source": "BC Data Catalogue, WHSE_TANTALIS.TA_PARK_ECORES_PA_SVW and "
        "TA_CONSERVANCY_AREAS_SVW, Open Government Licence - British Columbia",
        "kinds": kinds,
        "parks": rows,
    }
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    out.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    print(f"index: {len(rows)} rows, {len(raw):,} bytes, {out.stat().st_size:,} gzipped")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gpkg", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path, help="folder for cached API responses")
    ap.add_argument("--out", required=True, type=Path, help="CSV to write")
    ap.add_argument("--places", type=Path, help="also write the candidate places as JSON here")
    ap.add_argument("--index", type=Path, help="also write the map's park list here")
    ap.add_argument("--max-corners", type=int, default=1500, help="per park, in the park list")
    ap.add_argument("--min-tol", type=float, default=0.0, help="least simplification, degrees")
    a = ap.parse_args(argv)
    areas = load_areas(a.gpkg)
    client = Client(a.cache)
    got, places = match(areas, client)
    write_csv(areas, got, a.out)
    if a.places:
        a.places.write_text(json.dumps(places))
    if a.index:
        write_index(areas, got, places, a.index, a.max_corners, a.min_tol)
    print(f"{len(got)} of {len(areas)} areas matched; {client.calls} requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
