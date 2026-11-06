"""The Methods section of terms.html: terms_assets/methods.html with every number filled in.

Numbers come from the code's constants and from the atlas manifest (model, index, layout
fidelity), never typed into the template, so the text cannot drift from what the site runs.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from what_to_id import atlas_update, confusion, host_pairs, levels, pool_levels, terms_figures
from what_to_id.page_lookalike import _fetch

TEMPLATE = Path(__file__).parent / "terms_assets/methods.html"
OUTCOME = TEMPLATE.with_name("levels_outcome.json")  # scripts/levels_outcome.py
OUTCOME_B = TEMPLATE.with_name("levels_outcome_b.json")  # the same, on a later pool
CLOSE_CALLS_CHANGED = "2026-11-06"  # pool_levels.quantize: Close calls lowest margin first
ORDERINGS = {
    "page": "The page's order (level, then score within the level)",
    "margin_lowest_first": "Lowest margin first",
    "own_lowest_first": "Lowest own score first",
    "top_lowest_first": "Lowest best score first",
}
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


def _ci(r: dict, col: str, digits: int = 2) -> str:
    lo, hi = r[f"{col}_ci"]
    return f"{r[col]:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


def _level_rows(ev: dict) -> str:
    rows = []
    for key, name in LEVEL_NAMES.items():
        r = ev["levels"][key]
        rr = _ci(r, "corrected_rr") if "corrected_rr" in r else "1 (reference)"
        rows.append(
            f"<tr><td>{name}</td><td>{r['n']:,}</td><td>{r['corrected_per_1000']:.2f}</td>"
            f"<td>{rr}</td></tr>"
        )
    return "\n".join(rows)


def evaluation(data_url: str | None = None) -> dict[str, str]:
    """Placeholders filled from the committed output of scripts/levels_outcome.py."""
    ev = json.loads(OUTCOME.read_text())
    ev_b = json.loads(OUTCOME_B.read_text())
    mis, none = ev["levels"]["mislabel"], ev["levels"]["none"]
    base = ev["baselines"]
    baseline_rows = "\n".join(
        f"<tr><td>{label}</td><td>{_ci(base[k], 'auc', 3)}</td>"
        f"<td>{_ci(base[k + '_shown'], 'auc', 3)}</td></tr>"
        for k, label in ORDERINGS.items()
    )
    cohort = ev["cohort_file"]
    cohort_url = f"{data_url.rstrip('/')}/{cohort}" if data_url and cohort else None

    def rr(r: dict, col: str) -> str:
        return _ci(r, f"{col}_rr")

    return {
        "__EVAL_ROWS__": _level_rows(ev),
        "__CAL_BINS__": str(len(ev["figures"]["corrected_by_margin"]["n"])),
        "__REPL_OUTCOME_FIRST__": ev["outcome_on"],
        "__CLOSE_CHANGED__": CLOSE_CALLS_CHANGED,
        "__REPL_OUTCOME__": ev_b["outcome_on"],
        "__REPL_ROWS__": _level_rows(ev_b),
        "__BASELINE_ROWS__": baseline_rows,
        "__CLOSE_AUC__": _ci(base["close_calls_lowest_margin_first"], "auc", 3),
        "__COHORT_LINK__": f'<a href="{cohort_url}">{cohort}</a>' if cohort_url else MISSING,
        "__FIG_MARGIN__": terms_figures.margin_hist(
            ev["figures"]["margin_hist"], LEVEL_NAMES, [0, -levels.TAXONOMIST_MARGIN]
        ),
        "__FIG_CALIBRATION__": terms_figures.corrected_by_margin(
            ev["figures"]["corrected_by_margin"]
        ),
        "__SUG_MIS__": _pct(mis["to_suggested_share"]),
        "__SUG_MIS_GENUS__": _pct(mis["to_suggested_genus_share"]),
        "__SUG_NONE__": _pct(none["to_suggested_share"]),
        "__SUG_NONE_GENUS__": _pct(none["to_suggested_genus_share"]),
        "__SUG_MIS_RR__": rr(mis, "to_suggested"),
        "__SUG_MIS_GENUS_RR__": rr(mis, "to_suggested_genus"),
        "__EVAL_SCORED__": ev["scored_on"],
        "__EVAL_OUTCOME__": ev["outcome_on"],
        "__EVAL_REPS__": f"{ev['bootstrap_reps']:,}",
        "__EVAL_COHORT__": f"{ev['cohort']:,}",
    }


def render(manifest: dict | None = None, data_url: str | None = None) -> str:
    html = TEMPLATE.read_text()
    for key, text in (values(manifest) | evaluation(data_url)).items():
        html = html.replace(key, text)
    if "__" in html:
        raise ValueError("terms_methods: a placeholder in methods.html has no value")
    return html
