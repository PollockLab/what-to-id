"""The map's taxon logic (map_taxa.js), run in node."""

import json
import shutil
import subprocess
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

# rows [latin, common, id, rank, parent row]: records carry rows 0-3, ancestors follow
T = [
    ["Sphagnum fuscum", "Rusty Peat Moss", 5, 0, 5],
    ["Polytrichum", "Haircap Mosses", 6, 1, 6],
    ["Agaricus", "", 8, 1, 7],
    ["Marchantia", "", 9, 1, 8],
    ["Plantae", "Plants", 2, 2, -1],
    ["Sphagnum", "Peat Mosses", 4, 1, 6],
    ["Bryophyta", "Mosses", 3, 2, 4],
    ["Agaricales", "Gilled Mushrooms", 47167, 3, -1],
    ["Marchantiophyta", "Liverworts", 64615, 2, 4],
]
META = {
    "place_id": 7085,
    "max_url": 2000,
    "imprecise_m": 1000,
    "groups": ["Fungi", "Plantae"],
    "names": {"Fungi": "Fungi", "Plantae": "Plants"},
    "group_ids": {"Fungi": 47170, "Plantae": 47126},
    "presets": [["Bryophytes", [3, 64615], "Mosses and liverworts"]],
}
BOX = {"w": -125, "s": 48, "e": -122, "n": 50}


def run(body: str):
    src = files("what_to_id").joinpath("map_assets/map_taxa.js").read_text()
    script = (
        f"{src}\nvar T={json.dumps(T)},META={json.dumps(META)},BOX={json.dumps(BOX)};\n"
        f"process.stdout.write(JSON.stringify((function(){{{body}}})()));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def url(st: dict) -> dict:
    base = {"groups": [], "all": 2, "up": False, "d1": "", "d2": "", "months": [], "only": {}}
    r = run(f"return TX.identifyUrl({json.dumps({**base, **st})},BOX,META);")
    q = {k: v[0] for k, v in parse_qs(urlparse(r["url"]).query).items()}
    return {"q": q, "lost": r["lost"]}


def test_filter_keeps_descendants_and_subtracts_excludes():
    r = run(
        "var f=TX.filter(T,[{id:3},{id:4,not:true},{id:64615}]);"
        "return [Array.from(f.inc),Array.from(f.exc),f.ids,f.not];"
    )
    inc, exc, ids, nots = r
    assert inc == [1, 1, 0, 1, 0, 1, 1, 0, 1]
    assert exc == [1, 0, 0, 0, 0, 1, 0, 0, 0]
    assert ids == [3, 64615] and nots == [4]


def test_filter_without_table_or_picks_keeps_everything():
    assert run("var f=TX.filter(null,[{id:3}]);return [f.inc,f.ids];") == [None, [3]]
    assert run("var f=TX.filter(T,[]);return [f.inc,f.exc];") == [None, None]


def test_hash_value_round_trips():
    assert run("return TX.write([{id:3,not:false},{id:4,not:true}]);") == "3,-4"
    assert run("return TX.read('3,-4,x,3,,-0');") == [
        {"id": 3, "not": False},
        {"id": 4, "not": True},
        {"id": 0, "not": True},
    ]
    assert run("return TX.read(null);") == []


def test_identify_url_for_clades_groups_and_not():
    r = url({"taxa": [3, 64615, 47170], "not": [4]})
    assert r["q"]["taxon_id"] == "3,64615,47170" and r["q"]["without_taxon_id"] == "4"
    assert "iconic_taxa" not in r["q"] and r["lost"] == []
    assert r["q"]["place_id"] == "7085" and r["q"]["quality_grade"] == "needs_id"
    r = url({"groups": ["Fungi"], "not": [54743]})
    assert r["q"]["iconic_taxa"] == "Fungi" and r["q"]["without_taxon_id"] == "54743"
    assert "taxon_id" not in r["q"]


def test_identify_url_says_what_it_leaves_out():
    many = list(range(1000000, 1000051))
    r = url({"taxa": many, "not": [4]})
    assert "taxon_id" not in r["q"] and r["q"]["without_taxon_id"] == "4"
    assert r["lost"] == ["taxa"]
    long = list(range(10**8, 10**8 + 50))
    meta = {**META, "max_url": 400}
    base = {"groups": [], "all": 2, "up": False, "d1": "", "d2": "", "months": [], "only": {}}
    st = {**base, "taxa": [3], "not": long}
    got = run(f"return TX.identifyUrl({json.dumps(st)},BOX,{json.dumps(meta)});")
    assert got["lost"] == ["not"] and "taxon_id=3" in got["url"]


def test_old_q_resolves_to_clades():
    r = run("return TX.resolve(T,'agaricales, -Sphagnum, peat mosses, Marchant, nothing',null);")
    # Sphagnum and "peat mosses" name the same taxon: only the first pick of it stays
    assert r == [{"id": 47167, "not": False}, {"id": 4, "not": True}, {"id": 9, "not": False}]
    assert run("return [TX.within(T,5,[2]),TX.within(T,8,[2]),TX.within(T,99,[2])];") == [
        True,
        False,
        False,
    ]


def test_terms_shape():
    body = (
        "var t=TX.terms({T:T,picks:[{id:3,not:false},{id:64615,not:false},{id:47167,not:true}],"
        "groups:['Fungi'],meta:META,tax:[0,1,2,3,65535],grp:[1,1,0,1,0],n:5});"
        "return t.map(function(x){return [x.dim,x.kind,x.id,x.label,x.exclude,Array.from(x.mask()),"
        "x.inat()];});"
    )
    g, pre, cl = run(body)
    assert g == [
        "taxon",
        "group",
        47170,
        "Fungi",
        False,
        [0, 0, 1, 0, 1],
        {"params": {"taxon_id": "47170"}, "exact": True},
    ]
    assert pre[:5] == ["taxon", "preset", [3, 64615], "Bryophytes", False]
    assert pre[5] == [1, 1, 0, 1, 0] and pre[6]["params"] == {"taxon_id": "3,64615"}
    assert cl[:6] == ["taxon", "clade", 47167, "Agaricales", True, [0, 0, 1, 0, 0]]
    assert cl[6] == {"params": {"without_taxon_id": "47167"}, "exact": True}
