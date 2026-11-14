"""The left-needs-ID layer's decoding and filtering (map_resolved.js), run in node on a file the
Python side wrote."""

import base64
import functools
import gzip
import json
import shutil
import subprocess
from importlib.resources import files

import pytest

from what_to_id.map_points import encode_points
from what_to_id.map_resolved import encode_left

from .embeddings_fixture import TREE, pool_frame
from .test_map_resolved import NOW, log_frame

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
JS = (
    "map_taxa.js",
    "map_chips.js",
    "map_filter.js",
    "identify_links.js",
    "map_rings.js",
    "map_area.js",
)
RING = [-123.5, 48.5, -122.5, 48.5, -122.5, 49.5, -123.5, 49.5]  # lon, lat of a box round the log


@functools.cache
def fixture():
    """The map's META and taxa for a small pool, and a file of six records that left."""
    pool = pool_frame(range(100, 103))  # groups Aves, Insecta, Plantae; taxa 1000-1002
    pool["observed_on"] = pool["created_at"] = ["2026-06-01", "2026-08-01", "2026-11-03"]
    blobs, meta = encode_points(pool, TREE)
    taxa = json.loads(gzip.decompress(blobs[meta["taxa"]]))
    # ids 1 to 6 left 0, 6, 7, 20, 29 and 31 days ago; id 3 has a taxon the pool lacks, 4 is east
    log = log_frame(
        range(1, 7), [0, 6, 7, 20, 29, 31], taxon_id=[1000, 1001, 1004, 1002, 1000, 1000]
    )
    log["iconic_taxon"] = ["Aves", "Insecta", "Plantae", "Aves", "Insecta", "Aves"]
    log["observed_on"] = log["created_at"] = [
        f"2026-{m}-{d}"
        for m, d in (
            ("10", "30"),
            ("10", "01"),
            ("09", "15"),
            ("08", "01"),
            ("07", "01"),
            ("07", "02"),
        )
    ]
    log.loc[log["id"] == 4, "lon"] = -120.0
    log["lat"], log["lon"] = 49.0, log["lon"].where(log["id"] == 4, -123.0)
    return meta, taxa, base64.b64encode(encode_left(log, pool, TREE, NOW)).decode()


def run(body: str):
    meta, taxa, blob = fixture()
    src = files("what_to_id").joinpath("map_assets")
    js = "\n".join((src / f).read_text() for f in (*JS, "map_resolved.js"))
    script = (
        f"{js}\nvar META={json.dumps(meta)},T={json.dumps(taxa)},MF=MapFilter(META),"
        f"zb=require('zlib').gunzipSync(Buffer.from('{blob}','base64')),"
        "shift=(MF.D0-Date.UTC(1900,0,1))/MF.DAY,"
        "R=leftDecode(zb.buffer.slice(zb.byteOffset,zb.byteOffset+zb.length),shift,MF.LAST);\n"
        "function ids(h,win,rings){var S=MF.read(new URLSearchParams(h)),"
        "m=leftKeep(MF,CH,META.groups,S,TX.filter(T,S.picks),R,(rings||[]).map(MapArea.index),win);"
        "return Array.from(R.id).filter(function(x,i){return m[i];});}\n"
        f"process.stdout.write(JSON.stringify((function(){{{body}}})()));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_decode_gives_the_records_in_the_maps_days_and_the_log_start_and_build_day():
    got = run(
        "return [R.n,Array.from(R.id),R.build-R.start,Array.from(R.obs.slice(0,2)),"
        "MF.iso(R.build-shift)];"
    )
    # the log starts at the 31-day-old record, which the file leaves out
    assert got[:3] == [5, [1, 2, 3, 4, 5], 31]
    assert got[3] == [151, 122]  # 2026-10-30 and 2026-10-01 counted from 2026-06-01
    assert got[4] == "2026-11-03"


def test_the_window_counts_from_the_build_day_not_the_browsers_clock():
    assert run("return [ids('',7),ids('',30)];") == [[1, 2], [1, 2, 3, 4, 5]]


def test_groups_taxa_dates_months_and_uploaded_dates_filter_as_on_the_map():
    got = run(
        "return [ids('groups=Aves',30),ids('groups=-Aves',30),ids('taxa=900',30),"
        "ids('taxa=800',30),"
        "ids('from=2026-09-01',30),ids('months=10',30),ids('by=uploaded&from=2026-10-25',30)];"
    )
    assert got == [[1, 4], [2, 3, 5], [1, 2, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3], [1, 2], [1]]


def test_a_taxon_pick_keeps_a_record_whose_taxon_left_the_pool_through_its_ancestor():
    # id 3 is taxon 1004, not in the pool: it counts under the family row, not under Genus A
    assert run("return [ids('taxa=800',30).indexOf(3)>=0,ids('taxa=900',30).indexOf(3)>=0];") == [
        True,
        False,
    ]


def test_areas_keep_the_records_inside_them():
    assert run(f"return ids('',30,[[{RING}]]);") == [1, 2, 3, 5]
    assert run(f"return ids('',30,[[{RING}],[[-121,49,-119,49,-119,50,-121,50]]]);") == [
        1,
        2,
        3,
        4,
        5,
    ]


def test_a_file_of_the_wrong_size_is_refused():
    assert (
        run("try{leftDecode(new ArrayBuffer(10),0,9);}catch(e){return e.message;}")
        == "unexpected size"
    )


SAY = (
    "var nf=new Intl.NumberFormat('en-CA'),fmt=function(d,y){return 'D'+d+(y?'Y':'');};"
    "function say(k,rg,win,R,v){var s=leftSay(k,rg,!!v,win,R,fmt,nf);return [s.text,s.tip,s.note];}"
)


def test_the_line_names_the_window_only_when_the_log_reaches_back_that_far():
    got = run(
        SAY + "return [say(5,2,30,{build:100,start:71,live:71}),"
        "say(5,2,30,{build:100,start:72,live:72}),say(5,0,7,{build:100,start:99,live:99}),"
        "say(5,2,30,{build:100,start:71,live:71},1)];"
    )
    assert got == [
        ["5 left Needs ID in the last 30 days, 2 as Research Grade", "D71 to D100Y, UTC", ""],
        ["5 left Needs ID since D72, 2 as Research Grade", "D72 to D100Y, UTC", ""],
        ["5 left Needs ID since D99", "D99 to D100Y, UTC", ""],
        [
            "5 in view left Needs ID in the last 30 days, 2 as Research Grade",
            "D71 to D100Y, UTC",
            "",
        ],
    ]


def test_research_grade_only_is_noted_while_the_window_reaches_before_the_live_log():
    got = run(
        SAY + "return [say(5,5,30,{build:100,start:60,live:90}),"  # window starts day 71, live 90
        "say(5,5,7,{build:100,start:60,live:90}),"  # window starts day 94, after live: no note
        "say(5,5,30,{build:100,start:80,live:90})];"  # log younger than the window
    )
    note = "Before D90 only Research Grade is counted."
    assert [g[2] for g in got] == [note, "", note]
    assert got[0][0] == "5 left Needs ID in the last 30 days, 5 as Research Grade"
    assert got[2][0] == "5 left Needs ID since D80, 5 as Research Grade"
