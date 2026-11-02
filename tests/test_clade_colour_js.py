"""The clade colours the tree and the map share (clade_colour.js), run in node: siblings stay
apart in CIEDE2000, far more than the old shades of the group colour did, and every colour reads
on both pages."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path(__file__).parents[1] / "src/what_to_id/map_assets"
HELPER = Path(__file__).with_name("clade_colour_check.js")  # CIEDE2000, contrast, the old shades
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

# Children as a taxa table has them, by records: the Plantae phyla, the biggest groups' children.
KIDS = {
    "Plantae": (47126, "Tracheophyta Bryophyta Marchantiophyta Rhodophyta Chlorophyta Charophyta "
                       "Anthocerotophyta Glaucophyta"),
    "Insecta": (47158, "Lepidoptera Coleoptera Hymenoptera Diptera Hemiptera Odonata Orthoptera "
                       "Trichoptera"),
    "Aves": (3, "Passeriformes Anseriformes Charadriiformes Accipitriformes Piciformes "
                "Pelecaniformes"),
    "Fungi": (47170, "Basidiomycota Ascomycota Mucoromycota Chytridiomycota"),
    "Mollusca": (47115, "Gastropoda Bivalvia Polyplacophora Cephalopoda"),
    "Amphibia": (20978, "Anura Caudata"),
}  # fmt: skip
META = {"groups": list(KIDS), "group_ids": {g: v[0] for g, v in KIDS.items()}, "names": {}}
# The children of depth-2 taxa: Tracheophyta's classes, Passeriformes' and Anura's families.
DEEP = {
    "Tracheophyta": "Magnoliopsida Liliopsida Polypodiopsida Pinopsida Lycopodiopsida "
                    "Equisetopsida Gnetopsida Ginkgoopsida Cycadopsida",
    "Passeriformes": "Corvidae Paridae Turdidae Fringillidae Passerellidae Parulidae Icteridae "
                     "Sittidae Troglodytidae",
    "Anura": "Ranidae Hylidae Bufonidae Ascaphidae Scaphiopodidae Pipidae Microhylidae "
             "Leptodactylidae Dendrobatidae",
}  # fmt: skip


def table():
    t = [["Life", "", 48460, 0, -1, 0]]
    for g, (gid, kids) in KIDS.items():
        t.append([g, "", gid, 0, 0, 0])
        top = len(t) - 1
        for k, name in enumerate(kids.split()):
            t.append([name, "", 100000 + len(t), 0, top, 1000 - k])
            me = len(t) - 1
            # three children below each, so deeper rows get their own colours; more below DEEP's
            subs = DEEP[name].split() if name in DEEP else [f"{name} {q}" for q in range(3)]
            for q, sub in enumerate(subs):
                t.append([sub, "", 100000 + len(t), 0, me, 50 - q])
    return t


def node(script):
    pre = "const fs = require('fs');\n"
    for f in (ASSETS / "map_filter.js", ASSETS / "clade_colour.js", HELPER):
        pre += f"eval(fs.readFileSync({str(f)!r}, 'utf8'));\n"  # plain scripts of this repo
    pre += f"const T = {json.dumps(table())}, META = {json.dumps(META)};\n"
    pre += f"const DEEP = {json.dumps(DEEP)};\n"
    pre += "const out = (x) => console.log(JSON.stringify(x));\n"
    done = subprocess.run([NODE], input=pre + script, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_siblings_sit_far_apart_and_the_old_shades_did_not():
    got = node(
        """
const P = CladeColour.build(T, META), res = {};
Object.keys(P.gr).forEach((g) => {
  const k = P.kids[P.gr[g]], base = MapFilter.color(g, META.groups.indexOf(g));
  res[g] = {n: k.length, names: k.map((r) => T[r][0]), now: least(k.map((r) => P.col[r])),
    was: least(k.map((r, i) => old(base, TONES[i % TONES.length])))};});
out(res);"""
    )
    assert got["Plantae"]["names"] == KIDS["Plantae"][1].split()  # in the table's record order
    for g, r in got.items():
        print(f"{g}: {r['n']} siblings, least CIEDE2000 old {r['was']:.1f}, new {r['now']:.1f}")
        assert r["now"] >= 12, g
        assert r["now"] > 2 * r["was"], g


def test_every_group_hue_holds_eight_siblings_apart_and_reads_on_both_pages():
    got = node(
        """
const groups = Object.keys(MapFilter.BY), res = [];
groups.forEach((g) => { for (const m of [2, 3, 4, 5, 6, 7, 8, 17]) {
  const T = [[g, '', 1, 0, -1, 0]];
  for (let k = 0; k < m; k++) T.push(['c' + k, '', 10 + k, 0, 0, 9 - k]);
  T.push(['deep', '', 99, 0, 1, 1]);
  const P = CladeColour.build(T, {groups, group_ids: {[g]: 1}}), cs = P.col.filter(Boolean);
  res.push({g, m, least: least(P.kids[0].slice(0, 8).map((r) => P.col[r])),  // the legend's 8
    worst: Math.min(...cs.flatMap((c) => BG.map((b) => contrast(c, b)))),
    deep: P.col[m + 1], over: P.col[1]}); }});
out(res);"""
    )
    for r in got:
        assert r["least"] >= 12, r
        assert r["worst"] >= 2, r
        assert r["deep"] != r["over"]  # a row below a sub-clade has its own colour
    print(
        "least CIEDE2000 among the first 8 siblings, any group, 2 to 17 siblings:",
        min(r["least"] for r in got),
    )


def test_the_colours_follow_the_table_only_and_leave_rows_outside_groups_uncoloured():
    got = node(
        """
const a = CladeColour.build(T, META), b = CladeColour.build(JSON.parse(JSON.stringify(T)), META);
const none = CladeColour.build([], META);
const bare = CladeColour.build(T.map((t) => t.slice(0, 5)), META);
out({same: JSON.stringify(a.col) === JSON.stringify(b.col), life: a.col[0] === undefined,
  group: a.col[a.gr.Plantae], empty: none.col.length, bare: bare.kids[bare.gr.Plantae].length,
  cut: a.par[a.gr.Plantae]});"""
    )
    assert got["same"] and got["life"]
    assert got["group"] == [40, 160, 60]  # a group keeps its map colour
    assert got["empty"] == 0
    assert got["bare"] == 8  # without record counts every child still takes a colour
    assert got["cut"] == -1  # a group's taxon stands alone, as on the tree


def test_a_focus_spreads_its_children_round_the_hue_circle():
    got = node(
        """
const P = CladeColour.build(T, META), res = {};
Object.keys(DEEP).forEach((t) => {
  const f = T.findIndex((x) => x[0] === t), k = P.kids[f].slice(0, 8), F = P.at(f);
  const cs = k.map((r) => F[r]);
  res[t] = {was: least(k.map((r) => P.col[r])), now: least(cs), self: F[f], own: P.col[f],
    worst: Math.min(...cs.flatMap((c) => BG.map((b) => contrast(c, b))))};});
res.same = P.at(P.gr.Plantae) === P.col && P.at(-1) === P.col;  // the overview has no focus
out(res);"""
    )
    assert got.pop("same")
    for t, r in got.items():
        print(f"{t}: least CIEDE2000 of 8 kids, overview {r['was']:.1f}, focused {r['now']:.1f}")
        assert r["now"] >= 18, t
        assert r["worst"] >= 2, t
        assert r["self"] == r["own"], t  # the focus keeps its own colour


FLOOR = 7  # least CIEDE2000 of a focus's first 8 children under any of the four, rounded down


def test_siblings_under_colour_vision_deficiency():
    # Machado 2009 at full severity: a focus picks the arrangement of its children that keeps
    # them furthest apart under all four, so the focused sets have a floor under each; groups
    # print theirs.
    got = node(
        """
const P = CladeColour.build(T, META), res = {};
const sets = Object.keys(P.gr).map((g) => [g, P.kids[P.gr[g]].slice(0, 8).map((r) => P.col[r])]);
Object.keys(DEEP).forEach((t) => {
  const f = T.findIndex((x) => x[0] === t), F = P.at(f), ms = [];
  for (let i = 0; i < 20; i++) {
    const Q = CladeColour.build(T, META), t0 = performance.now();
    Q.at(f); ms.push(performance.now() - t0); }
  res[t + ' ms'] = ms.sort((a, b) => a - b)[10];
  sets.push([t + ' focused', P.kids[f].slice(0, 8).map((r) => F[r])]);});
sets.forEach(([n, cs]) => { res[n] = {normal: least(cs)};
  Object.keys(CVD).forEach((k) => { res[n][k] = least(cs.map((c) => sim(c, k))); }); });
out(res);"""
    )
    for n in [n for n in got if n.endswith(" ms")]:
        ms = got.pop(n)
        # printed, not asserted: a time bound flakes on a busy CI runner
        print(f"{n[:-3]}: focusing takes {ms:.2f} ms (median of 20)")
    for n, r in got.items():
        print(n, ", ".join(f"{k} {v:.1f}" for k, v in r.items()))
        assert r["normal"] >= 12, n
        if n.endswith("focused"):
            assert min(r.values()) >= FLOOR, n
