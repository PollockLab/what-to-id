"""The Food web page: feeding photos and food-word searches against the metaweb.

eating.html stays as a redirect, so the page's first address and its hashes keep working.
pollination.html is the same template on pollination-metaweb.json and the Visited flower of
observations, with the evidence cards left out; each page links to the other when both are built.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from what_to_id import atlas_search_page, page_nav

ASSETS = Path(__file__).parent / "eating_assets"
PAGE_NAME = "food-web.html"
OLD_NAME = "eating.html"
OBS_FILE = "foodweb-obs.json"
TEXT_FILE = "foodweb-text.json"
VLM_FILE = "foodweb-vlm.json"
METAWEB_FILE = "metaweb.json"
POLLINATION_NAME = "pollination.html"
POLLINATION_METAWEB = "pollination-metaweb.json"
POLLINATION_OBS = "pollination-obs.json"
REDIRECT = (
    '<!doctype html><meta charset="utf-8"><title>Food web</title>'
    f'<meta http-equiv="refresh" content="0;url={PAGE_NAME}">'
    f"<script>location.replace('{PAGE_NAME}'+location.hash)</script>"
    f'<a href="{PAGE_NAME}">Food web</a>\n'
)


# the photo-search modules (not its page script) the food_search.js control reuses
SEARCH_SCRIPTS = [v for k, v in atlas_search_page.SCRIPTS.items() if k != "__ATLAS_SEARCH_APP__"]


# the pollination page's words: food_web.js reads these over its predation defaults (W)
WORDS = {
    "eat": "visit flowers of",
    "eats": "visits flowers of",
    "lab": "visits",
    "cap": 25,  # partners the survey network draws, most pairs first
    "ing": "visiting flowers of",
    "pred": "Pollinator",
    "preds": "pollinators",
    "prey": "Plant",
    "web": "the pollination web",
    "kin": "plant",
    "drop": "not known to be a plant",
    "none": "No pair has a photograph yet.",
    "cards": False,
    "tries": [
        ["Western Honey Bee", "a common visitor", {"q": "eats", "x": "Apis mellifera"}],
        ["White Clover", "who visits it", {"q": "eaten", "y": "Trifolium repens"}],
        ["Bombus mixtus on White Clover", "documented",
         {"q": "does", "x": "Bombus mixtus", "y": "Trifolium repens"}],
    ],
}  # fmt: skip
HOW = (
    '<details class="how"><summary>How this is made</summary>\n<p id="src"></p>\n'
    "<p>Pairs are GloBI records of pollinates and visitsFlowersOf in British Columbia, an animal "
    "and a plant. Photographed before counts iNaturalist observations whose Interaction -> "
    "Visited flower of field names the plant. Export network is the Food web page's CSV, with "
    "the pollinator in the predator columns and the plant in the prey columns.</p></details>"
)
# (food_web.html text, pollination text), each once in the template
SWAPS = [
    ("Food web: What to ID next", "Pollination: What to ID next"),
    ("<h1>Food web in BC</h1>", "<h1>Pollination in BC</h1>"),
    (
        "Which predator-prey pairs are documented, and which photos could show a new one. Pick a "
        "question, mark what you can see in the most promising photos, and watch the network "
        "fill in. Marks stay in this browser for now.",
        "Which pollinators are documented visiting which flowers in BC. Pick a question and "
        "read the predicted web, then see which pairs have a photograph.",
    ),
    ('<div class="flow">', '<div class="flow nocards">'),
    ("<span>4</span>", "<span>3</span>"),
    (
        "Predicted from the expert food web (GloBI stand-in). Click a cell to ask about that "
        "pair, or a name to ask what it eats or what eats it.",
        "Predicted from GloBI's pollination records (stand-in). Click a cell to ask about that "
        "pair, or a name to ask what it visits or who visits it.",
    ),
    ("Predicted food web, scrolls sideways", "Predicted pollination web, scrolls sideways"),
    ('<span><i class="g"></i>first photograph, confirmed here</span>', ""),
]


def render(data_url: str = "", kind: str = "predation", toggle: bool = False) -> str:
    """The page; a `data_url` (the atlas index, as for search.html) adds "Search photos".
    kind "pollination" is the other page; `toggle` adds the link between the two."""
    html = (ASSETS / "food_web.html").read_text()
    cfg = {"obs": OBS_FILE, "metaweb": METAWEB_FILE, "text": TEXT_FILE, "vlm": VLM_FILE}
    search = ""
    if kind == "pollination":
        cfg = {"obs": POLLINATION_OBS, "metaweb": POLLINATION_METAWEB, "words": WORDS}
        cfg["csv"] = "pollination-network.csv"
        for old, new in SWAPS:
            assert old in html, old
            html = html.replace(old, new)
        html = re.sub(r'<details class="how">.*?</details>', lambda _: HOW, html, flags=re.S)
    elif data_url:
        cfg["search"] = {"dataUrl": data_url}
        search = "\n".join(p.read_text() for p in [*SEARCH_SCRIPTS, ASSETS / "food_search.js"])
    if toggle:
        cfg["page"] = POLLINATION_NAME if kind == "pollination" else PAGE_NAME
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
    """food-web.html and the eating.html redirect in `out_dir`; None without both data files.
    pollination.html joins them, with a link each way, when its two data files are there."""
    out = Path(out_dir)
    if not (out / OBS_FILE).exists() or not (out / METAWEB_FILE).exists():
        return None
    (out / OLD_NAME).write_text(REDIRECT)
    pollen = (out / POLLINATION_OBS).exists() and (out / POLLINATION_METAWEB).exists()
    if pollen:
        (out / POLLINATION_NAME).write_text(render(kind="pollination", toggle=True))
    target = out / PAGE_NAME
    target.write_text(render(data_url, toggle=pollen))
    return target


if __name__ == "__main__":
    import sys

    out = build(sys.argv[1], *sys.argv[2:3])  # an optional atlas data URL, as for atlas_search_page
    print(out or "needs foodweb-obs.json and metaweb.json in the directory")
