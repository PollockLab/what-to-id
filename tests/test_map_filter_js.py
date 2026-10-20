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
    "flags": ["introduced", "threatened", "obscured", "imprecise", "accuracy"],
}


def run(body: str, meta=META):
    src = files("what_to_id").joinpath("map_assets")
    js = "\n".join((src / f).read_text() for f in ("map_taxa.js", "map_chips.js", "map_filter.js"))
    script = (
        f"{js}\nvar META={json.dumps(meta)},MF=MapFilter(META);\n"
        f"process.stdout.write(JSON.stringify((function(){{{body}}})()));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_hash_round_trips_dates_months_groups_and_only():
    h = "by=uploaded&from=2024-03-01&to=2024-06-30&months=3,4"
    h += "&groups=-Aves,Insecta&only=-introduced&acc=100"
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
    assert got[1][4] == 2 and got[1][5] == 12 and got[1][7] & 1 and not got[1][7] & 4


# accuracy class in flags: 0 unknown, 1 over 1 km (8), then 1 km, 100 m, 10 m (64, 128, 192)
CLASS_FLAGS = [0, 8, 64, 128, 192]
OBSCURED = 4


def test_accuracy_class_reads_the_flags_byte():
    got = run(f"return {CLASS_FLAGS}.map(function(f){{return MF.accClass(f|3);}});")
    assert got == [0, 1, 2, 3, 4]


@pytest.mark.parametrize(
    "acc,passes",
    [
        ("", [1, 1, 1, 1, 1]),
        ("unknown", [1, 0, 0, 0, 0]),
        ("known", [0, 1, 1, 1, 1]),
        ("1000", [0, 0, 1, 1, 1]),
        ("100", [0, 0, 0, 1, 1]),
        ("10", [0, 0, 0, 0, 1]),
    ],
)
def test_accuracy_choice_filters_each_class_on_both_filter_paths(acc, passes):
    # the GPU path (accOut into the status, then categories) and the CPU path (rest) must agree
    got = run(
        f"var S=MF.read(new URLSearchParams({json.dumps('acc=' + acc)})),F={CLASS_FLAGS},"
        "st=MF.categories(S,false,false)[3],f=new Uint8Array(F),o=new Uint16Array(5),"
        "r=MF.rest(S,o,o,f,5,new Uint8Array(5).fill(1));"
        "return [F.map(function(x){return st.indexOf(MF.ST_KEEP|MF.accOut(S.acc,x))>=0?1:0;}),"
        "Array.from(r)];"
    )
    assert got == [passes, passes]


def test_obscured_records_pass_only_any_and_unknown():
    got = run(
        f"return ['','unknown','known','1000','10'].map(function(a){{"
        f"return MF.accOut(a,{OBSCURED}|64)?0:1;}});"
    )
    # unknown keeps obscured records (it asks about missing accuracy); precision choices drop them
    assert got == [1, 0, 0, 0, 0]
    assert run(f"return MF.accOut('unknown',{OBSCURED})") == 0


def test_old_exact_hash_reads_as_within_1_km():
    got = run(
        "var S=MF.read(new URLSearchParams('only=introduced,exact'));"
        "return [S.acc,S.only,MF.write(S)];"
    )
    assert got == ["1000", {"introduced": "inc"}, ["only=introduced", "acc=1000"]]


def test_unknown_acc_value_is_ignored_and_a_pool_without_accuracy_has_no_choice():
    assert run("return MF.read(new URLSearchParams('acc=7')).acc") == ""
    old = {**META, "flags": ["introduced", "threatened", "obscured"]}
    got = run(
        "return ['acc=100','only=exact'].map(function(h){"
        "return MF.read(new URLSearchParams(h)).acc;})",
        old,
    )
    assert got == ["", ""]
