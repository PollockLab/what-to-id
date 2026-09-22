"""Methods section 8: sample size, from the simulated power of the confirmatory family.

The power numbers come from the power_weighted grid (page_power). The page says which numbers the
model gives and which are its inputs: only the preview's map scores and the taxon group sizes come
from data.
"""

from __future__ import annotations

from what_to_id.manifest import Manifest
from what_to_id.page_doc import Doc, a, codes, see
from what_to_id.page_order_text import order_name
from what_to_id.page_power import (
    IDS,
    NULL_RUNS,
    PLAIN,
    PREVIEW_NULL,
    WEIGHTED,
    power_panel,
)
from what_to_id.page_svg import fmt
from what_to_id.power_weighted import WeightedScenario


def size_section(m: Manifest, f: dict, doc: Doc) -> str:
    sc = WeightedScenario(1)
    level = 0.05 / (sc.n_arms - 1)
    newest, poor = order_name("recency").lower(), order_name("gap_first")
    lpoor = poor.lower()
    # Only this build's orders are named on the page; the plain-count lists may not be in it.
    plain = (
        f"{order_name('similarity').lower()} and {order_name('novelty').lower()}"
        if {"similarity", "novelty"} <= set(m.arms)
        else "the draft protocol's lists judged on the plain count"
    )
    this = (
        ""
        if f["k"] == sc.n_arms
        else f" The simulation is for the draft protocol's {sc.n_arms} lists. This build has "
        f"{f['k']}."
    )
    intro = (
        "<p>Power is the chance that the test finds a difference that is really there. The power "
        "code simulates participants working the lists in turn and runs two comparisons: "
        f"{lpoor} against {newest} on the weighted count, and one generic comparison on the "
        f"plain count. The {sc.n_arms} lists set only how each participant's effort is split and "
        f"the level, 0.05/{sc.n_arms - 1}, Holm's first step over {sc.n_arms - 1} comparisons. "
        "A p that low is always a finding under Holm, so the power shown is a lower bound. A "
        f"weighted run is a finding only when {lpoor} comes out ahead, a plain-count run in "
        f"either direction. No participant count is fixed: the figures run from {IDS[0]} to "
        f"{IDS[-1]}.{this}</p>"
    )
    fig_w = doc.figure(
        power_panel({f"factor {k:.1f}": r for k, r in WEIGHTED[0].items()}, "weighted count"),
        f"{poor} on the weighted count, against {newest}: simulated power at three ID-rate "
        f"factors, its ID rate as a share of the rate on {newest}. Blitz model, 1,000 runs per "
        "point, seed 0. Dashed line: power 0.8. A simulation, not BC data.",
        name="power",
    )
    fig_p = doc.figure(
        power_panel({f"lift {k:.1f}": r for k, r in PLAIN[0].items()}, "plain count"),
        f"{plain[0].upper()}{plain[1:]}, each against {newest}: "
        "simulated power for three lifts. A lift of 0.2 means 20 percent more IDs per record "
        "worked. 1,000 runs per point, seed 0. Dashed line: power 0.8.",
        name="power-plain",
    )
    mean = PREVIEW_NULL[2]
    se = (level * (1 - level) / NULL_RUNS) ** 0.5
    null = (
        '<p id="methods-null-rate"><b>False findings.</b> With no true difference (the preview '
        f"at factor 1.0, {fmt(NULL_RUNS)} runs over both seeds and all participant counts), the "
        f"test found one in {mean:.3f} of runs against its level of {level:.3f}, about "
        f"{mean / level:.1f} times as often, well beyond the simulation error of about "
        f"{se:.3f}. The likely reason is that the split is drawn by record: chance differences "
        "between lists make people lean the same way, which the sign-flip test cannot see. "
        f"That is why the {see('methods-record-test', 'record-level p')} is reported next to "
        "each comparison.</p>"
    )
    factors = " and ".join(f"{k:.1f}" for k in WEIGHTED[0])
    lifts = " and ".join(f"{k:.1f}" for k in PLAIN[0])
    planning = (
        f"<p><b>Planning values, with no source.</b> The ID-rate factors ({factors}), the lifts "
        f"({lifts}), effort (lognormal, median {sc.depth_median:.0f} records, sigma "
        f"{sc.depth_sigma}) and skill, the chance of identifying a reviewed record "
        f"(Beta({sc.skill_a:.0f}, {sc.skill_b:.0f})), are assumed. Only the preview's map scores "
        "and the group sizes come from data.</p>"
    )
    return (
        intro
        + fig_w
        + fig_p
        + null
        + planning
        + "<p>The model assumes one build, one taxon group per participant, and even effort "
        "across lists. Its map scores come from the newest preview records, not a random "
        "sample. A binding batch cap concentrates high map scores on the data-poor list; "
        "without that cap, the lists serve the same scores on average. "
        + a("src/what_to_id/power_weighted.py", "Simulation code and settings")
        + ".</p>"
        + codes("power_weighted", "power")
    )
