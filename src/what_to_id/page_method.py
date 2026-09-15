"""The "How the test works" section of the rotation page. Kept out of page_rotation.py for length.

Every word here reaches the public page, so it names no list order (ARM_WORDS guards that) and
says nothing about which letter is which list. Each step has a short line and a folded "More"
block; the blocks say what the code does and link to it, so a reader can check each claim.
"""

from __future__ import annotations

import random

from what_to_id.manifest import Manifest

_SG = '"Space Grotesk",Inter,system-ui,sans-serif'
REPO = "https://github.com/PollockLab/what-to-id"

METHOD_CSS = f"""
details.how{{margin-top:2rem}}
details.how summary{{cursor:pointer;font-family:{_SG};font-size:.8rem;font-weight:700;
text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}}
details.how summary:hover{{color:var(--acc)}}
.how ul{{margin:.3rem 0;padding-left:1.1rem}}
.how .pipe{{list-style:none;display:flex;flex-wrap:wrap;gap:.5rem 1.2rem;padding:0;
margin:1rem 0 1.2rem}}
.how .pipe li{{position:relative;margin:0;padding:.4rem .7rem;background:var(--panel);
border:1px solid #2a3a4d;border-radius:10px;line-height:1.3}}
.how .pipe li+li::before{{content:"\\2192";position:absolute;left:-1rem;top:50%;
transform:translateY(-50%);color:var(--acc)}}
.pipe b{{display:block;font-family:{_SG}}}
.pipe span{{font-size:.8rem}}
details.more{{margin:.3rem 0 .7rem}}
details.more summary{{font-family:inherit;font-size:.88rem;font-weight:600;text-transform:none;
letter-spacing:normal;color:var(--acc)}}
.more p{{margin:.45rem 0}}
.tablewrap{{overflow-x:auto;margin:.5rem 0}}
.how table{{border-collapse:collapse;font-size:.85rem;width:auto;background:transparent;
color:var(--ink)}}
.how th,.how td{{border:1px solid #2a3a4d;padding:.3rem .55rem;text-align:left;
white-space:nowrap}}
.how thead th{{background:var(--panel);color:var(--ink);font-weight:600}}
.how tbody th{{color:var(--mut);font-weight:500}}
.how caption{{text-align:left;font-size:.8rem;padding:0 0 .3rem;color:var(--mut)}}
.how .src{{font-size:.85rem;margin:1rem 0 0}}
""".strip()

# Plain words for each order in the method section. Never the arm names, which ARM_WORDS guards.
ORDER_TEXT = {
    "recency": "<b>Newest first.</b> The control, close to what iNaturalist shows today.",
    "gap_first": "<b>Data-poor places first.</b> Records from areas with few or old records.",
    "similarity": "<b>Look-alike photos together.</b> Similar photos come in groups.",
    "novelty": "<b>Unfamiliar photos first.</b> Photos least like any Research Grade photo.",
    "surprise": "<b>Unexpected sightings first.</b> Species seen where, or in a climate where, "
    "few Research Grade records of that species are.",
}

# How each order sorts, as arms.py and cells.py do it. Same rule: no arm names.
ORDER_DETAIL = {
    "recency": "<b>Newest first</b> sorts by the time the record was added to iNaturalist, "
    "newest first.",
    "gap_first": "<b>Data-poor places first</b> sorts by the where-to-blitz map score of the "
    "nearest 25 km map cell for the record's taxon group, highest first. The score is the map's "
    '"Species discovery" setting: its discovery measure plus 0.6 times its record-age measure, '
    "cut to 0 to 1. A record more than 20 km from a cell centre has no score and goes last. "
    "A taxon group without its own map uses the map for all groups.",
    "similarity": "<b>Look-alike photos together</b> uses an image model (BioCLIP 2.5) that "
    "turns each photo into numbers, so photos that look alike sit close together. It picks start "
    "photos spread across all the photos and grows a group of about one batch around each, "
    "adding the free photo closest to the group centre. Groups with the highest mean map score "
    "come first. Batches are cut from this order, so a batch can end one group and start the "
    "next.",
    "novelty": "<b>Unfamiliar photos first</b> compares each photo, with the same image model, "
    "with every Research Grade photo of its taxon group in the reference pull. Records whose "
    "closest verified photo is least alike come first.",
    "surprise": "<b>Unexpected sightings first</b> gives each record a tail probability: how "
    "far out its place, or its climate, is for the proposed species, against that species' "
    "Research Grade records. Least expected first. Ties go to a range-model score if the build "
    "has one, then to species with the fewest Research Grade records in the region.",
}

_CODE = {
    "inat": "src/what_to_id/inat.py",
    "assign": "src/what_to_id/assign.py",
    "arms": "src/what_to_id/arms.py",
    "cells": "src/what_to_id/cells.py",
    "batches": "src/what_to_id/batches.py",
    "page": "src/what_to_id/page_rotation.py",
    "readback": "src/what_to_id/readback.py",
    "analysis": "src/what_to_id/analysis.py",
    "power": "src/what_to_id/power.py",
    "replay": "src/what_to_id/replay.py",
}


def _a(path: str, text: str) -> str:
    return f'<a href="{REPO}/blob/main/{path}" target="_blank" rel="noopener">{text}</a>'


def _code(key: str) -> str:
    path = _CODE[key]
    return _a(path, f"<code>{path.rsplit('/', 1)[-1]}</code>")


def _more(topic: str, body: str) -> str:
    return f'<details class="more"><summary>More on {topic}</summary>{body}</details>'


def _pipeline() -> str:
    steps = (
        ("Pull", "BC records that need an ID, with a photo"),
        ("Split", "each record to one list, at random"),
        ("Order", "each list sorts its records its own way"),
        ("Deal", "Next batch takes the next list"),
        ("Identify", "in iNaturalist, as usual"),
        ("Compare", "each person with themself"),
    )
    items = "".join(f"<li><b>{b}</b><span>{s}</span></li>" for b, s in steps)
    return f'<ol class="pipe" aria-label="The test from start to end">{items}</ol>'


def _rotation_example(n_lists: int) -> str:
    """Two made-up turn orders over n_lists lists. Numbers only, never a list letter."""
    presses = min(2 * n_lists, 8)
    rows = []
    for seed, opened in ((1, 10 * n_lists), (2, n_lists)):
        cycle = random.Random(seed).sample(range(1, n_lists + 1), n_lists)
        cells = "".join(
            f"<td>{cycle[i % n_lists] if i < opened else ''}</td>" for i in range(presses)
        )
        each = opened // n_lists
        rows.append(
            f'<tr><th scope="row">Opens {opened} batches</th><td>'
            + " &rarr; ".join(map(str, cycle))
            + f"</td>{cells}<td>{each} batch{'es' if each > 1 else ''} from each list</td></tr>"
        )
    head = "".join(f'<th scope="col">Press {i}</th>' for i in range(1, presses + 1))
    return (
        '<div class="tablewrap"><table><caption>Two made-up identifiers (not your order)'
        '</caption><thead><tr><th scope="col">Identifier</th><th scope="col">Turn order</th>'
        f'{head}<th scope="col">In the end</th></tr></thead><tbody>{"".join(rows)}</tbody>'
        "</table></div>"
    )


_WHY_ROTATE = (
    '<div class="tablewrap"><table><caption>Why every identifier works every list</caption>'
    '<thead><tr><th scope="col"></th><th scope="col">One list per identifier</th>'
    '<th scope="col">Every identifier works every list</th></tr></thead><tbody>'
    '<tr><th scope="row">A busy identifier\'s effort goes to</th><td>one list</td>'
    "<td>all lists, equally</td></tr>"
    '<tr><th scope="row">A list scores high because of</th><td>who landed on it</td>'
    "<td>its order</td></tr>"
    '<tr><th scope="row">What is compared</th><td>list totals</td>'
    "<td>each identifier with themself</td></tr></tbody></table></div>"
)


def _assignment(manifest: Manifest) -> str:
    if manifest.assignment == "keyed":
        return (
            "<p>A keyed hash of the record number (HMAC-SHA256 with a private key) picks the "
            "record's list. The same record stays on the same list in every daily build, and "
            "on average each list gets the same mix of taxon groups and observers. The key is kept "
            "private and, by the draft protocol, opened only after the read-back.</p>"
        )
    return (
        "<p>This build shuffled the records once, with a private seed. The shuffle runs inside "
        "each set of records that share a taxon group and an observer group (3 observer groups "
        "from a hash of the user number, and one more for records with no user) and deals the "
        "records to the lists in turn, so inside each set the lists differ in size by one "
        "record at most.</p>"
    )


def _lists_more(manifest: Manifest) -> str:
    when = f" on {manifest.freeze}" if manifest.freeze else ""
    served = (
        f" This build serves the first {int(manifest.max_batches)} batches of each list in each "
        "group."
        if manifest.max_batches
        else ""
    )
    details = "".join(f"<li>{ORDER_DETAIL[a]}</li>" for a in manifest.arms)
    return _more(
        "the lists",
        f"<p>This build holds {int(manifest.pool_rows):,} British Columbia records that needed "
        f"an ID and had a photo when pulled{when} ({_code('inat')}).</p>"
        f"{_assignment(manifest)}"
        "<p>Then each list sorts its records, one taxon group at a time, and cuts them into "
        f"batches of up to {int(manifest.batch_size)} records.{served}</p>"
        f"<ul>{details}</ul>"
        f"<p>Code: {_code('assign')}, {_code('arms')}, {_code('cells')}, {_code('batches')}.</p>",
    )


def _batches_more(n_lists: int) -> str:
    return _more(
        "your batches",
        "<p>A few identifiers make most of the IDs. If each person kept one list, the list that "
        "drew the busiest identifier would win whatever its order. So your browser draws a "
        "random turn order of the lists once, and every press takes the next list in it:</p>"
        f"{_rotation_example(n_lists)}{_WHY_ROTATE}"
        "<p>The turn order is the same for every group, and each group keeps its own place in "
        "it. If a list has no batches left in a group, the press goes to the next list in the "
        "order, so the share stays even only while every list has batches. Your browser also "
        "starts each list at its own random batch and wraps around, so people in the same group "
        "do not all open the same first batches. A second device draws its own turn order, "
        "which is even too. When a new daily build comes, your batches start again and your "
        "turn order stays.</p>"
        "<p>Each batch is one iNaturalist Identify link with the record numbers and the BC "
        "place. Identify hides records that no longer need an ID and records you already reviewed "
        "(checked in a browser on 2026-09-11). The design borrows the "
        "within-person comparison of interleaved search tests "
        '(<a href="https://doi.org/10.1145/2094072.2094078" target="_blank" rel="noopener">'
        "Chapelle et al. 2012</a>).</p>"
        f"<p>Code: {_code('page')} (the <code>nextBatch</code> function).</p>",
    )


def _count_more() -> str:
    protocol = _a("docs/protocol.md#what-we-measure-decided-before-the-blitz", "the draft protocol")
    return _more(
        "the count",
        f"<p>The analysis will be fixed before the blitz. The current plan, in {protocol}:</p><ul>"
        "<li><b>Who counts.</b> Participants are the identifiers who join the blitz's "
        "iNaturalist project.</li>"
        "<li><b>What counts.</b> A participant's ID at species level or below (species, "
        "subspecies, variety, form or hybrid) on a record this page served, made between the "
        "blitz start and the cut-off date. A record counts once per person.</li>"
        "<li><b>Weights.</b> Data-poor places first is judged on a weighted count: each record "
        "counts its map score, from 0 to 1, in place of 1, on newest first too. A record with no "
        "score counts 0.</li>"
        "<li><b>The test.</b> For each participant, their count on a list minus their count on "
        "newest first. The test adds these differences, then flips the sign of each person's "
        "difference at random and adds again. People with no difference drop out. With 12 or "
        "fewer people left it tries every pattern, else 10,000 random ones. If few flipped sums "
        "are as far from zero as the real one, the difference is not chance. Two-sided at 5 "
        "percent, adjusted (Holm) when more than one list is compared with the control.</li>"
        "<li><b>Also reported.</b> A sign test on how many participants did better on each list, "
        "and, 30 days after the blitz ends, the share of served records that reached species "
        "level.</li>"
        "<li><b>Checks.</b> The same test on the days before the blitz, before participants were "
        "sent the page, should find nothing. Each participant's reviewed records should split "
        "about evenly over the lists.</li></ul>"
        f"<p>Code: {_code('readback')}, {_code('analysis')}; {_code('power')} simulates both "
        "page designs to estimate how many participants the test needs.</p>",
    )


def _same_more() -> str:
    return _more(
        "what stays the same",
        "<p>The page holds only list letters and Identify links. Which letter is which list is "
        "kept private and, by the draft protocol, opened after the read-back. The lists are "
        "unlabelled rather than blind: you can sometimes tell a list by its batches. The test "
        "does not depend on you not knowing, because it compares you with yourself.</p>"
        "<p>Identify shows each batch newest first and you can skip freely, so a batch sets "
        "which records you meet together, not the order you identify them in. A result holds "
        "for this region and these identifiers.</p>"
        "<p>In the blitz, each daily build runs again from its saved inputs, and the job stops "
        f"unless the rerun serves exactly the batches it logged ({_code('replay')}).</p>",
    )


def method_section(manifest: Manifest, n_lists: int) -> str:
    """The test in five steps, each with a folded "More" block, folded by default."""
    for table, name in ((ORDER_TEXT, "ORDER_TEXT"), (ORDER_DETAIL, "ORDER_DETAIL")):
        missing = [a for a in manifest.arms if a not in table]
        if missing:
            raise ValueError(f"no page words for list order(s) {missing}; add them to {name}")
    orders = "".join(f"<li>{ORDER_TEXT[a]}</li>" for a in manifest.arms)
    cycle = "".join(f'<span class="n">{i}</span>' for i in range(1, n_lists + 1))
    cycle_html = f'<div class="cycle" aria-hidden="true">{cycle}<i>&#8634;</i></div>'
    readme = _a("README.md#what-the-lists-test", "the README")
    steps = (
        "<b>The question.</b> Does the order of records change how many get an ID, and which?"
        + _more(
            "the question",
            "<p>Each order asks one of two questions. Speed: does it change how many IDs an "
            "hour of work gives? Value: does it change which gaps the IDs fill, for example "
            "places where few species are recorded? Newest first, close to what iNaturalist "
            f"shows today, is the control for both. More in {readme}.</p>",
        ),
        "<b>The lists.</b> Each record goes to one list at random, so on average every list holds "
        f"the same mix of taxon groups and observers. Only the order is different:<ul>{orders}</ul>"
        + _lists_more(manifest),
        "<b>Your batches.</b> Each press of Next batch takes the next of "
        f"{n_lists} lists, so your batches spread evenly over all of them.{cycle_html}"
        "<p>Your browser picks the turn order at random. The page does not say which list a "
        "batch is from.</p>" + _batches_more(n_lists),
        "<b>The count.</b> After the blitz, we count the records each participant gave a "
        "species-level ID on each list and compare each person with themself. A fast identifier "
        "puts the same effort into every list." + _count_more(),
        "<b>Nothing else changes.</b> You identify in iNaturalist as usual. Your IDs carry your "
        "name, count toward Research Grade and go to GBIF." + _same_more(),
    )
    items = "".join(f"<li>{s}</li>" for s in steps)
    return (
        '<details class="how"><summary>How the test works</summary>'
        f"{_pipeline()}<ol>{items}</ol>"
        f'<p class="src">All the code and the draft protocol: '
        f'<a href="{REPO}" target="_blank" rel="noopener">PollockLab/what-to-id</a>.</p>'
        "</details>\n"
    )
