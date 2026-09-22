"""The "How the test works" section of the rotation page: CSS, the short version and assembly.

Every word here reaches the public page, so it names no list order (ARM_WORDS guards that) and
never pairs a list letter with anything that depends on the order. The six-step flow is the only
summary. "Methods in full" follows, one numbered section per part of the method, built in
page_methods_setup (sections 1 to 5) and page_methods_analysis (6 to 11). Each section says
what the code does and links to it, so a reader can check each claim.
"""

from __future__ import annotations

from what_to_id.manifest import Manifest
from what_to_id.page_doc import REPO, Doc
from what_to_id.page_methods_analysis import (
    analysis_section,
    outcomes_section,
    references_section,
    repro_section,
)
from what_to_id.page_methods_setup import (
    ORDER_DETAIL,
    ORDER_TEXT,
    build_facts,
    design_section,
    orders_section,
    records_section,
    serving_section,
    split_section,
)
from what_to_id.page_methods_size import size_section
from what_to_id.page_methods_threats import threats_section
from what_to_id.page_order_text import order_name

__all__ = ["METHOD_CSS", "ORDER_DETAIL", "ORDER_TEXT", "method_section"]

_SG = '"Space Grotesk",Inter,system-ui,sans-serif'

METHOD_JS = """
(function() {
  function openMethod() {
    var id;
    try { id = decodeURIComponent(window.location.hash.slice(1)); }
    catch (e) { return; }
    var target = document.getElementById(id === 'orders' ? 'methods-orders' : id);
    if (!target || !target.closest('details.how')) return;
    for (var parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    if (target.tagName === 'DETAILS') target.open = true;
    var content = target.querySelector('details.method');
    if (content) content.open = true;
    requestAnimationFrame(function() { target.scrollIntoView(); });
  }
  window.addEventListener('hashchange', openMethod);
  openMethod();
})();
""".strip()

# List colours (Okabe-Ito): none is lighter, darker or "first", so none suggests an order.
# Batch shades do step from light to dark, because batches do come in order.
METHOD_CSS = f"""
details.how{{margin-top:2rem}}
details.how>summary{{cursor:pointer;font-family:{_SG};font-size:.8rem;font-weight:700;
text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}}
details.how>summary:hover{{color:var(--acc)}}
.how details.more{{margin:.6rem 0 1.1rem;padding:.15rem 0 .15rem .8rem;
border-left:2px solid #2a3a4d}}
.how details.more>summary{{cursor:pointer;font-size:.86rem;font-weight:600;color:var(--acc);
line-height:1.4;overflow-wrap:anywhere}}
.how details.more>summary:hover{{text-decoration:underline}}
.how details.more[open]>summary{{margin-bottom:.4rem}}
.how details.more[open]{{border-left-color:var(--acc)}}
@media (max-width:30rem){{.how details.more{{padding-left:0;border-left:0;
border-top:2px solid #2a3a4d}}.how details.more[open]{{border-top-color:var(--acc)}}}}
.how ul{{margin:.3rem 0;padding-left:1.1rem}}
.how .pipe{{display:flex;flex-wrap:wrap;gap:.9rem 1.2rem;margin:1rem 0 1.2rem}}
.pipe .stage{{flex:1 1 15rem;min-width:0}}
.pipe ol{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:1.1rem}}
.how .pipe li{{margin:0;line-height:1.4}}
.pipe b{{display:block;font-family:{_SG}}}
.pipe i.when{{display:block;font-style:normal;font-size:.68rem;font-weight:700;
text-transform:uppercase;letter-spacing:.06em;color:var(--acc);margin-bottom:.35rem}}
.pipe span{{font-size:.8rem}}
.how h3{{font-family:{_SG};font-size:1.08rem;margin:2.2rem 0 .5rem;scroll-margin-top:1rem}}
.how h4{{font-family:{_SG};font-size:.95rem;margin:1.6rem 0 .4rem;scroll-margin-top:1rem}}
.how section p,.how section li{{line-height:1.55}}
.how section{{border-top:1px solid #2a3a4d;scroll-margin-top:1rem}}
.how details.method>summary{{cursor:pointer;padding:.65rem 0;color:var(--ink)}}
.how details.method>summary h3{{display:inline;font-size:1rem;margin:0}}
.how details.method>summary a{{color:var(--acc);margin-left:.5rem;text-decoration:none}}
.how details.method>summary a:hover{{text-decoration:underline}}
.how details.method[open]{{padding-bottom:.8rem}}
.how summary:focus-visible{{outline:2px solid var(--acc);outline-offset:3px}}
.how details.order{{margin:.6rem 0;border-top:1px solid #2a3a4d}}
.how details.order>summary{{padding:.6rem 0;cursor:pointer;color:var(--acc);
font-size:.95rem;font-weight:400}}
.how .cite{{white-space:nowrap}}
.how dl.rule{{margin:.5rem 0 1rem}}
.how dl.rule dt{{font-weight:600;color:var(--ink);margin-top:.5rem}}
.how dl.rule dd{{margin:.1rem 0 0}}
.how figure.fig{{margin:1.1rem 0 1.4rem;padding:0}}
.how figure.fig svg{{display:block;height:auto;margin:0 auto}}
.how figcaption{{font-size:.84rem;line-height:1.5;color:var(--mut);margin:.55rem auto 0;
max-width:40rem}}
.how figcaption b{{color:var(--ink)}}
.how figcaption code{{font-size:.78rem;overflow-wrap:anywhere}}
.how ol.refs li{{margin:.35rem 0;overflow-wrap:anywhere}}
.tablewrap{{overflow-x:auto;margin:.6rem 0 1rem}}
.how table{{border-collapse:collapse;font-size:.85rem;width:auto;background:transparent;
color:var(--ink)}}
.how th,.how td{{border:1px solid #2a3a4d;padding:.3rem .55rem;text-align:left;
white-space:nowrap;vertical-align:top}}
.how table.wrap td{{white-space:normal;min-width:12rem;max-width:26rem}}
.how table.wrap tbody th{{white-space:normal;min-width:7rem}}
.how td code{{overflow-wrap:anywhere;word-break:break-all}}
.how thead th{{background:var(--panel);color:var(--ink);font-weight:600}}
.how tbody th{{color:var(--mut);font-weight:500}}
.how caption{{text-align:left;font-size:.8rem;padding:0 0 .3rem .2rem;color:var(--mut)}}
.how caption b{{color:var(--ink)}}
.how .src{{font-size:.85rem;margin:1rem 0 0}}
.how svg .t{{fill:var(--ink)}}
.how svg .tb{{fill:var(--ink);font-weight:600}}
.how svg .m{{fill:var(--mut)}}
.how svg .ink{{fill:#0f1620;font-weight:600}}
.how svg .bx{{fill:var(--panel);stroke:#3a4d63}}
.how svg .bx.side{{stroke-dasharray:4 3}}
.how svg .ar,.how svg .br{{stroke:var(--acc);stroke-width:1.4}}
.how svg .arh{{fill:var(--acc)}}
.how svg .ax,.how svg .tick{{stroke:#5d6b7a;stroke-width:1}}
.how svg .grid{{stroke:#223246;stroke-width:1}}
.how svg .lvl{{stroke:var(--mut);stroke-width:1.2;stroke-dasharray:5 4}}
.how svg .c1{{fill:#56B4E9}}
.how svg .c2{{fill:#E69F00}}
.how svg .c3{{fill:#CC79A7}}
.how svg .c4{{fill:#F0E442}}
.how svg .c5{{fill:#D55E00}}
.how svg .b1{{fill:#e8eef5}}
.how svg .b2{{fill:#a9bccf}}
.how svg .b3{{fill:#6f89a3}}
.how svg .s0,.how svg .s1,.how svg .s2,.how svg .s3,.how svg .s4{{fill:rgb(139,168,132)}}
.how svg .s0{{fill-opacity:.08}}
.how svg .s1{{fill-opacity:.25}}
.how svg .s2{{fill-opacity:.45}}
.how svg .s3{{fill-opacity:.65}}
.how svg .s4{{fill-opacity:.85}}
.how svg .far{{fill:none;stroke:#3a4d63;stroke-dasharray:3 3}}
.how svg .hull{{fill:rgba(139,168,132,.1);stroke:var(--acc);stroke-dasharray:4 3}}
.how svg .seed{{fill:none;stroke:#f0a000;stroke-width:1.8}}
.how svg .ref{{fill:#6b7d90}}
.how svg .near{{stroke:#8397ab;stroke-width:1}}
.how svg .bar,.how svg .pos{{fill:var(--acc)}}
.how svg .band{{fill:rgba(139,168,132,.28)}}
.how svg .rng{{stroke:var(--acc);stroke-width:4;stroke-linecap:round}}
.how svg .neg{{fill:#E69F00}}
.how svg .hist{{fill:#3d5068}}
.how svg .tail{{fill:#f0a000}}
.how svg .obs{{stroke:#f0a000;stroke-width:1.2;stroke-dasharray:3 2}}
.how svg .pw1{{fill:none;stroke:var(--acc);stroke-width:2.2}}
.how svg .pw1d,.how svg .pw1t{{fill:var(--acc)}}
.how svg .pw2{{fill:none;stroke:#56B4E9;stroke-width:2.2}}
.how svg .pw2d,.how svg .pw2t{{fill:#56B4E9}}
.how svg .pw3{{fill:none;stroke:#E69F00;stroke-width:2.2}}
.how svg .pw3d,.how svg .pw3t{{fill:#E69F00}}
""".strip()

SECTIONS = (
    ("methods-design", "Design at a glance", design_section),
    ("methods-records", "Records", records_section),
    ("methods-split", "Random split", split_section),
    ("methods-orders", "The orders", orders_section),
    ("methods-serving", "Serving batches", serving_section),
    ("methods-outcomes", "Outcomes", outcomes_section),
    ("methods-analysis", "Statistical analysis", analysis_section),
    ("methods-size", "Sample size", size_section),
    ("methods-threats", "Threats to validity", threats_section),
    ("methods-repro", "Reproducibility", repro_section),
    ("methods-refs", "References", references_section),
)


def _pipeline(manifest: Manifest, n_lists: int) -> str:
    """Six steps, saying who does each: we build the lists, you identify, we count."""
    weighted = (
        f"; {order_name('gap_first').lower()} is judged on IDs weighted by map score"
        if "gap_first" in manifest.arms
        else ""
    )
    stages = (
        (
            "Each build",
            ("We collect", "BC records that need an ID and have a photo"),
            (
                f"We split them into {n_lists} lists",
                "each record goes to one list by chance, so the lists hold a similar mix",
            ),
            ("Each list gets its own order", "one is newest first, like iNaturalist today"),
        ),
        (
            "During the blitz",
            (
                "You press Next batch",
                f"each press opens up to {manifest.batch_size} records from the next list in turn",
            ),
            ("You identify", "in iNaturalist, as usual"),
        ),
        (
            "After",
            (
                "We count",
                "each person's species-level IDs on each list, against newest first, and whether "
                f"the gap is bigger than chance{weighted}",
            ),
        ),
    )
    # One column per stage, so a stage's steps never wrap into the next stage's row.
    cols = "".join(
        f'<div class="stage"><i class="when">{when}</i><ol>'
        + "".join(f"<li><b>{b}</b><span>{s}</span></li>" for b, s in steps)
        + "</ol></div>"
        for when, *steps in stages
    )
    return f'<div class="pipe" aria-label="The test from start to end">{cols}</div>'


def method_section(manifest: Manifest, n_lists: int) -> str:
    """The test in six steps, then the methods in full. Folded by default."""
    for table, name in ((ORDER_TEXT, "ORDER_TEXT"), (ORDER_DETAIL, "ORDER_DETAIL")):
        missing = [x for x in manifest.arms if x not in table]
        if missing:
            raise ValueError(f"no page words for list order(s) {missing}; add them to {name}")
    facts = build_facts(manifest)
    doc = Doc()
    body = "".join(
        f'<section id="{sid}"><details class="method"'
        + (" open" if sid == "methods-orders" else "")
        + f"><summary><h3>{i}. {title}</h3>"
        + f'<a href="#{sid}" aria-label="Link to {title}">#</a></summary>'
        + f"{fn(manifest, facts, doc)}</details></section>"
        for i, (sid, title, fn) in enumerate(SECTIONS, 1)
    )
    return doc.finish(
        '<details class="how"><summary>How the test works</summary>'
        f"{_pipeline(manifest, n_lists)}"
        '<h3 id="methods">Methods in full</h3>'
        f"{body}"
        f'<p class="src">All the code and the draft protocol: '
        f'<a href="{REPO}" target="_blank" rel="noopener">PollockLab/what-to-id</a>. '
        "Code links point at the main branch.</p>"
        "</details>\n"
    )
