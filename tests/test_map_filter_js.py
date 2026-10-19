"""The map's filter state and category values (map_filter.js), run in node."""

import json
import shutil
import subprocess
from importlib.resources import files

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

META = {
    "day0": "2024-01-30",
    "days": 400,
    "groups": ["Aves", "Insecta", "Plantae"],
    "flags": ["introduced", "threatened", "obscured"],
}


def run(body: str):
    src = files("what_to_id").joinpath("map_assets")
    js = "\n".join((src / f).read_text() for f in ("map_taxa.js", "map_chips.js", "map_filter.js"))
    script = (
        f"{js}\nvar META={json.dumps(META)},MF=MapFilter(META);\n"
        f"process.stdout.write(JSON.stringify((function(){{{body}}})()));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_hash_round_trips_dates_months_groups_and_only():
    h = "by=uploaded&from=2024-03-01&to=2024-06-30&months=3,4"
    h += "&groups=-Aves,Insecta&only=-introduced,exact"
    got = run(
        f"var S=MF.read(new URLSearchParams({json.dumps(h)}));return [MF.write(S).join('&'),S];"
    )
    assert got[0] == h
    assert got[1]["groups"] == {"Insecta": "inc", "Aves": "not"} and got[1]["months"] == 0b1100


def test_empty_hash_is_everything_and_writes_nothing():
    got = run(
        "var S=MF.read(new URLSearchParams(''));"
        "return [MF.write(S),S.lo,S.hi,MF.categories(S,false,false)];"
    )
    assert got[0] == [] and (got[1], got[2]) == (0, 399)
    assert got[3][0] == [0, 1, 2] and got[3][1] == list(range(13)) and 8 in got[3][3]


def test_swapped_and_out_of_range_dates_clamp():
    got = run(
        "var S=MF.read(new URLSearchParams('from=2099-01-01&to=2020-01-01'));return [S.lo,S.hi];"
    )
    assert got == [0, 399]


def test_categories_follow_groups_months_and_status():
    got = run(
        "var S=MF.read(new URLSearchParams('groups=Aves&months=1&only=threatened'));"
        "return MF.categories(S,false,false);"
    )
    assert got[0] == [0] and got[1] == [0] and all(v & 2 and v & 8 for v in got[3])
    thin = run("var S=MF.read(new URLSearchParams(''));return MF.categories(S,false,true)[3];")
    assert thin and all(v & 16 for v in thin)


def test_record_packs_days_months_and_status():
    got = run(
        "var days=new Float32Array(4),cat=new Uint8Array(8);"
        "MF.record(days,cat,1,2,65535,10,MF.FLAG.introduced|MF.FLAG.imprecise);"
        "return [Array.from(days),Array.from(cat)];"
    )
    assert got[0][2:] == [-1, 10]
    assert got[1][4] == 2 and got[1][5] == 12 and got[1][7] & 1 and got[1][7] & 4
