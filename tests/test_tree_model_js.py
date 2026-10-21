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
ROOT = len(T)  # the root above the groups


def node(script):
    pre = f"const M = require({str(ASSET)!r});\n"
    pre += f"const T = {json.dumps(T)}, R = {json.dumps(RANKS)}, D = M.build(T, R, {GROUPS});\n"
    pre += "const out = (x) => console.log(JSON.stringify(x));\n"
    done = subprocess.run([NODE], input=pre + script, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_rollup_counts_records_and_species_and_drops_empty_taxa():
    got = node("out({tot: Array.from(D.tot), sp: Array.from(D.sp), kids: D.kids, grp: D.grp});")
    assert got["tot"][ROOT] == 6 + 2 + BOMBUS_TOT
    assert got["tot"][0] == 0  # the groups hang from the root, not from Life
    assert got["tot"][1] == 6 and got["tot"][5] == got["tot"][6] == 0
    assert got["kids"][2] == [3]  # Polytrichum has no records: not drawn
    assert got["kids"][8][:3] == [9, 10, 11]  # most records first
    assert got["sp"][ROOT] == 31 and got["sp"][1] == 1
    assert got["grp"][4] == "Plantae" and got["grp"][20] == "Animalia"
    assert got["grp"][0] == "Unknown"


def test_a_taxon_with_one_child_and_no_records_merges_into_it():
    got = node(
        "out({lead: M.lead(D, 1), chain: M.chain(D, 3), root: M.lead(D, D.root),"
        " crumbs: M.crumbs(D, 4)});"
    )
    assert got["lead"] == 3 and got["chain"] == [1, 2, 3]
    assert got["root"] == ROOT  # two groups below it: the root shows
    assert got["crumbs"] == [ROOT, 3]


def test_an_open_node_shows_k_children_then_a_bucket_for_the_rest():
    got = node(
        """
const S = {focus: D.root, sel: -1, open: new Map([[D.root, 1], [7, 1], [8, 1]])};
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
    assert got["e"] == 36 and got["focus"] == ROOT
    assert dict(got["open"]) == {ROOT: 1, 7: 1, 8: 2} and got["shown"]


def test_layout_fills_the_span_and_gives_each_leaf_its_minimum():
    got = node(
        """
const S = M.home(D, [1, 7]); M.toggle(D, S, 8);
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


def test_expand_below_stops_at_the_group_depth_and_the_budget():
    got = node(
        """
const S = {focus: D.root, sel: -1, open: new Map()};
const full = M.expandBelow(D, S, D.root, 400);
const top = Array.from(S.open.keys()).sort((a, b) => a - b);
const capped = M.expandBelow(D, S, 8, 5), shut = S.open.has(8);
out({full, top, capped, shut, deep: M.expandBelow(D, S, 8, 400), open: S.open.has(8)});"""
    )
    # Sphagnum and Bombus are genera, below the default depth (family): left closed
    assert not got["full"] and got["top"] == [7, ROOT]
    assert got["capped"] and not got["shut"]  # Bombus would add 24 leaves
    assert not got["deep"] and got["open"]  # from a genus, expand goes on down


# Life > Animalia > Insecta > Hymenoptera (> Apidae > Bombus > a species) and Diptera
INSECTS = [
    ["Life", "", 48460, LIFE, -1, 0],  # 0
    ["Animalia", "", 1, K_, 0, 0],  # 1
    ["Insecta", "", 47158, 5, 1, 0],  # 2: class
    ["Hymenoptera", "", 47201, 6, 2, 1],  # 3: order
    ["Apidae", "", 47221, 7, 3, 1],  # 4: family
    ["Bombus", "", 52775, G, 4, 0],  # 5
    ["Bombus vosnesenskii", "", 121519, SP, 5, 3],  # 6
    ["Diptera", "", 47822, 6, 2, 2],  # 7: order
]
INSECT_RANKS = [*RANKS, "class", "order", "family"]
INSECT_GROUPS = {1: "Animalia", 47158: "Insecta"}
INSECT_TREE = ", ".join(json.dumps(x) for x in (INSECTS, INSECT_RANKS, INSECT_GROUPS))


def test_insects_stop_at_order_and_the_rest_at_family():
    got = node(
        f"""
const I = M.build({INSECT_TREE});
const S = M.home(I, [2]), home = Array.from(S.open.keys()).sort();
M.expandBelow(I, S, 3, 400);
out({{home, below: Array.from(S.open.keys()).sort(), caps: [M.cap(I, 7), M.cap(I, 1), M.cap(D, 1)],
  order: M.step(M.LEVEL.order), family: M.step(M.LEVEL.family)}});"""
    )
    assert got["home"] == [2]  # no other animal: the root merges into Insecta, its orders closed
    assert got["below"] == [2, 3, 4]  # a click on an order still opens it down to species
    assert got["caps"] == [got["order"], got["family"], got["family"]]


def test_sub_clades_take_shades_of_their_group_colour_that_read_on_both_pages():
    # map_filter.js is a plain script of this repo, not a module: eval loads it
    filt = ASSET.parents[1] / "map_assets/map_filter.js"
    got = node(
        f"""
eval(require('fs').readFileSync({str(filt)!r}, 'utf8'));
const I = M.build({INSECT_TREE});
const two = (c) => M.BG.every((b) => M.contrast(c, b) >= 2);
const all = Object.values(MapFilter.BY).concat(MapFilter.PAL).filter(two);
const worst = Math.min(...all.flatMap((c) => M.TONES.flatMap((t) =>
  M.BG.map((b) => M.contrast(M.shade(c, t), b)))));
const ins = MapFilter.BY.Insecta, kinds = new Set(M.TONES.map((t) => M.shade(ins, t).join()));
const tones = [6, 7, 2].map((r) => M.tone(I, r));
out({{worst, n: all.length, kinds: kinds.size, same: M.shade(ins, 0), tones}});"""
    )
    assert got["n"] >= 25 and got["worst"] >= 2
    assert got["kinds"] >= 4 and got["same"] == [240, 130, 0]
    assert got["tones"] == [0, 0.45, 0]  # Bombus under Hymenoptera (first), Diptera second


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
    assert got["bad"] == [ROOT, -1]
    assert dict(got["plain"])[8] == 2  # without open=: home, with the selection revealed


def test_an_empty_table_is_one_empty_root():
    got = node(
        """
const E = M.build([], [], {}), V = M.layout(M.view(E, M.home(E, [])), 0, 6, 0.1);
out({row: V.root.row, kids: V.root.kids.length, a: V.root.a, name: M.name(E, V.root.row)});"""
    )
    assert got == {"row": 0, "kids": 0, "a": 3, "name": "Life"}


# Life > Animalia > (Chordata > Aves), (Arthropoda > Insecta, Malacostraca), Plantae, Bacteria.
# As on the map (iNaturalist's iconic taxa) a record takes its nearest group taxon, Animalia
# for any other animal, else Unknown.
ICONIC = [
    ["Life", "", 48460, LIFE, -1, 3],  # 0
    ["Animalia", "Animals", 1, K_, 0, 1],  # 1
    ["Chordata", "", 2, P_, 1, 0],  # 2
    ["Aves", "Birds", 3, 5, 2, 4],  # 3: class
    ["Arthropoda", "", 47120, P_, 1, 2],  # 4
    ["Insecta", "Insects", 47158, 5, 4, 6],  # 5
    ["Malacostraca", "", 85493, 5, 4, 1],  # 6
    ["Plantae", "Plants", 47126, K_, 0, 7],  # 7
    ["Bacteria", "", 67333, K_, 0, 2],  # 8
]
ORDER = ["Animalia", "Aves", "Insecta", "Plantae", "Unknown"]
NAMES = {"Animalia": "Other animals (Animalia)", "Aves": "Birds (Aves)", "Unknown": "Unknown"}
ICONIC_TREE = ", ".join(
    json.dumps(x)
    for x in (
        ICONIC,
        [*RANKS, "class"],
        {1: "Animalia", 3: "Aves", 47158: "Insecta", 47126: "Plantae"},
        {"order": ORDER, "names": NAMES, "total": 26 + 5},  # five records have no taxon
    )
)
ICONIC_GROUP = ["Unknown", "Animalia", "Animalia", "Aves", "Animalia", "Insecta", "Animalia"]
ICONIC_GROUP += ["Plantae", "Unknown"]


def test_the_root_children_are_the_map_groups_and_each_record_keeps_its_map_group():
    got = node(
        f"""
const I = M.build({ICONIC_TREE}), top = I.kids[I.root];
const picks = top.concat([4, 6, 8]).map((r) => M.pick(I, r));
const map = ['taxa=-3,47120', 'groups=-Aves,Insecta', 'groups=Aves,Insecta']
  .map((s) => M.find(I, s));
out({{top: top.map((r) => I.grp[r]), grp: I.grp.slice(0, I.n), tot: top.map((r) => I.tot[r]), picks,
  back: picks.map((p) => M.find(I, 'by=uploaded&' + p)), map,
  names: [1, 0, 3].map((r) => M.common(I, r)), own: I.own[0], none: I.none, nr: I.nr}});"""
    )
    assert got["top"] == ORDER and got["grp"] == ICONIC_GROUP
    assert got["tot"] == [1 + 2 + 1, 4, 6, 7, 3 + 2 + 5]  # the same counts as the map's group chips
    assert got["picks"] == [
        "groups=Animalia",
        "groups=Aves",
        "groups=Insecta",
        "groups=Plantae",
        "groups=Unknown",
        "taxa=47120,-47158",  # the other arthropods: Insecta is its own group
        "taxa=85493",
        "taxa=67333",
    ]
    assert got["back"] == [1, 3, 5, 7, 0, 4, 6, 8]
    assert got["names"] == ["Other animals", "Unknown", "Birds"]
    assert got["map"] == [4, 5, -1]
    # the records with no taxon count in Life's total, not in its own
    assert [got["own"], got["none"], got["nr"]] == [3, 5, 0]


def test_records_with_no_taxon_keep_life_from_merging_into_its_one_child():
    got = node(
        f"""
const I = M.build({ICONIC_TREE});
I.T[0][5] = 0;
const G = {{1: 'Animalia', 3: 'Aves', 47158: 'Insecta', 47126: 'Plantae'}};
const J = M.build(I.T, [...R, 'class'], G, {{order: {json.dumps(ORDER)}, total: 26 + 5 - 3}});
out({{lead: M.lead(J, 0), tot: J.tot[0], own: J.own[0], pick: M.pick(J, 0)}});"""
    )
    assert got == {"lead": 0, "tot": 2 + 5, "own": 0, "pick": "groups=Unknown"}


def test_without_drops_the_left_out_groups_and_their_counts_fall_out_of_every_total():
    got = node(
        """
const W = M.without(D, ['Animalia']), U = M.without(D, ['Unknown']), S = M.without(D, []);
out({root: [D.tot[ROOT], W.tot[ROOT], U.tot[ROOT]], kids: [D.kids[ROOT], W.kids[ROOT]],
  gone: W.tot[7], same: S === D, find: M.find(W, 'groups=-Animalia&taxa=51')});""".replace(
            "ROOT", str(ROOT)
        )
    )
    assert got["root"] == [6 + 2 + BOMBUS_TOT, 6, 6 + 2 + BOMBUS_TOT]
    assert got["kids"] == [[7, 1], [1]] and got["gone"] == 0 and got["same"]
    assert got["find"] == 4


def test_without_drops_left_out_taxa_with_everything_below_and_combines_with_groups():
    got = node(
        """
const B = M.build(T, R, {"47126": "Plantae", "1": "Animalia"}, {total: 500}), r = 'ROOT';
const A = M.without(B, [], [70]), P = M.without(B, [], [51]), C = M.without(B, ['Animalia'], [51]);
out({root: [B.tot[r], A.tot[r], P.tot[r], C.tot[r]], bombus: [A.tot[8], A.tot[9], A.tot[7]],
  sphagnum: [P.tot[1], P.tot[3], P.tot[4]], none: [B.none, A.none, C.none],
  same: M.without(B, [], []) === B, find: M.find(A, 'taxa=-70')});""".replace("'ROOT'", str(ROOT))
    )
    plant, animal = 6, 2 + BOMBUS_TOT
    assert got["root"] == [plant + animal + 27, plant + 2 + 27, plant - 5 + animal + 27, 1 + 27]
    assert got["bombus"] == [0, 0, 2] and got["sphagnum"] == [1, 1, 0]
    assert got["none"] == [27, 27, 27] and got["same"] and got["find"] == -1
