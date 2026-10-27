"""The Identify page: every pool record at its level, as a narrow column of cards.

    python -m what_to_id.page_identify --out SITE_DIR [--map-url map.html]

It writes identify.html (every script inlined) and reads, at view time, the map's pool shards and
the levels `pool_levels` wrote beside them (pool-levels.bin, pool-levels-looks.bin and, for the
range maps, pool-levels-range.bin when it was written). The selection is the map's: dates, months,
groups, taxa and the rest of the hash, the area (``wtid-area``) and the lasso's ids
(``wtid-keep``), through the same MapFilter the map and the photo space use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from what_to_id import page_nav

HERE = Path(__file__).parent
ASSETS = HERE / "identify_assets"
PAGE_NAME = "identify.html"
# The group of records labelled above species whose photo points to one species of the label.
# A placeholder name: rename it here and nowhere else.
NARROW_LABEL = "Narrow it down"
# (level as in identify.LEVEL_NAMES, name, one line for the page)
LEVELS = (
    (1, "Clear matches", "These look just like their label. Confirm many in one go."),
    (
        2,
        "Close calls",
        "Another species looks almost as likely, or it may be something else. Take a careful look.",
    ),
    (
        3,
        NARROW_LABEL,
        "Labelled above species, and the photo points to one species of it. Take it to species.",
    ),
    (4, "Odd shots", "Hard photos: hands, eggs, close-ups. Feeling lucky?"),
)
SCRIPTS = {
    "__ATLAS_SEARCH_META__": HERE / "atlas_search_assets" / "atlas_search_meta.js",
    "__MAP_TAXA__": HERE / "map_assets" / "map_taxa.js",
    "__MAP_CHIPS__": HERE / "map_assets" / "map_chips.js",
    "__IDENTIFY_LINKS__": HERE / "map_assets" / "identify_links.js",
    "__MAP_AREA__": HERE / "map_assets" / "map_area.js",
    "__MAP_FILTER__": HERE / "map_assets" / "map_filter.js",
    "__EMBEDDINGS_LAYOUT__": HERE / "embeddings_assets" / "embeddings_layout.js",
    "__SPACE_MASK__": HERE / "embeddings_assets" / "space_mask.js",
    "__IDENTIFY_RANGES__": ASSETS / "identify_ranges.js",
    "__IDENTIFY_APP__": ASSETS / "identify_app.js",
}


def render(map_url: str = "map.html") -> str:
    html = (ASSETS / PAGE_NAME).read_text()
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
        "__IDENTIFY_RANGES_CSS__": (ASSETS / "identify_ranges.css").read_text().rstrip(),
        "__CONFIG__": json.dumps({"mapUrl": map_url, "levels": LEVELS}).replace("<", "\\u003c"),
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    return html


def build(out_dir: str | Path, map_url: str = "map.html") -> Path:
    """Write ``identify.html`` into ``out_dir`` and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / PAGE_NAME
    target.write_text(render(map_url))
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_identify", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory")
    p.add_argument("--map-url", default="map.html", help="map page whose pool files it reads")
    a = p.parse_args(argv)
    print(f"page_identify: wrote {build(a.out, a.map_url)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
