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
}  # fmt: skip
META = {"groups": list(KIDS), "group_ids": {g: v[0] for g, v in KIDS.items()}, "names": {}}


def table():
    t = [["Life", "", 48460, 0, -1, 0]]
    for g, (gid, kids) in KIDS.items():
        t.append([g, "", gid, 0, 0, 0])
        top = len(t) - 1
        for k, name in enumerate(kids.split()):
            t.append([name, "", 100000 + len(t), 0, top, 1000 - k])
            for q in range(3):  # three children below each, so deeper rows get their own colours
                t.append([f"{name} {q}", "", 100000 + len(t), 0, top + 1 + 4 * k, 50 - q])
    return t


def node(script):
    pre = "const fs = require('fs');\n"
    for f in (ASSETS / "map_filter.js", ASSETS / "clade_colour.js", HELPER):
        pre += f"eval(fs.readFileSync({str(f)!r}, 'utf8'));\n"  # plain scripts of this repo
    pre += f"const T = {json.dumps(table())}, META = {json.dumps(META)};\n"
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
