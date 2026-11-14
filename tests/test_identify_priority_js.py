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
