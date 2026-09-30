"""A map of the pool: every record as a point, filtered by group, taxon, status flags and date.

The page (map.html) loads MapLibre and deck.gl from a CDN and reads the points from gzipped column
files next to it. The files hold record ids, positions, dates, taxa and flags, sorted by id, and
nothing about lists, so the map cannot tell which list a record sits on.

Each shard (pool-0.bin, pool-1.bin, ...), gzipped, little-endian, n records, columns back to back:
    uint32 id | uint16 lon | uint16 lat | uint16 obs | uint16 up | uint16 taxon
    | uint8 group | uint8 rank | uint8 ids | uint8 flags
lon and lat are quantized over META.bbox; obs (observed) and up (uploaded) count days from
META.day0, with NO_DAY for a missing date; taxon indexes the names in pool-taxa.bin (gzipped JSON
of [latin, common, id step] triples, sorted by iNaturalist taxon id; the step is the id minus the
previous row's, and the first row's is the id itself), group META.groups and rank META.ranks, with
0xFFFF and 0xFF for none.
ids holds min(IDs, 15) in the low nibble and min(agreements, 15) in the high nibble. flags sets
FLAG_BITS for the flags META.flags names; a pool pulled before those columns existed has none.
Shard 0 holds records observed in the last two calendar years (and any without a date), so the
page draws them first; older records follow in shard 1.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
from html import escape
from importlib.resources import files
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.batches import MAX_URL_LEN
from what_to_id.inat import BC_PLACE_ID
from what_to_id.page import ARM_WORDS, group_name

MAP_NAME = "map.html"
TAXA_NAME = "pool-taxa.bin"
NO_DAY = 0xFFFF
NO_TAXON = 0xFFFF
NO_RANK = 0xFF
_Q = 0xFFFF
BYTES_PER_RECORD = 18
IMPRECISE_M = 1000
FLAG_BITS = {"introduced": 1, "threatened": 2, "obscured": 4, "imprecise": 8}
_COLS = ("id", "lat", "lon", "observed_on", "created_at", "iconic_taxon")
_ASSETS = files("what_to_id") / "map_assets"


def shard_name(k: int) -> str:
    return f"pool-{k}.bin"


def encode_points(pool: pd.DataFrame) -> tuple[dict[str, bytes], dict]:
    """Pack the pool into the gzipped files the page reads, and the META it needs to read them."""
    missing = [c for c in _COLS if c not in pool]
    if missing:
        raise ValueError(f"pool lacks columns {missing}")
    if pool.empty:
        raise ValueError("pool is empty; nothing to map")
    df = pool.sort_values("id").reset_index(drop=True)
    ids = df["id"].to_numpy(dtype=np.int64)
    if ids.min() < 0 or ids.max() > 0xFFFFFFFF:
        raise ValueError("record ids do not fit in uint32")
    lat = df["lat"].to_numpy(dtype=np.float64)
    lon = df["lon"].to_numpy(dtype=np.float64)
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError("pool has records without coordinates")
    bbox = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]
    obs, up = _dates(df["observed_on"]), _dates(df["created_at"])
    if obs.isna().all():
        raise ValueError("no record has an observed date")
    day0 = min(d for d in (obs.min(), up.min()) if pd.notna(d))
    obs_off, up_off = (obs - day0).dt.days, (up - day0).dt.days
    last = int(max(obs_off.max(), up_off.max()))
    if last >= NO_DAY:
        raise ValueError("dates span more than 65,534 days")

    groups = sorted(df["iconic_taxon"].fillna("Unknown").astype(str).unique())
    gidx = pd.Categorical(df["iconic_taxon"].fillna("Unknown").astype(str), categories=groups)
    taxa, tidx = _taxa(df)
    ranks = sorted(df["rank"].dropna().astype(str).unique()) if "rank" in df else []
    ridx = (
        pd.Categorical(df["rank"].astype("string"), categories=ranks).codes
        if "rank" in df
        else np.full(len(df), -1)
    )
    known, flags = _flags(df)
    cols = {
        "id": ids.astype("<u4"),
        "lon": _quant(lon, bbox[0], bbox[2]),
        "lat": _quant(lat, bbox[1], bbox[3]),
        "obs": obs_off.fillna(NO_DAY).to_numpy().astype("<u2"),
        "up": up_off.fillna(NO_DAY).to_numpy().astype("<u2"),
        "taxon": tidx.astype("<u2"),
        "group": gidx.codes.astype("u1"),
        "rank": np.where(ridx < 0, NO_RANK, ridx).astype("u1"),
        "ids": (_nibble(df, "ident_count") | _nibble(df, "agree") << 4).astype("u1"),
        "flags": flags,
    }
    cut = (pd.Timestamp(year=int(obs.max().year) - 1, month=1, day=1) - day0).days
    recent = (obs_off >= cut).to_numpy() | obs.isna().to_numpy()
    out: dict[str, bytes] = {}
    shards = []
    for part in (recent, ~recent):
        if part.any():
            name = shard_name(len(shards))
            out[name] = _gz(b"".join(v[part].tobytes() for v in cols.values()))
            shards.append({"file": name, "n": int(part.sum())})
    out[TAXA_NAME] = _gz(json.dumps(taxa, ensure_ascii=False, separators=(",", ":")).encode())
    h = hashlib.sha256()
    for name in sorted(out):
        h.update(name.encode() + out[name])
    meta = {
        "n": int(len(df)),
        "bbox": bbox,
        "day0": day0.strftime("%Y-%m-%d"),
        "days": last + 1,
        "hist0": _hist_start(obs_off, day0),
        "groups": groups,
        "names": {g: group_name(g) for g in groups},
        "ranks": ranks,
        "flags": known,
        "shards": shards,
        "taxa": TAXA_NAME,
        "sha256": h.hexdigest(),
    }
    return out, meta


def decode_points(blobs: dict[str, bytes], meta: dict) -> pd.DataFrame:
    """Read the files back, as the page does; for tests and for a QGIS export."""
    frames = [_decode_shard(gzip.decompress(blobs[s["file"]]), int(s["n"])) for s in meta["shards"]]
    raw = {k: np.concatenate([f[k] for f in frames]) for k in frames[0]}
    x0, y0, x1, y1 = meta["bbox"]
    day0 = pd.Timestamp(meta["day0"])
    taxa = json.loads(gzip.decompress(blobs[meta["taxa"]]))

    def date(d: np.ndarray) -> pd.Series:
        return pd.Series(day0 + pd.to_timedelta(np.where(d == NO_DAY, 0, d), "D")).where(
            d != NO_DAY
        )

    def pick(table: list, idx: np.ndarray, none: int) -> list:
        return [None if i == none else table[i] for i in idx]

    names = pick(taxa, raw["taxon"], NO_TAXON)
    tids = np.cumsum([t[2] for t in taxa], dtype=np.int64)
    out = pd.DataFrame(
        {
            "id": raw["id"].astype(np.int64),
            "lon": x0 + raw["lon"] / _Q * (x1 - x0),
            "lat": y0 + raw["lat"] / _Q * (y1 - y0),
            "observed_on": date(raw["obs"]),
            "uploaded_on": date(raw["up"]),
            "iconic_taxon": np.asarray(meta["groups"], dtype=object)[raw["group"]],
            "taxon_id": pd.array(
                [None if t is None else tids[i] for t, i in zip(names, raw["taxon"], strict=True)],
                dtype="Int64",
            ),
            "taxon_name": [t and t[0] for t in names],
            "common_name": [t and t[1] for t in names],
            "rank": pick(meta["ranks"], raw["rank"], NO_RANK),
            "ident_count": raw["ids"] & 15,
            "agree": raw["ids"] >> 4,
        }
    )
    for name in meta["flags"]:
        out[name] = (raw["flags"] & FLAG_BITS[name]) > 0
    return out.sort_values("id").reset_index(drop=True)


def _decode_shard(blob: bytes, n: int) -> dict[str, np.ndarray]:
    if len(blob) != BYTES_PER_RECORD * n:
        raise ValueError(f"shard holds {len(blob)} bytes, expected {BYTES_PER_RECORD * n}")
    layout = [("id", "<u4"), ("lon", "<u2"), ("lat", "<u2"), ("obs", "<u2"), ("up", "<u2")]
    layout += [("taxon", "<u2"), ("group", "u1"), ("rank", "u1"), ("ids", "u1"), ("flags", "u1")]
    out, off = {}, 0
    for name, dt in layout:
        out[name] = np.frombuffer(blob, dt, n, off)
        off += np.dtype(dt).itemsize * n
    return out


def _quant(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    span = hi - lo or 1.0
    return np.rint((v - lo) / span * _Q).astype("<u2")


def _taxa(df: pd.DataFrame) -> tuple[list[list[str]], np.ndarray]:
    """[latin, common, id step] per distinct taxon, and each record's index into that table."""
    if "taxon_id" not in df or "taxon_name" not in df:
        return [], np.full(len(df), NO_TAXON)
    common = df["common_name"] if "common_name" in df else pd.Series("", index=df.index)
    t = pd.DataFrame({"tid": df["taxon_id"], "latin": df["taxon_name"], "common": common})
    table = t.dropna(subset=["tid"]).drop_duplicates("tid").sort_values("tid")
    if len(table) >= NO_TAXON:
        raise ValueError(f"{len(table)} taxa do not fit in uint16")
    pos = pd.Series(np.arange(len(table)), index=table["tid"].to_numpy())
    idx = t["tid"].map(pos).fillna(NO_TAXON).to_numpy()
    tids = table["tid"].to_numpy(dtype=np.int64)
    steps = np.diff(tids, prepend=0).tolist()
    names = [
        [str(a) if pd.notna(a) else "", str(c) if pd.notna(c) else "", int(k)]
        for a, c, k in zip(table["latin"], table["common"], steps, strict=True)
    ]
    return names, idx


def _flags(df: pd.DataFrame) -> tuple[list[str], np.ndarray]:
    """The flag names this pool can fill, and each record's flag byte."""
    bits = np.zeros(len(df), dtype="u1")
    known = []
    for name in ("introduced", "threatened", "obscured"):
        if name in df:
            known.append(name)
            on = df[name].astype("boolean").fillna(False).to_numpy(dtype=bool)
            bits |= np.where(on, FLAG_BITS[name], 0).astype("u1")
    if "pos_acc" in df:
        known.append("imprecise")
        acc = pd.to_numeric(df["pos_acc"], errors="coerce").fillna(0).to_numpy()
        bits |= np.where(acc > IMPRECISE_M, FLAG_BITS["imprecise"], 0).astype("u1")
    return known, bits


def _nibble(df: pd.DataFrame, col: str) -> np.ndarray:
    if col not in df:
        return np.zeros(len(df), dtype="u1")
    return np.clip(pd.to_numeric(df[col], errors="coerce").fillna(0), 0, 15).to_numpy("u1")


def _hist_start(obs_off: pd.Series, day0: pd.Timestamp) -> int:
    """The day the histogram starts: 1 January of the year holding the earliest 0.5% of records.

    Earlier records still count; the page draws them as one bar before the axis.
    """
    q = day0 + pd.Timedelta(days=int(obs_off.dropna().quantile(0.005)))
    return max(0, (pd.Timestamp(year=q.year, month=1, day=1) - day0).days)


def _gz(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


def _dates(col: pd.Series) -> pd.Series:
    """Calendar dates; created_at is UTC, observed_on is the observer's local date."""
    d = pd.to_datetime(col, errors="coerce", utc=True, format="mixed")
    return d.dt.tz_localize(None).dt.normalize()


def render_map(meta: dict, *, freeze: str | None, back: str = "index.html") -> str:
    """The map page. META goes inline; the points and names come from the files at load."""
    when = f" on {escape(freeze)}" if freeze else ""
    v = meta["sha256"][:12]
    page_meta = {
        **meta,
        "shards": [{**s, "file": f"{s['file']}?v={v}"} for s in meta["shards"]],
        "taxa": f"{meta['taxa']}?v={v}",
        "place_id": BC_PLACE_ID,
        "max_url": MAX_URL_LEN,
    }
    fill = {
        "TITLE": "Records that need an ID in BC",
        "WHEN": when,
        "BACK": escape(back),
        "PLACE_ID": str(BC_PLACE_ID),
        "MAPLIBRE_CSS": MAPLIBRE_CSS,
        "MAPLIBRE_JS": MAPLIBRE_JS,
        "DECK_JS": DECK_JS,
        "CSS": (_ASSETS / "map.css").read_text(),
        "META": json.dumps(page_meta, sort_keys=True).replace("</", "<\\/"),
        "BASEMAPS": json.dumps(BASEMAPS, sort_keys=True),
        "JS": (_ASSETS / "map.js").read_text(),
    }
    html = (_ASSETS / "map.html").read_text()
    for key, value in fill.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def write_map(out_dir: Path | str, pool: pd.DataFrame, *, freeze: str | None = None) -> list[Path]:
    """Write map.html and its data files into the site folder."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    blobs, meta = encode_points(pool)
    html = render_map(meta, freeze=freeze)
    low = html.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"{MAP_NAME}: arm name {w!r} leaked into the map page")
    for name, blob in blobs.items():
        (out / name).write_bytes(blob)
    (out / MAP_NAME).write_text(html)
    return [out / MAP_NAME, *(out / name for name in blobs)]


MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"
DECK_JS = "https://unpkg.com/deck.gl@9.1.14/dist.min.js"
BASEMAPS = {
    "light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write map.html and its data from a pool parquet.")
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="site folder")
    ap.add_argument("--freeze", default=None, help="date the pool stands for, YYYY-MM-DD")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    pool = pd.read_parquet(a.pool)
    for path in write_map(a.out, pool, freeze=a.freeze):
        logging.getLogger("what_to_id").info("wrote %s (%d bytes)", path, path.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
