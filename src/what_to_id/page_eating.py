"""The Food web page: feeding photos and food-word searches against the metaweb.

eating.html stays as a redirect, so the page's first address and its hashes keep working.
"""

from __future__ import annotations

import json
from pathlib import Path

from what_to_id import page_nav

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


def render() -> str:
    html = (ASSETS / "food_web.html").read_text()
    config = json.dumps(
        {"obs": OBS_FILE, "metaweb": METAWEB_FILE, "text": TEXT_FILE, "vlm": VLM_FILE}
    )
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
        "__EATING_CSS__": (ASSETS / "eating.css").read_text().rstrip(),
        "__CONFIG__": config,
        "__EATING_PICKER_JS__": (ASSETS / "eating_picker.js").read_text(),
        "__EATING_CORE_JS__": (ASSETS / "eating_core.js").read_text(),
        "__FOOD_LOOP_JS__": (ASSETS / "food_loop.js").read_text(),
        "__EATING_JS__": (ASSETS / "food_web.js").read_text(),
    }.items():
        html = html.replace(key, value)
    return html


def build(out_dir: str | Path) -> Path | None:
    """food-web.html and the eating.html redirect in `out_dir`; None without both data files."""
    out = Path(out_dir)
    if not (out / OBS_FILE).exists() or not (out / METAWEB_FILE).exists():
        return None
    (out / OLD_NAME).write_text(REDIRECT)
    target = out / PAGE_NAME
    target.write_text(render())
    return target


if __name__ == "__main__":
    import sys

    print(build(sys.argv[1]) or "needs foodweb-obs.json and metaweb.json in the directory")
