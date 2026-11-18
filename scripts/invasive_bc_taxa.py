"""Write src/what_to_id/invasive_bc_taxa.json: the taxa iNaturalist counts as introduced in BC.

Usage: uv run python scripts/invasive_bc_taxa.py
"""

import json
import time
import urllib.request
from datetime import date
from pathlib import Path

URL = (
    "https://api.inaturalist.org/v1/observations/species_counts"
    "?place_id=7085&introduced=true&captive=false&per_page=500&page="
)
OUT = Path(__file__).parents[1] / "src/what_to_id/invasive_bc_taxa.json"


def fetch(page):
    req = urllib.request.Request(URL + str(page), headers={"User-Agent": "what-to-id"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    ids, page = set(), 1
    while True:
        j = fetch(page)
        ids.update(r["taxon"]["id"] for r in j["results"])
        if page * 500 >= j["total_results"]:
            break
        page += 1
        time.sleep(1)  # be polite to the API
    assert len(ids) == j["total_results"], (len(ids), j["total_results"])
    doc = {
        "source": "iNaturalist /v1/observations/species_counts"
        "?place_id=7085&introduced=true&captive=false, "
        f"fetched {date.today()}",
        # captive=false: zoo and garden records mark a taxon introduced; needs-ID records are wild
        "rule": "taxa with wild BC (place 7085) observations iNaturalist counts as introduced",
        "taxa": sorted(ids),
    }
    OUT.write_text(json.dumps(doc) + "\n")
    print(len(ids), "taxa ->", OUT)


if __name__ == "__main__":
    main()
