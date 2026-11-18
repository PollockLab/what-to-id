"""Write src/what_to_id/invasive_bc_taxa.json: the taxa iNaturalist counts as introduced in BC.

Usage: uv run python scripts/invasive_bc_taxa.py [--out FILE] [--force]
"""

import reference_common as rc

QUERY = "place_id=7085&introduced=true&captive=false"


def main():
    a = rc.parse_args(rc.DATA / "invasive_bc_taxa.json")
    ids = {r["taxon"]["id"] for r in rc.species_counts(QUERY)}
    doc = {
        "source": f"iNaturalist /v1/observations/species_counts?{QUERY}",
        # captive=false: zoo and garden records mark a taxon introduced; needs-ID records are wild
        "rule": "taxa with wild BC (place 7085) observations iNaturalist counts as introduced",
        "taxa": sorted(ids),
    }
    rc.write(a.out, doc, a.force)


if __name__ == "__main__":
    main()
