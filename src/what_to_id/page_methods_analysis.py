"""Methods sections 6, 7, 8, 10 and 11: outcomes, analysis, sample size, reproducibility, refs.

Each part opens with what the step does and why it matters. The rest sits in a "More detail"
fold. The analysis plan is a draft. Where the page states a plan and not code, it says "the
draft protocol says". Numbers in the worked examples and the power figure come from the real
code. Section 9, threats, is in page_methods_threats.
"""

from __future__ import annotations

from what_to_id.manifest import Manifest
from what_to_id.page_doc import Doc, a, codes, fold, see
from what_to_id.page_figures import (
    POWER,
    POWER_COMMAND,
    power_figure,
    shuffle_example,
    signflip_example,
    signflip_figure,
)
from what_to_id.page_order_text import PER_LIST, PER_LIST_ANY, order_name
from what_to_id.page_svg import fmt

_PROTOCOL = "docs/protocol.md#what-we-measure-decided-before-the-blitz"
_RANKS = "species, subspecies, variety, form, hybrid or infrahybrid"


def outcomes_section(m: Manifest, f: dict, doc: Doc) -> str:
    rows = [
        [
            "Weighted count",
            "Per participant and list: served records the participant gave an ID at species "
            "level or below, each counting its map score, from 0 to 1, in place of 1. A record "
            "with no score counts 0.",
            "Primary, for data-poor places first",
            "Within a week of the end",
        ],
        [
            "Plain count",
            "The same records, each counting 1. A record counts once per person.",
            'Secondary. The draft protocol says: "Speed orders: the plain count." Nothing in the '
            "code measures time.",
            "Within a week of the end",
        ],
        [
            "Sign test",
            "How many participants did better on a list than on the control.",
            "Secondary, not adjusted",
            "Within a week of the end",
        ],
        [
            "Species share",
            "Code: share of served records whose community ID is at species, or that are Research "
            "Grade. The draft protocol says only: community taxon reached species.",
            "Secondary",
            "30 days after the end",
        ],
        [
            "Research Grade in a new cell",
            "Species that reached Research Grade in a grid cell with no Research Grade record of "
            "that species before the blitz. In the draft protocol, not yet in the code.",
            "The draft protocol's measure for unfamiliar photos first",
            "Not in the code",
        ],
        [
            "Weighted Research Grade",
            "Sum of map scores over served records that reached Research Grade.",
            "Secondary",
            "30 days after the end",
        ],
        [
            "Placebo",
            "The same test on IDs made in a window before the blitz start. It should find "
            f"nothing. {see('methods-placebo', 'Section 7')} says what a quiet window shows.",
            "Check",
            "Not stated",
        ],
        [
            "Exposure",
            "Served records each participant marked reviewed, per list. They should split about "
            "evenly. Reviews have no time stamp.",
            "Check",
            "Not stated",
        ],
    ]
    table = doc.table(
        "Outcomes. Definitions are from the code. Roles and timing are from the draft protocol.",
        ["Outcome", "What is counted", "Role", "Read back"],
        rows,
        wrap=True,
        name="outcomes",
    )
    per_list = doc.table(
        "What the analysis code computes for each list. It computes the same outcomes for every "
        "list.",
        ["List", "What the code computes for it"],
        [[order_name(arm), PER_LIST.get(arm, PER_LIST_ANY)] for arm in m.arms],
        wrap=True,
        name="per-list",
    )
    detail = (
        "<p><b>Who counts.</b> Participants are the identifiers in the blitz's iNaturalist "
        "project or on its sign-up form. The participants code reads one of the two, the project "
        "or the sign-up list, and writes one file of user ids. The analysis counts only "
        "participants when it is given that file. The draft protocol says to give it that "
        "file.</p>"
        "<p><b>The window.</b> From a start date given to the analysis up to a cut-off date "
        "given to the analysis. The code has no fixed dates. The draft protocol says IDs made "
        "during the blitz count, read back within a week of the end. Each ID keeps its own time "
        "stamp, so IDs made after the end do not count. A withdrawn ID still counts. An ID or a "
        "record deleted before the read-back is lost. The read-back is the step that asks "
        "iNaturalist, after the blitz, for every served record and its IDs.</p>"
    )
    return (
        "<p>For each participant and list, the analysis counts the served records the "
        f"participant gave an ID at species level or below ({_RANKS}), made in the window. "
        f"{doc.ref('outcomes')} gives the outcomes and "
        f"{doc.ref('per-list')} what the code computes for each list.</p>"
        + fold("who counts as a participant, and the window", detail)
        + f"{table}{per_list}"
        "<p>Where the draft protocol states no direction for a list, this page does not supply "
        f"one. The plan is in {a(_PROTOCOL, 'the draft protocol')}.</p>"
        + codes("readback", "participants", "analysis")
    )


def analysis_section(m: Manifest, f: dict, doc: Doc) -> str:
    ex, shuf = signflip_example(), shuffle_example()
    n = len(ex["diffs"])
    orders = see("methods-orders", "Section 4")
    all_served = (
        f"It assumes that every record in a list is served. A cap binds in this build ({orders}), "
        "so this build's p from it is not valid."
        if f["cap_reached"]
        else f"It assumes that every record in a list is served ({orders} says whether this build "
        "serves every record)."
    )
    redraw = (
        "In this keyed build each record is drawn on its own and evenly over the lists, as the "
        "assignment code does."
        if m.assignment == "keyed"
        else "In this seeded build the lists of the records in one stratum "
        f"({see('methods-split', 'Section 3')}) are shuffled among them, as the deal does."
    )
    diffs = ", ".join(f"{int(d):+d}" for d in ex["diffs"])
    fig = doc.figure(
        signflip_figure(),
        f"A worked example with {n} made-up people. Their differences are {diffs}, and the sum "
        f"is {int(ex['diffs'].sum())}. Of the {len(ex['sums'])} sign patterns, {ex['extreme']} "
        f"give a sum at least {int(ex['obs'])} from zero (shaded), so p = {ex['extreme']}/"
        f"{len(ex['sums'])} = {ex['p']:.4f}. This is the value the analysis code returns for "
        "these numbers.",
    )
    n_cmp = max(f["k"] - 1, 1)
    flips = (
        "<p><b>The assumption.</b> The test assumes that each difference is as likely to be "
        "positive as negative, and nothing more. It does not cover a difference that all people "
        f"share. The {see('methods-record-test', 'second test')} is the check for this.</p>"
        "<p><b>The drawn p.</b> With more than 12 people left, p = (1 + count) / (10,000 + 1), "
        "where count is the number of drawn patterns at least as far out. The 1 counts the real "
        f"pattern, so p is never 0 {doc.cite('phipson2010')}.</p>"
    )
    record = (
        "<p>The second test holds each record's IDs fixed, redraws which list each record would "
        "have gone to by the same rule the build used, and works out the same summed difference. "
        f"{redraw} p is the share of redrawn splits whose summed "
        "difference is at least as far from zero as the real one, counting the real split. "
        f"{all_served} The analysis command reports this p as <code>p_record</code>, with the "
        "keyed redraw, next to each comparison's p, and does not Holm-adjust it.</p>"
        "<p><b>Worked example.</b> Eight made-up records, four on the control and four on the "
        f"tested list, with {shuf['totals_text']} participant IDs on them in that order. The "
        f"control's four hold {shuf['control']} IDs and the tested list's four hold "
        f"{shuf['treated']}, a difference of {int(shuf['obs'])}. Over {fmt(shuf['reps'])} "
        f"redrawn splits the code returns p = {shuf['p']:.4f}, so with only eight records a gap "
        "of that size is common when nothing but the split changes.</p>"
    )
    holm = (
        "<p>Holm's method keeps the chance of any false finding at or below the test level over "
        "those comparisons. The smallest p is multiplied by the number of tests, the next by one "
        "less, and so on, and no adjusted p is smaller than the one before. Holm runs over one "
        "run of the analysis, which uses one weighting, and over one window. A second weighting, "
        "or the placebo window, is a separate run with its own Holm step, and the code does not "
        "adjust across runs.</p>"
        "<p>The sum adds up every person's difference, so people who make many IDs count for "
        "more. The sign test gives each person one vote, so the two together show whether a lift "
        "comes from a few people or from most.</p>"
    )
    return (
        "<p>For each participant and each list other than the control, take their count on the "
        "list minus their count on the control. A fast identifier adds IDs to every list, not "
        "only to one. People with no difference drop out. The "
        "statistic is the sum of the differences over the people left. If the list makes no "
        "difference, each difference is as likely to be positive as negative, so the test flips "
        f"the sign of each difference and adds again, many times {doc.cite('good2005')}. p is "
        "the share of sign patterns whose sum is at least as far from zero as the real sum. With "
        "12 or fewer people left, p is exact, from every sign pattern. With more, p comes from "
        "10,000 random sign patterns. The draft protocol says the test is two-sided, at 0.05.</p>"
        f"{fig}" + fold("the drawn p, and what the test assumes", flips) + ""
        '<h4 id="methods-record-test">A second test, on the records</h4>'
        "<p>The sign-flip test treats the person as the unit, but the design draws the split "
        "record by record. By chance the lists hold a different number of records and a "
        "different mix, which can make every person lean the same way, and flipping signs inside "
        "a person cannot separate that from the order's effect. This is the check the sign-flip "
        "test cannot give. A secondary test, fixed before the blitz, redraws the split and works "
        "out the same summed difference. It does not replace the primary test, which stays the "
        "weighted count with the sign-flip p.</p>"
        + fold("how the second test redraws the split, with a worked example", record)
        + "<p><b>More than one list.</b> Each list other than the control is compared with the "
        f"control, so this build gives {n_cmp} comparisons, and those {n_cmp} p values are "
        f"adjusted by Holm's method {doc.cite('holm1979')}. <b>Sign test.</b> An exact binomial "
        "test on how many people had a positive difference, zeros dropped. It is reported "
        "without adjustment.</p>"
        + fold("Holm's method, and why the sign test sits next to the sum", holm)
        + '<p id="methods-placebo"><b>Placebo.</b> The same test on IDs from a start given to '
        "the analysis, for example the freeze date, up to the blitz start. A quiet placebo "
        "window does not prove that a finding in the blitz window is real. It only fails to "
        "show one kind of difference, one that is there without the page.</p>" + codes("analysis")
    )


def _reach(series: str) -> int | None:
    """The fewest simulated identifiers with power 0.8 or more on one line of the figure."""
    ns = [r["identifiers"] for r in POWER if r["series"] == series and r["power"] >= 0.8]
    return min(ns, default=None)


def size_section(m: Manifest, f: dict, doc: Doc) -> str:
    window = (
        f"serves at most {fmt(f['batch_size'] * f['max_batches'])} records per list and taxon group"
        if f["max_batches"]
        else "has no cap on batches, so it serves every record of a list and taxon group"
    )
    intro = (
        "<p>Power is the chance that the test finds a lift that is really there. The power code "
        "simulates made-up identifiers and runs the test many times. It uses a lift of 20 "
        "percent: the treatment list gets 20 percent more IDs per record worked. This size is "
        "assumed to show the design. It is not an expected effect.</p>"
    )
    if not POWER:
        return (
            intro
            + "<p>The power simulation has not been run for this page yet.</p>"
            + codes("power")
        )
    model = (
        "<ul><li><b>Every list</b> lines. Each identifier's effort is lognormal, with a median "
        "of 100 records and sigma 1.5, split evenly over the lists. Skill is Beta(2, 3). The "
        "IDs on a list are Binomial(effort on the list, skill), with skill times 1.2 on the "
        "treatment list. The test is the per-identifier sign-flip test at 0.05 divided by the "
        "number of lists other than the control, the first Holm step for the draft protocol's "
        "0.05. This model leaves out batches, other identifiers and the cap. The simulation "
        "draws 1,000 random sign patterns per test, where the analysis draws 10,000, so a "
        "simulated p is coarser than the one the analysis reports.</li>"
        "<li><b>One list each</b> line. Each identifier works one list, with the same effort "
        "and skill. The test compares list totals over the first 3,000 records of each list and "
        "taxon group, with other IDs at 0.05 per record, against a null simulated the same way. "
        "Each identifier starts at a random record within the first 3,000 and wraps around. This "
        f"is close to, but not the same as, this page's random start batch, which {window}. The "
        "test knows the true null spread, so this line is an upper bound.</li></ul>"
    )
    runs = " and ".join(f"<code>{c}</code>" for c in POWER_COMMAND)
    fig = doc.figure(
        power_figure(POWER),
        "Simulated power to find a 20 percent lift, 2,000 runs per point. This is a simulation, "
        f"not BC data. This design uses {f['k']} lists. The 2-list line is from the earlier "
        "2-list draft and is kept for comparison. Dashed line: power 0.8.",
        name="power",
    )
    rerun = (
        f"{model}<p>With 5 identifiers the every-list lines are at 0: there are only 32 sign "
        "patterns, so the smallest two-sided p is 2/32 = 0.0625, above the level of 0.05 with 2 "
        f"lists and 0.05/3 with 4.</p><p>To reproduce {doc.ref('power')}, run {runs}. The "
        'every-list values are the "power (per identifier)" column of the rotation rows. The '
        'one-list values are the "power (window)" column of the sets rows of the 4-list run.</p>'
    )
    two, four = _reach("every-2"), _reach("every-4")
    peak = max(r["power"] for r in POWER if r["series"] == "one-4")
    return (
        intro + f"{fig}<p>In this simulation, with every identifier on every list, power "
        f"reaches 0.8 by {four} identifiers with this design's 4 lists, and by {two} with the "
        "earlier 2-list draft. Four lists need more identifiers, because Holm's correction "
        "splits the level over three comparisons. With one list per identifier power stays at "
        f"{peak:.2f} or below up to 100 identifiers.</p>"
        + fold("the simulation model, and how to rerun it", rerun)
        + codes("power")
    )


def repro_section(m: Manifest, f: dict, doc: Doc) -> str:
    image = "similarity" in m.arms or "novelty" in m.arms
    rows = [
        ["Freeze date", m.freeze],
        ["Blitz start given to the build", m.d1],
        ["Built at", m.created_at],
        ["Design", m.design],
        ["Assignment", m.assignment],
        ["Records in the pool", fmt(m.pool_rows)],
        ["Records served", fmt(f["served_rows"])],
        ["Batch size", fmt(m.batch_size)],
        ["Batches per list and group, at most", fmt(m.max_batches) if m.max_batches else "no cap"],
        ["Image model", f"<code>{m.backbone}</code>" if m.backbone else "none"],
        ["where-to-blitz commit", f"<code>{m.where_to_blitz_ref}</code>"],
        ["where-to-blitz grid hash", f"<code>{m.where_to_blitz_grid or 'not recorded'}</code>"],
        [
            "labelfirst commit",
            f"<code>{m.labelfirst_commit}</code>, the commit of labelfirst, "
            "the library that picks start photos, not of this repository",
        ],
        [
            "Code commit",
            f"<code>{m.code_commit}</code>, the commit of this repository that made the build"
            if m.code_commit
            else "not in this build's manifest. The build record written next to it, "
            "<code>build_record.json</code>, holds it. It is the output of "
            "<code>git rev-parse HEAD</code> in the checkout that ran the build, or, when that "
            "fails, the <code>GITHUB_SHA</code> of the run",
        ],
    ]
    if m.assignment == "keyed":
        rows.append(
            [
                "Key fingerprint",
                f"<code>{m.key_fingerprint}</code>, the first 12 hex characters of the SHA-256 "
                'hash of the text "what-to-id fingerprint" followed by the key. The same key '
                "gives the same fingerprint, so it shows whether two builds used the same key. "
                "It does not reveal the key.",
            ]
        )
    table = doc.table(
        "What identifies this build. None of it is secret.", ["Field", "Value"], rows, wrap=True
    )
    replay = (
        " The rerun cannot yet check builds with image-model lists, so this build cannot be "
        "checked this way."
        if image
        else ""
    )
    if m.assignment == "keyed":
        which = (
            "<p>Each build writes a public build record. This build is keyed: the private key "
            "picks each record's list, so without the key no one can tell which list is which. "
            "The daily job also uses keyed builds.</p>"
        )
    else:
        which = (
            "<p>Each build writes a public build record. This build is seeded: the seed is in "
            "the build record, so the seed and the public code give which list is which. The "
            "daily job uses keyed builds, and the key stays private.</p>"
        )
    detail = (
        "<p>The rerun refuses a pool whose checksum differs, a key whose fingerprint differs, or "
        f"a where-to-blitz grid whose hash differs.{replay} The commands are in "
        f"{a('README.md#use', 'the README')}.</p>{table}"
        "<p>Code links on this page show the latest code on the main branch, which can differ "
        "from the code that made this build. The code commit row above names the commit that "
        "made it.</p>"
    )
    return (
        f"{which}<p>In the blitz, the daily job keeps each day's pool and build record, reruns "
        "the build from them, and stops unless the rerun serves exactly the batches it "
        "logged.</p>"
        + fold("what the rerun checks, and the build record", detail)
        + codes("manifest", "replay", "daily")
    )


def references_section(m: Manifest, f: dict, doc: Doc) -> str:
    return doc.references()
