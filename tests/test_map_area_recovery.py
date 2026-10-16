"""Shared-area recovery runs the actual controller and main Identify binding in Node."""

import json
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse

import pytest

from what_to_id.map_parks import encode_rings
from what_to_id.page_map import _ASSETS

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def case_script(raw, count=3):
    source = (_ASSETS / "map.js").read_text()
    binding = source[source.index("function link(){") : source.index("// The filter extension")]
    script = r"""
const events = {}, nodes = new Map();
class Element {
  constructor(){this.hidden=false;this.textContent='';this.style={};this.attrs={};
    this.nodes=new Map();this.lastChild={};}
  querySelector(key){if(!this.nodes.has(key))this.nodes.set(key,new Element());
    return this.nodes.get(key);}
  appendChild(){} append(){} setAttribute(k,v){this.attrs[k]=String(v);}
  removeAttribute(k){delete this.attrs[k];} getAttribute(k){return this.attrs[k]??null;}
  addEventListener(){} contains(){return false;}
  set href(value){this.attrs.href=String(value);} get href(){return this.attrs.href;}
}
const document={documentElement:{},createElement:()=>new Element(),addEventListener(){}};
const getComputedStyle=()=>({getPropertyValue:()=>''});
const addEventListener=(key,fn)=>(events[key]??=[]).push(fn);
const location={hash:'#area='+encodeURIComponent(RAW)};
const $=key=>{if(!nodes.has(key))nodes.set(key,new Element());return nodes.get(key);};
"""
    script = f"const RAW={json.dumps(raw)}, COUNT={count};\n" + script
    script += "\n".join(
        (_ASSETS / name).read_text()
        for name in ["identify_links.js", "map_taxa.js", "map_step.js", "map_area.js"]
    )
    script += r"""
var P={n:COUNT,id:Array.from({length:COUNT},(_,i)=>101+i),
  pos:COUNT===3?[.5,.5,2,2,3,3]:Array(COUNT*2).fill(.5),
  obs:Array(COUNT).fill(0),up:Array(COUNT).fill(0)},KEEP=[];
var S={lo:0,hi:0,months:0,groups:{},only:{}},LAST=0;
const map={addControl(){},on(){},getBounds:()=>({getWest:()=>0,getSouth:()=>0,
  getEast:()=>4,getNorth:()=>4})};
const CH={groupLink:()=>({inc:[],taxa:[],not:[],groups:[],out:[]})},TF={ids:[],not:[]};
const META={groups:['Plantae'],place_id:7085,max_url:8000};
const PJ={params:()=>({}),inexact:()=>'',uncounted:()=>''},match=()=>true;
const iso=()=>'',gname=x=>x;
const step=IdStep({a:$('identify'),prev:$('idprev'),next:$('idnext'),build:'fixture',
  store:()=>{throw Error('off');}});
var AREA=MapArea({map,S,LAST,hash:RAW,P:()=>P,keep:()=>KEEP,change:()=>{},
  sel:()=>AREA.hash(),step});
"""
    script += binding
    script += r"""
function state(){const mask=AREA.mask(P.n);KEEP=P.id.map((_,i)=>mask?mask[i]:1);link();
  return {invalid:AREA.invalid?AREA.invalid():false,hash:AREA.hash(),
    mask:mask?Array.from(mask):null,
    href:$('identify').getAttribute('href'),disabled:$('identify').getAttribute('aria-disabled'),
    note:$('idnote').textContent,step:step.at()};}
const before=state();S.months=1;step.open();step.go(2);const rechecked=state();
AREA.clear();const cleared=state();
console.log(JSON.stringify({before,rechecked,cleared}));
"""
    return script


def run_case(raw, count=3):
    result = subprocess.run(["node"], input=case_script(raw, count), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "raw", ["ab!", "future&groups=Aves#tail%25", "AAgxTAAgxT_wTA~ab!", "ab!~AAgxTAAgxT_wTA"]
)
def test_unreadable_shared_area_retains_criterion_and_blocks_identify_until_clear(raw):
    result = run_case(raw)
    before, cleared = result["before"], result["cleared"]
    assert before["invalid"] is True
    assert before["mask"] is None  # Browseable is not a claim that the area is empty.
    assert before["href"] is None and before["disabled"] == "true"
    assert before["step"][1] == 0
    assert parse_qs(before["hash"])["area"] == [raw]
    assert result["rechecked"] == before
    assert "unavailable" in before["note"].lower()
    assert cleared["invalid"] is False and cleared["hash"] == ""
    assert cleared["href"].startswith("https://www.inaturalist.org/observations/identify?")
    assert cleared["disabled"] is None


@pytest.mark.parametrize(
    "raw,count,expected_ids",
    [
        (encode_rings([[0, 0, 1, 0, 1, 1, 0, 1]]), 3, [101]),
        (encode_rings([[10, 10, 11, 10, 11, 11, 10, 11]]), 3, None),
        (encode_rings([[0, 0, 1, 0, 1, 1, 0, 1]]), 10001, None),
    ],
)
def test_valid_legacy_area_empty_matches_and_large_fallback_are_unchanged(raw, count, expected_ids):
    before = run_case(raw, count)["before"]
    assert before["invalid"] is False and before["disabled"] is None
    query = parse_qs(urlparse(before["href"]).query)
    if expected_ids is not None:
        assert query["id"] == [",".join(map(str, expected_ids))]
    else:
        assert "id" not in query and "swlat" in query
    assert before["mask"] == ([1, 0, 0] if expected_ids else [1 if count > 3 else 0] * count)


def recovery_html():
    """Real DOM fixture, with only map rendering and the immutable point pool stubbed."""
    source = (_ASSETS / "map.js").read_text()
    binding = source[source.index("function link(){") : source.index("// The filter extension")]
    guard = source[source.index("// Guard activation") : source.index("// Zoomed out,")]
    modules = "\n".join(
        (_ASSETS / name).read_text()
        for name in ["identify_links.js", "map_taxa.js", "map_step.js", "map_area.js"]
    )
    return (
        '<!doctype html><meta charset="utf-8"><a id="identify" target="_blank">Identify these</a>'
        '<button id="idprev" hidden>Previous batch</button>'
        '<button id="idnext" hidden>Next batch</button><p id="idnote" hidden></p>'
        '<output id="count"></output><script>'
        + modules
        + r"""
const $=id=>document.getElementById(id);
var P={n:3,id:[101,102,103],pos:[.5,.5,2,2,3,3],obs:[0,0,0],up:[0,0,0]},KEEP=[];
var S={lo:0,hi:0,months:0,groups:{},only:{}},LAST=0;
const map={addControl:c=>document.body.append(c.onAdd()),on(){},fitBounds(){},
  getCanvas:()=>({style:{}}),doubleClickZoom:{enable(){},disable(){}},
  getBounds:()=>({getWest:()=>0,getSouth:()=>0,getEast:()=>4,getNorth:()=>4})};
const CH={groupLink:()=>({inc:[],taxa:[],not:[],groups:[],out:[]})},TF={ids:[],not:[]};
const META={groups:['Plantae'],place_id:7085,max_url:8000};
const PJ={params:()=>({}),inexact:()=>'',uncounted:()=>''},match=()=>true;
const iso=()=>'',gname=x=>x;
var AREA=MapArea({map,S,LAST,hash:new URLSearchParams(location.hash.slice(1)).get('area')||'',
  park:new URLSearchParams(location.hash.slice(1)).get('park')||'',
  bcpark:new URLSearchParams(location.hash.slice(1)).get('bcpark')||'',
  P:()=>P,keep:()=>KEEP,change:refilter,sel:()=>AREA.hash(),
  step:IdStep({a:$('identify'),prev:$('idprev'),next:$('idnext'),build:'fixture'}),
  get:()=>fetch('http://area-recovery/parks').then(response=>response.arrayBuffer())});
function refilter(){const mask=AREA.mask(P.n);KEEP=P.id.map((_,i)=>mask?mask[i]:1);
  $('count').textContent=AREA.invalid()?'Area unresolved':KEEP.reduce((a,b)=>a+b,0)+' results';
  link();history.replaceState(null,'','#'+AREA.hash());}
"""
        + binding
        + guard
        + r"""
refilter();window.probe=()=>({invalid:AREA.invalid(),hash:AREA.hash(),mask:AREA.mask(P.n),
  href:$('identify').getAttribute('href'),disabled:$('identify').getAttribute('aria-disabled')});
</script>"""
    )
