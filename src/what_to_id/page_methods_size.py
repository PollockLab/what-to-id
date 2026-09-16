"""Methods section 8: sample size, from the simulated power of the confirmatory family.

The power numbers come from the power_weighted grid (page_power). The page says which numbers the
model gives and which are its inputs: only the preview's map scores and the taxon group sizes come
from data.
"""

from __future__ import annotations

from functools import partial

from what_to_id.analysis import EXACT_MAX
from what_to_id.manifest import Manifest
from what_to_id.page_doc import Doc, a, codes, fold, see
from what_to_id.page_order_text import order_name
from what_to_id.page_power import (
    BLITZ_BEHIND,
    IDS,
    NOCAP,
    NOCAP_ARGS,
    NULL_RUNS,
    PLAIN,
    PREVIEW_AHEAD,
    PREVIEW_NULL,
    PREVIEW_PER_GROUP,
    PREVIEW_SPAN_DAYS,
    RERUN,
    RERUN_ARGS,
    SCORE_MET,
    WEIGHTED,
    p2,
    power_at,
    power_panel,
)
from what_to_id.page_svg import fmt
from what_to_id.power import BC_GROUP_COUNTS, BC_GROUPS
from what_to_id.power_weighted import BATCH_SIZE, MAX_BATCHES, WeightedScenario


def served_top(n_arms: int, cap: int, top: int = 3) -> list[tuple[str, int]]:
    """The largest groups, each with the preview rank the capped data-poor list keeps down to.

    A list draws about count / n_arms scores with replacement from the group's preview scores and
    keeps its top `cap`, so it serves about the top PREVIEW_PER_GROUP * cap / (count / n_arms)
    of the preview records.
    """
    big = sorted(zip(BC_GROUP_COUNTS, BC_GROUPS, strict=True), reverse=True)[:top]
    return [(g, round(PREVIEW_PER_GROUP * cap / (n / n_arms))) for n, g in big]


def _and(items: list[str]) -> str:
    return f"{', '.join(items[:-1])} and {items[-1]}" if len(items) > 1 else "".join(items)


def size_section(m: Manifest, f: dict, doc: Doc) -> str:
    sc = WeightedScenario(1)
    level = 0.05 / (sc.n_arms - 1)
    cap = MAX_BATCHES * BATCH_SIZE
    bind = [g for g, n in zip(BC_GROUPS, BC_GROUP_COUNTS, strict=True) if n / sc.n_arms > cap]
    free = [g for g in BC_GROUPS if g not in bind]
    ctl, dp = SCORE_MET["blitz"]
    newest, poor = order_name("recency").lower(), order_name("gap_first")
    lpoor = poor.lower()
    # Only this build's orders are named on the page; the plain-count lists may not be in it.
    plain = (
        f"{order_name('similarity').lower()} and {order_name('novelty').lower()}"
        if {"similarity", "novelty"} <= set(m.arms)
        else "the draft protocol's lists judged on the plain count"
    )
    w, p = partial(power_at, WEIGHTED), partial(power_at, PLAIN)
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
    results = (
        f"<p>For {lpoor}, if participants identify its records at the same rate as "
        f"{newest}'s, power is {w(1.0, 10)} with 10 participants. At 0.8 times that rate "
        f"it is {w(0.8, 10)} with 10 and {w(0.8, 20)} with 20. At 0.6 times it is {w(0.6, 20)} "
        f"with 20 and {w(0.6, 50)} with 50. It came out behind in at most {BLITZ_BEHIND:.3f} of "
        f"these runs. On the plain count, for {plain}, a lift of "
        f"0.3 gives {p(0.3, 20)} with 20 participants, 0.2 gives {p(0.2, 25)} with 25 and "
        f"{p(0.2, 40)} with 40, and 0.1 gives {p(0.1, 50)} with 50. A range is two seeds that "
        "round apart.</p>"
    )
    (top_g, top_k), *rest_top = served_top(sc.n_arms, cap)
    runs, ids, nc_ctl, nc_dp, nc_ahead = NOCAP
    why = (
        f"<p><b>Why the weighted count can lead.</b> The planned cap, {MAX_BATCHES} batches of "
        f"up to {BATCH_SIZE} records per list and taxon group, binds in {len(bind)} of the "
        f"{len(BC_GROUPS)} taxon groups, all but {_and(free)}. There {lpoor} serves only its "
        f"highest map scores and {newest} its newest records. In the model the records met on "
        f"{lpoor} have an average map score of {dp:.3f}, against {ctl:.3f} on {newest}. The "
        "model draws each list's scores, with replacement, from its group's "
        f"{fmt(PREVIEW_PER_GROUP)} preview records, and {lpoor} keeps its top {fmt(cap)}: like "
        f"the top {top_k} of the {fmt(PREVIEW_PER_GROUP)} preview records in {top_g}, "
        f"{_and([f'the top {k} in {g}' for g, k in rest_top])}. The real pool's top {fmt(cap)} "
        "per list is not measured, nor is the ID rate. The weighted count favours "
        f"{lpoor} while participants identify its records at more than {ctl / dp:.2f} times "
        f"their rate on {newest}, so the test mostly asks whether they slow down on data-poor "
        "records by more than that.</p>"
        "<p>The lead is a mechanism of the model, the cap keeping each list's top scores. With "
        "no binding cap the lists meet the same scores: in the preview both averaged "
        f"{SCORE_MET['preview'][0]:.3f} and {lpoor} was ahead in at most {p2(PREVIEW_AHEAD)} of "
        f"runs at any factor, and the blitz model with no cap ({runs} runs, {ids} participants, "
        f"factor 1.0, seed 0) gave {nc_ctl:.3f} on {newest} and {nc_dp:.3f} on {lpoor}, with "
        f"{'none' if nc_ahead == 0 else p2(nc_ahead)} ahead.</p>"
    )
    build = (
        "In this build a cap binds."
        if f["cap_reached"]
        else "In this build no cap binds, so its lists serve records with the same scores on "
        "average."
    )
    limits = (
        f"<p><b>This build.</b> {build} As written, the daily job builds only two lists "
        f"({a('docs/protocol.md#open-before-the-blitz', 'open before the blitz')}).</p>"
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
    rows = [[f"{poor}, weighted, factor {k:.1f}", *(w(k, n) for n in IDS)] for k in WEIGHTED[0]] + [
        [f"Plain count, lift {k:.1f}", *(p(k, n) for n in IDS)] for k in PLAIN[0]
    ]
    table = doc.table(
        "Simulated power by number of participants, 1,000 runs per point.",
        ["Line", *(str(n) for n in IDS)],
        rows,
        name="power-values",
    )
    detail = (
        f"{table}<p><b>The model.</b> Each run draws participants. Each works one taxon group, "
        "drawn in proportion to the group's BC records that need an ID and have a photo, "
        "created 2025-01-01 to 2026-09-11 (counts from the iNaturalist API on 2026-09-12, "
        f"recorded in power.py). Effort is split evenly over the {sc.n_arms} lists, and each "
        "list's share is worked from a random start batch, whole batches in turn. A reviewed "
        "record is identified with the participant's skill as the chance, times the ID-rate "
        f"factor on {lpoor}, capped at 1. In the blitz model each list of a group holds about a "
        f"quarter of its records, a binomial draw, and serves its first {MAX_BATCHES} batches "
        "in its own order. The plain-count runs use a simpler model: IDs on a list are "
        "Binomial(effort on the list, skill), with skill times one plus the lift on the tested "
        "list, and no batches, cap or other identifiers. Each simulated test is exact with "
        f"{EXACT_MAX} or fewer non-zero differences, as in the analysis, and otherwise draws "
        "1,000 random sign patterns, where the analysis draws 10,000.</p>"
        "<p><b>Limits.</b></p><ul>"
        f"<li>The preview is the newest {fmt(PREVIEW_PER_GROUP)} records that need an ID in each "
        "taxon group, not a random sample of the pool: under a day of uploads for Plantae, "
        f"about {PREVIEW_SPAN_DAYS['Actinopterygii']:.0f} days for Actinopterygii.</li>"
        "<li>The model assumes one daily build, no repeat visits, one taxon group per "
        "participant, and map scores unrelated to a record's age.</li></ul>"
        f"<p><b>Rerun.</b> From the repository root, with where-to-blitz at commit 3bdcc68 "
        f"checked out next to it, run <code>{RERUN[0]}</code>. The seed 1 check and the no-cap "
        f"run end instead in <code>{RERUN_ARGS[1]}</code> and <code>{NOCAP_ARGS}</code>. "
        "With "
        "<code>--webapp-dir</code> the command first scores the pool with the build's scoring "
        "code (<code>cells.score_records</code>). In the output the weighted lines are the "
        '"power" of the rows with exposure "blitz", and the plain lines that of the rows with '
        'outcome "plain".</p>'
    )
    return (
        intro
        + fig_w
        + fig_p
        + results
        + why
        + limits
        + null
        + planning
        + fold("the numbers, the model, its limits, and how to rerun it", detail)
        + codes("power_weighted", "power")
    )
