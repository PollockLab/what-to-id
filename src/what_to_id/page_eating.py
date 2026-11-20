"""The Food web page: feeding photos and food-word searches against the metaweb.

eating.html stays as a redirect, so the page's first address and its hashes keep working.
"""

from __future__ import annotations

import json
from pathlib import Path

from what_to_id import atlas_search_page, page_nav

ASSETS = Path(__file__).parent / "eating_assets"
PAGE_NAME = "food-web.html"
OLD_NAME = "eating.html"
OBS_FILE = "foodweb-obs.json"
TEXT_FILE = "foodweb-text.json"
VLM_FILE = "foodweb-vlm.json"
METAWEB_FILE = "metaweb.json"
REDIRECT = (
    '<!doctype html><meta charset="utf-8"><title>Food web</title>'
    f'<meta http-equiv="refresh" content="0;url={PAGE_NAME}">'
    f"<script>location.replace('{PAGE_NAME}'+location.hash)</script>"
    f'<a href="{PAGE_NAME}">Food web</a>\n'
)


# the photo-search modules (not its page script) the food_search.js control reuses
SEARCH_SCRIPTS = [v for k, v in atlas_search_page.SCRIPTS.items() if k != "__ATLAS_SEARCH_APP__"]


def render(data_url: str = "") -> str:
    """The page; a `data_url` (the atlas index, as for search.html) adds "Search photos"."""
    html = (ASSETS / "food_web.html").read_text()
    cfg = {"obs": OBS_FILE, "metaweb": METAWEB_FILE, "text": TEXT_FILE, "vlm": VLM_FILE}
    search = ""
    if data_url:
        cfg["search"] = {"dataUrl": data_url}
        search = "\n".join(p.read_text() for p in [*SEARCH_SCRIPTS, ASSETS / "food_search.js"])
    config = json.dumps(cfg).replace("<", "\\u003c")
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
        "__EATING_CSS__": (ASSETS / "eating.css").read_text().rstrip(),
        "__CONFIG__": config,
        "__EATING_PICKER_JS__": (ASSETS / "eating_picker.js").read_text(),
        "__EATING_CORE_JS__": (ASSETS / "eating_core.js").read_text(),
        "__FOOD_LOOP_JS__": (ASSETS / "food_loop.js").read_text(),
        "__FOOD_SEARCH_JS__": search,
        "__EATING_JS__": (ASSETS / "food_web.js").read_text(),
    }.items():
        html = html.replace(key, value)
    return html


def build(out_dir: str | Path, data_url: str = "") -> Path | None:
    """food-web.html and the eating.html redirect in `out_dir`; None without both data files."""
    out = Path(out_dir)
    if not (out / OBS_FILE).exists() or not (out / METAWEB_FILE).exists():
        return None
    (out / OLD_NAME).write_text(REDIRECT)
    target = out / PAGE_NAME
    target.write_text(render(data_url))
    return target


if __name__ == "__main__":
    import sys

    out = build(sys.argv[1], *sys.argv[2:3])  # an optional atlas data URL, as for atlas_search_page
    print(out or "needs foodweb-obs.json and metaweb.json in the directory")
