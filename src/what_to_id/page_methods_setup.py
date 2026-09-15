"""Methods sections 1 to 5: design, records, random split, the orders, serving batches.

Every number printed here is either this build's arm-blind aggregate (a total, or the smallest
and largest value over lists) or comes from running the real code on made-up input.
"""

from __future__ import annotations

import math
from collections import Counter

from what_to_id.manifest import Manifest
from what_to_id.page import group_name
from what_to_id.page_doc import Doc, codes
from what_to_id.page_figures import (
    CHANCE_SIMS,
    deal_figure,
    flow_figure,
    list_share_figure,
    serving_figure,
)
from what_to_id.page_order_figures import BS, ORDER_FIGURES
from what_to_id.page_order_text import (
    ORDER_CAPTION,
    ORDER_DETAIL,
    ORDER_PARAMS,
    ORDER_TEXT,
    ORDER_WHY,
    order_name,
)
from what_to_id.page_svg import fmt, range_words


def _span(lo: int, hi: int) -> str:
    return fmt(lo) if lo == hi else f"{fmt(lo)} to {fmt(hi)}"


def build_facts(m: Manifest) -> dict:
    """Arm-blind aggregates of this build: totals, and smallest and largest over lists."""
    per_list = dict.fromkeys(m.arms, 0)
    by_group: dict[str, dict[str, list[int]]] = {}
    for b in m.batches.values():
        per_list[b["arm"]] += len(b["ids"])
        by_group.setdefault(str(b["group"]), {}).setdefault(b["arm"], []).append(len(b["ids"]))
    groups, n_per_list = [], Counter()
    for g in sorted(by_group, key=group_name):
        lists = by_group[g]
        recs = [sum(lists.get(x, [])) for x in m.arms]
        nb = [len(lists.get(x, [])) for x in m.arms]
        sizes = [s for x in m.arms for s in lists.get(x, [])]
        n_per_list.update(nb)
        groups.append(
            {
                "name": group_name(g),
                "records": sum(recs),
                "recs": (min(recs), max(recs)),
                "batches": (min(nb), max(nb)),
                "sizes": (min(sizes), max(sizes)),
            }
        )
    counts = list(per_list.values())
    b_max = max((g["batches"][1] for g in groups), default=0)
    return {
        "b_max": b_max,
        "cap_reached": bool(m.max_batches) and b_max >= int(m.max_batches),
        "k": len(m.arms),
        "pool_rows": int(m.pool_rows),
        "served_rows": sum(counts),
        "n_batches": len(m.batches),
        "batch_size": int(m.batch_size),
        "max_batches": m.max_batches,
        "list_min": min(counts),
        "list_max": max(counts),
        "groups": groups,
        "modal_batches": max(n_per_list, key=lambda n: (n_per_list[n], n)) if n_per_list else 0,
    }


def design_section(m: Manifest, f: dict, doc: Doc) -> str:
    primary = (
        "Draft protocol: per participant, species-level IDs on data-poor places first, each "
        "weighted by its map score, minus the same on newest first."
        if "gap_first" in m.arms
        else "Draft protocol: species-level IDs per participant and list."
    )
    rows = [
        ["Question", "Does the order of records change how many get an ID, and which?"],
        ["Randomised", f"Each record, to one of {f['k']} lists."],
        [
            "Compared",
            "Each participant with themself: their count on each list against their "
            "count on the control.",
        ],
        ["Lists differ in", "Only the order: how records are sorted and cut into batches."],
        [
            "Control",
            "Newest first. Identify shows records newest first by default (iNaturalist source "
            f"{doc.cite('inatsource')}).",
        ],
        ["Primary outcome", primary],
        [
            "Test",
            "Paired sign-flip permutation test, Holm-adjusted when more than one list is "
            "compared with the control. The draft protocol says two-sided at 0.05.",
        ],
        [
            "Dates",
            f"Records added up to {m.freeze}. The build was given {m.d1} as the blitz start. "
            "The draft protocol proposes four weeks in November 2026 and leaves the dates open.",
        ],
        ["Analysis plan", "A draft for the BC team. It is not registered."],
    ]
    premise = (
        "<p>Identification is a rate-limiting step in getting records that are already observed "
        "to Research Grade, and so to GBIF. The Blitz the Gap authors call for expert "
        "identification blitzes and for more informative prioritisation of records to identify "
        f"{doc.cite('hebert2026')}. Expert identification blitzes have been run and studied "
        f"before {doc.cite('mesaglio2025')}. This test asks a narrower question: whether the "
        "order of records changes what gets identified.</p>"
        f"<p>This preview has {f['k']} lists. The draft protocol plans 2 for the blitz: newest "
        "first and data-poor places first. Every value this page gives from the draft protocol, "
        "in this table and later, is a draft. The BC team fixes these values before the blitz.</p>"
    )
    table = doc.table("The design in one table.", ["Part", "This test"], rows, wrap=True)
    fig = doc.figure(
        flow_figure(f),
        "Flow of records through this build, drawn in the style of a CONSORT flow diagram "
        f"{doc.cite('schulz2010')}. The counts are this build's. The lists are not named.",
    )
    return (
        f"{premise}<p>The test is a randomised comparison inside each person. Records are split "
        f"at random over {f['k']} lists that differ only in their order. Each participant works "
        "all lists in turn, and their count on each list is compared with their own count on the "
        f"control list.</p>{table}{fig}"
        + codes("manifest", "assign", "batches", "page", "analysis")
    )


def records_section(m: Manifest, f: dict, doc: Doc) -> str:
    sizes = sorted({g["records"] for g in f["groups"]}) or [0]
    if len(sizes) == 1 and sizes[0] > 0 and sizes[0] % 200 == 0:
        frame = (
            "<p><b>This build is a preview sample.</b> Every taxon group has exactly "
            f"{fmt(sizes[0])} served records, a whole number of pages of 200, so its pull most "
            "likely stopped after a page cap. So it holds the newest records, by record number, "
            "of each taxon group added up to the freeze date. It is not the blitz build and not a "
            "random sample of BC records.</p>"
        )
    else:
        frame = (
            "<p>This page cannot tell from the build record whether this pull stopped early. "
            "The blitz's daily job pulls with no page cap.</p>"
        )
    asks = (
        "in British Columbia (iNaturalist place 7085)",
        "need an ID (quality grade Needs ID)",
        "have a photo",
        "were observed on or after the pull's <code>d1</code> date. The daily job uses 2025-01-01.",
        f"were added to iNaturalist up to the freeze date, {m.freeze}",
    )
    return (
        "<p>The pull asks the iNaturalist API, one taxon group at a time, for records that are:"
        f"</p><ul>{''.join(f'<li>{s}</li>' for s in asks)}</ul>"
        "<p>It asks for the highest record numbers first, which are the newest records, 200 per "
        "page, and it can stop after a set number of pages. It then drops a record with no "
        "coordinates or no photo, and a record number that comes twice. The build record also "
        f"has a field named <code>d1</code>, but it holds another date: the blitz start given to "
        f"the build, {m.d1}. The build record does not keep the pull's <code>d1</code> or page "
        f"cap.</p>{frame}"
        "<p>A taxon group is one of iNaturalist's iconic taxa, for example Birds (Aves). Each "
        "taxon group gets its own batches, and you pick one on this page.</p>"
        f"<p>This build holds {fmt(f['pool_rows'])} records and serves {fmt(f['served_rows'])} "
        f"of them in {fmt(f['n_batches'])} batches, at most {f['b_max']} per list and taxon "
        "group. In the blitz, the daily job adds new records, drops served records that no "
        "longer need an ID, and builds again.</p>" + codes("inat", "pool_state", "daily")
    )


def split_section(m: Manifest, f: dict, doc: Doc) -> str:
    k = f["k"]
    if m.assignment == "keyed":
        how = (
            "<p><b>Keyed</b> means the split is decided by a hash that takes a private key as "
            "well as the record number, so nobody without the key can work out which list a "
            "record is on. A keyed hash of the record number (HMAC-SHA256 with a private key) "
            f"picks the record's list: the first 8 bytes of the hash, read as a number, modulo "
            f"{k}. The list "
            "depends only on the record number and the key, so the same record stays on the same "
            "list in every daily build as the pool grows and shrinks. On average each list gets "
            "the same mix of taxon groups and observers. The key is kept private and, by the "
            "draft protocol, opened only after the read-back.</p>"
        )
    else:
        how = (
            "<p>This build split the records inside strata. A stratum is one taxon group and one "
            "observer bucket. An observer bucket is one of 3 groups made from a checksum (CRC-32) "
            "of the observer's user number, or a fourth bucket for records with no user. The "
            "buckets keep the mix of observers alike across lists. In each stratum, a seed "
            "shuffles the records, and the records are dealt to the lists in turn. Each "
            "stratum's deal starts one list later than the one before, so left-over records do "
            "not all go to the same list. Inside a stratum, list sizes differ by one record at "
            "most.</p>"
        ) + doc.figure(
            deal_figure(k),
            "The split, run by the assignment code on 20 made-up bird records from two observer "
            f"buckets, with {k} made-up lists. Each square is a record in its shuffled place, "
            "coloured by the list it is dealt to. The second stratum starts one list later. The "
            f"numbers 1 to {k} name made-up lists, not the lists on this page.",
        )
    rows = [
        [
            g["name"],
            fmt(g["records"]),
            fmt(g["recs"][0]),
            fmt(g["recs"][1]),
            fmt(g["recs"][1] - g["recs"][0]),
        ]
        for g in f["groups"]
    ]
    table = doc.table(
        "Served records per taxon group in this build. The lists are not named, so the table "
        "gives only the smallest and the largest list.",
        ["Taxon group", "Records", "Smallest list", "Largest list", "Difference"],
        rows,
        name="sizes",
    )
    band = m.assignment == "keyed" and not f["cap_reached"]
    extra = ""
    if m.assignment == "keyed":
        extra = _chance_text(f)
    fig = doc.figure(
        list_share_figure(f["groups"], k, band),
        "The smallest and the largest list in each taxon group, as a share of that group's "
        "served records. The line joins the two. The upright line marks the even share, "
        f"{100 / k:.4g} percent."
        + (
            f" The band is the middle 95% of {fmt(CHANCE_SIMS)} simulated fair splits of the "
            "same number of records over the same number of lists, so a line that reaches past "
            "it is wider than chance usually gives. See the "
            f'<a href="#methods-threats">threats</a> section.'
            if band
            else ""
        ),
        name="shares",
    )
    return how + table + extra + fig + codes("assign")


def _chance_text(f: dict) -> str:
    """One plain sentence on how much list sizes differ by chance under the keyed split."""
    k, gs = f["k"], f["groups"]
    big = max(gs, key=lambda g: g["recs"][1] - g["recs"][0])
    small = min(gs, key=lambda g: g["recs"][1] - g["recs"][0])
    sd = math.sqrt(big["records"] * (1 / k) * (1 - 1 / k))
    return (
        "<p>The keyed split draws each record's list on its own. It does not deal a fixed number "
        "of records to each list, so list sizes in a taxon group differ by chance. For a group of "
        f"{fmt(big['records'])} records over {k} lists, one list's size has a standard deviation "
        f"of about {sd:.0f} records. In this build the largest difference between the smallest "
        f"and the largest list is {fmt(big['recs'][1] - big['recs'][0])} records in "
        f"{big['name'].split(' (')[0]}, and the smallest is "
        f"{fmt(small['recs'][1] - small['recs'][0])} records in "
        f"{small['name'].split(' (')[0]}. Differences of this size are what a fair draw gives. "
        'See the row on chance differences between lists in the <a href="#methods-threats">'
        "threats</a> section.</p>"
    )


def cap_text(f: dict) -> str:
    """Whether this build's cap on batches decides which records are served, from its data."""
    cap = f["max_batches"]
    if not cap:
        return "This build has no cap on batches, so every record is served."
    if not f["cap_reached"]:
        return (
            f"This build has a cap of {cap} batches per list and taxon group. No list reaches "
            "it, so every record is served."
        )
    left = f["pool_rows"] - f["served_rows"]
    return (
        f"This build serves only the first {cap} batches of each list in each taxon group, so "
        f"the order also decides which records are served. {fmt(left)} records are not served."
    )


def orders_section(m: Manifest, f: dict, doc: Doc) -> str:
    cap = " " + cap_text(f)
    parts = [
        "<p>Each list sorts its records one taxon group at a time, then cuts the sorted records "
        f"into batches of up to {f['batch_size']} records, in that order.{cap} The figures run "
        f"the order code on made-up records and cut the result into batches of up to {BS}.</p>"
    ]
    for i, arm in enumerate(m.arms, 1):
        name = order_name(arm)
        fig = doc.figure(ORDER_FIGURES[arm](), f"{name}, {ORDER_CAPTION[arm]}")
        parts.append(
            f'<h4 id="order-{i}">{name}</h4>{fig}<dl class="rule">'
            f"<dt>Rule</dt><dd>{ORDER_DETAIL[arm]}</dd>"
            f"<dt>Parameters</dt><dd>{ORDER_PARAMS[arm](doc)}</dd>"
            f"<dt>Why</dt><dd>{ORDER_WHY[arm](doc)}</dd></dl>"
        )
    keys = ["arms", "cells"] if "gap_first" in m.arms or "similarity" in m.arms else ["arms"]
    if "similarity" in m.arms or "novelty" in m.arms:
        keys.append("embed")
    return "".join(parts) + codes(*keys, "batches")


_WHY_ROTATE = [
    ["A busy identifier's effort goes to", "one list", "all lists, equally"],
    ["A list scores high because of", "who landed on it", "its order"],
    ["What is compared", "list totals", "each identifier with themself"],
]


def serving_section(m: Manifest, f: dict, doc: Doc) -> str:
    k, n = f["k"], f["modal_batches"]
    lo, hi = min((g["batches"][0] for g in f["groups"]), default=0), f["b_max"]
    served = (
        "" if f["cap_reached"] else " No list in this build reaches the cap, so here it does not."
    )
    fig = doc.figure(
        serving_figure(k, n),
        "Serving, with made-up identifiers. Turn order: each press of Next batch takes the next "
        f"list in the browser's turn order, here with {k} lists. The two browsers drew different "
        "turn orders. Start batch: inside one list and taxon group, each browser starts at a "
        "random batch and wraps around. In this build a list has "
        f"{range_words(lo, hi)} batches in a taxon group, most often {n}.",
    )
    rows = [[g["name"], _span(*g["batches"]), _span(*g["sizes"])] for g in f["groups"]]
    batches = doc.table(
        "Batches per list in each taxon group, and records per batch, in this build. The lists "
        "are not named, so the table gives the range over lists.",
        ["Taxon group", "Batches per list", "Records per batch"],
        rows,
    )
    s_lo = min(g["sizes"][0] for g in f["groups"])
    s_hi = max(g["sizes"][1] for g in f["groups"])
    batches += (
        f"<p>Across this build a batch holds {range_words(s_lo, s_hi)} records. A batch is the "
        f"next {f['batch_size']} records of the sorted list, and the last batch of a list in a "
        "taxon group takes the records left, so it is usually smaller. How many records you see "
        "in a batch also depends on how many of them still need an ID when you open it.</p>"
    )
    why = doc.table(
        "Why every identifier works every list.",
        ["", "One list per identifier", "Every identifier works every list"],
        _WHY_ROTATE,
    )
    edges = (
        "<li>A list with no batches left in a taxon group: the press goes to the next list in "
        "the turn order. So the share stays even only while every list has batches.</li>"
        "<li>No list with batches left: the page says you opened every batch in the group.</li>"
        "<li>A second device or browser draws its own turn order and start batches. Each one "
        "is even on its own.</li>"
        "<li>A new daily build: your batches start again and your start batches are drawn "
        "again. Your turn order stays.</li>"
        "<li>Start over puts one group's batches back. The turn order and start batches "
        "stay.</li>"
        "<li>Your place is saved in this browser only.</li>"
    )
    return (
        "<p>Each batch is one iNaturalist Identify link that lists its record numbers and the BC "
        "place, and nothing else. Identify hides records that no longer need an ID (checked in a "
        "browser on 2026-09-11), so a batch can show fewer records than it holds. The draft "
        "protocol says Identify also hides records you already reviewed. This was not "
        "checked.</p>"
        f"<p>Your browser draws a random turn order of the {k} lists once. Each press of Next "
        "batch takes the next list in that order. The turn order is the same for every taxon "
        "group, and each group keeps its own place in it. Inside each list and group, your "
        "browser also draws a random start batch, goes on from there and wraps around to the "
        "first batch.</p>"
        f"{fig}{batches}"
        f"<p>A few identifiers make most of the IDs {doc.cite('hebert2026')}. If each person "
        "kept one list, the list that "
        "drew the busiest identifier would win whatever its order. The design borrows the "
        f"within-person comparison of interleaved search tests {doc.cite('chapelle2012')}.</p>"
        f"{why}<h4>Edge cases</h4><ul>{edges}</ul>"
        '<h4 id="methods-estimand">What a list changes, as you see it</h4>'
        "<p>A list decides which records share a batch and the order of its batches after your "
        "random start. When the build serves only the first batches of each list, it also "
        f"decides which records are served.{served} It does not decide which batch you get "
        "first: your browser picks that at random. It does not decide the order inside a batch: "
        "the batch link carries no order, so Identify sets it, and you can skip. So the test "
        "measures the effect of meeting records in one list's batches in place of newest-first "
        "batches, served with random starts. In this build a list has "
        f"{range_words(lo, hi)} batches in a taxon group, so a random start lands on one of "
        "them, and a person who opens all of a list's batches in one group meets all its records "
        "that still need an ID.</p>" + codes("page", "batches")
    )


__all__ = [
    "ORDER_CAPTION",
    "ORDER_DETAIL",
    "ORDER_PARAMS",
    "ORDER_TEXT",
    "ORDER_WHY",
    "build_facts",
    "cap_text",
    "design_section",
    "order_name",
    "orders_section",
    "records_section",
    "serving_section",
    "split_section",
]
