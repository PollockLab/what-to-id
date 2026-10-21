"""A crowded tree of life in Chromium: no label overlaps another, the selection keeps its name."""

import re

import numpy as np
import pytest

from what_to_id.taxonomy import GROUP_TAXA

from . import test_tree_browser as tb
from .embeddings_fixture import pool_frame

browser = tb.browser


# Life's twelve groups as in BC, each with orders, families and species of very unequal size, so the
# inner labels and the rank names crowd the circle as on the real map.
SIZES = {
    "Insecta": 9,
    "Plantae": 8,
    "Fungi": 7,
    "Aves": 6,
    "Arachnida": 3,
    "Mollusca": 3,
    "Mammalia": 2,
    "Actinopterygii": 2,
    "Amphibia": 1,
    "Reptilia": 1,
    "Chromista": 1,
    "Protozoa": 1,
}
CROWD = {
    48460: [None, "Life", "", "stateofmatter"],
    1: [48460, "Animalia", "", "kingdom"],
    2: [1, "Chordata", "", "phylum"],
    47120: [1, "Arthropoda", "", "phylum"],
}
UNDER = {
    "Aves": 2,
    "Mammalia": 2,
    "Amphibia": 2,
    "Reptilia": 2,
    "Actinopterygii": 2,
    "Insecta": 47120,
    "Arachnida": 47120,
    "Mollusca": 1,
}
GRP = {}  # each species' group
for gi, (grp, n) in enumerate(SIZES.items()):
    gid = GROUP_TAXA[grp]
    CROWD[gid] = [UNDER.get(grp, 48460), grp, "", "phylum" if grp == "Mollusca" else "class"]
    for o in range(1 + n // 3):
        CROWD[oid := 200000 + gi * 1000 + o * 100] = [gid, f"{grp}ales {o}", "", "order"]
        for f in range(2):
            CROWD[fid := oid + 10 * (f + 1)] = [oid, f"{grp}aceae {o}{f}", "", "family"]
            for k in range(3):
                CROWD[fid + k + 1] = [fid, f"{grp} sp {o}{f}{k}", "", "species"]
                GRP[fid + k + 1] = grp


@pytest.fixture(scope="module")
def crowd_site(tmp_path_factory):
    tips = list(GRP)
    taxa = np.repeat(tips, [SIZES[GRP[t]] ** 2 for t in tips])
    pool = pool_frame(np.arange(1, len(taxa) + 1))
    pool["taxon_id"] = taxa
    pool["taxon_name"] = [CROWD[t][1] for t in taxa]
    pool["iconic_taxon"] = [GRP[t] for t in taxa]
    yield from tb.built(tmp_path_factory, CROWD, pool)


# Every shown label's outline on screen: a rotated rim label as its four corners, the rest as boxes.
QUADS = """() => [...document.querySelectorAll('#svg text.lb, #svg text.rk')].map(e => {
  const b = e.getBBox(), m = e.getScreenCTM(), x1 = b.x + b.width, y1 = b.y + b.height;
  const pt = (x, y) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
  return [e.className.baseVal, e.querySelector('title')?.textContent || e.textContent,
    [pt(b.x, b.y), pt(x1, b.y), pt(x1, y1), pt(b.x, y1)]]; })"""


def overlap(p, q):
    """Two convex quads intersect unless an edge's normal separates them (by over 0.5px)."""
    for poly in (p, q):
        for i in range(4):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % 4]
            nx, ny = y0 - y1, x1 - x0
            n = (nx * nx + ny * ny) ** 0.5 or 1
            a = [(x * nx + y * ny) / n for x, y in p]
            b = [(x * nx + y * ny) / n for x, y in q]
            if max(a) < min(b) + 0.5 or max(b) < min(a) + 0.5:
                return False
    return True


@pytest.mark.parametrize("w", [693, 900, 1400])
def test_no_two_labels_on_a_crowded_circle_overlap(browser, crowd_site, w):
    aves = 200000 + list(SIZES).index("Aves") * 1000
    page = tb.open_tree(browser, crowd_site, w=w, h=700, hash_=f"#sel={aves}")
    page.wait_for_selector("#svg text.lb.in.on")
    labels = page.evaluate(QUADS)
    assert any("rk" in c for c, _, _ in labels)
    for i, (_, t, p) in enumerate(labels):
        for _, u, q in labels[:i]:
            assert not overlap(p, q), (t, u)
    # the selection and every taxon above it keep their names in view, the root's with its count
    inner = [t for c, t, _ in labels if "in" in c.split()]
    names = {re.match(r"(?:.* › )?([^(,:]+?)(?: \(|,|:)", t)[1] for t in inner}
    assert {"Avesales 0", "Aves"} <= names, names
    assert page.locator("#svg text.lb.in", has_text=" · ").count() == 1
