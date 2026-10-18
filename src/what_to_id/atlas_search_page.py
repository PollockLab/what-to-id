"""Build the serverless photo-search page: one HTML file with every script inlined.

The page reads the static atlas index (see `atlas_index`) over HTTP Range from ``--data-url``
and asks iNaturalist for photos and names at view time. It writes nothing but ``search.html``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent
SCRIPTS = {
    "__IDENTIFY_LINKS__": HERE / "map_assets" / "identify_links.js",
    "__CLIP_TOKENIZER__": HERE / "atlas_assets" / "clip_tokenizer.js",
    "__ATLAS_SEARCH_INDEX__": HERE / "atlas_search_assets" / "atlas_search_index.js",
    "__ATLAS_SEARCH_META__": HERE / "atlas_search_assets" / "atlas_search_meta.js",
    "__ATLAS_SEARCH_ENCODER__": HERE / "atlas_search_assets" / "atlas_search_encoder.js",
    "__ATLAS_SEARCH_APP__": HERE / "atlas_search_assets" / "atlas_search_app.js",
}


def build(out_dir: str | Path, data_url: str = "atlas/", map_url: str = "map.html") -> Path:
    """Write ``search.html`` into ``out_dir`` and return its path."""
    if not data_url:
        raise ValueError("data_url must not be empty")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    config = json.dumps({"dataUrl": data_url, "mapUrl": map_url}).replace("<", "\\u003c")
    html = (HERE / "atlas_search_assets" / "atlas_search.html").read_text()
    html = html.replace("__ATLAS_SEARCH_CONFIG__", config)
    for placeholder, path in SCRIPTS.items():
        html = html.replace(placeholder, path.read_text())
    target = out / "search.html"
    target.write_text(html)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m what_to_id.atlas_search_page", description=__doc__
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument(
        "--data-url",
        default="atlas/",
        help="Static index base URL (needs CORS and Range), relative or absolute",
    )
    parser.add_argument("--map-url", default="map.html", help="Map page used by Show on map")
    args = parser.parse_args()
    print(build(args.out, args.data_url, args.map_url))


if __name__ == "__main__":
    main()
