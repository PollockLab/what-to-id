"""The map's user filter rules (map_user.js), run in node."""

import json
import shutil
import subprocess
from importlib.resources import files

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

RANKS = ["species", "genus", "family", "order"]
# rows [latin, common, iNaturalist id, rank, parent row]: two genera in family 1, one under order 5
T = [
    ["Aus bus", "", 101, 0, 3],  # 0 species in genus Aus
    ["Aus cus", "", 102, 0, 3],  # 1 another species in Aus
    ["Dus eus", "", 201, 0, 4],  # 2 species in genus Dus, same family
    ["Aus", "", 11, 1, 5],  # 3 genus
    ["Dus", "", 12, 1, 5],  # 4 genus
    ["Fidae", "", 1, 2, 7],  # 5 family
    ["Gus hus", "", 301, 0, 8],  # 6 species in a genus of another family
    ["Oales", "", 5, 3, -1],  # 7 order
    ["Gus", "", 13, 1, 7],  # 8 genus, parent is the order (no family row)
]


def run(body: str):
    src = files("what_to_id").joinpath("map_assets")
    js = "\n".join((src / f).read_text() for f in ("map_taxa.js", "map_user.js"))
    script = (
        f"{js}\nvar T={json.dumps(T)},RANKS={json.dumps(RANKS)};\n"
        f"Promise.resolve((async function(){{{body}}})()).then(function(v){{"
        f"process.stdout.write(JSON.stringify(v));}});"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def kept(ancestors, own=101):
    """Rows the My taxa rule keeps when the user identified taxon ``own`` under ``ancestors``."""
    body = (
        f"var r=[{{taxon:{{id:{own},ancestor_ids:{json.dumps(ancestors)}}}}}];"
        "var ids=usrRanked(T,RANKS,r),m=usrMask(T,ids);"
        "return [ids,Array.from(m).map(function(v,i){return v?i:-1;})"
        ".filter(function(i){return i>=0;})];"
    )
    return run(body)


def test_parse_takes_a_number_or_a_login_and_nothing_else():
    got = run(
        "return ['1234',' kueda ','a b','','0','99999999999','x'.repeat(41),'ab_c-d']"
        ".map(usrParse);"
    )
    assert got == [
        {"id": 1234},
        {"login": "kueda"},
        None,
        None,
        None,
        None,
        None,
        {"login": "ab_c-d"},
    ]


def test_a_species_identified_keeps_its_genus_and_not_the_family_or_siblings_genera():
    ids, rows = kept([5, 11, 101])  # the order is neither genus nor family
    assert ids == [11, 101]
    assert rows == [0, 1, 3]  # both Aus species and the genus-level record, not Dus or the family


def test_a_family_in_the_ancestors_keeps_family_level_records_and_every_genus_below():
    ids, rows = kept([5, 1, 11, 101])
    assert ids == [1, 11, 101]
    assert rows == [0, 1, 2, 3, 4, 5]  # Aus and Dus species, both genera and the family record
    assert 6 not in rows and 8 not in rows  # the other family's rows stay out


def test_a_taxon_without_ancestor_ids_still_keeps_itself_and_a_missing_one_keeps_nothing():
    assert kept([], own=201)[1] == [2]
    assert run("return Array.from(usrMask(T,usrRanked(T,RANKS,[]))).some(Boolean);") is False
    assert run("return usrRanked(T,RANKS,[{taxon:{}}]);") == []


def test_ranks_the_pool_lacks_are_not_matched():
    # genus 999 is not a pool row, so only the species itself and the pool's family count
    ids, _ = kept([1, 999, 101])
    assert ids == [1, 101]


def pages(total, per, cap):
    return run(
        f"var calls=[];function get(p){{calls.push(p);"
        f"var n=Math.min({total},p*{per})-(p-1)*{per};"
        f"return Promise.resolve({{total_results:{total},"
        "results:Array.from({length:Math.max(0,n)},function(){return {};})});}"
        f"var r=await usrPages(get,{cap},{per});return [r.items.length,r.capped,calls];"
    )


def test_paging_stops_at_the_cap_and_says_so():
    assert pages(100, 10, 3) == [30, True, [1, 2, 3]]


def test_paging_that_fits_is_not_capped_even_on_the_last_allowed_page():
    assert pages(30, 10, 3) == [30, False, [1, 2, 3]]
    assert pages(25, 10, 5) == [25, False, [1, 2, 3]]
    assert pages(0, 10, 5) == [0, False, [1]]


def test_the_real_caps_are_five_pages_of_500_taxa_and_25_of_200_ids():
    assert run("return [USR_CAP.taxa*USR_PER.taxa,USR_CAP.unid*USR_PER.unid];") == [2500, 5000]
