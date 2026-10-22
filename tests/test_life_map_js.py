"""The map of life on a synthetic layout: regions, zoom crop, look-alike levels, the file decode."""

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

ASSET = Path(__file__).parents[1] / "src/what_to_id/embeddings_assets/life_map.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

RANKS = ["class", "family", "genus", "kingdom", "order", "phylum", "species"]
GROUPS = ["Aves", "Insecta", "Plantae"]
COLOURS = [[50, 90, 220], [240, 130, 0], [40, 160, 60]]
RAMP_LO, RAMP_HI = (
    [205, 226, 251],
    [13, 54, 107],
)  # the blue ramp's ends: level 0 and level 3 or more
CLEAR = [0, 0, 0, 0]
# [latin, common, inat id, rank, parent row]
TAXA = [
    ["Animalia", "Animals", 1, "kingdom", -1],
    ["Plantae", "Plants", 47126, "kingdom", -1],
    ["Arthropoda", "", 47120, "phylum", 0],
    ["Chordata", "", 2, "phylum", 0],
    ["Insecta", "Insects", 47158, "class", 2],
    ["Aves", "Birds", 3, "class", 3],
    ["Tracheophyta", "", 211194, "phylum", 1],
    ["Magnoliopsida", "", 47124, "class", 6],
    ["Lepidoptera", "", 47157, "order", 4],
    ["Coleoptera", "", 47208, "order", 4],
    ["Nymphalidae", "", 47224, "family", 8],
    ["Carabidae", "", 49567, "family", 9],
    ["Passeriformes", "", 7251, "order", 5],
    ["Vanessa cardui", "", 48662, "species", 10],
    ["Carabus nemoralis", "", 51337, "species", 11],
    ["Turdus migratorius", "", 12727, "species", 12],
    ["Achillea millefolium", "", 52821, "species", 7],
]
ROW = {t[0]: i for i, t in enumerate(TAXA)}
# blob name -> (centre, radius, points, species row, group)
BLOBS = {
    "lep": ((-6.5, 0.0), 1.2, 20000, ROW["Vanessa cardui"], 1),
    "col": ((-3.0, 0.0), 1.2, 20000, ROW["Carabus nemoralis"], 1),
    "aves": ((6.0, 0.0), 1.5, 20000, ROW["Turdus migratorius"], 0),
    "patch": (
        (-4.75, 0.0),
        0.4,
        3000,
        ROW["Turdus migratorius"],
        0,
    ),  # birds between the two orders
    "plants": ((0.0, 5.0), 1.5, 20000, ROW["Achillea millefolium"], 2),
}


def lookalike_bytes(blob_of, order):
    """pool-lookalike.bin per the contract, records in file order `order` (file row -> point)."""
    n = len(blob_of)
    rng = np.random.default_rng(4)
    cls, ordr, fam, lev = (np.full(n, 15, np.uint8) for _ in range(4))
    for name, (c, o, f, lv) in {
        "lep": (12, 12, 12, 0),
        "col": (12, 6, 12, 3),
        "aves": (3, 12, 12, 2),
        "patch": (3, 12, 12, 2),
    }.items():
        m = blob_of == name
        cls[m], ordr[m], fam[m], lev[m] = c, o, f, lv + 2
    # 40% of the Coleoptera are undecidable (-1) or have no look-alike (-2): the mean skips them
    col = np.flatnonzero(blob_of == "col")
    odd = rng.random(len(col)) < 0.4
    lev[col[odd]] = rng.choice([0, 1], odd.sum())
    a = (cls | ordr << 4)[order]
    b = (fam | lev << 4)[order]
    return gzip.compress(a.tobytes() + b.tobytes())


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp("life-map")
    rng = np.random.default_rng(2)
    xy, tax, grp, blob_of = [], [], [], []
    for name, (centre, r, n, row, g) in BLOBS.items():
        ang, rad = rng.uniform(0, 2 * np.pi, n), r * np.sqrt(rng.uniform(0, 1, n))
        xy.append(np.column_stack([centre[0] + rad * np.cos(ang), centre[1] + rad * np.sin(ang)]))
        tax += [row] * n
        grp += [g] * n
        blob_of += [name] * n
    xy, blob_of = np.vstack(xy), np.array(blob_of)
    order = rng.permutation(len(tax))  # the file is in shard order, not in point order
    src = np.empty_like(order)
    src[order] = np.arange(len(order))
    (d / "look.bin").write_bytes(lookalike_bytes(blob_of, order))
    taxa = [[t[0], t[1], t[2], RANKS.index(t[3]), t[4], 0] for t in TAXA]
    data = {"pos": xy.ravel().tolist(), "tax": tax, "grp": grp, "src": src.tolist(), "T": taxa}
    (d / "world.json").write_text(json.dumps(data))
    return d


def node(world, script):
    pre = f"""
const LM = require({str(ASSET)!r}), fs = require('fs'), zlib = require('zlib');
const D = JSON.parse(fs.readFileSync({str(world / "world.json")!r}, 'utf8'));
const RANKS = {json.dumps(RANKS)}, COLOURS = {json.dumps(COLOURS)};
const A = LM.ancestors(D.T, RANKS), n = D.tax.length;
const fileBuf = () => {{ const b = zlib.gunzipSync(fs.readFileSync({str(world / "look.bin")!r}));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); }};
const base = {{pos: Float32Array.from(D.pos), n, tax: Uint16Array.from(D.tax),
  grp: Uint8Array.from(D.grp),
  groups: 3, color: (g) => COLOURS[g], T: D.T, ranks: RANKS, A, src: Uint32Array.from(D.src)}};
const map = (clade, look) => LM.build(Object.assign({{}}, base, {{clade, look}}));
const px = (M, img, x, y) => {{ const ix = Math.floor((x - M.ext[0]) * M.sx),
  iy = Math.floor((y - M.ext[1]) * M.sy);
  if (ix < 0 || iy < 0 || ix >= M.W || iy >= M.H) return null;
  const p = 4 * ((M.H - 1 - iy) * M.W + ix); return Array.from(img.slice(p, p + 4)); }};
const region = (M, x, y) => {{ const h = LM.hit(M, x, y);
  return h && h.slot >= 0 ? D.T[M.slots[h.slot].row][0] : h; }};
"""
    done = subprocess.run([NODE], input=pre + script, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def close(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=False))


def test_life_regions_are_the_dominant_class_in_its_group_colour(world):
    got = node(
        world,
        """
const M = map(-1, null);
console.log(JSON.stringify({ins: region(M, -6.5, 0), aves: region(M, 6, 0), pl: region(M, 0, 5),
  sea: LM.hit(M, 1.5, -1), insPx: px(M, M.image, -6.5, 0), seaPx: px(M, M.image, 1.5, -1),
  labels: M.labels.map((l) => l.text), look: M.look}));""",
    )
    assert (got["ins"], got["aves"], got["pl"]) == ("Insecta", "Aves", "Magnoliopsida")
    assert got["sea"]["sea"] and got["seaPx"][3] == 0  # empty space stays transparent
    life_tint = 0.55  # at life a region is at most this strong, so the points over it read
    assert close(
        got["insPx"], [round(v * life_tint + 255 * (1 - life_tint)) for v in COLOURS[1]] + [255]
    )
    assert {"Insecta", "Aves", "Magnoliopsida"} <= set(got["labels"])
    kingdoms = [t for t in got["labels"] if "% of map" in t]
    assert sorted(t.split("\n")[0] for t in kingdoms) == ["ANIMALIA", "PLANTAE"]
    assert got["look"] is None  # no look-alike file: no look-alike picture


def test_tidy_absorbs_small_islands_and_unset_land_but_keeps_large_regions_and_the_sea(world):
    got = node(
        world,
        """
const W = 60, H = 40, code = new Uint8Array(W * H);
for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
  const c = y * W + x;
  code[c] = x < 30 ? 0 : 1;
  if (x >= 10 && x < 13 && y >= 10 && y < 13) code[c] = 1;    // a 9-cell stray inside A
  if (x >= 40 && x < 55 && y >= 15 && y < 30) code[c] = 0;    // a 225-cell island inside B
  if (y >= 36) code[c] = LM.SEA;
  if (x === 5 && y === 30) code[c] = 253;                       // land with no record near
}
code[2 * W + 2] = LM.OUTSIDE;
LM.tidy(code, W, H, 1, 1);
const at = (x, y) => code[y * W + x];
console.log(JSON.stringify({stray: at(11, 11), island: at(47, 22), left: at(29, 5),
  right: at(30, 5), sea: at(20, 38), unset: at(5, 30), outside: at(2, 2)}));""",
    )
    assert got["stray"] == 0  # under MIN_ISLAND cells: joins the region around it
    assert got["island"] == 0  # a large island keeps its region
    assert (got["left"], got["right"]) == (0, 1)  # a straight border stays where it is
    assert got["sea"] == 255 and got["unset"] == 0 and got["outside"] == 254


def test_zoom_crops_to_the_territory_and_leaves_other_clades_clear_without_dropping_them(world):
    got = node(
        world,
        f"""
const M = map({ROW["Insecta"]}, LM.decodeLookalike(fileBuf(), n));
const h = LM.hit(M, -4.75, 0);
console.log(JSON.stringify({{fine: M.fine, lep: region(M, -6.5, 0), col: region(M, -3, 0),
  patch: h, patchPx: px(M, M.image, -4.75, 0), lookPx: px(M, M.look, -4.75, 0),
  plants: LM.hit(M, 0, 5), birds: LM.hit(M, 6, 0), ext: M.ext,
  lep_px: px(M, M.image, -6.5, 0),
  names: [M, map(-1, null)].map((m) => m.labels.filter((l) => !l.bold)
    .map((l) => [l.text, !!l.italic, l.of ? l.of.text : null]))}}));""",
    )
    assert got["fine"] == "order"
    for names in got[
        "names"
    ]:  # a region is named once, and at most once more beside its main label
        mains = [t for t, italic, _ in names if not italic]
        assert len(mains) == len(set(mains)) and all(of == t for t, italic, of in names if italic)
        assert all(sum(1 for t, it, _ in names if it and t == m) <= 1 for m in mains)
    assert got["lep_px"][3] == 255  # solid where the clade holds every record
    assert min(got["lep_px"][:3]) >= round(255 * (1 - 0.55))  # a pastel, like the life map under it
    assert (got["lep"], got["col"]) == ("Lepidoptera", "Coleoptera")
    patch = got["patch"]
    assert patch["outside"] and patch["n"] > 0  # the birds between the orders are still counted
    # the map of life under it shows through
    assert got["patchPx"] == CLEAR and got["lookPx"] == CLEAR
    assert got["plants"] is None and got["birds"] is None  # cropped to the Insecta territory
    x0, y0, x1, y1 = got["ext"]
    assert x0 < -7.5 and x1 > -2 and x1 < 0 and y1 < 3


def test_a_second_zoom_into_the_same_points_crops_as_the_first_and_new_points_are_not_stale(world):
    got = node(
        world,
        f"""
const ins = map({ROW["Insecta"]}, null).ext, lep = map({ROW["Lepidoptera"]}, null).ext,
  again = map({ROW["Insecta"]}, null).ext;
delete require.cache[require.resolve({str(ASSET)!r})];
const cold = require({str(ASSET)!r});  // a fresh module: no life pass kept from an earlier zoom
const fresh = (o) => cold.build(Object.assign({{}}, base, o)).ext;
console.log(JSON.stringify({{ins, lep, again, coldIns: fresh({{clade: {ROW["Insecta"]}}}),
  coldLep: fresh({{clade: {ROW["Lepidoptera"]}}}),
  twice: fresh({{clade: {ROW["Insecta"]}, pos: base.pos.map((v) => 2 * v)}})}}));""",
    )
    assert got["ins"] == got["again"] == got["coldIns"] and got["lep"] == got["coldLep"]
    assert got["ins"] != got["lep"]
    assert got["twice"] == [2 * v for v in got["ins"]]  # another point set, not the kept one


def test_look_alike_mean_skips_undecidable_and_none(world):
    got = node(
        world,
        f"""
const M = map({ROW["Insecta"]}, LM.decodeLookalike(fileBuf(), n));
console.log(JSON.stringify({{lep: px(M, M.look, -6.5, 0), col: px(M, M.look, -3, 0),
  lev: LM.hit(M, -3, 0).levels}}));""",
    )
    assert close(got["lep"], RAMP_LO + [255])  # every record's look-alike is in its own family
    assert close(got["col"], RAMP_HI + [255])  # level 3 for every record that has one
    assert got["lev"][3] > 0 and got["lev"][0] == got["lev"][1] == got["lev"][2] == 0


def test_low_agreement_fades_a_region_and_is_reported_per_clade(world):
    got = node(
        world,
        """
const L = LM.decodeLookalike(fileBuf(), n), W = map(-1, L), N = map(-1, null);
const agree = {}; W.slots.forEach((s) => { if (s.row >= 0) agree[D.T[s.row][0]] = s.agree; });
console.log(JSON.stringify({agree, avesW: px(W, W.image, 6, 0), avesN: px(N, N.image, 6, 0),
  insW: px(W, W.image, -6.5, 0), insN: px(N, N.image, -6.5, 0)}));""",
    )
    assert got["agree"]["Aves"] == pytest.approx(3 / 12) and got["agree"]["Insecta"] == 1
    assert got["agree"]["Magnoliopsida"] is None  # unknown agreement is not a number
    assert (
        sum(got["avesW"][:3]) > sum(got["avesN"][:3]) + 60
    )  # birds' neighbours are mostly not birds
    assert close(got["insW"], got["insN"])


def test_decode_reads_the_four_nibbles_and_rejects_a_wrong_size(world):
    got = node(
        world,
        """
const buf = new Uint8Array([0x5c, 0xff, 0x70, 0x3f]).buffer, L = LM.decodeLookalike(buf, 2);
let err = '';
try { LM.decodeLookalike(buf, 3); } catch (e) { err = e.message; }
console.log(JSON.stringify({cls: Array.from(L.agree.class), ord: Array.from(L.agree.order),
  fam: Array.from(L.agree.family), lev: Array.from(L.code).map(LM.level), err}));""",
    )
    assert got["cls"] == [12, 15] and got["ord"] == [5, 15]
    assert got["fam"] == [0, 15] and got["lev"] == [5, 1]
    assert "expected 6" in got["err"]


def test_zoom_ranks(world):
    got = node(
        world,
        f"""
console.log(JSON.stringify({{fam: LM.canZoom(D.T, RANKS, {ROW["Nymphalidae"]}),
  ord: LM.canZoom(D.T, RANKS, {ROW["Lepidoptera"]}),
  famMap: map({ROW["Lepidoptera"]}, null).fine}}));""",
    )
    assert got["fam"] is False and got["ord"] is True and got["famMap"] == "family"


def test_labels_that_would_collide_or_read_too_small_are_dropped(world):
    got = node(
        world,
        """
const big = {text: 'Insecta', pos: [0, 0], size: 4, area: 900},
  near = {text: 'Aves', pos: [4, 0.5], size: 3, area: 100, italic: true},
  far = {text: 'Aves', pos: [40, 0], size: 3, area: 100},
  tiny = {text: 'Ascidiacea', pos: [-40, 0], size: 0.5, area: 5},
  king = {text: 'ANIMALIA\\n31% of map', pos: [0, 0.2], size: 4, area: 1, bold: true};
const at = (z, L) => LM.place(L, z, 11).map((l) => l.text);
console.log(JSON.stringify({z2: at(2, [near, tiny, far, big]), z5: at(5, [near, tiny, far, big]),
  king: at(2, [big, king]), tie: at(5, [{text: 'Small', pos: [0, 0], size: 4, area: 10},
    {text: 'Large', pos: [0, 0], size: 5, area: 20}]),
  rep: [4, 5].map((z) => at(z, [far,
    {text: 'Aves', pos: [40, 2.5], size: 3, area: 50, italic: true, of: far}]))}));""",
    )
    # at zoom 2 (4 px a unit) the small label beside the big one and the 2 px one go
    assert got["z2"] == ["Insecta", "Aves"]
    # zoomed in, there is room for both and the tiny one reads
    assert sorted(got["z5"]) == ["Ascidiacea", "Aves", "Aves", "Insecta"]
    assert got["king"] == ["ANIMALIA\n31% of map"]  # a kingdom outranks any class label
    assert got["tie"] == ["Large"]  # both capped at 30 px: the larger region keeps its name
    # a repeat 2.5 units from its main label: 40 px at zoom 4 is too close, 80 px at zoom 5 reads
    assert got["rep"] == [["Aves"], ["Aves", "Aves"]]


def test_a_finer_grid_samples_the_same_zoom_at_twice_the_cells(world):
    got = node(
        world,
        f"""
const L = LM.decodeLookalike(fileBuf(), n), lo = map({ROW["Insecta"]}, L),
  hi = LM.build(Object.assign({{}}, base, {{clade: {ROW["Insecta"]}, look: L, long: 1024}}));
const rows = (M) => M.slots.map((s) => s.row);
console.log(JSON.stringify({{lo: [lo.W, lo.H], hi: [hi.W, hi.H], loRows: rows(lo), hiRows: rows(hi),
  ext: [lo.ext, hi.ext], lep: region(hi, -6.5, 0), col: region(hi, -3, 0),
  patch: px(hi, hi.image, -4.75, 0), lev: LM.hit(hi, -3, 0).levels[3] > 0,
  labels: [lo.labels.map((l) => l.text).sort(), hi.labels.map((l) => l.text).sort()]}}));""",
    )
    assert max(got["hi"]) == 1024 and max(got["lo"]) == 512
    assert all(abs(h - 2 * lo) <= 1 for h, lo in zip(got["hi"], got["lo"], strict=True))
    assert got["hiRows"] == got["loRows"] and got["ext"][0] == got["ext"][1]
    assert (got["lep"], got["col"]) == ("Lepidoptera", "Coleoptera")
    assert got["patch"] == CLEAR  # the birds' patch is still outside
    assert got["lev"] and got["labels"][0] == got["labels"][1]


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def test_a_zoom_shades_its_clade_colour_and_a_kingdom_keeps_the_class_colours_of_life(world):
    got = node(
        world,
        f"""
const life = map(-1, null), INS = {ROW["Insecta"]}, LEP = {ROW["Lepidoptera"]};
const known = (r) => (life.slots.find((s) => s.row === r) || {{}}).rgb || null;
const zoom = (o) => LM.build(Object.assign({{}}, base, o));
const ins = zoom({{clade: INS, rgb: known(INS)}});
const lepRgb = ins.slots.find((s) => s.row === LEP).rgb, lep = zoom({{clade: LEP, rgb: lepRgb}});
const ani = zoom({{clade: {ROW["Animalia"]}, known}});
const hues = (M) => M.slots.filter((s) => s.row >= 0).map((s) => LM.hsl(s.rgb)[0]);
const many = Array.from({{length: 15}}, (_, s) => LM.shade([60, 140, 200], s).map(Math.round));
console.log(JSON.stringify({{insHue: LM.hsl(known(INS))[0], orders: hues(ins),
  lepHue: LM.hsl(lepRgb)[0], families: hues(lep), lifeIns: known(INS),
  aniIns: ani.slots.find((s) => s.row === INS).rgb, distinct: new Set(many.map(String)).size,
  gray: LM.shade([128, 128, 128], 3).map(Math.round)}}));""",
    )
    assert len(got["orders"]) == 2 and all(hue_gap(h, got["insHue"]) <= 28.5 for h in got["orders"])
    assert got["families"] and all(hue_gap(h, got["lepHue"]) <= 28.5 for h in got["families"])
    assert got["aniIns"] == got["lifeIns"]  # a class keeps the colour the map of life gave it
    assert got["distinct"] == 15  # siblings still tell apart
    assert got["gray"] == [128, 128, 128]  # no hue to keep, no hue added


def test_the_view_focuses_the_deepest_clade_filling_it_and_a_zoom_defers_to_life_outside(world):
    got = node(
        world,
        f"""
const life = map(-1, null), ins = map({ROW["Insecta"]}, null);
const lepZ = map({ROW["Lepidoptera"]}, null);
const focus = (Z, b) => LM.focus(life, Z, A, D.T, RANKS, b);
const name = (u) => u && D.T[u.row][0];
console.log(JSON.stringify({{all: focus(null, [-12, -6, 12, 9]),
  insects: focus(null, [-8.5, -2, -1.2, 2]), lep: focus(ins, [-7.6, -1, -5.4, 1]),
  plants: focus(null, [-1.5, 3.5, 1.5, 6.5]),
  keep: [focus(lepZ, [-4.1, -1, -1.9, 1]), focus([ins, lepZ], [-4.1, -1, -1.9, 1])],
  leave: focus([ins, lepZ], [-12, -6, 12, 9]), birds: focus([ins, lepZ], [5, -1, 7, 1]),
  sea: focus(null, [20, 20, 21, 21]), onLep: name(LM.region(life, ins, -6.5, 0)),
  onPatch: name(LM.region(life, ins, -4.75, 0)), onBirds: name(LM.region(life, ins, 6, 0)),
  overSea: LM.region(life, ins, 1.5, -1), insExt: ins.ext,
  ext: LM.extent(Object.assign({{}}, base, {{clade: {ROW["Insecta"]}}}))}}));""",
    )
    assert got["all"] == -1  # the whole map in view: all of life
    assert got["insects"] == ROW["Insecta"]  # both orders in view: their class
    assert got["lep"] == ROW["Lepidoptera"]  # one order fills the view: the order, not its class
    assert got["plants"] == ROW["Magnoliopsida"] and got["sea"] == -1
    # past an order's own map, its class's map, still cached, reads the view before the map of life
    assert got["keep"] == [ROW["Insecta"], ROW["Coleoptera"]]
    assert got["leave"] == -1 and got["birds"] == ROW["Aves"]
    assert got["onLep"] == "Lepidoptera"  # the zoom map's own region
    assert got["onPatch"] == got["onBirds"] == "Aves"  # outside the zoom's clade, the map of life
    assert got["overSea"] is None
    assert got["ext"] == got["insExt"]  # the camera flies to the box the zoom map is cropped to
