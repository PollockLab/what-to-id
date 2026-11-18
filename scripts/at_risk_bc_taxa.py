"""Write src/what_to_id/at_risk_bc_taxa.json: BC needs-ID taxa that are at risk, with their tier.

Usage: uv run python scripts/at_risk_bc_taxa.py [--out FILE] [--force]
"""

import time

import reference_common as rc

FLAGGED = "place_id=7085&quality_grade=needs_id&threatened=true"
CANADA_STATUSES = {"endangered", "threatened", "special concern", "extirpated"}
PER_REQUEST = 30  # /v1/taxa/<ids> answers 422 above this


def tier(statuses):
    """1 listed in Canada, 2 BC S1-S2, 3 BC S3; the first that matches, else None."""
    for c in statuses:
        listed = any(
            w in (c.get("authority") or "") for w in ("COSEWIC", "Species at Risk", "SARA")
        )
        if listed and (c.get("status") or "").replace("_", " ").lower() in CANADA_STATUSES:
            return 1
    iucn = max(
        (
            c.get("iucn") or 0
            for c in statuses
            if c.get("authority") == "NatureServe" and (c.get("place") or {}).get("id") == 7085
        ),
        default=0,
    )
    return 2 if iucn >= 40 else 3 if iucn == 30 else None


def main():
    a = rc.parse_args(rc.DATA / "at_risk_bc_taxa.json")
    ids = sorted({r["taxon"]["id"] for r in rc.species_counts(FLAGGED)})
    tiers = {}
    for i in range(0, len(ids), PER_REQUEST):
        url = (
            f"{rc.API}/taxa/{','.join(map(str, ids[i : i + PER_REQUEST]))}?preferred_place_id=7085"
        )
        for t in rc.get(url)["results"]:
            if n := tier(t.get("conservation_statuses") or []):
                tiers[t["id"]] = n
        time.sleep(1)
    rg = {
        r["taxon"]["id"]: r["count"]
        for r in rc.species_counts("place_id=7085&quality_grade=research")
    }
    doc = {
        "source": "iNaturalist /v1/taxa/<ids>?preferred_place_id=7085 conservation_statuses, "
        f"for the taxa of /v1/observations/species_counts?{FLAGGED}; BC Research Grade counts "
        "from /v1/observations/species_counts?place_id=7085&quality_grade=research",
        "rule": "tier 1 listed in Canada (SARA or COSEWIC: Endangered, Threatened, Special "
        "Concern, Extirpated), tier 2 NatureServe British Columbia S1-S2 (iucn 40 or more), "
        "tier 3 BC S3 (iucn 30), first match",
        "columns": ["taxon_id", "tier", "bc_research_grade"],
        "taxa": [[i, tiers[i], rg.get(i, 0)] for i in sorted(tiers)],
    }
    rc.write(a.out, doc, a.force)


if __name__ == "__main__":
    main()
