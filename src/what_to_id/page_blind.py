"""The blind identification page: a student answers before the record is revealed.

    python -m what_to_id.page_blind --records records.json --out SITE_DIR [--title TITLE]

``records.json`` is ``[{"id": 1, "group": "Fungi", "photos": [url, ...], "planted": false}, ...]``.
The page embeds only what it shows before the answer; the observation link is built in the browser
from the id after the answer is saved to localStorage. ``planted`` is never written to the page.
"""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path

from what_to_id import page_nav

ASSETS = Path(__file__).parent / "blind_assets"
PAGE_NAME = "blind.html"
OBS_URL = "https://www.inaturalist.ca/observations/"

CSS = """
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 system-ui,-apple-system,
"Segoe UI",sans-serif}
header,main,footer{max-width:640px;margin:0 auto;padding:12px 16px}
header{display:flex;justify-content:space-between;align-items:center;gap:8px}
footer{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;border-top:1px solid var(--line)}
h1{font-size:18px;margin:0}
button,input[type=text]{font:inherit;min-height:44px;padding:0 12px;border:1px solid var(--line);
border-radius:6px;background:var(--panel);color:var(--ink)}
button{cursor:pointer}
button:disabled{opacity:.5;cursor:default}
input[type=text]{width:100%;box-sizing:border-box}
.link{border:0;background:none;color:var(--bar);text-decoration:underline;min-width:44px}
.hint{color:var(--muted);font-size:14px;margin:4px 0}
legend{width:100%}
fieldset{border:0;padding:0;margin:12px 0;display:flex;flex-wrap:wrap;gap:4px 16px}
fieldset label{min-height:44px;display:inline-flex;align-items:center;gap:6px}
#main-photo{width:100%;max-height:70vh;object-fit:contain;background:var(--chip);border-radius:6px}
#thumbs{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
#thumbs button{padding:0;min-height:0;width:64px;height:64px;overflow:hidden}
#thumbs img{width:100%;height:100%;object-fit:cover}
.row{display:flex;gap:8px;flex-wrap:wrap}
#reveal a{display:inline-block;margin:12px 0;min-height:44px;line-height:44px}
[hidden]{display:none!important}
""".strip()

BODY = """
<header><h1>__TITLE__</h1>
<span id="who" hidden>Signed in as <b id="login-name"></b>
<button type="button" id="change" class="link">change</button></span></header>
<main id="main-content">
__NOTHING__
<section id="login-view" hidden><form id="login-form">
<p>You see the photos of one iNaturalist record at a time. Name what you see. The page shows no
suggestion and no other person's ID, on purpose: we want your own judgement.</p>
<ol><li>Look at all the photos. Tap a small photo to see it large.</li>
<li>Type the most precise name you are sure of: species, genus or family. A common or a
scientific name is fine.</li>
<li>Pick how sure you are. If you have no idea, press I cannot say.</li>
<li>After you answer, you can open the record and see what other people said.</li></ol>
<p>Your answers stay in this browser until you press Export answers.</p>
<label for="login">Your iNaturalist login</label>
<input type="text" id="login" autocomplete="off" autocapitalize="none" required>
<p><button type="submit">Start</button></p></form></section>
<section id="record-view" hidden>
<img id="main-photo" alt=""><div id="thumbs"></div>
<p id="photo-hint" class="hint"></p>
<p>Group: <b id="group"></b></p>
<form id="answer"><label for="taxon">What is it? The most precise name you are sure of</label>
<input type="text" id="taxon" autocomplete="off" placeholder="species, genus or family">
<fieldset><legend>How sure are you?</legend>
<label><input type="radio" name="conf" value="sure" required> sure</label>
<label><input type="radio" name="conf" value="likely"> likely</label>
<label><input type="radio" name="conf" value="guess"> guess</label></fieldset>
<div class="row"><button type="submit">Save answer</button>
<button type="button" id="abstain">I cannot say</button></div></form>
<div id="reveal" hidden><p>Your answer: <b id="mine"></b></p>
<p><a id="link" target="_blank" rel="noopener">
See what other people said on iNaturalist (new tab)</a></p>
<button type="button" id="next">Next record</button></div></section>
<section id="done-view" hidden><p>All done. Thank you. Press Export answers to download your
answers as a file.</p></section>
</main>
<footer><span id="count" aria-live="polite"></span>
<button type="button" id="export">Export answers</button>
<button type="button" id="clear" class="link">Clear my answers</button></footer>
"""


def render(records: list[dict], title: str = "Blind identification") -> str:
    """The page. Only id, group and photos of each record are embedded, in the JSON script."""
    shown = [{k: r[k] for k in ("id", "group", "photos")} for r in records]
    data = json.dumps({"records": shown, "obs": OBS_URL}).replace("<", "\\u003c")
    body = BODY.replace("__TITLE__", escape(title)).replace(
        "__NOTHING__", "" if records else "<p>There is nothing to identify.</p>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{page_nav.CSS}\n{CSS}</style></head><body>"
        f'{body}<script type="application/json" id="blind-data">{data}</script>'
        f"<script>{(ASSETS / 'blind_app.js').read_text()}</script></body></html>"
    )


def build(out_dir: str | Path, records: list[dict], title: str = "Blind identification") -> Path:
    """Write ``blind.html`` into ``out_dir`` and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / PAGE_NAME
    target.write_text(render(records, title))
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_blind", description=__doc__)
    p.add_argument("--records", type=Path, required=True, help="JSON list of records")
    p.add_argument("--out", type=Path, required=True, help="site directory")
    p.add_argument("--title", default="Blind identification")
    a = p.parse_args(argv)
    print(f"page_blind: wrote {build(a.out, json.loads(a.records.read_text()), a.title)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
