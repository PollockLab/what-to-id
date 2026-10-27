"""The levels page: Needs ID records at three levels, one entry from Explore.

    python -m what_to_id.page_levels --out SITE_DIR (--data-url URL | --parquet FILE)

The atlas manifest at ``--data-url`` may carry ``"levels"`` (``{"name", "built_at", "count"}``)
naming `levels.parquet` beside it (`levels.LEVEL_COLUMNS`); without it nothing is written.
``--parquet`` builds from a local file instead.

It writes levels.html (every script inlined) and levels-data.bin, gzipped JSON:
``levels`` ([key, name, line] per level), ``groups`` (names by records desc), ``taxa`` (names),
``hosts``, ``exts`` and one array per record column, in display order: ``id``, ``photo``,
``meta``, ``taxon`` and ``looks`` (indexes into ``taxa``), ``level`` and ``group`` (indexes, -1
for no group); with a ``range_note`` column also ``notes`` (the lines) and ``note`` (index, -1
for none). A photo URL is built as in confusion-data.bin (see `page_confusion`).

Range maps need ``"ranges"`` and ``"range_cells"`` in the manifest entry (or, with ``--parquet``,
level-ranges.parquet and level-range-cells.parquet beside it; `level_ranges`), and add: ``grid``
(per H3 cell, its boundary as flat ``[lon, lat, ...]`` integer thousandths of a degree), ``rng``
(aligned with ``taxa``: base64 bitset over the grid cells, bit i in byte i>>3 at 1<<(i&7), or ""
when the range is unknown) and, with lat and lon columns, ``plat`` and ``plon`` (the record's
point in integer hundredths of a degree, null when missing) and, with an out_km column, ``okm``
(km from the point to the label's range, 0 inside it, -1 unknown). Without the range files the
page has no maps.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sys
import tempfile
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import page_nav
from what_to_id.levels import LEVEL_COLUMNS, LEVELS
from what_to_id.page_confusion import photo_columns
from what_to_id.page_lookalike import _fetch

HERE = Path(__file__).parent
ASSETS = HERE / "confusion_assets"
PAGE_NAME = "levels.html"
DATA_NAME = "levels-data.bin"
SCRIPTS = {
    "__EMBEDDINGS_LAYOUT__": HERE / "embeddings_assets" / "embeddings_layout.js",
    "__IDENTIFY_LINKS__": HERE / "map_assets" / "identify_links.js",
    "__LEVELS_APP__": ASSETS / "levels_app.js",
}


def _scaled(x: pd.Series, k: int) -> list:
    """Integers of x * k, None for missing."""
    r = (x * k).round().astype("Int64")
    return r.astype(object).where(r.notna(), None).tolist()


def encode(
    levels: pd.DataFrame,
    built_at: str = "",
    ranges: pd.DataFrame | None = None,
    grid: pd.DataFrame | None = None,
) -> bytes:
    """The gzipped levels-data.bin for these rows in their order (see the module docstring)."""
    missing = [c for c in LEVEL_COLUMNS if c not in levels.columns]
    if missing:
        raise ValueError(f"the levels table lacks {', '.join(missing)}")
    keys = [k for k, _, _ in LEVELS]
    unknown = set(levels["level"]) - set(keys)
    if unknown:
        raise ValueError(f"unknown levels {sorted(unknown)}")
    ids = levels["id"].to_numpy(np.int64)
    if len(ids) and (ids.min() <= 0 or ids.max() > 0xFFFFFFFF):
        raise ValueError("record ids must be positive and fit 32 bits")
    taxa, taxon_ix = np.unique(
        pd.concat([levels["taxon_name"], levels["looks_like_name"]]).fillna("").astype(str),
        return_inverse=True,
    )
    groups = levels["iconic_taxon"].dropna().value_counts().index.tolist()
    photo, meta, hosts, exts = photo_columns(levels["photo_url"], "page_levels")
    head = {
        "built_at": built_at,
        "levels": [list(x) for x in LEVELS],
        "groups": groups,
        "taxa": taxa.tolist(),
        "hosts": hosts,
        "exts": exts,
        "id": ids.tolist(),
        "photo": photo.tolist(),
        "meta": meta.tolist(),
        "taxon": taxon_ix[: len(levels)].tolist(),
        "looks": taxon_ix[len(levels) :].tolist(),
        "level": levels["level"].map({k: i for i, k in enumerate(keys)}).tolist(),
        "group": levels["iconic_taxon"]
        .map({g: i for i, g in enumerate(groups)})
        .fillna(-1)
        .astype(int)
        .tolist(),
    }
    if "range_note" in levels.columns:
        notes = levels["range_note"].dropna().unique()
        head["notes"] = notes.tolist()
        head["note"] = (
            levels["range_note"]
            .map({n: i for i, n in enumerate(notes)})
            .fillna(-1)
            .astype(int)
            .tolist()
        )
    if ranges is not None and grid is not None:
        head["grid"] = [
            np.column_stack([np.round(lo * 1000), np.round(la * 1000)]).astype(int).ravel().tolist()
            for la, lo in zip(grid["lat"], grid["lon"], strict=True)
        ]
        bits = {}
        for n, cs in zip(ranges["name"], ranges["cells"], strict=True):
            b = np.zeros(len(grid), bool)
            b[np.asarray(cs, int)] = True
            bits[n] = base64.b64encode(np.packbits(b, bitorder="little").tobytes()).decode()
        head["rng"] = [bits.get(n, "") for n in taxa.tolist()]
        if {"lat", "lon"} <= set(levels.columns):
            head["plat"], head["plon"] = _scaled(levels["lat"], 100), _scaled(levels["lon"], 100)
        if "out_km" in levels.columns:
            head["okm"] = levels["out_km"].fillna(-1).astype(int).tolist()
    return gzip.compress(json.dumps(head, separators=(",", ":")).encode(), 9, mtime=0)


def render(data_url: str, built_at: str = "") -> str:
    html = (ASSETS / PAGE_NAME).read_text()
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
        "__CONFIG__": json.dumps({"data": data_url}).replace("<", "\\u003c"),
        "__BUILT__": f"Built {escape(built_at[:10])}." if built_at else "",
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    return html


def build(out: Path, data_url: str | None, parquet: Path | None = None) -> Path | None:
    out.mkdir(parents=True, exist_ok=True)
    built_at = ""
    ranges = grid = None
    with tempfile.TemporaryDirectory() as tmp:
        if parquet is None:
            if not data_url:
                raise ValueError("give --data-url or --parquet")
            base = data_url.rstrip("/") + "/"
            _fetch(base + "manifest.json", Path(tmp) / "manifest.json")
            entry = json.loads((Path(tmp) / "manifest.json").read_text()).get("levels")
            if not entry:
                print("page_levels: the manifest has no levels table; nothing written")
                return None
            parquet = Path(tmp) / "levels.parquet"
            _fetch(base + entry["name"], parquet)
            built_at = entry.get("built_at", "")
            if entry.get("ranges") and entry.get("range_cells"):
                for key, path in (
                    ("ranges", Path(tmp) / "r.parquet"),
                    ("range_cells", Path(tmp) / "g.parquet"),
                ):
                    _fetch(base + entry[key], path)
                ranges, grid = (
                    pd.read_parquet(Path(tmp) / "r.parquet"),
                    pd.read_parquet(Path(tmp) / "g.parquet"),
                )
        else:
            r, g = (
                parquet.parent / n for n in ("level-ranges.parquet", "level-range-cells.parquet")
            )
            if r.exists() and g.exists():
                ranges, grid = pd.read_parquet(r), pd.read_parquet(g)
        df = pd.read_parquet(parquet)
    blob = encode(df, built_at, ranges, grid)
    (out / DATA_NAME).write_bytes(blob)
    print(f"page_levels: {DATA_NAME} {len(blob) / 1e6:.2f} MB gzipped, {len(df)} records")
    version = hashlib.sha256(blob).hexdigest()[:12]
    target = out / PAGE_NAME
    target.write_text(render(f"{DATA_NAME}?v={version}", built_at))
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_levels", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory")
    p.add_argument("--data-url", help="atlas base URL holding manifest.json")
    p.add_argument("--parquet", type=Path, help="build from this local levels.parquet")
    a = p.parse_args(argv)
    try:
        target = build(a.out, a.data_url, a.parquet)
    except (ValueError, OSError) as exc:
        print(f"page_levels: {exc}", file=sys.stderr)
        return 1
    if target:
        print(f"page_levels: wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
