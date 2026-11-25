"""Vision-model hints for the Food web page's evidence cards: one small static file.

    python -m what_to_id.foodweb_vlm --out SITE_DIR/foodweb-vlm.json [--csv foodweb_vlm_sample.csv]

The input is a collaborator's run (Burak Ekim, Beery lab, MIT) over BC iNaturalist observations,
reduced to the columns the page shows (src/what_to_id/foodweb_vlm_sample.csv: obs_id, p_feeding,
prey_bbox_0_1000, prey_name_qwen, prey_bioclip_{1,2,3}[_p], taxon_name, predator_canmw). The output
keeps only {"model": provenance, "obs": {"<id>": {p, box?, name?, prey: [[name, p], ...]}}}: no
observer, description, photo or place. A card whose observation id is in the file shows the hint.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

MODEL = (
    "Qwen2.5-VL-7B (P feeding from the Yes logit); Qwen3-VL-8B (prey box, open name); "
    "BioCLIP 2 (prey top 3 over 532 BC metaweb species and 7 coarse groups)"
)
FLOOR = 0.3
SAMPLE = Path(__file__).with_name("foodweb_vlm_sample.csv")


def genus(name: str | None) -> str:
    return (name or "").split(" ")[0].lower()


def slim(row: dict) -> dict:
    """One CSV row as the file's record."""
    r = {"p": round(float(row["p_feeding"]), 3)}
    name = (row.get("prey_name_qwen") or "").strip()
    if name and "none" not in name.lower():  # "none" and "X (none)": the model saw no prey
        r["name"] = name
        if row.get("prey_bbox_0_1000"):  # a box without a prey is drawn on nothing
            r["box"] = [round(float(v)) for v in json.loads(row["prey_bbox_0_1000"])]
    own = {genus(row.get("taxon_name")), genus(row.get("predator_canmw"))} - {""}
    prey = []
    for i in (1, 2, 3):
        n, p = row.get(f"prey_bioclip_{i}"), row.get(f"prey_bioclip_{i}_p")
        # shortcut: floor fit on 3 known hits in a 50-obs sample, refit on annotator labels
        if n and p and float(p) >= FLOOR and genus(n) not in own:
            prey.append([n, round(float(p), 3)])
    r["prey"] = prey
    return r


def build(rows, model: str = MODEL) -> dict:
    return {"model": model, "obs": {str(r["obs_id"]).strip(): slim(r) for r in rows}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv", default=str(SAMPLE))
    ap.add_argument("--model", default=MODEL, help="provenance line shown on the page")
    a = ap.parse_args(argv)
    with open(a.csv, newline="") as f:
        out = build(csv.DictReader(f), a.model)
    if not out["obs"]:
        print("no model rows read", file=sys.stderr)
        return 1
    Path(a.out).write_text(json.dumps(out, separators=(",", ":")))
    print(len(out["obs"]), "observations ->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
