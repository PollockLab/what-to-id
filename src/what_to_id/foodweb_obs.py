"""BC observations with iNaturalist's Eating or Eaten by field, as the small static file the Eating
page reads.

    python -m what_to_id.foodweb_obs --out SITE_DIR/foodweb-obs.json

Read-only: public GETs of /v1/observations with field:Eating or field:Eaten by in BC (place
7085), no login. iNaturalist has no Eating annotation (controlled_terms lists none), only these
fields. Eating (field 13) holds a taxon (the prey) or text; Eaten by (field 879) holds a taxon
(the predator) or text. Each record keeps its own taxon, what the field names (f: [name, id] for
a taxon, x: text), the comment count (their text is not kept), quality grade, date, place and
photo: {"obs": [{id, t: [name, id, common], k: "eating"|"by", f, x, c, q, on, at, ph, np}], "n":
{...}}. np is the photo count, from the same response.

`--kind pollination` reads only field 3126, Interaction->Visited flower of (a taxon: the plant the
observed animal visits), as k "visit" records in pollination-obs.json, for pollination.html.

`--ids FILE` adds the observations of a vision model's run (CSV with an obs_id column, fetched by
id, any place) as k "model" records: the observed taxon is the predator, no field, so the card
asks for the prey like an empty Eating field.

`--metaweb FILE` also writes foodweb-text.json beside it: BC observations of a metaweb predator
species whose description (words eating, eats, ate, feeding) or tags (predation,
eating, feeding) talk about food, with the description and tags kept (k "text"). The evidence
search ranks them against the candidate prey. Comments are not searchable through the API.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

from what_to_id.site_files import publish

API = "https://api.inaturalist.org/v1/observations"
BC_PLACE_ID = 7085
FIELDS = {
    "eating": ("Eating", 13),
    "by": ("Eaten by", 879),
    "visit": (
        "Interaction->Visited flower of",
        3126,
    ),  # a taxon: the plant the observed animal visits
}
POLLINATION_FILE = "pollination-obs.json"
PER_PAGE = 200
TEXT = 80  # characters of a field's text kept
LIMIT = 10000  # iNaturalist refuses page * per_page beyond this


def _species(t: dict) -> str:
    """A subspecies, variety or form named as its species (Feral Pigeon is Rock Pigeon)."""
    n = t["name"]
    return " ".join(n.split()[:2]) if t.get("rank") in ("subspecies", "variety", "form") else n


def slim(o: dict, kind: str) -> dict | None:
    """One observation as the file's record, or None when it has no taxon or photo."""
    t, name = o.get("taxon"), FIELDS.get(kind, (None, None))[1]
    ph = (o.get("photos") or [{}])[0].get("url")
    if not t or not ph:
        return None
    ll = [round(float(v), 4) for v in o["location"].split(",")] if o.get("location") else None
    r = {
        "id": o["id"],
        "t": [_species(t), t["id"], t.get("preferred_common_name") or ""],
        "k": kind,
        "c": o.get("comments_count") or 0,
        "q": o.get("quality_grade"),
        "on": o.get("observed_on") or "",
        "at": o.get("place_guess") or "",
        "ll": ll,
        "ph": ph.replace("/square.", "/medium."),
        "np": len(o["photos"]),
    }
    for f in o.get("ofvs") or []:
        if f.get("field_id") != name:
            continue
        if f.get("taxon"):
            r["f"] = [_species(f["taxon"]), f["taxon"]["id"]]
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
        if (page + 1) * PER_PAGE > LIMIT:
            print(f"{kind}: cut at iNaturalist's {LIMIT} result limit", file=sys.stderr)
            return out
        page += 1
        time.sleep(pause)


def fetch_ids(ids: list[int], pause: float = 1.0) -> list[dict]:
    """Records (k "model", no field) for observations a vision model flagged, by id in batches."""
    import requests

    out = []
    for i in range(0, len(ids), PER_PAGE):
        p = {"id": ",".join(map(str, ids[i : i + PER_PAGE])), "per_page": PER_PAGE}
        r = requests.get(API, params=p, timeout=60, headers={"User-Agent": "what-to-id"})
        r.raise_for_status()
        out += [x for x in (slim(o, "model") for o in r.json()["results"]) if x]
        time.sleep(pause)
    return out


def read_ids(path: str) -> list[int]:
    """The obs_id column of a CSV, in order, without repeats."""
    with open(path, newline="") as f:
        return list(dict.fromkeys(int(r["obs_id"]) for r in csv.DictReader(f)))


# not "caught" or "prey": they name the victim as often (caught in a web, Song Sparrow prey)
SEARCHES = [("description", w) for w in ("eating", "eats", "ate", "feeding")] + [
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
            if (page + 1) * PER_PAGE > LIMIT:
                print(f"{word}: cut at iNaturalist's {LIMIT} result limit", file=sys.stderr)
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
    ap.add_argument("--kind", choices=("predation", "pollination"), default="predation")
    ap.add_argument("--metaweb", help="metaweb.json: also write foodweb-text.json beside --out")
    ap.add_argument("--ids", help="CSV with an obs_id column: add those observations as k model")
    a = ap.parse_args(argv)
    if a.kind == "pollination":  # only the Visited flower of field; no text search, no map copy
        obs = fetch("visit")
        if not obs:
            print("no flower-visit observations read", file=sys.stderr)
            return 1
        doc = {"fetched": date.today().isoformat(), "field": FIELDS["visit"][0]}
        doc |= {"n": counts(obs), "obs": obs}
        Path(a.out).write_text(json.dumps(doc, separators=(",", ":")))
        print(doc["n"], "->", a.out)
        return 0
    obs = fetch("eating") + fetch("by")
    if a.ids:
        seen = {o["id"] for o in obs}
        obs += [o for o in fetch_ids(read_ids(a.ids)) if o["id"] not in seen]
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
