"""The How it works page, terms.html: the glossary's terms and each view's own explanation.

    python -m what_to_id.terms_page --out SITE_DIR

The only way in is the More link of a toggletip (glossary.py), so it has no tab. The view
explanations are read from the templates of their pages at build time, never retyped.
"""

from __future__ import annotations

import argparse
import json
import re
from html import escape
from pathlib import Path

from what_to_id import page_identify, page_nav
from what_to_id.glossary import GLOSSARY

HERE = Path(__file__).parent
PAGE_NAME = "terms.html"
# Labels the key does not give, after "id" is read as "ID". Levels use the Identify names.
LABELS = {
    "research-grade": "Research Grade",
    "globi": "GloBI",
    "match-n": "Match number",
    "my-taxa": "My taxa",
    "not-identified-by-me": "Not yet identified by me",
    "all-of-bc": "All of BC",
    **{
        "level-" + re.sub("[^a-z]+", "-", name.lower()).strip("-"): name
        for _, name, _ in page_identify.LEVELS
    },
}
GROUPS = {
    "Records": [
        *("needs-id", "research-grade", "left-needs-id", "batch", "identify-only"),
        *("location-hidden", "location-uncertain", "location-accuracy"),
        *("observed", "uploaded", "introduced", "threatened", "agreeing-ids"),
    ],
    "Levels": ["levels", *(k for k in GLOSSARY if k.startswith("level-"))],
    "Map filters": [
        *("life-groups", "observer-filter", "my-taxa", "not-identified-by-me"),
        *("colour-by-levels", "colour-by-groups", "in-view", "all-of-bc", "your-groups"),
    ],
    "Views": [
        *("photo-space", "taxonomy", "confused-pairs", "closest-matches", "match-n", "cosine"),
        *("clade", "globi", "backlog-per-identifier", "share-needing-id", "identified-to-rank"),
    ],
}
CSS = """
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:8px 0}h2{font-size:18px;margin:28px 0 8px}
h3{font-size:15px;margin:20px 0 6px}
a{color:var(--bar)}dt{font-weight:650;margin-top:10px}dd{margin:2px 0 0}
dt:target{background:var(--chip);outline:2px solid var(--bar)}
""".strip()


def label(key: str) -> str:
    return LABELS.get(key) or re.sub(r"\bid(s?)\b", r"ID\1", key.replace("-", " ").capitalize())


def _cut(source: str, pattern: str) -> str:
    """The first group of `pattern` in `source`, or a clear error when the template moved."""
    m = re.search(pattern, source, re.S)
    if not m:
        raise ValueError(f"terms_page: cannot find {pattern!r}; did its template change?")
    return m.group(1).strip()


def views(dates: dict | None = None) -> list[tuple[str, str, str]]:
    """(id, heading, html) of each explanation, copied from its page's template."""
    identify = _cut(
        page_identify.render(dates=dates),
        r'<details class="about" id="about"><summary>About</summary>(.*?)</details>',
    )
    confusion = _cut(
        (HERE / "confusion_assets/confusion.html").read_text(),
        r"<summary>How this list is made</summary>(.*?)</details>",
    )
    confusion = re.sub(r"<dt>Built</dt><dd>__BUILT__</dd>\s*", "", confusion)  # set per build
    tree = _cut((HERE / "tree_assets/tree.html").read_text(), r'<p id="about" hidden>(.*?)</p>')
    space = _cut(
        (HERE / "embeddings_assets/embeddings.html").read_text(),
        r'<p class="note" id="honest">(.*?)</p>',
    )
    space = space.replace('<span id="fid"></span> ', "")  # filled by the page's script
    return [
        ("identify", "Identify", identify),
        ("confused-pairs-method", "Confused pairs: how this list is made", confusion),
        ("taxonomy-about", "Taxonomy", f"<p>{tree}</p>"),
        ("photo-space-honest", "Photo space", f"<p>{space}</p>"),
    ]


def render(dates: dict | None = None) -> str:
    terms = []
    for group, keys in GROUPS.items():
        items = []
        for k in keys:
            definition, use = GLOSSARY[k]
            text = escape(definition) + (f" {escape(use)}" if use else "")
            items.append(f'<dt id="{k}">{escape(label(k))}</dt><dd>{text}</dd>')
        terms.append(f"<h3>{escape(group)}</h3>\n<dl>{''.join(items)}</dl>")
    how = "\n".join(
        f'<section id="{i}"><h3>{escape(h)}</h3>\n{body}</section>' for i, h, body in views(dates)
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>How it works</title>\n<style>\n{page_nav.CSS}\n{CSS}\n</style></head><body>\n"
        f'{page_nav.nav(PAGE_NAME)}<main id="main-content">\n<h1>How it works</h1>\n'
        f"<h2>Terms</h2>\n{chr(10).join(terms)}\n<h2>How each view works</h2>\n{how}\n"
        "</main></body></html>\n"
    )


def build(out_dir: str | Path) -> Path:
    """Write ``terms.html`` into ``out_dir`` and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dates = out / page_identify.DATES_NAME
    target = out / PAGE_NAME
    target.write_text(render(json.loads(dates.read_text()) if dates.exists() else None))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m what_to_id.terms_page", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="site directory")
    print(build(parser.parse_args().out))


if __name__ == "__main__":
    main()
