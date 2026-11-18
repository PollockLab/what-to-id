"""Rerun every reference-list fetcher, then write a markdown summary of what changed per list.

Usage: uv run python scripts/refresh_reference.py [SUMMARY.md] [--force]
The summary (for a PR body) goes to SUMMARY.md, else stdout; fetcher output goes to stderr.

Not covered: challenge_taxa.json (a pinned commit of where-to-blitz, filtered by hand) and
map_assets/bc_parks.json.gz (BC Data Catalogue GeoPackage, scripts/bc_park_places.py).
"""

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import reference_common as rc

LISTS = ["invasive_bc_taxa", "at_risk_bc_taxa"]
CAP = 50


def members(path):
    """{taxon id: tier or None}: what counts as a change; Research Grade counts and dates do not."""
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())["taxa"]
    return {t[0]: t[1] for t in rows} if rows and isinstance(rows[0], list) else dict.fromkeys(rows)


def names(taxa):
    out = {}
    taxa = sorted(taxa)[:CAP]
    for i in range(0, len(taxa), 30):  # /v1/taxa/<ids> answers 422 above 30
        chunk = ",".join(map(str, taxa[i : i + 30]))
        # names are a courtesy: the summary falls back to ids rather than lose the refresh
        with contextlib.suppress(urllib.error.HTTPError):
            out.update({t["id"]: t["name"] for t in rc.get(f"{rc.API}/taxa/{chunk}")["results"]})
        time.sleep(1)
    return out


def section(name, old, new):
    old_ids, new_ids = set(old), set(new)
    retiered = {i for i in old_ids & new_ids if old[i] != new[i]}
    old, new = old_ids, new_ids
    lines = [
        f"### {name}",
        f"{len(old)} -> {len(new)} taxa, {len(new - old)} added, {len(old - new)} removed",
    ]
    if retiered:
        lines.append(f"- {len(retiered)} changed tier")
    for label, taxa in (("Added", new - old), ("Removed", old - new)):
        if taxa:
            got = names(taxa)
            shown = ", ".join(f"{got.get(i, '?')} ({i})" for i in sorted(taxa)[:CAP])
            more = f", and {len(taxa) - CAP} more" if len(taxa) > CAP else ""
            lines.append(f"- {label}: {shown}{more}")
    return "\n".join(lines)


def main():
    argv = sys.argv[1:]
    force = ["--force"] if "--force" in argv else []
    dest = next((a for a in argv if a != "--force"), None)
    parts, changed = [], False
    for name in LISTS:
        path = rc.DATA / f"{name}.json"
        old = members(path)
        script = Path(__file__).with_name(f"{name}.py")
        subprocess.run([sys.executable, str(script), *force], check=True, stdout=sys.stderr)
        new = members(path)
        changed |= old != new
        parts.append(section(name, old, new))
    text = "\n\n".join(parts) + "\n"
    if dest:
        Path(dest).write_text(text)
    else:
        print(text, end="")
    # the workflow opens a PR only for a material change, not for counts and dates alone
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a") as f:
            f.write(f"changed={str(changed).lower()}\n")


if __name__ == "__main__":
    main()
