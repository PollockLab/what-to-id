import json
import shutil
import subprocess
from importlib.resources import files

import pytest

ASSETS = files("what_to_id") / "map_assets"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _counts(bounds, lo=0, hi=9, up=False, groups=False, everywhere=False):
    """map.js's inView() against 5 records at lon 0, 1, 5, 179 and -179 (lat 0). Kept: all but
    #1, which only the group filter leaves out; #3 has no day. Returns the count, or None for a
    view 360 degrees wide or more or the switch on All of BC (everywhere: no restriction, so the
    page shows nShown()); with groups, the per-group counts instead."""
    source = (ASSETS / "map.js").read_text()
    start = source.index("var VC=null")
    body = source[start : source.index("function render()", start)]
    harness = f"""
const NO=65535,LAST=9,S={{lo:{lo},hi:{hi},up:{json.dumps(up)}}},B={json.dumps(bounds)};
const full=()=>S.lo===0&&S.hi===LAST,MapArea={{Q:1e4}};
const map={{getBounds:()=>({{getWest:()=>B[0],getSouth:()=>B[1],
  getEast:()=>B[2],getNorth:()=>B[3]}})}};
const P={{n:5,pos:Float32Array.of(0,0,1,0,5,0,179,0,-179,0),obs:Uint16Array.of(2,2,2,NO,2),
  up:Uint16Array.of(8,8,8,8,8),grp:Uint8Array.of(0,1,0,1,0)}};
const KEEP=Uint8Array.of(1,0,1,1,1),BK=Uint8Array.of(1,1,1,1,1),META={{groups:['A','B']}};
let VM=new Uint8Array(0);
"""
    out = "Array.from(VC.g)" if groups else "inView()"
    run = subprocess.run(
        [
            "node",
            "-e",
            f"{harness}{body}ALL={json.dumps(everywhere)};inView();console.log(JSON.stringify({out}))",
        ],
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
def test_in_view_rounds_the_box_as_the_view_sent_to_identify_is_rounded():
    assert _counts([-1, -1, 4.99996, 1]) == 2  # east edge rounds to 5: #2 counts
    assert _counts([-1, -1, 4.99994, 1]) == 1


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


@needs_node
def test_in_view_counts_each_group_with_the_group_filter_left_out():
    assert _counts([-1, -1, 2, 1], groups=True) == [1, 1]  # #1 counts for its group
    assert _counts([-180, -90, 180, 90], groups=True) == [3, 2]  # the world: every dated record
    assert _counts([-180, -90, 180, 90], lo=1, groups=True) == [3, 1]  # the dateless #3 drops


@needs_node
def test_all_of_bc_ignores_the_view_and_counts_every_group():
    assert _counts([-1, -1, 2, 1], everywhere=True) is None  # the page then shows nShown()
    assert _counts([-1, -1, 2, 1], groups=True, everywhere=True) == [3, 2]
    assert _counts([-1, -1, 2, 1], lo=1, groups=True, everywhere=True) == [3, 1]


def _node(harness, start, end, script):
    source = (ASSETS / "map.js").read_text()
    i = source.index(start)
    body = source[i : source.index(end, i)]
    run = subprocess.run(
        ["node", "-e", harness + body + script], capture_output=True, text=True, check=True
    )
    return json.loads(run.stdout)


@needs_node
def test_fit_frames_the_kept_records_and_skips_an_empty_set():
    harness = """
const S={lo:0,hi:9},LAST=9,NODAY=0,CUM=[],out=[];
const map={resize:()=>out.push('resize'),fitBounds:(b,o)=>out.push([b,o.maxZoom])};
const P={n:3,pos:Float32Array.of(-123,49,-120,50,-125,48)};
"""
    got = _node(
        harness,
        "function full()",
        "var VC=null",
        "fitTo(i=>i!==2);fitTo(()=>false);fitTo(i=>i===1);console.log(JSON.stringify(out))",
    )
    # each fit first takes the map's new size: the count above it may have rewrapped
    fits = [[[[-123, 49], [-120, 50]], 14], [[[-120, 50], [-120, 50]], 14]]
    assert got == ["resize", fits[0], "resize", fits[1]]


@needs_node
def test_a_new_taxon_or_group_fits_the_map_unless_the_viewer_moved_it():
    harness = """
let K='',TK0=null,MOVED=false,fits=0;const ZB={hidden:true};
const taxaKey=()=>K,shows=()=>null,fitTo=()=>fits++;
"""
    # the first key is the page's own, a months change leaves the key, a moved map gets the button
    script = (
        "console.log(JSON.stringify([['taxa=5',0],['taxa=5',0],['taxa=6',0],['',0],"
        "['groups=Aves',1],['',1]].map(([k,m])=>{K=k;MOVED=!!m;const f=fits;fitNew();"
        "return [fits-f,ZB.hidden];})))"
    )
    got = _node(harness, "// a new taxon or group", "// kept records dated", script)
    assert got == [[0, True], [0, True], [1, True], [0, True], [0, False], [0, True]]
