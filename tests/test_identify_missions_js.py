"""IdentifyMissions.pick: parts of one group in one cell, sized as the grid will show them,
the best six with a new group first."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src/what_to_id/identify_assets/identify_missions.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SCRIPT = """
const pick = IdentifyMissions.pick;
// a part: n records of group g in cell c, each its own species unless sp says, scoring s
function rows(parts) {
  const r = {n: 0, idx: [], g: [], cell: [], sp: [], score: [], risk: []};
  parts.forEach(([g, c, n, s, sp]) => {
    for (let k = 0; k < n; k++) {
      r.idx.push(r.n); r.g.push(g); r.cell.push(c); r.sp.push(sp === undefined ? r.n : sp);
      r.score.push(s); r.risk.push(0); r.n++;
    }
  });
  return r;
}
const sizes = m => m.map(x => x.n);
const out = {};
out.empty = pick(rows([])).length;
out.nocell = pick(Object.assign(rows([[0, 1, 20, 5]]), {cell: Array(20).fill(-1)})).length;
// sizes outside 10..200 are dropped, 10 and 200 stay
out.bounds = sizes(pick(rows([[0, 1, 9, 5], [1, 2, 10, 4], [2, 3, 200, 3], [3, 4, 201, 9]])));
// all one group: the six best cells, best first
const cells = [0, 1, 2, 3, 4, 5, 6, 7].map(c => [0, c, 10 + c, 8 - c]);
out.onegroup = pick(rows(cells)).map(x => x.cell);
// a new group before a group repeats, though group 0 scores best
const sp = rows([[0, 1, 10, 9], [0, 2, 10, 8], [0, 3, 10, 7], [1, 4, 10, 1], [2, 5, 10, 1]]);
out.spread = pick(sp).map(x => [x.g, x.cell]);
// the cap: a species holds three cards; a part of one species keeps them all
const capped = rows([[0, 1, 30, 1, 7], [0, 1, 30, 1, 8], [0, 1, 30, 1, 9], [0, 1, 1, 1, 10]]);
out.cap = sizes(pick(capped, {cap: 3}));
out.one = sizes(pick(rows([[0, 1, 30, 1, 7]]), {cap: 3}));
// determinism: the same input, the same missions, a mission's cards best first
const a = rows([[0, 1, 15, 2], [1, 2, 15, 2], [2, 3, 15, 2]]);
out.same = JSON.stringify(pick(a)) === JSON.stringify(pick(a));
out.top = pick(a, {top: 2}).length;
const b = rows([[0, 1, 12, 1]]);
b.score[5] = 9;
out.best = pick(b)[0].rows[0];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def got():
    run = subprocess.run(
        [NODE], input=SRC.read_text() + SCRIPT, capture_output=True, text=True, check=True
    )
    return json.loads(run.stdout)


def test_nothing_to_pick_gives_no_missions(got):
    assert got["empty"] == 0 and got["nocell"] == 0


def test_parts_outside_ten_to_two_hundred_cards_are_dropped(got):
    assert sorted(got["bounds"]) == [10, 200]


def test_one_group_gives_its_best_cells_in_score_order(got):
    assert got["onegroup"] == [0, 1, 2, 3, 4, 5]


def test_a_group_not_yet_picked_comes_before_a_repeat(got):
    assert got["spread"] == [[0, 1], [1, 4], [2, 5], [0, 2], [0, 3]]


def test_a_part_counts_the_cards_the_grid_will_show(got):
    assert got["cap"] == [10] and got["one"] == [30]


def test_the_choice_is_deterministic_and_a_mission_lists_its_best_card_first(got):
    assert got["same"] and got["top"] == 2 and got["best"] == 5
