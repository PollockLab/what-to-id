"""Shared by the reference-list fetchers: an iNaturalist GET with backoff, paged species_counts,
and the write guard.
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

API = "https://api.inaturalist.org/v1"
USER_AGENT = os.environ.get("WHAT_TO_ID_USER_AGENT", "what-to-id")
DATA = Path(__file__).parents[1] / "src/what_to_id"
MAX_DROP = 0.10  # a list that shrinks more than this is likelier a broken fetch than a real change


def get(url, tries=8):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
        time.sleep(min(5 * 2**attempt, 60))


def species_counts(query):
    """Every result of /observations/species_counts?query, checked against total_results."""
    out, page = [], 1
    while True:
        j = get(f"{API}/observations/species_counts?{query}&per_page=500&page={page}")
        out += j["results"]
        if page * 500 >= j["total_results"]:
            break
        page += 1
        time.sleep(1)  # be polite to the API
    assert len({r["taxon"]["id"] for r in out}) == j["total_results"], (
        len(out),
        j["total_results"],
    )
    return out


def parse_args(default_out):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--force", action="store_true", help="write even if the list shrinks over 10%%")
    return ap.parse_args()


def write(out, doc, force):
    """Write doc, stamped with today's date, unless its taxa shrank more than MAX_DROP."""
    doc = {"source": doc.pop("source"), "fetched": str(date.today()), **doc}
    old = len(json.loads(out.read_text())["taxa"]) if out.exists() else 0
    new = len(doc["taxa"])
    if old and new < old * (1 - MAX_DROP) and not force:
        raise SystemExit(f"{out.name}: {old} -> {new} taxa is a drop over 10%; --force to write")
    out.write_text(json.dumps(doc) + "\n")
    print(new, "taxa (was", old, ") ->", out)
