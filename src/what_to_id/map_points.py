"""Pack the pool into the map's gzipped point files and read them back (layout: page_map.py)."""

from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from what_to_id.map_observer import OBSERVER_NAME, observer_users
from what_to_id.map_oneid import with_one_id
from what_to_id.page import group_name
from what_to_id.site_files import hashed
from what_to_id.taxonomy import (
    AT_RISK,
    GROUP_TAXA,
    NO_RANK,
    NO_TAXON,
    PRESETS,
    taxa_table,
)

TAXA_NAME = "pool-taxa.bin"
NO_DAY = 0xFFFF
_Q = 0xFFFF
BYTES_PER_RECORD = 17
RECENT_DAYS = 90
SHARD_MAX = 4_000_000
ACC_M = (1000, 100, 10)
DAY_FLOOR = pd.Timestamp("1900-01-01")
EARLY_OBS = 16
EARLY_UP = 32
FLAG_BITS = {"introduced": 1, "threatened": 2, "obscured": 4, "imprecise": 8}
# The accuracy class in the flags byte: 0 unknown, 1 over 1 km (bit 8, as "imprecise"), then within
# 1 km, 100 m and 10 m in the two high bits: 64, 128, 192.
ACC_BITS = (0, 8, 64, 128, 192)
_COLS = ("id", "lat", "lon", "observed_on", "created_at", "iconic_taxon")


def shard_name(k: int) -> str:
    return f"pool-{k}.bin"


def encode_points(pool: pd.DataFrame, tree: dict | None = None) -> tuple[dict[str, bytes], dict]:
    """Pack the pool into the gzipped files the page reads, and the META it needs to read them.

    ``tree`` is the taxon tree from taxonomy.load_tree; without it the taxa rows have no parents.
    """
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
    early_obs, early_up = (obs < DAY_FLOOR).to_numpy(), (up < DAY_FLOOR).to_numpy()
    day0 = max(min(d for d in (obs.min(), up.min()) if pd.notna(d)), DAY_FLOOR)
    obs, up = obs.clip(lower=DAY_FLOOR), up.clip(lower=DAY_FLOOR)
    obs_off, up_off = (obs - day0).dt.days, (up - day0).dt.days
    last = int(max(obs_off.max(), up_off.max()))
    if last >= NO_DAY:
        raise ValueError("dates span more than 65,534 days")

    groups = sorted(df["iconic_taxon"].fillna("Unknown").astype(str).unique())
    gidx = pd.Categorical(df["iconic_taxon"].fillna("Unknown").astype(str), categories=groups)
    taxa, tidx, ranks, complete = taxa_table(df, tree)
    known, flags = _flags(df)
    flags = flags | np.where(early_obs, EARLY_OBS, 0).astype("u1")
    flags = flags | np.where(early_up, EARLY_UP, 0).astype("u1")
    obs_day = obs_off.fillna(NO_DAY).to_numpy().astype("<u2")
    cols = {
        "id": ids.astype("<u4"),
        "lon": _quant(lon, bbox[0], bbox[2]),
        "lat": _quant(lat, bbox[1], bbox[3]),
        "obs": obs_day,
        "up": up_off.fillna(NO_DAY).to_numpy().astype("<u2"),
        "taxon": tidx.astype("<u2"),
        "group": gidx.codes.astype("u1"),
        "ids": (_nibble(df, "ident_count") | _nibble(df, "agree") << 4).astype("u1"),
        "flags": flags,
    }
    # obs_day is NO_DAY for a missing date, so those records count as recent too
    recent = obs_day >= max(last - RECENT_DAYS + 1, 0)
    older = np.flatnonzero(~recent)
    older = older[np.lexsort((ids[older], -obs_day[older].astype(np.int64)))]
    parts = [np.flatnonzero(recent), *np.array_split(older, max(1, -(-len(older) // SHARD_MAX)))]
    out: dict[str, bytes] = {}
    shards = []
    order = []
    for part in parts:
        if len(part):
            part = np.sort(part)
            order.append(part)
            blob = _gz(b"".join(_planes(_step(k, v[part])) for k, v in cols.items()))
            name = hashed(shard_name(len(shards)), blob)
            out[name] = blob
            shards.append({"file": name, "n": len(part)})
    users = observer_users(df, np.concatenate(order) if order else np.empty(0, dtype=np.intp))
    if users is not None:
        blob = _gz(users.tobytes())
        observer = hashed(OBSERVER_NAME, blob)
        out[observer] = blob
    blob = _gz(json.dumps(taxa, ensure_ascii=False, separators=(",", ":")).encode())
    taxa_name = hashed(TAXA_NAME, blob)
    out[taxa_name] = blob
    meta = {
        "n": int(len(df)),
        "bbox": bbox,
        "day0": day0.strftime("%Y-%m-%d"),
        "days": last + 1,
        "hist0": _hist_start(obs_off, day0),
        "groups": groups,
        "names": {g: group_name(g) for g in groups},
        "group_ids": {g: GROUP_TAXA[g] for g in groups if g in GROUP_TAXA},
        "ranks": ranks,
        "flags": with_one_id(df, known),
        "shards": shards,
        "taxa": taxa_name,
        "taxa_n": int(np.unique(tidx[tidx != NO_TAXON]).size),
    }
    if complete:
        meta["presets"], meta["value"] = PRESETS, AT_RISK
    if users is not None:
        meta["observer"] = observer
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
    out = pd.DataFrame(
        {
            "id": raw["id"].astype(np.int64),
            "lon": x0 + raw["lon"] / _Q * (x1 - x0),
            "lat": y0 + raw["lat"] / _Q * (y1 - y0),
            "observed_on": date(raw["obs"]),
            "uploaded_on": date(raw["up"]),
            "iconic_taxon": np.asarray(meta["groups"], dtype=object)[raw["group"]],
            "taxon_id": pd.array(
                [t and t[2] for t in names],
                dtype="Int64",
            ),
            "taxon_name": [t and t[0] for t in names],
            "common_name": [t and t[1] for t in names],
            "rank": [None if not t or t[3] == NO_RANK else meta["ranks"][t[3]] for t in names],
            "ident_count": raw["ids"] & 15,
            "agree": raw["ids"] >> 4,
        }
    )
    out["observed_before_1900"] = (raw["flags"] & EARLY_OBS) > 0
    out["uploaded_before_1900"] = (raw["flags"] & EARLY_UP) > 0
    for name in meta["flags"]:
        if name in FLAG_BITS:
            out[name] = (raw["flags"] & FLAG_BITS[name]) > 0
    if "accuracy" in meta["flags"]:
        out["acc_class"] = np.select(
            [raw["flags"] & b == b for b in ACC_BITS[:0:-1]], [4, 3, 2, 1], 0
        )
    return out.sort_values("id").reset_index(drop=True)


def _decode_shard(blob: bytes, n: int) -> dict[str, np.ndarray]:
    if len(blob) != BYTES_PER_RECORD * n:
        raise ValueError(f"shard holds {len(blob)} bytes, expected {BYTES_PER_RECORD * n}")
    layout = [("id", "<u4"), ("lon", "<u2"), ("lat", "<u2"), ("obs", "<u2"), ("up", "<u2")]
    layout += [("taxon", "<u2"), ("group", "u1"), ("ids", "u1"), ("flags", "u1")]
    out, off = {}, 0
    for name, dt in layout:
        w = np.dtype(dt).itemsize
        planes = np.frombuffer(blob, "u1", w * n, off).reshape(w, n)
        out[name] = planes.T.copy().view(dt).ravel()
        off += w * n
    out["id"] = np.cumsum(out["id"], dtype=np.int64).astype("<u4")
    return out


def _step(name: str, v: np.ndarray) -> np.ndarray:
    """The id column as steps from the previous id; other columns as they are."""
    return np.diff(v, prepend=0).astype("<u4") if name == "id" else v


def _planes(v: np.ndarray) -> bytes:
    """A column byte by byte: every value's low byte, then the next byte, and so on."""
    return v.view("u1").reshape(-1, v.itemsize).T.tobytes()


def _quant(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    span = hi - lo or 1.0
    return np.rint((v - lo) / span * _Q).astype("<u2")


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
        known += ["imprecise", "accuracy"]
        acc = pd.to_numeric(df["pos_acc"], errors="coerce").to_numpy(dtype=float)
        cls = np.where(np.isnan(acc), 0, 1 + sum(acc <= m for m in ACC_M))
        bits |= np.array(ACC_BITS, dtype="u1")[cls]
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
