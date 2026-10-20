"""The tree of life's model: record rollups, merged chains, paging, revealing and the layout."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ASSET = Path(__file__).parents[1] / "src/what_to_id/tree_assets/tree_model.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

RANKS = ["genus", "kingdom", "phylum", "species", "stateofmatter"]
G, K_, P_, SP, LIFE = range(5)
# [latin, common, id, rank, parent row, own records]
T = [
    ["Life", "life", 48460, LIFE, -1, 0],  # 0
    ["Plantae", "Plants", 47126, K_, 0, 0],  # 1
    ["Bryophyta", "Mosses", 311249, P_, 1, 0],  # 2
    ["Sphagnum", "", 50, G, 2, 1],  # 3
    ["Sphagnum fuscum", "", 51, SP, 3, 5],  # 4
    ["Polytrichum", "", 60, G, 2, 0],  # 5: no records anywhere below
    ["Polytrichum commune", "", 61, SP, 5, 0],  # 6
    ["Animalia", "Animals", 1, K_, 0, 2],  # 7
    ["Bombus", "", 70, G, 7, 0],  # 8: thirty species below
] + [[f"Bombus s{k}", "", 100 + k, SP, 8, 30 - k] for k in range(30)]
BOMBUS_TOT = sum(30 - k for k in range(30))
GROUPS = {"47126": "Plantae", "1": "Animalia"}


def node(script):
    pre = f"const M = require({str(ASSET)!r});\n"
    pre += f"const T = {json.dumps(T)}, R = {json.dumps(RANKS)}, D = M.build(T, R, {GROUPS});\n"
    pre += "const out = (x) => console.log(JSON.stringify(x));\n"
    done = subprocess.run([NODE], input=pre + script, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_rollup_counts_records_and_species_and_drops_empty_taxa():
    got = node("out({tot: Array.from(D.tot), sp: Array.from(D.sp), kids: D.kids, grp: D.grp});")
    assert got["tot"][0] == got["tot"][len(T)] == 6 + 2 + BOMBUS_TOT
    assert got["tot"][1] == 6 and got["tot"][5] == got["tot"][6] == 0
    assert got["kids"][2] == [3]  # Polytrichum has no records: not drawn
    assert got["kids"][8][:3] == [9, 10, 11]  # most records first
    assert got["sp"][0] == 31 and got["sp"][1] == 1
    assert got["grp"][4] == "Plantae" and got["grp"][20] == "Animalia" and got["grp"][0] == ""


def test_a_taxon_with_one_child_and_no_records_merges_into_it():
    got = node(
        "out({lead: M.lead(D, 1), chain: M.chain(D, 3), root: M.lead(D, D.root),"
        " crumbs: M.crumbs(D, 4)});"
    )
    assert got["lead"] == 3 and got["chain"] == [1, 2, 3]
    assert got["root"] == 0  # the synthetic root above Life is hidden
    assert got["crumbs"] == [0, 3]


def test_an_open_node_shows_k_children_then_a_bucket_for_the_rest():
    got = node(
        """
const S = {focus: 0, sel: -1, open: new Map([[0, 1], [7, 1], [8, 1]])};
const kids = (V) => V.all.find((n) => n.row === 8).kids;
const one = kids(M.view(D, S)); M.more(S, 8); const two = kids(M.view(D, S));
const last = {more: one[one.length - 1].more, tot: one[one.length - 1].tot};
out({n: one.length, last, two: two.length, twoLast: two[two.length - 1].row});"""
    )
    assert got["n"] == 25
    assert got["last"]["more"] == 6 and got["last"]["tot"] == sum(30 - k for k in range(24, 30))
    assert got["two"] == 30 and got["twoLast"] != -1


def test_reveal_pages_through_the_bucket_and_resets_a_focus_elsewhere():
    got = node(
        """
const S = {focus: 3, sel: -1, open: new Map()};
const e = M.reveal(D, S, 9 + 27);
const shown = M.view(D, S).all.some((n) => n.row === e);
out({e, focus: S.focus, open: Array.from(S.open), shown});"""
    )
    assert got["e"] == 36 and got["focus"] == 0
    assert dict(got["open"]) == {0: 1, 7: 1, 8: 2} and got["shown"]


def test_layout_fills_the_span_and_gives_each_leaf_its_minimum():
    got = node(
        """
const S = M.home(D, [1, 7]); M.toggle(D, S, 7); M.toggle(D, S, 8);
const V = M.layout(M.view(D, S), 0, 6, 0.1), leaves = V.all.filter((n) => !n.kids.length);
const gaps = V.all.filter((n) => n.kids.length).map((n) =>
  [n.kids[0].a0 - n.a0, n.kids[n.kids.length - 1].a1 - n.a1]);
const tight = M.layout(M.view(D, S), 0, 1, 0.1).all.filter((n) => !n.kids.length);
const w = (ns) => ns.map((n) => n.a1 - n.a0);
out({sum: w(leaves).reduce((s, x) => s + x, 0), min: Math.min(...w(leaves)), gaps,
  tight: Math.min(...w(tight)), n: tight.length});"""
    )
    assert got["sum"] == pytest.approx(6) and got["min"] >= 0.1 - 1e-9
    assert all(g == [0, 0] for g in got["gaps"])
    assert got["tight"] == pytest.approx(1 / got["n"])  # too many leaves: all equal


def test_expand_below_stops_at_the_budget():
    got = node(
        """
const S = {focus: 0, sel: -1, open: new Map()};
const capped = M.expandBelow(D, S, 0, 5), small = Array.from(S.open.keys());
const S2 = {focus: 0, sel: -1, open: new Map()};
out({capped, small, full: M.expandBelow(D, S2, 0, 400), all: Array.from(S2.open.keys()).sort()});"""
    )
    assert got["capped"] and got["small"] == [0, 7, 3]  # Bombus would add 24 leaves
    assert not got["full"] and got["all"] == [0, 3, 7, 8]


def test_hash_round_trips_and_ignores_unknown_ids():
    got = node(
        """
const S = {focus: 7, sel: 20, open: new Map([[7, 1], [8, 2]])};
const h = M.write(D, S), back = M.read(D, '#' + h + '&junk', [1, 7]);
const bad = M.read(D, '#sel=999&focus=61', [1, 7]);
const plain = M.read(D, '#sel=' + T[36][2], [1, 7]);
out({h, back: [back.focus, back.sel, Array.from(back.open)], bad: [bad.focus, bad.sel],
  plain: Array.from(plain.open)});"""
    )
    assert got["h"] == "focus=1&sel=111&open=1,70.2"
    assert got["back"] == [7, 20, [[7, 1], [8, 2]]]
    assert got["bad"] == [0, -1]
    assert dict(got["plain"])[8] == 2  # without open=: home, with the selection revealed


def test_an_empty_table_is_one_empty_root():
    got = node(
        """
const E = M.build([], [], {}), V = M.layout(M.view(E, M.home(E, [])), 0, 6, 0.1);
out({row: V.root.row, kids: V.root.kids.length, a: V.root.a, name: M.name(E, V.root.row)});"""
    )
    assert got == {"row": 0, "kids": 0, "a": 3, "name": "All taxa"}
