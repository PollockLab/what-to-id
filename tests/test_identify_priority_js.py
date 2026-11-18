"""The Prioritize comparator reduces exactly to the orders Identify had (sort=conf, sort=gaps and
the default blend of band and gap tier), and with every prioritizer off it orders by id."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src/what_to_id/identify_assets/identify_gaps.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SCRIPT = """
const n = 400;
let a = 12345;
const rnd = () => (a = (a * 1664525 + 1013904223) % 4294967296) / 4294967296;
const rank = [...Array(n).keys()].sort(() => rnd() - 0.5);  // a rank per record, 0 best
const tier = rank.map(() => Math.floor(rnd() * 3));
const key = rank.map(() => Math.floor(rnd() * 2));  // two groups of the level's order
const id = rank.map(() => Math.floor(rnd() * 4e9));
const band = r => {
  const p = (r + 1) / n;
  return p <= 0.01 ? 0 : p <= 0.05 ? 1 : p <= 0.25 ? 2 : 3;
};
const idx = [...Array(n).keys()];
// the orders before Prioritize, best last (identify_app.js on main)
const old = {
  conf: (x, y) => key[x] - key[y] || rank[y] - rank[x],
  gaps: (x, y) => key[x] - key[y] || (tier[x] - tier[y]) || rank[y] - rank[x],
  both: (x, y) => {
    const pr = i => band(rank[i]) - tier[i];
    return key[x] - key[y] || pr(y) - pr(x) || band(rank[y]) - band(rank[x]) || rank[y] - rank[x];
  },
};
const mk = (wc, wg) => IdentifyGaps.compare({
  key, id, base: 'new', seed: 1,
  score: Float64Array.from(idx, i => wc * (3 - band(rank[i])) + wg * tier[i]),
  fine: Float64Array.from(idx, i => -rank[i]),
});
const sorted = c => idx.slice().sort(c);
const same = (c, d) => JSON.stringify(sorted(c)) === JSON.stringify(sorted(d));
const off = base => IdentifyGaps.compare(
  {key, id, base, seed: 1, score: new Float64Array(n), fine: null});
const asc = sorted(off('new')).map(i => [key[i], id[i]]);
const desc = sorted(off('old')).map(i => [key[i], id[i]]);
const ok = (v, up) => v.every((p, j) => !j || p[0] > v[j - 1][0] ||
  p[0] === v[j - 1][0] && (up ? p[1] >= v[j - 1][1] : p[1] <= v[j - 1][1]));
console.log(JSON.stringify({
  conf: same(mk(1, 0), old.conf), gaps: same(mk(0, 1), old.gaps), both: same(mk(1, 1), old.both),
  newest: ok(asc, true), oldest: ok(desc, false),
  heavier: sorted(mk(3, 1)).join() !== sorted(mk(1, 1)).join(),
}));
"""


def test_the_weighted_blend_reduces_to_the_old_orders_and_all_off_is_by_id():
    script = SRC.read_text() + SCRIPT
    out = subprocess.run([NODE], input=script, capture_output=True, text=True, check=True).stdout
    got = json.loads(out)
    assert got == dict.fromkeys(got, True), got


RSORT = """
let a = 99;
const rnd = () => (a = (a * 1664525 + 1013904223) % 4294967296) / 4294967296;
const n = 5000;
const pick = k => Math.floor(rnd() * k);
const mkArr = (T, f) => T.from({length: n}, f);
const scores = {ties: () => pick(3) / 4, spread: () => rnd() * 1.7, flat: () => 0};
const ok = {};
for (const base of ['new', 'old', 'rand']) {
  for (const fine of [false, true]) {
    for (const [name, sc] of Object.entries(scores)) {
      // few distinct keys, scores and ids (ids repeat so ties reach the last field), ids past 2^31
      const o = {
        key: mkArr(Uint16Array, () => pick(4) + 8), id: mkArr(Uint32Array, () => 3e9 + pick(400)),
        score: mkArr(Float64Array, sc), base, seed: 7,
        fine: fine ? mkArr(Float64Array, () => -pick(70000)) : null,
      };
      for (const pre of [false, true]) {
        // repeats in any order (ties keep it), or as build fills it: by key, then by id
        const ord = pre ? Int32Array.from({length: n}, (_, i) => i).sort(
          (x, y) => o.key[x] - o.key[y] || o.id[x] - o.id[y]) : mkArr(Int32Array, () => pick(n));
        const want = Int32Array.from(ord).sort(IdentifyGaps.compare(o));
        IdentifyGaps.rsort(ord, o);
        ok[[base, fine, name, pre].join()] = want.join() === ord.join();
      }
    }
  }
}
const e = new Int32Array(0);
const z = {key: new Uint16Array(1), id: new Uint32Array(1), score: new Float64Array(1)};
IdentifyGaps.rsort(e, {...z, fine: null, base: 'new', seed: 0});
ok.empty = e.length === 0;
console.log(JSON.stringify(ok));
"""


def test_the_radix_sort_gives_the_comparator_order_ties_included():
    script = SRC.read_text() + RSORT
    out = subprocess.run([NODE], input=script, capture_output=True, text=True, check=True).stdout
    got = json.loads(out)
    assert len(got) == 37 and got == dict.fromkeys(got, True), got
