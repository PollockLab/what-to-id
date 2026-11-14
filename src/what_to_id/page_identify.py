"""The Identify page: every pool record at its level, as a narrow column of cards.

    python -m what_to_id.page_identify --out SITE_DIR [--map-url map.html] [--study study.json]

It writes identify.html (every script inlined) and reads, at view time, the map's pool shards and
the levels `pool_levels` wrote beside them (pool-levels.bin, pool-levels-looks.bin and, for the
range maps, pool-levels-range.bin when it was written). The selection is the map's: dates, months,
groups, taxa and the rest of the hash, the area (``wtid-area``) and the lasso's ids
(``wtid-keep``), through the same MapFilter the map and the photo space use. With ``--study``
(page_rotation's study.json) the page opens on the Batches tab, which serves the study's batches
as cards.
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from what_to_id import page_nav, site_files
from what_to_id.page_rotation import read_study

HERE = Path(__file__).parent
ASSETS = HERE / "identify_assets"
PAGE_NAME = "identify.html"
DATES_NAME = "pool-levels-dates.json"  # written by `pool_levels` beside the levels
FIRST_NAME = "pool-levels-first.bin"  # likewise: the first cards, drawn while the pool loads
# The group of records labelled above species whose photo points to one species of the label.
# A placeholder name: rename it here and nowhere else.
NARROW_LABEL = "Narrow it down"
# (level as in identify.LEVEL_NAMES, name, one line for the page)
LEVELS = (
    (1, "Easy confirms", "These look just like their label. Confirm many in one go."),
    (
        5,
        "Might be wrong",
        "The photo is a hard shot, or another species matches it about as well or better."
        " Check whether the label is right.",
    ),
    (
        3,
        NARROW_LABEL,
        "Labelled above species, and the photo points to one species of it. Take it to species.",
    ),
)
# The kinds a tab shows, in order: Might be wrong (5) lists likely mislabels by margin, then odd
# shots, then close calls. This order beat interleaving the three by rank on crowd corrections
# (AUC +0.028 [0.013, 0.044], 10-15 to 11-03 BC).
MERGE = {5: (5, 4, 2)}
# (level, the kind control's name) for Might be wrong's kinds
KINDS = ((5, "Likely mislabelled"), (4, "Odd shots"), (2, "Close calls"))
# GoatCounter's script, pinned (sha384 of https://gc.zgo.at/count.v4.js on 2026-11-05)
GOATCOUNTER_JS = "https://gc.zgo.at/count.v4.js"
GOATCOUNTER_SRI = "sha384-nRw6qfbWyJha9LhsOtSb2YJDyZdKvvCFh0fJYlkquSFjUxp9FVNugbfy8q1jdxI+"
# The iNaturalist OAuth app (PKCE, no secret) that posts identifications as the viewer.
# Placeholder: set INAT_CLIENT_ID to the approved app's client id. Empty hides Sign in, and the
# cards keep their Identify links. The app's redirect URI must be INAT_REDIRECT exactly.
INAT_CLIENT_ID = ""
INAT_REDIRECT = "https://pollocklab.github.io/what-to-id/identify.html"
SCRIPTS = {
    "__ATLAS_SEARCH_META__": HERE / "atlas_search_assets" / "atlas_search_meta.js",
    "__MAP_TAXA__": HERE / "map_assets" / "map_taxa.js",
    "__MAP_CHIPS__": HERE / "map_assets" / "map_chips.js",
    "__IDENTIFY_LINKS__": HERE / "map_assets" / "identify_links.js",
    "__MAP_AREA__": HERE / "map_assets" / "map_area.js",
    "__TAXON_TREE__": HERE / "embeddings_assets" / "taxon_tree.js",
    "__GROUP_LIST__": HERE / "map_assets" / "group_list.js",
    "__MAP_HIST__": HERE / "map_assets" / "map_hist.js",
    "__MAP_TIME__": HERE / "map_assets" / "map_time.js",
    "__MAP_FILTER__": HERE / "map_assets" / "map_filter.js",
    "__EMBEDDINGS_LAYOUT__": HERE / "embeddings_assets" / "embeddings_layout.js",
    "__FETCH_ONCE__": HERE / "site_assets" / "fetch_once.js",
    "__SPACE_MASK__": HERE / "embeddings_assets" / "space_mask.js",
    "__IDENTIFY_RANGES__": ASSETS / "identify_ranges.js",
    "__MAP_USER__": HERE / "map_assets" / "map_user.js",
    "__MAP_PROJECTS__": HERE / "map_assets" / "map_projects.js",
    "__MAP_ONLY__": HERE / "map_assets" / "map_only.js",
    "__IDENTIFY_ONLY__": ASSETS / "identify_only.js",
    "__IDENTIFY_UNCONFIRMED__": ASSETS / "identify_unconfirmed.js",
    "__IDENTIFY_COMPARE__": ASSETS / "identify_compare.js",
    "__IDENTIFY_STUDY__": ASSETS / "identify_study.js",
    "__IDENTIFY_INAT__": ASSETS / "identify_inat.js",
    "__IDENTIFY_NARROW__": ASSETS / "identify_narrow.js",
    "__IDENTIFY_GAPS__": ASSETS / "identify_gaps.js",
    "__IDENTIFY_WWW__": ASSETS / "identify_www.js",
    "__IDENTIFY_PROGRESS__": ASSETS / "identify_progress.js",
    "__IDENTIFY_FLOW__": ASSETS / "identify_flow.js",
    "__IDENTIFY_CARD__": ASSETS / "identify_card.js",
    "__IDENTIFY_WHERE__": ASSETS / "identify_where.js",
    "__GROUP_ICONS__": ASSETS / "group_icons.js",
    "__IDENTIFY_BAR__": ASSETS / "identify_bar.js",
    "__IDENTIFY_SHELL__": ASSETS / "identify_shell.js",
    "__IDENTIFY_APP__": ASSETS / "identify_app.js",
}


def _day(iso: str | None) -> str | None:
    if not iso:
        return None
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def analytics(code: str | None) -> str:
    """GoatCounter's counting script for site ``code`` (``<code>.goatcounter.com``), or nothing."""
    if not code:
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", code):
        raise ValueError(f"not a GoatCounter site code: {code!r}")
    return (
        f'<script data-goatcounter="https://{code}.goatcounter.com/count" '
        """data-goatcounter-settings='{"allow_frame":true}' async """
        f'src="{GOATCOUNTER_JS}" integrity="{GOATCOUNTER_SRI}" crossorigin="anonymous"></script>'
    )


def render(
    map_url: str = "map.html",
    dates: dict | None = None,
    first: str | None = None,
    goatcounter: str | None = None,
    study: dict | None = None,
) -> str:
    """The page; `dates` is `pool_levels.scoring_dates` output, for the About; `first` the URL of
    the first cards beside the map, None without them; `goatcounter` a GoatCounter site code,
    None for no counting; `study` page_rotation's study.json, None for no Batches tab."""
    photos, scored = _day((dates or {}).get("photos")), _day((dates or {}).get("scored"))
    when = f"Photos downloaded on {photos}" if photos else ""
    if scored:
        when = f"{when}, scored on {scored}" if when else f"Scored on {scored}"
    html = (ASSETS / PAGE_NAME).read_text()
    # the page fetches these same origin with default credentials: as=fetch crossorigin matches
    preload = "".join(
        f'<link rel="preload" as="fetch" crossorigin href="{htmllib.escape(urljoin(map_url, f))}">'
        for f in (site_files.META_NAME, first)
        if f
    )
    for key, value in {
        "__PRELOADS__": preload,
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
        "__IDENTIFY_RANGES_CSS__": (ASSETS / "identify_ranges.css").read_text().rstrip(),
        "__MAP_AREA_CSS__": (HERE / "map_assets" / "map_area.css").read_text().rstrip(),
        "__MAP_PANELS_CSS__": (HERE / "map_assets" / "map_panels.css").read_text().rstrip(),
        "__IDENTIFY_UI_CSS__": (ASSETS / "identify_ui.css").read_text().rstrip(),
        "__IDENTIFY_SHELL_CSS__": (ASSETS / "identify_shell.css").read_text().rstrip(),
        "__IDENTIFY_BAR_CSS__": (ASSETS / "identify_bar.css").read_text().rstrip(),
        "__CONFIG__": json.dumps(
            {
                "mapUrl": map_url,
                "levels": LEVELS,
                "merge": MERGE,
                "kinds": KINDS,
                "first": first,
                "study": study and {k: study[k] for k in ("build", "day", "names", "lists")},
                "oauth": {"client": INAT_CLIENT_ID, "redirect": INAT_REDIRECT},
            }
        ).replace("<", "\\u003c"),
        **{f"__LEVEL_{n}__": name for n, name, _ in LEVELS},
        "__SCORING_DATES__": f"{when}." if when else "",
        "__PHOTO_DOWNLOAD__": f"{photos} photo download" if photos else "last photo download",
        "__ANALYTICS__": analytics(goatcounter),
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    return html


def build(
    out_dir: str | Path,
    map_url: str = "map.html",
    goatcounter: str | None = None,
    study: str | Path | None = None,
) -> Path:
    """Write ``identify.html`` into ``out_dir`` and return its path; ``study`` a study.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / PAGE_NAME
    dates = out / DATES_NAME
    first = (out / site_files.MAP_NAME).exists() and site_files.path(out, "first")
    html = render(
        map_url,
        json.loads(dates.read_text()) if dates.exists() else None,
        first.name if first else None,
        goatcounter,
        read_study(study) if study else None,
    )
    target.write_text(html)
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_identify", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory")
    p.add_argument("--map-url", default="map.html", help="map page whose pool files it reads")
    p.add_argument(
        "--goatcounter",
        help="GoatCounter site code; counts page views and clicks (none: no counting)",
    )
    p.add_argument("--study", type=Path, help="study.json (page_rotation); adds the Batches tab")
    a = p.parse_args(argv)
    print(f"page_identify: wrote {build(a.out, a.map_url, a.goatcounter, a.study)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
