"""Build the split page: the map beside the tree of life or the photo space, selection in step.

Each page runs in an iframe (``?embed=1`` hides its header) and reports selection changes to this
page by postMessage; this page relays them to the other frames, which apply them in place. With no
``?view=`` it opens the map and the tree. It writes nothing but ``split.html``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from what_to_id import page_nav
from what_to_id.embeddings_page import ASSETS, HERE

PAGE_NAME = "split.html"
SCRIPTS = {
    "__MAP_FILTER__": HERE / "map_assets" / "map_filter.js",
    "__CLIP_TOKENIZER__": HERE / "atlas_assets" / "clip_tokenizer.js",
    "__ATLAS_SEARCH_INDEX__": HERE / "atlas_search_assets" / "atlas_search_index.js",
    "__ATLAS_SEARCH_META__": HERE / "atlas_search_assets" / "atlas_search_meta.js",
    "__ATLAS_SEARCH_ENCODER__": HERE / "atlas_search_assets" / "atlas_search_encoder.js",
}
BAR = (
    '<div class="xbar" id="xbar"><span class="counts" id="counts" aria-live="polite"></span>'
    '<form id="sf" role="search"><input id="sq" type="search" aria-label="Photo search" '
    'autocomplete="off" spellcheck="false" '
    'placeholder="a hummingbird feeding at a flower, or an observation link">'
    '<button type="submit">Search</button></form>'
    '<span id="sm" class="counts" aria-live="polite"></span>'
    '<span class="seg" role="group" aria-label="View">'
    '<button type="button" data-v="side">Side by side</button>'
    '<button type="button" data-v="map">Map</button>'
    '<button type="button" data-v="space">Photo</button>'
    '<button type="button" data-v="tree">Tree</button></span>'
    '<button type="button" class="i" id="i" aria-expanded="false" aria-controls="note" '
    'aria-label="About this view">i</button>'
    '<p class="note" id="note" hidden>The map and the photo space share one selection: change '
    "a filter in either and the other follows. Dates, months, show only, groups, taxa and the "
    "map's area and the photo space's lasso travel across; projects stay with the map. The tree's "
    "Show on map sends its taxon to the map.</p></div>"
)


def build(
    out_dir: str | Path,
    map_url: str = "map.html",
    space_url: str = "embeddings.html",
    data_url: str = "atlas/",
    tree_url: str = "tree.html",
) -> Path:
    """Write ``split.html`` into ``out_dir`` and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = (ASSETS / "split.html").read_text()
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME, set(dict(page_nav.PAGES)), extra=BAR),
        "__MAP_FILE__": json.dumps(map_url),
        "__SPACE_FILE__": json.dumps(space_url),
        "__TREE_FILE__": json.dumps(tree_url),
        "__DATA_URL__": json.dumps(data_url),
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    target = out / PAGE_NAME
    target.write_text(html)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m what_to_id.split_page", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument("--data-url", default="atlas/", help="Static photo-search index base URL")
    args = parser.parse_args()
    print(build(args.out, data_url=args.data_url))


if __name__ == "__main__":
    main()
