"""Build the tree of life page: one HTML file with every script inlined. Stdlib only.

The page rolls the records that need an ID up iNaturalist's taxonomy and draws them as a radial
tree with an outline beside it. It reads the map's taxa file (pool-taxa.bin, built with ``--tree``)
next to it, and the map's META (ranks, groups, the taxa file name) is copied from ``map.html`` at
build time, so build the map first. It writes nothing but ``tree.html``.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from what_to_id import page_nav

HERE = Path(__file__).parent
ASSETS = HERE / "tree_assets"
PAGE_NAME = "tree.html"
SCRIPTS = {
    "__MAP_FILTER__": HERE / "map_assets" / "map_filter.js",
    "__MAP_TAXA__": HERE / "map_assets" / "map_taxa.js",
    "__EMBEDDINGS_LAYOUT__": HERE / "embeddings_assets" / "embeddings_layout.js",
    "__TREE_MODEL__": ASSETS / "tree_model.js",
    "__TREE_VIEW__": ASSETS / "tree_view.js",
}
KEYS = ("ranks", "taxa", "groups", "group_ids", "names", "place_id", "max_url", "n")


def map_meta(out: Path) -> dict:
    """The META object page_map wrote into ``out/map.html``."""
    page = out / "map.html"
    if not page.exists():
        raise FileNotFoundError(f"{page} is missing: build the map first (what_to_id.page_map)")
    html = page.read_text()
    start, end = html.find("var META="), html.find(";var BASEMAPS=")
    if start < 0 or end < start:
        raise ValueError(f"{page} holds no META: was it written by what_to_id.page_map?")
    meta = json.loads(html[start + len("var META=") : end])
    missing = [k for k in KEYS if k not in meta]
    if missing:
        raise ValueError(f"{page} META lacks {', '.join(missing)}")
    return {k: meta[k] for k in KEYS}


def build(out_dir: str | Path, map_url: str = "map.html") -> Path:
    """Write ``tree.html`` into ``out_dir`` (which holds the built map) and return its path."""
    out = Path(out_dir)
    meta = map_meta(out)
    taxa = out / meta["taxa"].split("?")[0]
    rows = json.loads(gzip.decompress(taxa.read_bytes()))
    if rows and len(rows[0]) < 6:
        raise ValueError(f"{taxa} has no record counts: build the map with --tree")
    config = json.dumps({"meta": meta, "mapUrl": map_url}).replace("<", "\\u003c")
    html = (ASSETS / PAGE_NAME).read_text()
    for key, value in {
        "__TREE_CONFIG__": config,
        "__SITE_CSS__": page_nav.CSS,
        "__SELECT_CSS__": (HERE / "map_assets" / "map_select.css").read_text(),
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    target = out / PAGE_NAME
    target.write_text(html)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m what_to_id.tree_page", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Site directory holding map.html")
    parser.add_argument("--map-url", default="map.html", help="Map page used by Show on map")
    args = parser.parse_args()
    print(build(args.out, args.map_url))


if __name__ == "__main__":
    main()
