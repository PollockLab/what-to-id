"""The map's chip click rule and selection bar (map_chips.js), run in node."""

import json
import shutil
import subprocess
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

GROUPS = ["Animalia", "Aves", "Insecta", "Plantae"]
META = {
    "place_id": 7085,
    "max_url": 8000,
    "imprecise_m": 1000,
    "groups": GROUPS,
    "names": {"Aves": "Birds", "Insecta": "Insects", "Plantae": "Plants"},
    "group_ids": {"Aves": 3, "Insecta": 47158, "Plantae": 47126},
}
BOX = {"w": -125, "s": 48, "e": -122, "n": 50}
# just enough DOM for chip() and bar(): elements with attributes, classes, children and clicks
DOM = r"""
function El(tag){this.tag=tag;this.children=[];this.attrs={};this.cls={};
  this.hidden=false;this._t='';
  var self=this;this.classList={toggle:function(c,on){self.cls[c]=!!on;}};}
Object.defineProperty(El.prototype,'textContent',{get:function(){return this._t;},
  set:function(v){this._t=String(v);if(v==='')this.children=[];}});
Object.defineProperty(El.prototype,'className',{set:function(v){var s=this;String(v).split(' ')
  .forEach(function(c){if(c)s.cls[c]=true;});}});
El.prototype.setAttribute=function(k,v){this.attrs[k]=String(v);};
El.prototype.appendChild=function(c){this.children.push(c);c.parent=this;return c;};
El.prototype.focus=function(){FOCUS=this;};
El.prototype.all=function(tag){var out=[];(function walk(e){e.children.forEach(function(c){
  if(c.tag===tag)out.push(c);walk(c);});})(this);return out;};
El.prototype.querySelector=function(tag){return this.all(tag)[0]||null;};
El.prototype.querySelectorAll=function(tag){return this.all(tag);};
var FOCUS=null,document={createElement:function(t){return new El(t);}};
"""


def run(body: str):
    src = files("what_to_id").joinpath("map_assets")
    js = (src / "map_taxa.js").read_text() + "\n" + (src / "map_chips.js").read_text()
    script = (
        f"{DOM}\n{js}\nvar META={json.dumps(META)},BOX={json.dumps(BOX)};\n"
        f"process.stdout.write(JSON.stringify((function(){{{body}}})()));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_click_cycle_picks_leaves_out_then_clears():
    three = run("var s='',o=[];for(var i=0;i<4;i++)o.push(s=CH.next(s,true));return o;")
    assert three == ["inc", "not", "", "inc"]
    two = run("var s='',o=[];for(var i=0;i<3;i++)o.push(s=CH.next(s,false));return o;")
    assert two == ["inc", "", "inc"]


def test_chip_button_steps_its_state_and_says_it():
    body = (
        "var box=new El('div'),st={},n=0,b=CH.chip(box,'Insecta','Insects',function(){return st;},"
        "true,'Insects',function(){n++;}),out=[];"
        "for(var i=0;i<3;i++){b.onclick();out.push([st.Insecta||'',b.attrs['aria-pressed'],"
        "b.attrs['aria-label'],b.textContent,!!b.cls.not]);}"
        "var two={},c=CH.chip(box,'exact','Exact location',function(){return two;},false,'',"
        "function(){});c.onclick();var a=two.exact;c.onclick();"
        "return {three:out,n:n,two:[a,two.exact||''],kids:box.children.length};"
    )
    got = run(body)
    assert got["three"] == [
        ["inc", "true", "Insects", "Insects", False],
        ["not", "true", "Not Insects", "not Insects", True],
        ["", "false", "Insects", "Insects", False],
    ]
    assert got["n"] == 3 and got["two"] == ["inc", ""] and got["kids"] == 2


def test_hash_round_trips_new_and_old_formats():
    keys = json.dumps(GROUPS)
    got = run(
        f"var k={keys},st=CH.read('Insecta,-Aves,Nope,-Insecta',k);"
        "return {st:st,back:CH.write(st,k),old:CH.read('Aves,Plantae',k),none:CH.read(null,k),"
        "only:CH.read('introduced,-threatened,-exact',['introduced','threatened','exact'],['exact']),"
        "again:CH.write(CH.read(CH.write(st,k),k),k)};"
    )
    # a repeated key keeps its first state
    assert got["st"] == {"Insecta": "inc", "Aves": "not"}
    # written in the groups' own order, a minus for left out
    assert got["back"] == "-Aves,Insecta" and got["again"] == got["back"]
    assert got["old"] == {"Aves": "inc", "Plantae": "inc"} and got["none"] == {}
    # exact location is two-state, so a minus on it is dropped
    assert got["only"] == {"introduced": "inc", "threatened": "not"}


def test_groups_pass_by_picks_less_left_out():
    keys = json.dumps(GROUPS)
    got = run(
        f"var k={keys};return [CH.groupPass({{}},k,false),"
        "CH.groupPass({Aves:'inc',Insecta:'inc'},k,false),"
        "CH.groupPass({Insecta:'not'},k,false),CH.groupPass({Aves:'inc',Insecta:'not'},k,true)];"
    )
    assert got == [
        [True, True, True, True],
        [False, True, True, False],
        [True, True, False, True],
        # with taxa included the picked groups go with them, so only the left-out one drops here
        [True, True, False, True],
    ]


def link(groups, taxa=(), only=None):
    """The Identify query for group states and included taxon ids, as map.js builds it."""
    body = (
        f"var gl=CH.groupLink({json.dumps(groups)},META.groups,META.group_ids,"
        f"{json.dumps(bool(taxa))}),t={json.dumps(list(taxa))};"
        "var st={groups:gl.groups,all:META.groups.length,up:false,d1:'',d2:'',months:[],"
        "taxa:gl.inc.length?null:t.concat(gl.taxa),not:[].concat(gl.not),"
        f"only:{json.dumps(only or {})}}};"
        "return {u:TX.identifyUrl(st,BOX,META).url,inc:gl.inc,out:gl.out};"
    )
    r = run(body)
    q = {k: v[0] for k, v in parse_qs(urlparse(r["u"]).query).items()}
    return q, r["inc"], r["out"]


def test_identify_leaves_a_group_out_by_its_taxon_id():
    q, inc, out = link({"Insecta": "not"})
    assert q["without_taxon_id"] == "47158" and "iconic_taxa" not in q and "taxon_id" not in q
    assert inc == [] and out == []
    q, _, _ = link({"Insecta": "inc"})
    assert q["iconic_taxa"] == "Insecta" and "without_taxon_id" not in q
    # with taxa included the picked group joins them and the left-out one is subtracted
    q, _, out = link({"Aves": "inc", "Insecta": "not"}, taxa=[311249])
    assert q["taxon_id"] == "311249,3" and q["without_taxon_id"] == "47158" and out == []


def test_identify_group_without_an_id_stays_exact_or_is_named():
    # no taxa: the link names every other group instead
    q, _, out = link({"Animalia": "not", "Insecta": "not"})
    assert q["iconic_taxa"] == "Aves,Plantae" and "without_taxon_id" not in q and out == []
    # with taxa it cannot, and says which group it keeps
    q, _, out = link({"Animalia": "not"}, taxa=[311249])
    assert out == ["Animalia"] and q["taxon_id"] == "311249" and "without_taxon_id" not in q


def test_identify_status_filters_pick_or_leave_out():
    q, _, _ = link({}, only={"introduced": "not", "threatened": "inc"})
    assert q["introduced"] == "false" and q["threatened"] == "true"
    q, _, _ = link({}, only={"threatened": "not", "exact": "inc"})
    assert q["threatened"] == "false" and "introduced" not in q
    assert q["obscuration"] == "none" and q["acc_below_or_unknown"] == "1001"
    # old states (true) still read as picked
    q, _, _ = link({}, only={"introduced": True})
    assert q["introduced"] == "true"


BAR = r"""
var S={picks:[{id:3,not:false},{id:4,not:true}],groups:{Insecta:'not',Aves:'inc'},months:5,
  only:{introduced:'not',exact:'inc'}},log=[],areaOn=true;
var pj={items:function(){return [{label:'in BC Rarities',not:true,
  remove:function(){log.push('pj');}}];}};
var area={term:function(){return areaOn?{label:'Garibaldi Park'}:null;},
  clear:function(){areaOn=false;log.push('area');}};
var T=[['Bryophyta','Mosses',3,2,-1],['Plantae','Plants',4,2,-1]];
function items(){return CH.items({S:S,meta:META,
  terms:TX.terms({T:T,picks:S.picks,groups:[],meta:META,n:0}),
  picker:{changed:function(){log.push('taxa');}},pj:pj,months:['January','February','March'],
  only:[['introduced','Introduced to BC'],['exact','Exact location']],area:area,
  redraw:function(){log.push('redraw');}});}
var box=new El('div');box.appendChild(new El('p')).appendChild(new El('button'));
box.appendChild(new El('ul'));
var q=new El('input'),cleared=0,B=CH.bar({box:box,clear:function(){cleared++;},fallback:q});
function xs(){return box.querySelectorAll('button').slice(1);}
function texts(){return box.querySelector('ul').children.map(function(li){
  return [li.children[0].textContent,!!li.cls.not,li.children[1].attrs['aria-label']];});}
"""


def test_selection_bar_lists_every_chip_and_removes_each():
    body = (
        BAR + "B.set(items());var first=texts(),hid=box.hidden;"
        # remove the group Insects (5th chip): its state goes and focus moves to the next ×
        "xs()[4].onclick();B.set(items());var afterGroup={groups:S.groups,focus:FOCUS===xs()[4]};"
        # the taxon chip removes its pick, the month chip its bit, the area chip the area
        "xs()[0].onclick();B.set(items());"
        "var m=texts().map(function(t){return t[0];}).indexOf('March');"
        "xs()[m].onclick();B.set(items());"
        "var a=texts().length-1;xs()[a].onclick();"
        "return {first:first,hid:hid,afterGroup:afterGroup,picks:S.picks,months:S.months,log:log};"
    )
    got = run(body)
    assert got["first"] == [
        ["Bryophyta", False, "Remove Bryophyta"],
        ["not Plantae", True, "Remove not Plantae"],
        ["not in BC Rarities", True, "Remove not in BC Rarities"],
        ["Birds", False, "Remove Birds"],
        ["not Insects", True, "Remove not Insects"],
        ["January", False, "Remove January"],
        ["March", False, "Remove March"],
        ["not Introduced to BC", True, "Remove not Introduced to BC"],
        ["Exact location", False, "Remove Exact location"],
        ["Garibaldi Park", False, "Remove Garibaldi Park"],
    ]
    assert got["hid"] is False
    assert got["afterGroup"] == {"groups": {"Aves": "inc"}, "focus": True}
    assert got["picks"] == [{"id": 4, "not": True}] and got["months"] == 1
    assert got["log"] == ["redraw", "taxa", "redraw", "area"]


def test_selection_bar_clear_all_and_empty():
    body = (
        BAR + "B.set(items());box.querySelector('button').onclick();"
        "S={picks:[],groups:{},months:0,only:{}};areaOn=false;pj.items=function(){return [];};"
        "B.set(items());"
        "return {cleared:cleared,hidden:box.hidden,n:texts().length,focus:FOCUS===q};"
    )
    assert run(body) == {"cleared": 1, "hidden": True, "n": 0, "focus": True}
