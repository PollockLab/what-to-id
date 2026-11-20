"""BC observations with iNaturalist's Eating or Eaten by field, as the small static file the Eating
page reads.

    python -m what_to_id.foodweb_obs --out SITE_DIR/foodweb-obs.json

Read-only: public GETs of /v1/observations with field:Eating or field:Eaten by in BC (place
7085), no login. iNaturalist has no Eating annotation (controlled_terms lists none), only these
fields. Eating (field 13) holds a taxon (the prey) or text; Eaten by (field 879) holds a taxon
(the predator) or text. Each record keeps its own taxon, what the field names (f: [name, id] for
a taxon, x: text), the comment count (their text is not kept), quality grade, date, place and
photo: {"obs": [{id, t: [name, id, common], k: "eating"|"by", f, x, c, q, on, at, ph, np, nt}], "n":
{...}}. np is the photo count and nt is 1 when the description or a comment mentions food (the
text itself is not kept); both come from the same response, no further request.

`--metaweb FILE` also writes foodweb-text.json beside it: BC observations of a metaweb predator
species whose description (words eating, eats, ate, feeding, prey, caught) or tags (predation,
eating, feeding) talk about food, with the description and tags kept (k "text"). The evidence
search ranks them against the candidate prey. Comments are not searchable through the API.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from what_to_id.site_files import publish

API = "https://api.inaturalist.org/v1/observations"
BC_PLACE_ID = 7085
FIELDS = {"eating": ("Eating", 13), "by": ("Eaten by", 879)}
PER_PAGE = 200
TEXT = 80  # characters of a field's text kept
# a description or comment that talks about food: a feeding word or a Latin name (Genus species)
FOOD = re.compile(
    r"\b(eat\w*|ate|feed\w*|fed|prey\w*|devour\w*|kill\w*|hunt\w*|caught|catch\w*|carry\w*|"
    r"carcass|scaveng\w*|bit(?:e|ing)|swallow\w*|consum\w*)\b|\b[A-Z][a-z]{2,} [a-z]{3,}\b"
)


def slim(o: dict, kind: str) -> dict | None:
    """One observation as the file's record, or None when it has no taxon or photo."""
    t, name = o.get("taxon"), FIELDS[kind][1]
    ph = (o.get("photos") or [{}])[0].get("url")
    if not t or not ph:
        return None
    ll = [round(float(v), 4) for v in o["location"].split(",")] if o.get("location") else None
    r = {
        "id": o["id"],
        "t": [t["name"], t["id"], t.get("preferred_common_name") or ""],
        "k": kind,
        "c": o.get("comments_count") or 0,
        "q": o.get("quality_grade"),
        "on": o.get("observed_on") or "",
        "at": o.get("place_guess") or "",
        "ll": ll,
        "ph": ph.replace("/square.", "/medium."),
        "np": len(o["photos"]),
        "nt": int(
            any(
                FOOD.search(t or "")
                for t in [o.get("description"), *(c.get("body") for c in o.get("comments") or [])]
            )
        ),
    }
    for f in o.get("ofvs") or []:
        if f.get("field_id") != name:
            continue
        if f.get("taxon"):
            r["f"] = [f["taxon"]["name"], f["taxon"]["id"]]
        elif str(f.get("value") or "").strip():
            r["x"] = str(f["value"]).strip()[:TEXT]
        break
    return r


def fetch(kind: str, pause: float = 1.0) -> list[dict]:
    import requests

    out, page = [], 1
    while True:
        p = {
            "place_id": BC_PLACE_ID,
            f"field:{FIELDS[kind][0]}": "",
            "per_page": PER_PAGE,
            "page": page,
        }
        r = requests.get(API, params=p, timeout=60, headers={"User-Agent": "what-to-id"})
        r.raise_for_status()
        res = r.json()["results"]
        out += [x for x in (slim(o, kind) for o in res) if x]
        if len(res) < PER_PAGE:
            return out
        page += 1
        time.sleep(pause)


SEARCHES = [("description", w) for w in ("eating", "eats", "ate", "feeding", "prey", "caught")] + [
    ("tags", w) for w in ("predation", "eating", "feeding")
]
TEXT_FILE = "foodweb-text.json"


def predators(metaweb: dict) -> set[str]:
    return {p[0] for p in metaweb["pairs"]}


def slim_text(o: dict, preds: set[str]) -> dict | None:
    """A text-search hit as a record, or None unless it is a photographed species of a predator."""
    t = o.get("taxon") or {}
    name = t.get("name") or ""
    if t.get("rank") != "species" or not (name in preds or name.split(" ")[0] in preds):
        return None
    r = slim(o, "eating")
    if not r:
        return None
    r.update(
        k="text", d=(o.get("description") or "").strip()[: TEXT * 3], g=(o.get("tags") or [])[:8]
    )
    return r


def fetch_text(preds: set[str], pause: float = 1.0) -> list[dict]:
    import requests

    out: dict[int, dict] = {}
    for search_on, word in SEARCHES:
        page = 1
        while True:
            p = {
                "place_id": BC_PLACE_ID,
                "q": word,
                "search_on": search_on,
                "per_page": PER_PAGE,
                "page": page,
                "order_by": "created_at",
            }
            r = requests.get(API, params=p, timeout=60, headers={"User-Agent": "what-to-id"})
            r.raise_for_status()
            res = r.json()["results"]
            for o in res:
                rec = slim_text(o, preds)
                if rec:
                    out.setdefault(rec["id"], rec)
            if len(res) < PER_PAGE:
                break
            page += 1
            time.sleep(pause)
    return list(out.values())


def counts(obs: list[dict]) -> dict:
    return {
        "obs": len(obs),
        "named": sum("f" in o for o in obs),
        "text_only": sum("f" not in o and "x" in o for o in obs),
        "empty": sum("f" not in o and "x" not in o for o in obs),
        "with_comments": sum(o["c"] > 0 for o in obs),
        "needs_id": sum(o["q"] == "needs_id" for o in obs),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--metaweb", help="metaweb.json: also write foodweb-text.json beside --out")
    a = ap.parse_args(argv)
    obs = fetch("eating") + fetch("by")
    if not obs:
        print("no feeding observations read", file=sys.stderr)
        return 1
    with open(a.out, "w") as f:
        json.dump(
            {"fetched": date.today().isoformat(), "n": counts(obs), "obs": obs},
            f,
            separators=(",", ":"),
        )
    site = Path(a.out).parent
    if (
        site / "map.html"
    ).exists():  # the map reads it as META.files.foodobs, for its feeding photos
        publish(site, "foodobs", Path(a.out).name, Path(a.out).read_bytes())
    if a.metaweb:
        text = fetch_text(predators(json.loads(Path(a.metaweb).read_text())))
        (site / TEXT_FILE).write_text(
            json.dumps(
                {"fetched": date.today().isoformat(), "n": len(text), "obs": text},
                separators=(",", ":"),
            )
        )
        print(len(text), "text hits ->", site / TEXT_FILE)
    print(counts(obs), "->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
