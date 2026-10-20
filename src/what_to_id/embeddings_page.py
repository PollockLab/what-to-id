"""Build the photo-space page: one HTML file with every script inlined.

Every observation that needs an ID is a point at its position in a 2D layout of the BioCLIP image
embeddings. The page reads the layout parts and the neighbour files from ``--data-url`` (the atlas
repo, see `atlas_index`), joins them by id with the map's pool shards next to it, and asks
iNaturalist for photos and names at view time. It writes nothing but ``embeddings.html``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from what_to_id import page_nav

HERE = Path(__file__).parent
ASSETS = HERE / "embeddings_assets"
# Same pin as page_map.DECK_JS; not imported because the deploy script runs on a bare python3
DECK_JS = "https://unpkg.com/deck.gl@9.1.14/dist.min.js"
SCRIPTS = {
    "__ATLAS_SEARCH_INDEX__": HERE / "atlas_search_assets" / "atlas_search_index.js",
    "__ATLAS_SEARCH_META__": HERE / "atlas_search_assets" / "atlas_search_meta.js",
    "__MAP_TAXA__": HERE / "map_assets" / "map_taxa.js",
    "__MAP_CHIPS__": HERE / "map_assets" / "map_chips.js",
    "__IDENTIFY_LINKS__": HERE / "map_assets" / "identify_links.js",
    "__MAP_AREA__": HERE / "map_assets" / "map_area.js",
    "__MAP_FILTER__": HERE / "map_assets" / "map_filter.js",
    "__TAXON_TREE__": ASSETS / "taxon_tree.js",
    "__EMBEDDINGS_LAYOUT__": ASSETS / "embeddings_layout.js",
    "__EMBEDDINGS_SELECT__": ASSETS / "embeddings_select.js",
    "__EMBEDDINGS_APP__": ASSETS / "embeddings_app.js",
}
PAGE_NAME = "embeddings.html"


def build(
    out_dir: str | Path,
    data_url: str = "atlas/",
    map_url: str = "map.html",
    search_url: str = "search.html",
) -> Path:
    """Write ``embeddings.html`` into ``out_dir`` and return its path."""
    if not data_url:
        raise ValueError("data_url must not be empty")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    config = {"dataUrl": data_url, "mapUrl": map_url, "searchUrl": search_url}
    html = (ASSETS / "embeddings.html").read_text()
    for key, value in {
        "__EMBEDDINGS_CONFIG__": json.dumps(config).replace("<", "\\u003c"),
        "__DECK_JS__": DECK_JS,
        "__SITE_CSS__": page_nav.CSS,
        "__SELECT_CSS__": (HERE / "map_assets" / "map_select.css").read_text(),
        "__SITE_NAV__": page_nav.nav(PAGE_NAME, set(dict(page_nav.PAGES))),
    }.items():
        html = html.replace(key, value)
    for placeholder, path in SCRIPTS.items():
        html = html.replace(placeholder, path.read_text())
    target = out / PAGE_NAME
    target.write_text(html)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m what_to_id.embeddings_page", description=__doc__
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument(
        "--data-url",
        default="atlas/",
        help="Static index base URL (needs CORS and Range), relative or absolute",
    )
    parser.add_argument("--map-url", default="map.html", help="Map page whose pool files it joins")
    args = parser.parse_args()
    print(build(args.out, args.data_url, args.map_url))


if __name__ == "__main__":
    main()
