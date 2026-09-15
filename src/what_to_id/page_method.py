"""The "How the test works" section of the rotation page. Kept out of page_rotation.py for length.

Every word here reaches the public page, so it names no list order (ARM_WORDS guards that) and
says nothing about which letter is which list.
"""

from __future__ import annotations

from what_to_id.manifest import Manifest

_SG = '"Space Grotesk",Inter,system-ui,sans-serif'

METHOD_CSS = f"""
details.how{{margin-top:2rem}}
details.how summary{{cursor:pointer;font-family:{_SG};font-size:.8rem;font-weight:700;
text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}}
details.how summary:hover{{color:var(--acc)}}
.how ul{{margin:.3rem 0;padding-left:1.1rem}}
""".strip()

# Plain words for each order in the method section. Never the arm names, which ARM_WORDS guards.
ORDER_TEXT = {
    "recency": "<b>Newest first.</b> The control, close to what iNaturalist shows today.",
    "gap_first": "<b>Data-poor places first.</b> Records from areas with few or old records.",
    "similarity": "<b>Look-alike photos together.</b> Similar photos sit in the same batch.",
    "novelty": "<b>Unfamiliar photos first.</b> Photos least like any Research Grade photo.",
    "surprise": "<b>Unexpected sightings first.</b> Species seen where, or in a climate where, "
    "few Research Grade records of that species are.",
}


def method_section(manifest: Manifest, n_lists: int) -> str:
    """The test in five steps, with one line per order in this build, folded by default."""
    missing = [a for a in manifest.arms if a not in ORDER_TEXT]
    if missing:
        raise ValueError(f"no page words for list order(s) {missing}; add them to ORDER_TEXT")
    orders = "".join(f"<li>{ORDER_TEXT[a]}</li>" for a in manifest.arms)
    cycle = "".join(f'<span class="n">{i}</span>' for i in range(1, n_lists + 1))
    cycle_html = f'<div class="cycle" aria-hidden="true">{cycle}<i>&#8634;</i></div>'
    steps = (
        "<b>The question.</b> Does the order of records change how many get an ID, and which?",
        "<b>The lists.</b> Each record goes to one list at random, so every list holds the same "
        f"mix of species and observers. Only the order is different:<ul>{orders}</ul>",
        "<b>Your batches.</b> Each press of Next batch takes the next of "
        f"{n_lists} lists, so your batches spread evenly over all of them.{cycle_html}"
        "<p>Your browser picks the turn order at random. The page does not say which list a "
        "batch is from.</p>",
        "<b>The count.</b> After the blitz, we count each participant's species-level IDs on each "
        "list and compare each person with themself. A fast identifier adds the same to every "
        "list.",
        "<b>Nothing else changes.</b> You identify in iNaturalist as usual. Your IDs carry your "
        "name, count toward Research Grade and go to GBIF.",
    )
    items = "".join(f"<li>{s}</li>" for s in steps)
    return f'<details class="how"><summary>How the test works</summary><ol>{items}</ol></details>\n'
