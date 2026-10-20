"""Build the site entry point: a card for each page that is present in the output folder.

Writes ``index.html``. A card appears only when its page was built. Pages named in ``live`` are
rebuilt on every run and show that day's date; frozen pages (the committed study page)
show none. Stdlib only, so scripts/atlas_page.sh-style bare python3 can run it.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from what_to_id import page_nav

PAGE_NAME = "index.html"
# (file, title, what the reader can do)
MAIN = (
    ("split.html", "Explore", "Map and photo space side by side."),
    ("search.html", "Photo search", "Find photos by describing them."),
)
EXPERIMENTAL = (("study.html", "What to ID next", "Take a batch of records to identify."),)
CSS = """
main{max-width:64rem;margin:0 auto;padding:2rem 1rem 3rem;font:15px/1.5 system-ui,sans-serif}
h1{font-size:1.6rem;margin:0 0 1.2rem}
.tasks{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:1rem}
a.card{display:block;padding:1.1rem 1.2rem;color:var(--ink);text-decoration:none;
  background:var(--panel);border:1px solid var(--line);border-radius:8px}
a.card:hover{border-color:var(--bar)}
a.card b{display:block;font-size:1.15rem;color:var(--bar);margin-bottom:.3rem}
a.card small{display:block;margin-top:.8rem;color:var(--muted)}
.experiments{margin-top:1.5rem;color:var(--muted)}
.experiments summary{cursor:pointer;min-height:44px;display:list-item;padding:.7rem 0}
"""


def build(out_dir: str | Path, live: tuple[str, ...] = (), day: str | None = None) -> Path:
    """Write ``index.html`` into ``out_dir``, with a card for each page already there."""
    day = day or datetime.now(UTC).strftime("%Y-%m-%d")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def cards(pages):
        found = []
        for name, title, blurb in pages:
            if (out / name).is_file():
                stamp = f"<small>refreshed {day}</small>" if name in live else ""
                found.append(
                    f'<a class="card" href="{name}"><b>{escape(title)}</b>'
                    f"{escape(blurb)}{stamp}</a>"
                )
        return f'<div class="tasks">{"".join(found)}</div>' if found else ""

    experiments = cards(EXPERIMENTAL)
    if experiments:
        experiments = (
            f'<details class="experiments"><summary>Experimental</summary>{experiments}</details>'
        )
    built = {p.name for p in out.glob("*.html")} | {PAGE_NAME}
    html = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Choose a task</title>\n<style>{page_nav.CSS}\n{CSS}</style>\n</head>\n<body>\n"
        f'{page_nav.nav(PAGE_NAME, built)}<main id="main-content">\n<h1>Choose a task</h1>\n'
        f"{cards(MAIN)}\n{experiments}</main>\n</body>\n</html>\n"
    )
    target = out / PAGE_NAME
    target.write_text(html)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m what_to_id.landing_page", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument("--live", nargs="*", default=(), help="Pages built today (dated)")
    args = parser.parse_args()
    print(build(args.out, tuple(args.live)))


if __name__ == "__main__":
    main()
