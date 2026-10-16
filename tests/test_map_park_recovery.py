"""The intended park OR set survives pending, failed and partial restoration."""

import json
import shutil
import subprocess
from urllib.parse import parse_qs

import pytest

from .test_map_area_recovery import case_script

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def park_case(park="", bcpark="", replies=None, list_state="empty"):
    script = case_script("")
    script = script[: script.index("const before=state();")]
    script = (
        f"const PARK={json.dumps(park)}, BCPARK={json.dumps(bcpark)},"
        f" REPLIES={json.dumps(replies or {})}, LIST={json.dumps(list_state)};\n"
        + r"""
var areaBox,requestedPlaces=[];
const setTimeout=fn=>{queueMicrotask(fn);return 1;};
const fetch=url=>{const id=url.split('/').pop(),kind=REPLIES[id]||'pending';
  requestedPlaces.push(id);
  if(kind==='pending')return new Promise(()=>{});
  if(kind==='reject')return Promise.reject(Error('fixture rejection'));
  const geometry=kind==='missing'?{}:{geometry_geojson:{type:'Polygon',
    coordinates:[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}};
  return Promise.resolve({ok:true,
    json:()=>({results:[{id:Number(id),name:'Park '+id,...geometry}]})});};
function parkList(){if(LIST==='reject')return Promise.reject(Error('fixture list failure'));
  if(LIST==='pending')return new Promise(()=>{});
  const data=JSON.stringify({kinds:['Park'],parks:[]});
  return Promise.resolve(new TextEncoder().encode(data).buffer);}
"""
        + script
    )
    script = script.replace(
        "const map={addControl(){},", "const map={addControl:c=>{areaBox=c.onAdd();},"
    )
    script = script.replace(
        "hash:RAW,P:()=>P", "hash:RAW,park:PARK,bcpark:BCPARK,get:parkList,P:()=>P"
    )
    script += r"""
(async()=>{const pending=state();for(let i=0;i<80;i++)await Promise.resolve();
  const settled=state();AREA.clear();const cleared=state();
  console.log(JSON.stringify({pending,settled,cleared,requestedPlaces}));})();
"""
    result = subprocess.run(["node"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("reply", ["pending", "reject", "missing"])
def test_place_pending_failure_and_missing_geometry_keep_identity_and_block_identify(reply):
    result = park_case(park="111", replies={"111": reply})
    for state in [result["pending"], result["settled"]]:
        assert state["invalid"] is True
        assert state["href"] is None and state["disabled"] == "true"
        assert parse_qs(state["hash"])["park"] == ["111"]
        assert state["mask"] is None
    assert result["cleared"]["invalid"] is False
    assert result["cleared"]["href"].startswith("https://www.inaturalist.org/")


@pytest.mark.parametrize("list_state", ["pending", "reject", "empty"])
def test_bc_list_pending_failure_and_unknown_key_remain_requested(list_state):
    result = park_case(bcpark="0096", list_state=list_state)
    for state in [result["pending"], result["settled"]]:
        assert state["invalid"] is True and state["href"] is None
        assert parse_qs(state["hash"])["bcpark"] == ["0096"]


@pytest.mark.parametrize(
    "replies", [{"111": "ready", "222": "missing"}, {"111": "missing", "222": "ready"}]
)
def test_partial_or_restoration_never_becomes_an_exact_subset(replies):
    result = park_case(park="111,222", replies=replies)
    state = result["settled"]
    assert state["invalid"] is True and state["href"] is None
    assert parse_qs(state["hash"])["park"] == ["111,222"]
    assert state["mask"] == [1, 0, 0]


def test_all_places_restored_reenable_the_original_or_query():
    result = park_case(park="111,222", replies={"111": "ready", "222": "ready"})
    assert result["pending"]["href"] is None
    assert result["settled"]["invalid"] is False
    assert parse_qs(result["settled"]["hash"])["park"] == ["111,222"]
    assert "place_id=111%2C222" in result["settled"]["href"]


def test_loaded_legacy_place_does_not_hide_an_unknown_bc_park():
    result = park_case(park="111", bcpark="0096", replies={"111": "ready"})
    state = result["settled"]
    assert state["invalid"] is True and state["href"] is None
    assert parse_qs(state["hash"]) == {"park": ["111"], "bcpark": ["0096"]}
    assert state["mask"] == [1, 0, 0]


@pytest.mark.parametrize(
    "token",
    ["ab!", " ab! ", "-111", "0", "111.5", "Infinity", "9007199254740993", "bad&taxa=3#%25"],
)
@pytest.mark.parametrize("mixed", [False, True])
def test_invalid_place_tokens_are_preserved_without_requests(token, mixed):
    raw = "111," + token if mixed else token
    result = park_case(park=raw, replies={"111": "ready"})
    state = result["settled"]
    assert state["invalid"] is True and state["href"] is None
    assert parse_qs(state["hash"]) == {"park": [raw]}
    assert result["requestedPlaces"] == (["111"] if mixed else [])
    assert state["mask"] == ([1, 0, 0] if mixed else None)
    assert result["cleared"]["invalid"] is False
    assert result["cleared"]["hash"] == ""


@pytest.mark.parametrize("token", ["111", "111.0", "1.11e2", "0x6f", " 111 "])
def test_safe_integer_place_interpretations_keep_normalization(token):
    result = park_case(park=token, replies={"111": "ready"})
    assert result["requestedPlaces"] == ["111"]
    assert result["settled"]["invalid"] is False
    assert result["settled"]["hash"] == "park=111"
    assert "place_id=111" in result["settled"]["href"]


def test_largest_safe_integer_place_is_not_rejected_or_rounded():
    token = "9007199254740991"
    result = park_case(park=token, replies={token: "ready"})
    assert result["requestedPlaces"] == [token]
    assert result["settled"]["invalid"] is False
    assert result["settled"]["hash"] == "park=" + token
