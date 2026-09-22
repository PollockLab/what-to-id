"""Methods sections 6, 7, 10 and 11: outcomes, analysis, reproducibility and references.

Each part opens with what the step does and why it matters. The rest sits in a "More detail"
fold. The analysis plan is a draft. Where the page states a plan and not code, it says "the
draft protocol says". Numbers in the worked examples come from the real code. Section 8, sample
size, is in page_methods_size, and section 9, threats, in page_methods_threats.
"""

from __future__ import annotations

from what_to_id.manifest import Manifest
from what_to_id.page_doc import Doc, a, codes, fold, see
from what_to_id.page_order_text import PER_LIST, PER_LIST_ANY, count_role, order_name
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
            count_role(m.arms, "cell_score"),
            "Within a week of the end",
        ],
        [
            "Plain count",
            "The same records, each counting 1. A record counts once per person.",
            f"{count_role(m.arms, 'none')} Nothing in the code measures time.",
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
            "Not tested. Unfamiliar photos first is judged on the plain count"
            if "novelty" in m.arms
            else "Not tested",
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
        [
            "Outsider share",
            "Per list, the share of served records a non-participant identified first, against "
            f"newest first's ({see('methods-outsider', 'Section 7')}).",
            "Check",
            "Not stated",
        ],
    ]
    table = doc.table(
        "Outcomes. Definitions are from the code. Roles are from the draft protocol and are fixed "
        "in the analysis code. Timing is from the draft protocol.",
        ["Outcome", "What is counted", "Role", "Read back"],
        rows,
        wrap=True,
        name="outcomes",
    )
    per_list = doc.table(
        "What the analysis code computes for each list. It computes both counts for every list "
        "and holds each tested list to its own primary count.",
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
    n_cmp = max(f["k"] - 1, 1)
    flips = (
        "<p><b>The assumption.</b> With no effect, each person's difference is symmetric about "
        "zero: +3 is as likely as -3. The sign test needs less, only that a difference is as "
        "likely positive as negative.</p>"
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
    )
    holm = (
        "<p>Holm's method keeps the chance of any false finding at or below the test level over "
        "those comparisons. The smallest p is multiplied by the number of tests, the next by one "
        "less, and so on, and no adjusted p is smaller than the one before. By default the "
        "analysis command runs Holm over the primary p values only, one per tested list. Each "
        "list's other count is reported next to it, marked secondary, without adjustment. Each "
        "window gets its own Holm step, and the code does not adjust across windows.</p>"
        "<p>The sum adds up every person's difference, so people who make many IDs count for "
        "more. The sign test gives each person one vote, so the two together show whether a lift "
        "comes from a few people or from most.</p>"
    )
    return (
        "<p>For each participant and each list other than the control, take their count on the "
        "list minus their count on the control. A fast identifier adds IDs to every list, not "
        "only to one. People with no difference drop out. The "
        "statistic is the sum of the differences over the people left. If the list makes no "
        "difference, each person's difference is symmetric about zero, so the test flips "
        f"the sign of each difference and adds again, many times {doc.cite('good2005')}. p is "
        "the share of sign patterns whose sum is at least as far from zero as the real sum. With "
        "12 or fewer people left, p is exact, from every sign pattern. With more, p comes from "
        "10,000 random sign patterns. The draft protocol says the test is two-sided, at 0.05.</p>"
        + fold("the drawn p, and what the test assumes", flips)
        + ""
        '<h4 id="methods-record-test">A second test, on the records</h4>'
        "<p>The sign-flip test treats the person as the unit, but the design draws the split "
        "record by record. By chance the lists hold a different number of records and a "
        "different mix, which can make every person lean the same way, and flipping signs inside "
        "a person cannot separate that from the order's effect. In the power simulation this "
        "made false findings more common than the test's level "
        f"({see('methods-null-rate', 'Section 8')}). "
        "A secondary test, fixed before the blitz, redraws the split and works "
        "out the same summed difference. It does not replace the primary test, which stays each "
        "list's primary count with the sign-flip p.</p>"
        + fold("how the second test redraws the split", record)
        + "<p><b>More than one list.</b> Each list other than the control is compared with the "
        f"control on its own primary count ({doc.ref('per-list')}), so this build gives {n_cmp} "
        f"comparisons, and those {n_cmp} p values are "
        f"adjusted by Holm's method {doc.cite('holm1979')}. <b>Sign test.</b> An exact binomial "
        "test on how many people had a positive difference, zeros dropped. It is reported "
        "without adjustment.</p>"
        + fold("Holm's method, and why the sign test sits next to the sum", holm)
        + '<p id="methods-placebo"><b>Placebo.</b> The same test on IDs from a start given to '
        "the analysis, for example the freeze date, up to the blitz start. A quiet placebo "
        "window does not prove that a finding in the blitz window is real. It only fails to "
        "show one kind of difference, one that is there without the page.</p>"
        '<p id="methods-outsider"><b>Other identifiers.</b> For each list, the read-back command, '
        "when it is given the participants, a start and a cut-off (<code>--users</code>, "
        "<code>--start</code>, <code>--cutoff</code>), gives the share of served records that "
        "someone other than a participant identified, at any rank, in the window, before any "
        "participant did, and that share minus newest first's. The observer's IDs on their own "
        "record are left out on both sides: a record added during the blitz gets its observer's ID"
        " at upload, which would otherwise count as found first by someone else. The draft"
        " protocol expects newest first to lose more records this way, which favours the tested "
        "lists. The read-back keeps the time of each ID but not the time a record reached Research"
        " Grade, so this check counts IDs only. It is a check, not an outcome, and has no "
        "test.</p>" + codes("analysis", "readback")
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
