import gzip
import json
import re
import shutil
import subprocess
from importlib.resources import files

import numpy as np
import pandas as pd
import pytest
import requests

from what_to_id.inat import BC_PLACE_ID, PER_PAGE
from what_to_id.map_projects import (
    PROJECTS,
    PROJECTS_NAME,
    decode_projects,
    encode_projects,
    list_ids,
    load_projects,
    main,
    project_meta,
    update_projects,
)
from what_to_id.page_map import MAP_NAME, write_map

from .conftest import make_pool

A, B = PROJECTS[0]["id"], PROJECTS[1]["id"]
NOW = pd.Timestamp("2026-10-06T12:00:00Z")
ASSETS = files("what_to_id") / "map_assets"


class _Api:
    """A stand-in iNaturalist answering count and id-listing requests from per-project id sets.

    ``updated`` holds the ids an updated_since query returns; ``fail`` raises for that project.
    """

    def __init__(self, projects, updated=(), fail=None):
        self.projects = {k: sorted(v) for k, v in projects.items()}
        self.updated, self.fail, self.calls = set(updated), fail, []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        if params["project_id"] == self.fail:
            raise requests.ConnectionError("down")
        lo, hi = params.get("id_above", 0), params.get("id_below", 2**32)
        hit = [i for i in self.projects[params["project_id"]] if lo < i < hi]
        if "updated_since" in params:
            hit = [i for i in hit if i in self.updated]
        if params.get("order") == "desc":
            hit = hit[::-1]
        page = hit[: params["per_page"]] if params["per_page"] else []

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"total_results": len(hit), "results": [{"id": i} for i in page]}

        return R()


def _state(**ids):
    since = "2026-10-05T12:00:00Z"
    return {
        int(k[1:]): {"ids": np.array(v, dtype=np.int64), "since": since} for k, v in ids.items()
    }


def test_file_round_trips_and_is_deterministic():
    state = {
        A: {"ids": np.array([5, 300, 70000, 2**32 - 1, 300]), "since": "2026-10-06T00:00:00Z"},
        B: {"ids": np.array([], dtype=np.int64), "since": "2026-10-05T00:00:00Z"},
    }
    blob = encode_projects(state)
    back = decode_projects(blob)
    assert list(back) == [A, B]
    assert back[A]["ids"].tolist() == [5, 300, 70000, 2**32 - 1]
    assert back[B]["ids"].tolist() == [] and back[B]["since"] == "2026-10-05T00:00:00Z"
    assert blob == encode_projects(state)
    raw = gzip.decompress(blob)
    hn = int.from_bytes(raw[:4], "little")
    assert json.loads(raw[4 : 4 + hn])["projects"][0] == {
        "id": A,
        "n": 4,
        "since": "2026-10-06T00:00:00Z",
    }
    # steps 5, 295, 69700, ..., stored low bytes first
    assert raw[4 + hn : 4 + hn + 3] == bytes([5, 295 & 255, 69700 & 255])


def test_file_rejects_bad_sizes_and_ids():
    raw = gzip.decompress(encode_projects(_state(p1=[1, 2, 3])))
    with pytest.raises(ValueError, match="does not match"):
        decode_projects(gzip.compress(raw[:-1]))
    with pytest.raises(ValueError, match="too short"):
        decode_projects(gzip.compress(b"\x01"))
    with pytest.raises(ValueError, match="uint32"):
        encode_projects(_state(p1=[2**32]))


def test_list_ids_pages_up_by_id_above_with_only_ids():
    api = _Api({A: range(1, 2 * PER_PAGE + 51)})
    ids, used = list_ids({"project_id": A, "place_id": BC_PLACE_ID}, session=api, sleep=0)
    assert ids.tolist() == list(range(1, 2 * PER_PAGE + 51)) and used == 3
    assert [c["id_above"] for c in api.calls] == [0, PER_PAGE, 2 * PER_PAGE]
    assert all(c["only_id"] == "true" and c["order"] == "asc" for c in api.calls)
    with pytest.raises(RuntimeError, match="raise the cap"):
        list_ids({"project_id": A}, session=_Api({A: range(1, 1000)}), sleep=0, max_requests=2)


def test_first_run_lists_each_project_with_the_pool_query():
    api = _Api({A: [10, 20, 30], B: [20, 40]})
    state, stats = update_projects({}, [10, 20], d1="1900-01-01", now=NOW, session=api, sleep=0)
    assert state[A]["ids"].tolist() == [10, 20, 30] and state[B]["ids"].tolist() == [20, 40]
    assert state[A]["since"] == "2026-10-06T12:00:00Z"
    assert stats[A] == {"requests": 2, "listed": 3, "n": 3}
    p = api.calls[1]
    assert p["project_id"] == A and p["place_id"] == BC_PLACE_ID
    assert p["quality_grade"] == "needs_id" and p["photos"] == "true"


def test_first_run_skips_a_project_too_big_for_the_cap():
    api = _Api({A: range(1, 5 * PER_PAGE), B: [7]})
    state, stats = update_projects(
        {}, [], d1="1900-01-01", now=NOW, session=api, sleep=0, max_requests=3
    )
    assert list(state) == [B] and stats[A] == {"requests": 1}


def test_later_runs_drop_what_left_the_pool_add_updates_and_repair_the_rest():
    old = _state(**{f"p{A}": [10, 20, 30, 50], f"p{B}": [20]})
    # 30 left the pool; 60 is new and updated; 70 and 80 joined the project without an update
    # (members added later); 50 left the project while still needing an ID
    api = _Api({A: [10, 20, 60, 70, 80], B: [20]}, updated=[60])
    pool = [10, 20, 50, 60, 70, 80]
    state, stats = update_projects(old, pool, d1="1900-01-01", now=NOW, session=api, sleep=0)
    assert state[A]["ids"].tolist() == [10, 20, 60, 70, 80]
    assert state[A]["ids"].dtype == np.int64 and state[B]["ids"].dtype == np.int64
    assert stats[A]["left_pool"] == 1 and stats[A]["updated"] == 1
    assert stats[A]["gone"] == 1 and stats[A]["missing"] == 2
    assert stats[B] == {
        "requests": 2,
        "left_pool": 0,
        "updated": 0,
        "gone": 0,
        "missing": 0,
        "n": 1,
    }


def test_a_failed_project_keeps_its_list_and_cursor():
    old = _state(**{f"p{A}": [10, 30], f"p{B}": [20]})
    api = _Api({A: [10], B: [20]}, fail=A)
    state, _ = update_projects(old, [10, 20], d1="1900-01-01", now=NOW, session=api, sleep=0)
    assert state[A] == {"ids": state[A]["ids"], "since": "2026-10-05T12:00:00Z"}
    assert state[A]["ids"].tolist() == [10] and state[B]["since"] == "2026-10-06T12:00:00Z"


def test_updated_since_starts_before_the_last_run():
    old = _state(**{f"p{A}": [1], f"p{B}": [2]})
    api = _Api({A: [1], B: [2]})
    update_projects(old, [1, 2], d1="1900-01-01", now=NOW, session=api, sleep=0)
    assert {c["updated_since"] for c in api.calls if "updated_since" in c} == {
        "2026-10-05T11:00:00Z"
    }


def test_cli_seeds_then_updates_the_state(tmp_path, monkeypatch):
    import what_to_id.map_projects as mp

    api = _Api({A: [1000, 1001], B: [1002]})
    monkeypatch.setattr(mp, "make_session", lambda: api)
    monkeypatch.setattr(mp, "SLEEP", 0)
    make_pool(10).to_parquet(tmp_path / "pool.parquet", index=False)
    args = ["--pool", str(tmp_path / "pool.parquet"), "--state", str(tmp_path / PROJECTS_NAME)]
    assert main([*args, "--d1", "1900-01-01"]) == 0
    assert decode_projects((tmp_path / PROJECTS_NAME).read_bytes())[A]["ids"].tolist() == [
        1000,
        1001,
    ]
    assert main([*args, "--d1", "1900-01-01"]) == 0
    assert any("updated_since" in c for c in api.calls)


def _page_meta(html):
    return json.loads(re.search(r"var META=(\{.*?\});var BASEMAPS", html).group(1))


def test_map_carries_the_project_file_and_its_meta(tmp_path):
    pool = make_pool(20)
    path = tmp_path / "state.bin"
    path.write_bytes(encode_projects(_state(**{f"p{A}": [1000, 1005], f"p{B}": [1001]})))
    out = write_map(tmp_path / "site", pool, projects=path)
    assert (tmp_path / "site" / PROJECTS_NAME).read_bytes() == path.read_bytes()
    assert tmp_path / "site" / PROJECTS_NAME in out
    html = (tmp_path / "site" / MAP_NAME).read_text()
    meta = _page_meta(html)["projects"]
    assert meta["file"].startswith(PROJECTS_NAME + "?v=")
    assert meta["list"] == [
        {"id": A, "title": PROJECTS[0]["title"], "n": 2},
        {"id": B, "title": PROJECTS[1]["title"], "n": 1},
    ]
    assert "function projectFilter(" in html and 'id="projbox" hidden' in html


def test_map_ships_without_projects_when_the_file_is_missing_or_bad(tmp_path):
    pool = make_pool(20)
    assert load_projects(None) is None and load_projects(tmp_path / "nope.bin") is None
    (tmp_path / "bad.bin").write_bytes(b"not gzip")
    assert load_projects(tmp_path / "bad.bin") is None
    other = tmp_path / "other.bin"
    other.write_bytes(encode_projects(_state(p1=[1000])))
    assert project_meta(other.read_bytes()) is None
    for p in (tmp_path / "nope.bin", tmp_path / "bad.bin", other):
        write_map(tmp_path / "site", pool, projects=p)
        assert "projects" not in _page_meta((tmp_path / "site" / MAP_NAME).read_text())
        assert not (tmp_path / "site" / PROJECTS_NAME).exists()


# The page's project code, run in node: the file decoder, the bitmask and the Identify link.
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _node(script):
    js = (ASSETS / "map_taxa.js").read_text() + "\n" + (ASSETS / "map_projects.js").read_text()
    run = subprocess.run(
        ["node", "-e", js + "\n" + script], capture_output=True, text=True, check=True
    )
    return json.loads(run.stdout)


@needs_node
def test_page_decodes_the_file_and_marks_records():
    state = _state(**{f"p{A}": [5, 300, 70000, 2**32 - 1], f"p{B}": [300, 400]})
    raw = gzip.decompress(encode_projects(state))
    got = _node(
        f"var b=Buffer.from('{raw.hex()}','hex'),"
        "buf=b.buffer.slice(b.byteOffset,b.byteOffset+b.length);"
        f"var L=projDecode(buf,[{{id:{B}}},{{id:{A}}},{{id:1}}]);"
        # two shards, each sorted by id
        "var id=new Uint32Array([300,400,4294967295,5,70000,71000]),m=new Uint8Array(6);"
        "projMask(id,L,m,0,6);"
        "var l=L.map(function(a){return a&&Array.from(a);});"
        "console.log(JSON.stringify({l:l,m:Array.from(m)}));"
    )
    assert got["l"] == [[300, 400], [5, 300, 70000, 2**32 - 1], None]
    assert got["m"] == [3, 1, 2, 2, 2, 0]


@needs_node
def test_identify_link_is_exact_for_or_and_not_and_wider_for_and():
    lst = [{"id": A, "title": "A", "n": 500}, {"id": B, "title": "B", "n": 60}]
    picks = {
        "or": ([{"k": 0, "not": False}, {"k": 1, "not": False}], True),
        "and": ([{"k": 0, "not": False}, {"k": 1, "not": False}], False),
        "a_not_b": ([{"k": 0, "not": False}, {"k": 1, "not": True}], True),
        "not_both": ([{"k": 0, "not": True}, {"k": 1, "not": True}], False),
    }
    script = (
        f"var list={json.dumps(lst)},picks={json.dumps(picks)},out={{}};"
        "for(var k in picks){var p=projParams(picks[k][0],picks[k][1],list);"
        "out[k]={exact:p.exact,url:TX.identifyUrl({groups:[],all:3,months:[]},"
        "{w:-130,s:48,e:-120,n:55},{place_id:7085,max_url:8000,imprecise_m:1000},p.q).url};}"
        "console.log(JSON.stringify(out));"
    )
    got = _node(script)

    def q(k):
        return dict(re.findall(r"[?&]([^=&]+)=([^&]*)", got[k]["url"].replace("%2C", ",")))

    assert got["or"]["exact"] and q("or")["project_id"] == f"{A},{B}"
    assert "not_in_project" not in q("or")
    assert got["a_not_b"]["exact"] and q("a_not_b")["project_id"] == str(A)
    assert q("a_not_b")["not_in_project"] == str(B)
    assert got["not_both"]["exact"] and q("not_both")["not_in_project"] == f"{A},{B}"
    assert "project_id" not in q("not_both")
    # AND: iNaturalist cannot require both, so the link opens the smaller project
    assert not got["and"]["exact"] and q("and")["project_id"] == str(B)
    assert q("and")["place_id"] == "7085" and q("and")["quality_grade"] == "needs_id"
    assert q("and")["swlat"] == "48.0000"


@needs_node
def test_page_keeps_records_by_the_picked_combination():
    got = _node(
        "var c={};[[0,0],[1,0],[2,0],[3,0]].forEach(function(r){var m=r[0];"
        "c[m]=[projKeep(m,3,0,true),projKeep(m,3,0,false),projKeep(m,1,2,true),projKeep(m,0,3,true)];});"
        "console.log(JSON.stringify(c));"
    )
    # columns: A or B, A and B, A not B, neither
    assert got == {
        "0": [False, False, False, True],
        "1": [True, False, True, False],
        "2": [True, False, False, False],
        "3": [True, True, False, False],
    }


@needs_node
def test_chips_read_as_selection_terms():
    lst = [{"id": A, "title": "A", "n": 500}, {"id": B, "title": "B", "n": 60}]
    got = _node(
        f"var list={json.dumps(lst)},m=new Uint8Array([0,1,2,3]),out={{}};"
        "[true,false].forEach(function(any){"
        "out[any]=projTerms([{k:0,not:false},{k:1,not:false},{k:1,not:true}],any,list,m)"
        ".map(function(t){return {dim:t.dim,kind:t.kind,id:t.id,label:t.label,ex:t.exclude,"
        "m:Array.from(t.mask()),inat:t.inat()};});});"
        "console.log(JSON.stringify(out));"
    )
    a, b, nb = got["true"]
    assert (a["dim"], a["kind"], a["id"], a["label"], a["ex"]) == (
        "project",
        "project",
        A,
        "A",
        False,
    )
    assert a["m"] == [0, 1, 0, 1] and b["m"] == [0, 0, 1, 1]
    assert a["inat"] == {"params": {"project_id": str(A)}, "exact": True}
    assert nb["ex"] and nb["inat"] == {"params": {"not_in_project": str(B)}, "exact": True}
    # match all: the included terms cannot be said exactly on iNaturalist, the excluded one can
    assert [t["inat"]["exact"] for t in got["false"]] == [False, False, True]
