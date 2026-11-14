"""A map of the pool: every record as a point, filtered by group, taxon, status flags and date.

The page (map.html) loads MapLibre and deck.gl from a CDN and reads the points from gzipped column
files next to it. The files hold record ids, positions, dates, taxa and flags, sorted by id, and
nothing about lists, so the map cannot tell which list a record sits on. A viewer can also keep
only the records inside a polygon they draw or load from GeoJSON, or inside a BC park
(map_area.js); that runs in the page, and the build only copies the park list (map_parks.py) next
to it.

Each shard (pool-0.<hash>.bin, pool-1.<hash>.bin, ..., see `site_files`), gzipped, little-endian,
n records sorted by id, columns back to back:
    uint32 id step | uint16 lon | uint16 lat | uint16 obs | uint16 up | uint16 taxon
    | uint8 group | uint8 ids | uint8 flags
Each wider column is stored byte by byte: the low byte of every value, then the next byte, and so
on, which gzip packs tighter. The id step is the id minus the previous record's, and the first
record's is the id itself. lon and lat are quantized over META.bbox; obs (observed) and up
(uploaded) count days from META.day0, with NO_DAY for a missing date; taxon indexes pool-taxa.bin
(gzipped JSON of [latin, common, iNaturalist taxon id, rank] rows, most recorded taxon first; rank
indexes META.ranks) and group META.groups, with 0xFFFF and 0xFF for none. A taxon's rank is the one
its first record by id carries. Built with the taxon tree, each row also names its parent's row and
then its own record count, and ancestor rows follow the META.taxa_n record rows (see
taxonomy.py); META.presets, the shortcut chips, is set only when every record taxon has its whole
line of ancestors. META.group_ids holds the iNaturalist taxon of each group that has one, for the
Identify link.
ids holds min(IDs, 15) in the low nibble and min(agreements, 15) in the high nibble. flags sets
FLAG_BITS for the flags META.flags names. "oneid" has no bit (map_oneid.py). Dates before DAY_FLOOR
(1900-01-01) are stored at that day, so day0 is never earlier; the flags byte then also sets
EARLY_OBS (16) or EARLY_UP (32) to say the stored day is a floor, shown as "before 1900".
Shard 0 holds records observed in the last RECENT_DAYS days of the map (and any without a date), so
the page draws them first; older records follow, newest first, in shards of at most SHARD_MAX.

META.totals, when the build fetched them, holds iNaturalist's count of every BC record with a photo
that needs an ID or is Research Grade, per group and month, by observed ("obs") and uploaded
("up") date: one list per META.groups entry, one count per month from META.totals.m0 to the
month of the last day, with earlier months added into the first. META.totals.only holds the same
counts for each status filter ("introduced", "threatened", "exact"), so the share still shows
under one of them. The page sets the pool against them to show the share still needing an ID.
"on" is the day they were fetched.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import time
from html import escape
from importlib.resources import files
from pathlib import Path

import pandas as pd
import requests

from what_to_id import page_nav
from what_to_id.batches import MAX_URL_LEN
from what_to_id.inat import BC_PLACE_ID, INAT, SLEEP, TIMEOUT, make_session
from what_to_id.map_parks import PARKS_NAME, parks_blob, parks_version
from what_to_id.map_points import ACC_M, DAY_FLOOR, _dates, _gz, encode_points
from what_to_id.map_projects import add_projects
from what_to_id.page import ARM_WORDS
from what_to_id.sdm_manifest import sdm_meta
from what_to_id.site_files import META_NAME, dump, hashed, read_meta, write_meta
from what_to_id.taxonomy import load_tree

MAP_NAME = "map.html"
TOTAL_GRADES = "needs_id,research"
TOTAL_FIELDS = {"obs": "observed", "up": "created"}
# iNaturalist's search parameters for the page's status and accuracy filters. The precision choices
# also require obscuration=none: the map draws obscured records at rounded public coordinates, so
# their accuracy says nothing about the point. acc_below is strict, so within N m is below N + 1.
TOTAL_ONLY = {
    "introduced": {"introduced": "true"},
    "threatened": {"threatened": "true"},
    "acc_unknown": {"acc": "false"},
    "acc_known": {"acc": "true", "obscuration": "none"},
    **{f"acc_{m}": {"acc_below": m + 1, "obscuration": "none"} for m in ACC_M},
}
_PKG = files("what_to_id")
_ASSETS = _PKG / "map_assets"
# Inlined in this order: map_taxa.js, map_area.js, map_step.js, map_projects.js, map_user.js,
# map_resolved.js (records that left needs-ID), map_chips.js, map_filter.js the helpers and filter
# state map.js calls, group_list.js, map_hist.js, map_time.js, map_only.js and filter_bar.js the
# filter panel, map_card.js the card, map_sdm.js the habitat model overlay, clade_colour.js and
# level_colour.js the
# colours, map_rail.js and map_sheet.js Explore's panels, map_bare.js Identify's Where map.
MAP_CSS = ("map.css", "map_panels.css", "map_select.css", "map_area.css", "map_bare.css")
# The record card's closest matches (the atlas index reader and the iNaturalist photo lookup of the
# search page) and range chip (the Identify page's range module), and the photo space's taxon tree
# for the groups list's ranks, by path under the package.
SHARED_JS = (
    "site_assets/fetch_once.js",
    "atlas_search_assets/atlas_search_index.js",
    "atlas_search_assets/atlas_search_meta.js",
    "identify_assets/identify_ranges.js",
    "embeddings_assets/taxon_tree.js",
    "site_assets/saved_records.js",
)
SHARED_CSS = ("identify_assets/identify_ranges.css",)
MAP_JS = (
    "identify_links.js",
    "map_taxa.js",
    "map_step.js",
    "map_area.js",
    "map_value.js",
    "map_projects.js",
    "map_user.js",
    "map_resolved.js",
    "map_chips.js",
    "map_filter.js",
    "clade_colour.js",
    "group_list.js",
    "map_hist.js",
    "map_time.js",
    "map_only.js",
    "filter_bar.js",
    "map_suggest.js",
    "level_colour.js",
    "map_card.js",
    "map_sdm.js",
    "map.js",
    "map_rail.js",
    "map_sheet.js",
    "map_bare.js",
)


def fetch_totals(groups: list[str], *, on: str, session=None, sleep: float = SLEEP) -> dict:
    """Monthly counts of every BC record with a photo that needs an ID or is Research Grade.

    One histogram request per group and date field, each covering every month on record, then
    the same again under each status filter in TOTAL_ONLY. The pool's "Unknown" group is
    iNaturalist's ``iconic_taxa=unknown``.
    """
    session = session or make_session()

    def fetch(extra: dict) -> dict:
        out: dict = {}
        for key, field in TOTAL_FIELDS.items():
            out[key] = {}
            for g in groups:
                params = {
                    "place_id": BC_PLACE_ID,
                    "quality_grade": TOTAL_GRADES,
                    "photos": "true",
                    "d1": DAY_FLOOR.strftime("%Y-%m-%d"),
                    "iconic_taxa": "unknown" if g == "Unknown" else g,
                    "date_field": field,
                    "interval": "month",
                    **extra,
                }
                r = session.get(f"{INAT}/histogram", params=params, timeout=TIMEOUT)
                r.raise_for_status()
                out[key][g] = {k[:7]: int(v) for k, v in r.json()["results"]["month"].items()}
                if sleep:
                    time.sleep(sleep)
        return out

    return {"on": on, **fetch({}), "only": {k: fetch(v) for k, v in TOTAL_ONLY.items()}}


def align_totals(raw: dict, meta: dict) -> dict:
    """The fetched totals as the page reads them: per group, a count per month of the map.

    A group the fetch lacks counts zero; months before the map's first fold into it, and months
    after its last day are dropped. A status filter the fetch lacks is left out.
    """
    day0 = pd.Timestamp(meta["day0"])
    last = day0 + pd.Timedelta(days=meta["days"] - 1)
    n = (last.year - day0.year) * 12 + last.month - day0.month + 1

    def rows(counts: dict) -> list[list[int]]:
        out = []
        for g in meta["groups"]:
            row = [0] * n
            for ym, v in counts.get(g, {}).items():
                k = (int(ym[:4]) - day0.year) * 12 + int(ym[5:7]) - day0.month
                if k < n:
                    row[max(k, 0)] += v
            out.append(row)
        return out

    out: dict = {"on": raw["on"], "m0": day0.strftime("%Y-%m")}
    out.update({key: rows(raw[key]) for key in TOTAL_FIELDS})
    out["only"] = {
        f: {key: rows(t[key]) for key in TOTAL_FIELDS} for f, t in raw.get("only", {}).items()
    }
    return out


def over_totals(pool: pd.DataFrame, meta: dict) -> int:
    """How many group-months hold more pool records than their totals.

    The totals are fetched minutes after the pool, so a few records can change grade in between;
    the page caps the share at 100%, and this count says how often it has to.
    """
    t = meta["totals"]
    m0 = pd.Timestamp(t["m0"] + "-01")
    over = 0
    for key, col in (("obs", "observed_on"), ("up", "created_at")):
        d = _dates(pool[col]).clip(lower=DAY_FLOOR)
        k = (d.dt.year - m0.year) * 12 + d.dt.month - m0.month
        g = pool["iconic_taxon"].fillna("Unknown").astype(str)
        counts = pd.DataFrame({"g": g, "k": k}).dropna().groupby(["g", "k"]).size()
        for (grp, month), c in counts.items():
            i, month = meta["groups"].index(grp), int(month)
            if 0 <= month < len(t[key][i]) and c > t[key][i][month]:
                over += 1
    return over


def render_map(meta: dict, *, freeze: str | None, data_url: str | None = None) -> str:
    """The map page. META goes inline; the points and names come from the files at load.

    ``data_url`` is the atlas index the record card's closest matches come from; without it the
    card has none."""
    when = ""
    if freeze:
        f = escape(freeze)
        when = f' on <time id="updated" datetime="{f}" title="{f}">{f}</time>'
    page_meta = {
        "files": {},  # the files written after the map, see site_files.publish
        **meta,
        "place_id": BC_PLACE_ID,
        "max_url": MAX_URL_LEN,
        "parks": f"{PARKS_NAME}?v={parks_version(parks_blob())}",
        **({"data_url": data_url} if data_url else {}),
    }
    fill = {
        "TITLE": "Records that need an ID in BC",
        "WHEN": when,
        "PLACE_ID": str(BC_PLACE_ID),
        "MAPLIBRE_CSS": MAPLIBRE_CSS,
        "MAPLIBRE_JS": MAPLIBRE_JS,
        "DECK_JS": DECK_JS,
        "CSS": "\n".join((page_nav.CSS, _assets(MAP_CSS), _assets(SHARED_CSS, _PKG))),
        "NAV": page_nav.nav("map.html"),
        "META": dump(page_meta),
        "BASEMAPS": json.dumps(BASEMAPS, sort_keys=True),
        "JS": _assets(SHARED_JS, _PKG) + "\n" + _assets(MAP_JS),
    }
    html = (_ASSETS / "map.html").read_text()
    for key, value in fill.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def _assets(names: tuple[str, ...], base=_ASSETS) -> str:
    return "\n".join((base / n).read_text() for n in names)


def write_map(
    out_dir: Path | str,
    pool: pd.DataFrame,
    *,
    freeze: str | None = None,
    totals: dict | None = None,
    tree: dict | None = None,
    projects: Path | None = None,
    data_url: str | None = None,
    sdm_manifest: str | Path | None = None,
) -> list[Path]:
    """Write map.html and its data; totals from fetch_totals, projects from map_projects, the
    habitat models of the range popover (META.sdm) from sdm_manifest."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    blobs, meta = encode_points(pool, tree)
    if tree is not None and "presets" not in meta:
        _warn("the taxon tree lacks some of the pool's taxa; the shortcut chips stay hidden")
    if totals is not None:
        meta["totals"] = align_totals(totals, meta)
        over = over_totals(pool, meta)
        gz = _gz(dump(meta.pop("totals")).encode())  # a file, not inline: it is most of the page
        name = hashed("pool-totals.bin", gz)
        blobs[name] = gz
        meta.setdefault("files", {})["totals"] = name
        if over:
            _warn(f"{over} group-months hold more records than their totals; the page caps them")
    add_projects(blobs, meta, projects)
    # the habitat overlay's cover over the model outside Canada and the USA, see map_sdm.js
    mask = (_ASSETS / "outside_ca_us.geojson.gz").read_bytes()
    meta.setdefault("files", {})["sdmmask"] = hashed("pool-sdm-mask.bin", mask)
    blobs[meta["files"]["sdmmask"]] = mask
    if sdm_manifest is not None:
        taxa = json.loads(gzip.decompress(blobs[meta["taxa"]]))
        try:
            meta["sdm"] = sdm_meta(sdm_manifest, [t[0] for t in taxa])
        except (OSError, requests.RequestException, KeyError, ValueError) as e:
            _warn(f"no habitat models, the range popover goes without: {e}")  # the build goes on
    html = render_map(meta, freeze=freeze, data_url=data_url)
    low = html.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"{MAP_NAME}: arm name {w!r} leaked into the map page")
    blobs[PARKS_NAME] = parks_blob()
    for name, blob in blobs.items():
        (out / name).write_bytes(blob)
    (out / MAP_NAME).write_text(html)
    write_meta(out, read_meta(html))
    return [out / MAP_NAME, out / META_NAME, *(out / name for name in blobs)]


MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"
DECK_JS = "https://unpkg.com/deck.gl@9.1.14/dist.min.js"
BASEMAPS = {
    "light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}


def _warn(msg: str) -> None:
    logging.getLogger("what_to_id").warning(msg)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{msg}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write map.html and its data from a pool parquet.")
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="site folder")
    ap.add_argument("--freeze", default=None, help="date the pool stands for, YYYY-MM-DD")
    ap.add_argument(
        "--totals",
        action="store_true",
        help="fetch all-record totals from iNaturalist (about 112 requests); on failure the map "
        "is built without them",
    )
    ap.add_argument("--tree", type=Path, help="taxon tree cache from what_to_id.taxonomy")
    ap.add_argument("--projects", type=Path, help="pool-projects.bin, from map_projects")
    ap.add_argument(
        "--data-url", help="atlas index base URL, for the record card's closest matches"
    )
    ap.add_argument(
        "--sdm-manifest",
        help="ECCC habitat model manifest.json, URL or file, for the range popover's habitat line",
    )
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    pool = pd.read_parquet(a.pool)
    tree = load_tree(a.tree) or None
    if a.tree and tree is None:
        _warn(f"no taxon tree at {a.tree}; building the map without clade search")
    totals = None
    if a.totals:
        groups = sorted(pool["iconic_taxon"].fillna("Unknown").astype(str).unique())
        on = a.freeze or pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
        try:
            totals = fetch_totals(groups, on=on)
        except (requests.RequestException, KeyError, ValueError) as e:
            _warn(f"could not fetch the all-record totals, building the map without them: {e}")
    for path in write_map(
        a.out,
        pool,
        freeze=a.freeze,
        totals=totals,
        tree=tree,
        projects=a.projects,
        data_url=a.data_url,
        sdm_manifest=a.sdm_manifest,
    ):
        logging.getLogger("what_to_id").info("wrote %s (%d bytes)", path, path.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
