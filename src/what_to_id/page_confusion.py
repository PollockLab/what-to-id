"""The confused-pairs page: per species in the Needs ID pool, the species its photos most look like.

    python -m what_to_id.page_confusion --out SITE_DIR --data-url URL [--parquet FILE]

The atlas manifest at ``--data-url`` may carry ``"confusion": {"name", "built_at", "count"}``, the
name of a small parquet beside it (taxon_id, taxon_name, looks_like_taxon_id, looks_like_name,
n_photos, n_species_photos, share). Without that key nothing is written. It writes confusion.html,
one table sorted by photo count, and confusion-taxa.json, the taxon ids with a row, which the tree
page reads to show its "Often confused with" link. ``--parquet`` builds from a local file instead.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from html import escape
from pathlib import Path

import pandas as pd

from what_to_id import page_nav
from what_to_id.page_lookalike import _fetch

PAGE_NAME = "confusion.html"
TAXA_NAME = "confusion-taxa.json"
IDENTIFY = (
    "https://www.inaturalist.org/observations/identify?taxon_id={}&place_id=7085"
    "&quality_grade=needs_id"
)

CSS = """
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:8px 0}
.muted{color:var(--muted)}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:650;color:var(--muted)}
td.n{text-align:right;font-variant-numeric:tabular-nums}
th.n{text-align:right}
a{color:var(--bar)}
tr:target td{background:var(--total)}
@media (max-width:600px){th,td{padding:6px}}
""".strip()


def _name(s: str) -> str:
    return f"<i>{escape(s)}</i>"


def render(df: pd.DataFrame, built_at: str = "") -> str:
    rows, seen = [], set()
    for r in df.sort_values("n_photos", ascending=False, kind="stable").itertuples():
        tid = int(r.taxon_id)
        anchor = "" if tid in seen else f' id="t{tid}"'
        seen.add(tid)
        rows.append(
            f"<tr{anchor}><td>{_name(r.taxon_name)}</td><td>{_name(r.looks_like_name)}</td>"
            f'<td class="n">{int(r.n_photos)}</td><td class="n">{round(r.share * 100):.0f}%</td>'
            f'<td><a href="{IDENTIFY.format(tid)}" target="_blank" rel="noopener">Identify</a>'
            "</td></tr>"
        )
    built = f'<p class="muted">Built {escape(built_at[:10])}</p>' if built_at else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Confused pairs</title><style>{page_nav.CSS}\n{CSS}</style></head><body>\n"
        f'{page_nav.nav(PAGE_NAME)}<main id="main-content"><h1>Confused pairs</h1>\n'
        "<p>A photo counts as confused when the BioCLIP text vector of another species name is "
        "closer to it than the vector of its own species name. The proposals themselves are never "
        "the reference.</p>\n"
        f'{built}<div class="wrap"><table><thead><tr><th>Labelled as</th><th>Looks like</th>'
        '<th class="n">Photos</th><th class="n">Share of its photos</th><th></th></tr></thead>\n'
        f"<tbody>{''.join(rows)}</tbody></table></div></main></body></html>\n"
    )


def build(out: Path, data_url: str | None, parquet: Path | None = None) -> Path | None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        built_at = ""
        if parquet is None:
            if not data_url:
                raise ValueError("give --data-url or --parquet")
            base = data_url.rstrip("/") + "/"
            _fetch(base + "manifest.json", Path(tmp) / "manifest.json")
            entry = json.loads((Path(tmp) / "manifest.json").read_text()).get("confusion")
            if not entry:
                print("page_confusion: the manifest has no confusion table; nothing written")
                return None
            parquet = Path(tmp) / "confusion.parquet"
            _fetch(base + entry["name"], parquet)
            built_at = entry.get("built_at", "")
        df = pd.read_parquet(parquet)
    target = out / PAGE_NAME
    target.write_text(render(df, built_at))
    (out / TAXA_NAME).write_text(json.dumps(sorted({int(t) for t in df["taxon_id"]})))
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_confusion", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory")
    p.add_argument("--data-url", help="atlas base URL holding manifest.json")
    p.add_argument("--parquet", type=Path, help="build from this local file, skipping the manifest")
    a = p.parse_args(argv)
    try:
        target = build(a.out, a.data_url, a.parquet)
    except (ValueError, OSError) as exc:
        print(f"page_confusion: {exc}", file=sys.stderr)
        return 1
    if target:
        print(f"page_confusion: wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
