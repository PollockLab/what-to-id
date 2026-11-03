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


def genera(results, min_=50):
    """The [genus id, count] pairs the My taxa rule keeps for species_counts ``results``."""
    return run(f"return usrGenera(T,RANKS,{json.dumps(results)},{min_});")


def rows(ids):
    """The pool rows the mask keeps for genera ``ids``."""
    body = (
        f"var m=usrMask(T,{json.dumps(ids)});"
        "return Array.from(m).map((v,i)=>v?i:-1).filter(i=>i>=0);"
    )
    return run(body)


def res(taxon, count, ancestors):
    return {"count": count, "taxon": {"id": taxon, "ancestor_ids": ancestors}}


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


def test_counts_are_summed_per_genus_and_kept_at_the_threshold():
    r = [
        res(101, 30, [5, 1, 11, 101]),
        res(102, 25, [5, 1, 11, 102]),  # Aus: 55
        res(201, 49, [5, 1, 12, 201]),  # Dus: 49, one short
        res(301, 50, [7, 13, 301]),  # Gus: exactly 50
    ]
    assert genera(r) == [[11, 55], [13, 50]]
    assert genera(r, 20) == [[11, 55], [12, 49], [13, 50]]
    assert genera(r, 100) == []


def test_a_genus_level_record_counts_for_its_genus():
    assert genera([res(11, 50, [5, 1, 11])]) == [[11, 50]]


def test_there_is_no_family_rollup_and_the_taxon_itself_is_not_kept():
    # a family-level record, an order-level one, and a species whose genus the pool lacks
    r = [res(1, 500, [5, 1]), res(5, 500, [5]), res(555, 500, [5, 1, 999, 555])]
    assert genera(r) == []
    assert rows([11]) == [0, 1, 3]  # both Aus species and the genus row, not Dus, the family or Gus


def test_missing_taxa_and_counts_keep_nothing():
    assert genera([]) == [] and genera([{"taxon": {}}]) == [] and genera([{"count": 99}]) == []
    assert run("return Array.from(usrMask(T,[])).some(Boolean);") is False


def keep(results, min_):
    return run(f"return usrKeep(T,RANKS,{json.dumps(results)},{min_});")


def test_a_threshold_that_keeps_nothing_falls_back_to_the_highest_lower_one_that_keeps_a_genus():
    r = [res(101, 30, [5, 1, 11, 101]), res(201, 6, [5, 1, 12, 201])]  # Aus 30, Dus 6
    assert keep(r, 50) == {"genera": [[11, 30]], "used": 20}
    assert keep(r, 100) == {"genera": [[11, 30]], "used": 20}
    assert keep(r, 20) == {"genera": [[11, 30]], "used": 20}  # kept as chosen, no fallback
    assert keep([res(201, 6, [5, 1, 12, 201])], 100) == {"genera": [[12, 6]], "used": 5}


def test_when_even_five_keeps_nothing_nothing_is_kept():
    assert keep([res(201, 4, [5, 1, 12, 201])], 50) == {"genera": [], "used": 0}
    assert keep([], 5) == {"genera": [], "used": 0}


def fit(ids, tax, budget):
    return run(f"return usrFit(T,RANKS,{json.dumps(ids)},{json.dumps(tax)},{budget});")


def test_every_genus_goes_to_identify_when_the_ids_fit():
    assert fit([11, 12, 13], [], 8) == {"ids": [11, 12, 13], "cut": 0}  # "11,12,13" is 8 characters
    assert fit([], [], 8) == {"ids": [], "cut": 0}


def test_over_the_budget_the_genera_with_the_most_records_to_identify_stay():
    tax = [0, 1, 3, 2, 6, 6, 6, 8, 7, 99]  # Aus x3, Dus x1, Gus x4, then an order row and a bad one
    got = fit([11, 12, 13], tax, 5)
    assert got["cut"] == 1 and sorted(got["ids"]) == [11, 13] and 12 not in got["ids"]
    assert fit([11, 12, 13], tax, 1) == {"ids": [], "cut": 3}


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
