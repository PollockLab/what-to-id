"""Methods section 9: threats to validity, one short row each and the longer reasoning in a fold.

Each row names the threat in one clause and the response in one sentence. Where another section
explains the response, the row links to it in place of saying it again.
"""

from __future__ import annotations

from what_to_id.manifest import Manifest
from what_to_id.page_doc import Doc, codes, see


def threats_section(m: Manifest, f: dict, doc: Doc) -> str:
    serving = see("methods-serving", "Section 5")
    outsider = see("methods-outsider", "Section 7")
    daily = (
        f"This build is keyed, so a record stays on its list ({see('methods-split', 'Section 3')})."
        if m.assignment == "keyed"
        else "This build is seeded, and a seeded split depends on the whole stratum, so a new "
        "pool can move records. The daily job uses keyed builds, which keep each record on its "
        "list."
    )
    rows = [
        [
            "Other identifiers",
            "People who do not use this page likely meet the newest records first "
            f"({see('identify-default', 'Section 1')}). Under a cap they can remove more of the "
            "control's served records, which favours the tested lists.",
            f"Checked, not corrected ({outsider}). Their IDs do not count in the outcomes "
            f"({see('methods-outcomes', 'Section 6')}). The "
            f"{see('methods-placebo', 'placebo window')} is a partial check.",
        ],
        [
            "Busy identifiers",
            "A few people make most IDs.",
            f"Each person's batches rotate over the lists ({serving}).",
        ],
        [
            "Shared pool",
            "Everyone works on the same records, and an ID by one person can take a record out "
            "of a batch for others, faster on some lists.",
            "This is part of what a list does, not noise that averages out.",
        ],
        [
            "ID accuracy",
            "The count is of species-level IDs, not of correct IDs.",
            "The share of served records at species level or Research Grade after 30 days is a "
            "partial check.",
        ],
        [
            "Knowing the list",
            "People may work differently on a list they think is tested.",
            f"Batches carry no list name ({serving}), and each person is compared with themself.",
        ],
        [
            "Participants' IDs off the page",
            "In normal Identify participants likely meet the newest records first too, and under "
            "a cap those are mostly newest first's served records. A participant's ID on a served "
            "record counts however it was made.",
            "Not corrected. This favours the control, so it works against the tested lists.",
        ],
        [
            "A list runs out",
            f"When a list has no batches left, a person's split is no longer even ({serving}).",
            f"{doc.ref('batches')}, in the {see('more-batches', 'batch fold of Section 5')}, "
            "gives this build's batches per list, and the exposure check shows how each "
            "participant's reviews split.",
        ],
        [
            "Change over time",
            "Rates change over time, and IDs per person may change with them.",
            "All lists run in the same weeks for the same people, so a change in how much a "
            "person identifies touches all lists alike. New records may not: daily builds add them "
            "to every list, newest first puts them in its first batches, and each other list "
            "places them by its own order.",
        ],
        ["Daily builds", "A new build could move records between lists.", daily],
        [
            "Order inside a batch",
            f"The list does not set the order inside a batch ({serving}).",
            "The test is about which records meet together, not the order they are worked in "
            f"({see('methods-estimand', 'Section 5')}).",
        ],
        [
            "More than one list",
            "Each extra list is one more chance of a false finding.",
            f"Holm's method adjusts the p values ({see('methods-analysis', 'Section 7')}).",
        ],
        [
            "Too few participants",
            "The test may miss a real lift.",
            f"{see('methods-size', 'Section 8')} gives the simulated power.",
        ],
        [
            "Chance differences between lists",
            "By chance the lists hold different numbers of records and a different mix.",
            f"The {see('methods-record-test', 'secondary test in Section 7')} checks for this. "
            "The primary test does not correct for it.",
        ],
        [
            "Who takes part",
            "Participants joined the blitz project or signed up. They are not a random sample of "
            "iNaturalist identifiers.",
            "Each person is compared with themself, so who takes part does not bias the "
            "difference. It does decide who the result is about.",
        ],
        [
            "Where results hold",
            "A result holds for records in British Columbia, for the dates of this build, and "
            "for the lists and settings of this build.",
            "Another region, another season or another set of orders has to run the test to know.",
        ],
    ]
    if "gap_first" in m.arms:
        rows.append(
            [
                "No map score",
                "Records more than 20 km from a cell centre have no score.",
                f"The weighted count gives them 0 ({see('methods-outcomes', 'Section 6')}).",
            ]
        )
    table = doc.table(
        "Threats to validity.",
        ["Threat", "What could happen", "What the design does"],
        rows,
        wrap=True,
    )
    return table + codes("analysis", "assign", "page")
