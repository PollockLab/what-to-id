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
"""

from __future__ import annotations

import argparse
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


def encode(levels: pd.DataFrame, built_at: str = "") -> bytes:
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
        df = pd.read_parquet(parquet)
    blob = encode(df, built_at)
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
