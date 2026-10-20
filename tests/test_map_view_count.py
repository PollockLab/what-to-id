import json
import shutil
import subprocess
from importlib.resources import files

import pytest

ASSETS = files("what_to_id") / "map_assets"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _counts(bounds, lo=0, hi=9, up=False):
    """map.js's inView() against 5 records at lon 0, 1, 5, 179 and -179 (lat 0). Kept: all but
    #1; #3 has no day. Returns the count, or None for a view
    360 degrees wide or more (no restriction)."""
    source = (ASSETS / "map.js").read_text()
    start = source.index("var VC=null;")
    body = source[start : source.index("function render()", start)]
    harness = f"""
const NO=65535,LAST=9,S={{lo:{lo},hi:{hi},up:{json.dumps(up)}}},B={json.dumps(bounds)};
const full=()=>S.lo===0&&S.hi===LAST;
const map={{getBounds:()=>({{getWest:()=>B[0],getSouth:()=>B[1],
  getEast:()=>B[2],getNorth:()=>B[3]}})}};
const P={{n:5,pos:Float32Array.of(0,0,1,0,5,0,179,0,-179,0),obs:Uint16Array.of(2,2,2,NO,2),
  up:Uint16Array.of(8,8,8,8,8)}};
const KEEP=Uint8Array.of(1,0,1,1,1);
"""
    run = subprocess.run(
        ["node", "-e", harness + body + "console.log(JSON.stringify(inView()))"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(run.stdout)


@needs_node
def test_in_view_counts_kept_records_inside_the_box():
    assert _counts([-1, -1, 2, 1]) == 1  # #0 in, #1 in but not kept, the rest outside
    assert _counts([-1, 10, 2, 11]) == 0  # nothing at that latitude


@needs_node
def test_in_view_follows_the_date_range_and_dateless_records():
    assert _counts([-1, -1, 6, 1], lo=3, hi=9) == 0  # both kept records are dated day 2
    assert _counts([-1, -1, 6, 1], lo=0, hi=9) == 2
    assert _counts([-1, -1, 6, 1], lo=0, hi=1) == 0
    assert _counts([-1, -1, 6, 1], up=True, lo=8, hi=9) == 2  # by upload date
    assert _counts([178, -1, 180, 1], lo=0, hi=9) == 1  # the dateless #3 counts over all dates only
    assert _counts([178, -1, 180, 1], lo=1, hi=9) == 0


@needs_node
def test_in_view_handles_the_antimeridian_and_the_whole_world():
    assert _counts([170, -1, 190, 1]) == 2  # 179 and -179 (as 181)
    assert _counts([-185, -1, -175, 1]) == 2  # wraps to 175..-175
    assert _counts([-180, -1, -178, 1]) == 1  # -179 only
    assert _counts([-180, -90, 180, 90]) is None  # 360 degrees wide: no restriction
