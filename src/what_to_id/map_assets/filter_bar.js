// The filter bar: the date histograms and controls, the group, month and show-only chips, the taxa
// picker and the selection bar. It reads the viewer's choices from S and everything else through
// the options, so the map and the split view can both host it. The host passes
//   S, META, mf (MapFilter(META)), nf (a number format), pj (map_projects.js), sel() (the selection as hash terms),
//   P() (the records), taxa() (the taxa rows or null), area() (the area filter), cum() and tc() (the day
//   and month counts behind the histograms, see recount in map.js),
//   search() (rebuilds the taxon filter after a pick), refilter() (a filter changed, recount),
//   render() (only the dates changed), drag() (the dates moved mid-brush: move only the GPU range), extra() (more selection bar items), reset() (after Reset all),
//   pass() (the records in view, the group filter left out) and inside(row) for the groups list's ranks.
// It returns what the host calls back: update() after a recount, draw() on resize, show*() after the
// host changes S, oldQuery(), total() and pct() for the header's share line, and groups (group_list.js).
// Needs map_taxa.js (TX), map_chips.js (CH), map_hist.js, map_time.js and group_list.js.
var FilterBar=(function(){
'use strict';
function $(id){return document.getElementById(id);}
function FilterBar(o){
var S=o.S,META=o.META,MF=o.mf,nf=o.nf,PJ=o.pj,refilter=o.refilter,render=o.render,
  LAST=MF.LAST,MONTH=MF.MONTH,iso=MF.iso,dayOf=MF.dayOf,clamp=MF.clamp;

// The date histograms (map_hist.js).
var MH=MapHist({S:S,META:META,mf:MF,nf:nf,over:$('over'),hist:$('hist'),htip:$('htip'),unit:$('unit'),cum:o.cum,tc:o.tc,
  render:render,drag:o.drag}),draw=MH.draw,total=MH.total,pct=MH.pct;

// Controls (map_time.js).
var TM=MapTime({S:S,mf:MF,render:render,refilter:refilter,byObs:$('byObs'),byUp:$('byUp'),presets:$('presets'),from:$('from'),to:$('to'),
  months:$('months'),mclear:$('mclear')}),showMonths=TM.showMonths;
function chip(box,label,pressed,onclick,title){var b=document.createElement('button');
  b.type='button';b.textContent=label;if(title)b.title=title;
  b.setAttribute('aria-pressed',String(pressed));
  b.onclick=function(){b.setAttribute('aria-pressed',String(onclick()));refilter();};
  $(box).appendChild(b);return b;}
// Like the months: with no group picked every group shows. The list's rows pick and leave out groups.
var GL=GroupList({box:$('groups'),bar:$('gbar'),keep:$('gkeep'),mine:$('mine'),S:S,META:META,nf:nf,changed:refilter,taxa:o.taxa,P:o.P,
  pass:o.pass,inside:o.inside,pk:function(){return PK;}}),showGroups=GL.show;
$('gall').onclick=function(){S.groups={};showGroups();refilter();};
// Introduced and threatened can be left out too. The location accuracy is one choice of several: the known
// classes run from any to within 10 m, so one slider, and unknown, off that scale, is a toggle on its label
// line; a pool without accuracy has neither.
var ONLYDEF=MF.ONLYDEF,
  ONLY=ONLYDEF.map(function(d){return CH.chip($('flags'),d[0],d[1],function(){return S.only;},true,
    d[3],refilter);}),
  ACCDEF=META.flags.indexOf('accuracy')<0?[]:MF.ACCDEF,STOPS=['','known','1000','100','10'],AR=$('accr'),
  UB=ACCDEF.length?document.createElement('button'):null;
if(UB){UB.type='button';UB.className='link accu';UB.title=ACCDEF[0][2]+'. Click to pick.';$('acclbl').appendChild(UB);
  UB.onclick=function(){S.acc=S.acc==='unknown'?'':'unknown';showOnly();refilter();};
  AR.oninput=function(){S.acc=STOPS[+AR.value];showOnly();refilter();};}
function accLabel(){var d=ACCDEF.filter(function(a){return a[0]===S.acc;})[0];return d?d[1]:'';}
function showOnly(){ONLY.forEach(function(b,j){CH.show(b,ONLYDEF[j][1],S.only[ONLYDEF[j][0]]||'');});
  if(!UB)return;CH.show(UB,'Unknown only',S.acc==='unknown'?'inc':'');
  var k=STOPS.indexOf(S.acc);AR.value=Math.max(k,0);AR.setAttribute('aria-valuetext',accLabel()||'Any accuracy');
  [].forEach.call($('acc').querySelectorAll('.accticks span'),function(t,j){t.classList.toggle('on',j===k);});AR.title=k>0?ACCDEF[k][2]:'Any location accuracy';}
showOnly();
if(!ONLY.length&&!UB)$('flagbox').hidden=true;
if(!UB)$('acc').hidden=$('acclbl').hidden=true;
// Picked taxa: chips in the selection bar, one set with the groups. A shortcut picks, then leaves out, a set
// of taxa, and shows only once the taxa file carries the whole tree.
function counts(){var p=o.P();return TX.counts(o.taxa(),p.tax,p.n);}
var PK=TX.picker({input:$('q'),list:$('sugg'),msg:$('qn'),picks:S.picks,ranks:META.ranks,
  nf:nf,taxa:o.taxa,counts:counts,
  onChange:function(){o.search();showClades();refilter();}});
var PRE=META.presets||[],CB=PRE.map(function(c){return chip('clades',c[0],false,function(){
  S.split=S.split.filter(function(n){return n!==c[0];});PK.cycle(c[1]);return PK.state(c[1])!=='';},c[2]);});
$('cladebox').hidden=!CB.length;
function showClades(){CB.forEach(function(b,k){CH.show(b,PRE[k][0],PK.state(PRE[k][1]));});}
showClades();
// An old link's q, names to keep, becomes picks once the taxa load. It kept those names within the
// groups; when every name lies inside the groups the picks alone say the same, so the groups clear.
function oldQuery(){if(!S.oldq)return;
  var T=o.taxa(),got=TX.resolve(T,S.oldq,counts()),gid=META.group_ids||{},
    gs=CH.picked(S.groups,META.groups,'inc').filter(function(g){return gid[g];}).map(function(g){return gid[g];});
  if(!got.length)$('q').value=S.oldq;S.oldq='';
  got.forEach(function(p){S.picks.push(p);});
  if(got.length&&!CH.any(S.groups)&&got.every(function(p){return p.not||TX.within(T,p.id,gs);}))
    S.groups={},showGroups();
  showClades();}
// The selection bar lists every chip, the dates too; its Clear all clears them, and Reset also the map view.
function redraw(){showGroups();showMonths();showOnly();refilter();}
function clearAll(){S.lo=0;S.hi=LAST;S.up=false;S.months=0;S.groups={};S.only={};S.acc='';S.user=S.umode='';S.umin=0;S.picks.length=0;S.split=[];$('q').value='';showClades();
  o.search();o.area().clear();PJ.reset();redraw();}
$('reset').onclick=function(){clearAll();o.reset();};
var BAR=CH.bar({box:$('selbar'),clear:clearAll,fallback:$('q')});
function items(){return CH.items({S:S,meta:META,terms:TX.terms({T:o.taxa(),picks:S.picks,groups:[],meta:META,n:0,split:S.split}),
  picker:PK,pj:PJ,months:MONTH,only:ONLYDEF,acc:{label:accLabel(),clear:function(){S.acc='';}},area:o.area(),mf:MF,redraw:redraw}).concat(o.extra());}
// Each folding section's summary counts its active chips, so a folded one still says what it holds.
function tally(){var n=function(st){var c=0;for(var k in st)if(st[k])c++;return c;},e;
  [['ntaxa',S.picks.length],['nonly',n(S.only)+(S.acc?1:0)],['nproj',PJ.items().length],['ngroups',n(S.groups)]].forEach(function(d){e=$(d[0]);if(e)e.textContent=d[1]?String(d[1]):'';});}
// Groups, Taxa and Show only start open, Projects folded; a section opens as the viewer
// last left it, and one a link filters on opens regardless (projects only know theirs once loaded).
var FOLD='wtid-map-fold';
(function(){var saved={};try{saved=JSON.parse(localStorage.getItem(FOLD))||{};}catch(e){}
  var open={grpsec:CH.any(S.groups),flagbox:CH.any(S.only)||!!S.acc,projbox:/(^|[#&])projects=/.test(location.hash),usrbox:!!S.user};
  [].forEach.call(document.querySelectorAll('details.sec'),function(d){
    if(open[d.id])d.open=true;else if(d.id in saved)d.open=saved[d.id];
    d.addEventListener('toggle',function(){saved[d.id]=d.open;
      try{localStorage.setItem(FOLD,JSON.stringify(saved));}catch(e){}});});})();

// Brings the controls up to date with S and the counts, after every recount.
function update(){
  TM.update();
  $('reset').hidden=!o.sel().length;  // nothing to reset until a filter is set
  BAR.set(items());tally();draw();
}
return {update:update,draw:draw,total:total,pct:pct,oldQuery:oldQuery,groups:GL,
  showGroups:showGroups,showMonths:showMonths,showOnly:showOnly,showClades:showClades};
}
return FilterBar;
})();
