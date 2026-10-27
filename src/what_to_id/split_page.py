"""Build the split page: Identify, the map, the photo space and the tree side by side, in step.

Each page runs in an iframe (``?embed=1`` hides its header) and reports selection changes to this
page by postMessage; this page relays them to the other frames, which apply them in place. Each of
the four panes (Identify, map, photos, tree) has its own toggle. With no ``?view=`` it opens
Identify and the map, or without ``identify.html`` in ``out_dir`` the map and the tree, or without
``tree.html`` too the map and the photo space, so build those pages first. It writes
``explore.html``, plus ``split.html``, which forwards old links to it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from what_to_id import page_nav
from what_to_id.embeddings_page import ASSETS, HERE

PAGE_NAME = "explore.html"
# the page was split.html; old links and bookmarks forward here with their query and hash
OLD_NAME = "split.html"
FORWARD = (
    '<!doctype html><meta charset="utf-8"><title>Explore</title>'
    f"<script>location.replace('{PAGE_NAME}'+location.search+location.hash)</script>"
    f'<a href="{PAGE_NAME}">Explore</a>'
)
SCRIPTS = {
    "__MAP_FILTER__": HERE / "map_assets" / "map_filter.js",
    "__CLIP_TOKENIZER__": HERE / "atlas_assets" / "clip_tokenizer.js",
    "__ATLAS_SEARCH_INDEX__": HERE / "atlas_search_assets" / "atlas_search_index.js",
    "__ATLAS_SEARCH_META__": HERE / "atlas_search_assets" / "atlas_search_meta.js",
    "__ATLAS_SEARCH_ENCODER__": HERE / "atlas_search_assets" / "atlas_search_encoder.js",
}
# One toggle per pane; a phone holds one pane, so there a toggle picks it.
IDENTIFY_BUTTON = '<button type="button" data-p="identify">Identify</button>'
TREE_BUTTON = '<button type="button" data-p="tree">Tree</button>'
BAR = (
    '<div class="xbar" id="xbar"><span class="counts" id="counts" aria-live="polite"></span>'
    '<form id="sf" role="search"><input id="sq" type="search" aria-label="Photo search" '
    'autocomplete="off" spellcheck="false" '
    'placeholder="a hummingbird feeding at a flower, or an observation link">'
    '<button type="submit">Search</button></form>'
    '<span id="sm" class="counts" aria-live="polite"></span>'
    f'<span class="seg" role="group" aria-label="View">{IDENTIFY_BUTTON}'
    '<button type="button" data-p="map">Map</button>'
    '<button type="button" data-p="space">Photos</button>'
    f"{TREE_BUTTON}</span>"
    '<button type="button" class="i" id="i" aria-expanded="false" aria-controls="note" '
    'aria-label="About this view">i</button>'
    '<p class="note" id="note" hidden>Show Identify, the map, the photos and the tree in any mix. '
    "The panes share one selection: change a filter in any and the others follow. Dates, months, "
    "show only, groups, taxa, the photo search and the map's area and the photo space's lasso "
    "travel across; projects stay with the map. The tree counts what the map shows, or the photo "
    "space's points when the map is hidden, and its Show on map sends its taxon to the map."
    "</p></div>"
)


def build(
    out_dir: str | Path,
    map_url: str = "map.html",
    space_url: str = "embeddings.html",
    data_url: str = "atlas/",
    tree_url: str = "tree.html",
    identify_url: str = "identify.html",
) -> Path:
    """Write ``explore.html`` and the ``split.html`` forward into ``out_dir``, return the first."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = (ASSETS / "split.html").read_text()
    has_tree = (out / tree_url).exists()
    has_identify = (out / identify_url).exists()
    # explore.html is written last, so an optional page missing here is missing from the site
    pages = {p for p, _ in page_nav.PAGES if p not in page_nav.OPTIONAL or (out / p).exists()}
    bar = BAR if has_tree else BAR.replace(TREE_BUTTON, "")
    bar = bar if has_identify else bar.replace(IDENTIFY_BUTTON, "")
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME, pages, extra=bar),
        "__IDENTIFY_FILE__": json.dumps(identify_url if has_identify else None),
        "__MAP_FILE__": json.dumps(map_url),
        "__SPACE_FILE__": json.dumps(space_url),
        "__TREE_FILE__": json.dumps(tree_url if has_tree else None),
        "__DATA_URL__": json.dumps(data_url),
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    target = out / PAGE_NAME
    target.write_text(html)
    (out / OLD_NAME).write_text(FORWARD)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m what_to_id.split_page", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument("--data-url", default="atlas/", help="Static photo-search index base URL")
    args = parser.parse_args()
    print(build(args.out, data_url=args.data_url))


if __name__ == "__main__":
    main()
