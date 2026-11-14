"""The How it works page, terms.html: the glossary's terms and each view's own explanation.

    python -m what_to_id.terms_page --out SITE_DIR [--data-url URL] [--study study.json]

The only way in is the More link of a toggletip (glossary.py), so it has no tab. The view
explanations are read from the templates of their pages at build time, never retyped.
"""

from __future__ import annotations

import argparse
import json
import re
from html import escape
from pathlib import Path

from what_to_id import page_identify, page_nav, terms_methods
from what_to_id.glossary import GLOSSARY
from what_to_id.page_method import METHOD_CSS, METHOD_JS
from what_to_id.page_rotation import read_study

HERE = Path(__file__).parent
PAGE_NAME = "terms.html"
# Labels the key does not give, after "id" is read as "ID". Levels use the Identify names.
LABELS = {
    "research-grade": "Research Grade",
    "globi": "GloBI",
    "match-n": "Match number",
    "observer-filter": "Only records the user observed",
    "my-taxa": "Only the user's genera",
    "my-taxa-first": "Your genera first",
    "not-identified-by-me": "Hide records the user identified",
    "all-of-bc": "All of BC",
    **{
        "level-" + re.sub("[^a-z]+", "-", name.lower()).strip("-"): name
        for _, name, _ in page_identify.LEVELS
    },
}
GROUPS = {
    "Records": [
        *("needs-id", "research-grade", "left-needs-id", "batch", "identify-only"),
        "identify-keys",
        *("location-hidden", "location-uncertain", "location-accuracy"),
        *("observed", "uploaded", "introduced", "threatened", "agreeing-ids"),
    ],
    "Levels": ["levels", *(k for k in GLOSSARY if k.startswith("level-"))],
    "Map filters": [
        *(
            "your-selection",
            "life-groups",
            "taxa-filter",
            "observer-filter",
            "my-taxa-first",
            "my-taxa",
            "not-identified-by-me",
        ),
        *("colour-by-levels", "colour-by-groups", "in-view", "all-of-bc", "your-groups"),
    ],
    "Views": [
        *("photo-space", "taxonomy", "confused-pairs", "closest-matches", "match-n", "cosine"),
        *("clade", "globi", "backlog-per-identifier", "share-needing-id", "identified-to-rank"),
    ],
}
CSS = """
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:55ch;margin:0 auto;padding:16px}  /* about 75 characters a line */
main p,main dd,main li{text-wrap:pretty}
h1{font-size:28px;line-height:1.2;margin:8px 0}h2{font-size:22px;line-height:1.25;margin:32px 0 8px}
h3{font-size:18px;margin:24px 0 6px}
a{color:var(--bar)}dt{font-weight:650;margin-top:10px}dd{margin:2px 0 0}
code{font-size:14px;word-break:break-all}ol.refs{padding-left:20px}ol.refs li{margin:4px 0}
table.eval{border-collapse:collapse;font-size:15px}
figure{margin:12px 0;overflow-x:auto}
figure svg{width:100%;min-width:560px;height:auto;font-size:14px;fill:var(--ink)}
figcaption{font-size:15px;color:var(--muted,inherit)}
table.eval th,table.eval td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left}
dt:target{background:var(--chip);outline:2px solid var(--bar)}
.how{--mut:var(--muted);--acc:var(--bar)}
""".strip()
# Linked from the Batches tab on Identify: what the study changes, records and asks.
STUDY = """<h2 id="study">The study behind Batches</h2>
<p>The Batches tab on Identify comes from a research study of which records to show identifiers
first. The records are split by chance into lists, and each list puts its records in its own
order. Your browser takes the lists in a random order, drawn once, and each press of Next batch
shows a batch from the next list in turn. That order of lists is the only thing randomized.</p>
<p>What is recorded: the identifications people make, which are public on iNaturalist, and the
batches your browser was served, which stay in your browser unless you press Download my
batches. If you sign in with iNaturalist, the sign in lasts for that tab only, and the IDs you
post from a card go straight to iNaturalist.</p>
<p>Taking part is just identifying as usual. There is nothing to sign up for, and you can stop
or switch to another tab at any time.</p>"""


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


def render(
    dates: dict | None = None,
    manifest: dict | None = None,
    data_url: str | None = None,
    study: dict | None = None,
) -> str:
    """The page; ``study`` (page_rotation's study.json) adds the test's fold under The study."""
    terms = []
    for group, keys in GROUPS.items():
        items = []
        for k in keys:
            definition, use = GLOSSARY[k]
            text = escape(definition) + (f" {escape(use)}" if use else "")
            items.append(f'<dt id="{k}">{escape(label(k))}</dt><dd>{text}</dd>')
        terms.append(f"<h3>{escape(group)}</h3>\n<dl>{''.join(items)}</dl>")
    fold = (
        # the fold's heading and references ids would repeat the Methods section's
        study["methods"]
        .replace('<h3 id="methods">', '<h3 id="study-methods">')
        .replace('"methods-refs"', '"study-methods-refs"')
        .replace('"#methods-refs"', '"#study-methods-refs"')
        + f"<style>{METHOD_CSS}</style><script>{METHOD_JS}</script>"
        if study and study.get("methods")
        else ""
    )
    how = "\n".join(
        f'<section id="{i}"><h3>{escape(h)}</h3>\n{body}</section>' for i, h, body in views(dates)
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>How it works</title>\n<style>\n{page_nav.CSS}\n{CSS}\n</style></head><body>\n"
        f'{page_nav.nav(PAGE_NAME)}<main id="main-content">\n<h1>How it works</h1>\n'
        f"<h2>Terms</h2>\n{chr(10).join(terms)}\n<h2>How each view works</h2>\n{how}\n"
        f"{STUDY}\n{fold}\n"
        f'<h2 id="methods">Methods</h2>\n{terms_methods.render(manifest, data_url)}\n'
        f'<p>Planning a bioblitz? See <a href="{page_nav.BLITZ}" target="_blank" rel="noopener">'
        'Where to Blitz\u00a0<span aria-hidden="true">\u2197</span>'
        '<span class="site-vh"> (opens in a new tab)</span></a>.</p>\n'
        "</main></body></html>\n"
    )


def build(
    out_dir: str | Path, data_url: str | None = None, study: str | Path | None = None
) -> Path:
    """Write ``terms.html`` into ``out_dir`` and return its path; ``study`` a study.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dates = out / page_identify.DATES_NAME
    manifest = terms_methods.fetch_manifest(data_url) if data_url else None
    target = out / PAGE_NAME
    target.write_text(
        render(
            json.loads(dates.read_text()) if dates.exists() else None,
            manifest,
            data_url,
            read_study(study) if study else None,
        )
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m what_to_id.terms_page", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="site directory")
    parser.add_argument("--data-url", help="atlas base URL holding manifest.json, for Methods")
    parser.add_argument("--study", type=Path, help="study.json (page_rotation), for The study")
    args = parser.parse_args()
    print(build(args.out, args.data_url, args.study))


if __name__ == "__main__":
    main()
