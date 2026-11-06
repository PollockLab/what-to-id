"""The Methods section of terms.html: terms_assets/methods.html with every number filled in.

Numbers come from the code's constants and from the atlas manifest (model, index, layout
fidelity), never typed into the template, so the text cannot drift from what the site runs.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from what_to_id import atlas_update, confusion, host_pairs, levels, pool_levels
from what_to_id.page_lookalike import _fetch

TEMPLATE = Path(__file__).parent / "terms_assets/methods.html"
OUTCOME = TEMPLATE.with_name("levels_outcome.json")  # scripts/levels_outcome.py
LEVEL_NAMES = {
    "none": "No level",
    "easy": "Clear matches",
    "taxonomist": "Close calls",
    "weird": "Odd shots",
    "mislabel": "Might be mislabelled",
}
MISSING = "(not in this build)"  # a build without an index still gets the text


def fetch_manifest(data_url: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        _fetch(data_url.rstrip("/") + "/manifest.json", path)
        return json.loads(path.read_text())


def _pct(x: float) -> str:
    return f"{x:.0%}"


def values(manifest: dict | None) -> dict[str, str]:
    """Placeholder -> text. Manifest-fed ones read `MISSING` without a manifest."""
    m = manifest or {}
    model, taxa = m.get("model", {}), m.get("taxa", {})
    fid, defaults, refine = (
        m.get("layout", {}).get("fidelity", {}),
        m.get("defaults", {}),
        m.get("refine", {}),
    )

    def get(d: dict, k: str, f=str) -> str:
        return f(d[k]) if k in d else MISSING

    layout = MISSING
    if fid:
        ee = fid.get("early_exaggeration", (MISSING, MISSING))
        layout = "; ".join(
            [
                f"affinities {fid.get('affinities', MISSING)}",
                f"initialisation {fid.get('init', MISSING)}",
                f"gradient {fid.get('gradient', MISSING)}",
                f"learning rate {fid.get('learning_rate', MISSING)}",
                f"early exaggeration {ee[0]} for {ee[1]} iterations",
                f"phases {fid.get('phases', MISSING)} (iterations@exaggeration)",
            ]
        )
    return {
        "__MODEL_ID__": get(model, "id"),
        "__MODEL_REVISION__": get(model, "revision"),
        "__DIMS__": get(m, "dims"),
        "__PROMPT__": get(taxa, "prompt"),
        "__TAXA_COUNT__": get(taxa, "count", lambda n: f"{n:,}"),
        "__WEIRD_SHARE__": _pct(levels.WEIRD_SHARE),
        "__EASY_TOP_SHARE__": _pct(levels.EASY_TOP_SHARE),
        "__MIN_PER_CLASS__": str(confusion.MIN_PER_CLASS),
        "__TAXONOMIST_MARGIN__": f"{levels.TAXONOMIST_MARGIN:g}",
        "__MIN_LOOKALIKE_RECORDS__": str(levels.MIN_LOOKALIKE_RECORDS),
        "__STEPS__": str(pool_levels.STEPS),
        "__PAIRS_PER_SPECIES__": str(confusion.FIR_PAIRS_PER_SPECIES),
        "__RECORDS_PER_PAIR__": str(confusion.FIR_RECORDS_PER_PAIR),
        "__NEIGHBOR_K__": str(atlas_update.NEIGHBOR_K),
        "__LAYOUT_DETAIL__": layout,
        "__FID_N__": get(fid, "n_eval", lambda n: f"{n:,}"),
        "__FID_K__": get(fid, "k"),
        "__FID_MEAN__": get(fid, "mean", _pct),
        "__FID_MEDIAN__": get(fid, "median", _pct),
        "__FID_ZERO__": get(fid, "share_zero", _pct),
        "__NLIST__": get(m, "nlist", lambda n: f"{n:,}"),
        "__M__": get(m, "m"),
        "__NBITS__": get(m, "nbits"),
        "__REFINE_BITS__": get(refine, "bits"),
        "__NPROBE__": get(defaults, "nprobe"),
        "__SHORTLIST__": get(defaults, "shortlist"),
        "__UPDATE_NPROBE__": str(atlas_update.DEFAULT_NPROBE),
        "__GLOBI_RELEASE__": host_pairs.DUMP_RELEASE,
        "__GLOBI_MIN_ROWS__": str(host_pairs.MIN_ROWS),
    }


def evaluation() -> dict[str, str]:
    """Placeholders filled from the committed output of scripts/levels_outcome.py."""
    ev = json.loads(OUTCOME.read_text())
    rows = []
    for key, name in LEVEL_NAMES.items():
        r = ev["levels"][key]
        rr = "1 (reference)"
        if "corrected_rr" in r:
            lo, hi = r["corrected_rr_ci"]
            rr = f"{r['corrected_rr']:.2f} [{lo:.2f}, {hi:.2f}]"
        rows.append(
            f"<tr><td>{name}</td><td>{r['n']:,}</td><td>{r['corrected_per_1000']:.2f}</td>"
            f"<td>{rr}</td></tr>"
        )
    return {
        "__EVAL_SCORED__": ev["scored_on"],
        "__EVAL_OUTCOME__": ev["outcome_on"],
        "__EVAL_REPS__": f"{ev['bootstrap_reps']:,}",
        "__EVAL_COHORT__": f"{ev['cohort']:,}",
        "__EVAL_ROWS__": "\n".join(rows),
    }


def render(manifest: dict | None = None) -> str:
    html = TEMPLATE.read_text()
    for key, text in (values(manifest) | evaluation()).items():
        html = html.replace(key, text)
    if "__" in html:
        raise ValueError("terms_methods: a placeholder in methods.html has no value")
    return html
