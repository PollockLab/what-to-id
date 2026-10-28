// The filter bar: the date histograms and controls, the group, month and show-only chips, the taxa
// picker and the selection bar. It reads the viewer's choices from S and everything else through
// the options, so the map and the split view can both host it. The host passes
//   S, META, mf (MapFilter(META)), nf (a number format), pj (map_projects.js), sel() (the selection as hash terms),
//   P() (the records), taxa() (the taxa rows or null), area() (the area filter), cum() and tc() (the day
//   and month counts behind the histograms, see recount in map.js),
//   search() (rebuilds the taxon filter after a pick), refilter() (a filter changed, recount),
//   render() (only the dates changed), extra() (more selection bar items), reset() (after Reset all),
//   pass() (the records in view, the group filter left out) and inside(row) for the groups list's ranks.
// It returns what the host calls back: update() after a recount, draw() on resize, show*() after the
// host changes S, oldQuery(), total() and pct() for the header's share line, and groups (group_list.js).
// Needs map_taxa.js (TX), map_chips.js (CH) and group_list.js.
var FilterBar=(function(){
'use strict';
function $(id){return document.getElementById(id);}
var MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function FilterBar(o){
var S=o.S,META=o.META,MF=o.mf,nf=o.nf,PJ=o.pj,refilter=o.refilter,render=o.render,
  LAST=MF.LAST,DOM=MF.DOM,MOY=MF.MOY,DOW=MF.DOW,MI=MF.MI,MONTH=MF.MONTH,iso=MF.iso,dayOf=MF.dayOf,clamp=MF.clamp,
  css=getComputedStyle(document.documentElement);
function tok(n){return css.getPropertyValue(n).trim();}

// Two histograms. The overview has one bar per year over every date, on a log scale so that sparse
// early years still show. The detail shows the period in view, with bars sized to it (days, weeks,
// months or years) and scaled to its tallest bar. Picking a period in either zooms the detail to it.
var hist=$('hist'),over=$('over'),htip=$('htip'),VIEW=[0,LAST],HE=[0,LAST+1],HU='year',drag=null;
var OE=edges('year',0,LAST);
function count(a,b){var c=o.cum();return c[b+1]-c[a];}
// All records, needing an ID or Research Grade, for days a..b under the group and month filters.
// Null when the totals are off or the days do not span whole months (the last day ends a month).
function total(a,b){
  var TC=o.tc();
  if(!TC||!(a===0||DOM[a]===1)||!(b===LAST||DOM[b+1]===1))return null;
  return TC[MI[b]+1]-TC[MI[a]];
}
function pct(v,t){var f=Math.min(1,v/t)*100;return (f<1&&f>0?'<1':Math.round(f))+'%';}
function viewOf(){
  if(S.lo===0&&S.hi===LAST)return [META.hist0,LAST];
  var pad=Math.max(0,Math.ceil((31-(S.hi-S.lo+1))/2));
  return [clamp(S.lo-pad),clamp(S.hi+pad)];
}
function unitOf(v){var n=v[1]-v[0]+1;return n<=92?'day':n<=732?'week':n<=25*366?'month':'year';}
function edges(u,v0,v1){
  var e=[v0];
  for(var d=v0+1;d<=v1;d++)if(u==='day'||(u==='week'&&DOW[d]===0)||(DOM[d]===1&&
    (u==='month'||(u==='year'&&MOY[d]===0))))e.push(d);
  e.push(v1+1);return e;
}
function year(d){return iso(d).slice(0,4);}
function dlabel(d){return DOM[d]+' '+MON[MOY[d]]+' '+year(d);}
function binLabel(u,a){return u==='day'?dlabel(a):u==='week'?'Week of '+dlabel(a):
  u==='month'?MONTH[MOY[a]]+' '+year(a):year(a);}
function on(a,b){return b>=S.lo&&a<=S.hi&&(!S.months||b-a>40||!!(S.months>>MOY[a]&1)||
  !!(S.months>>MOY[b]&1));}
function tickLabel(u,e,k,step){
  var a=e[k],b=e[k+1]-1;
  if(u==='year'||u==='month')return DOM[a]===1&&MOY[a]===0&&year(a)%step===0?year(a):null;
  if(u==='week'){if(DOM[a]!==1&&MOY[a]===MOY[b])return null;var m=DOM[a]===1?a:b;
    return MON[MOY[m]]+(MOY[m]===0?' '+year(m):'');}
  return [1,8,15,22].indexOf(DOM[a])>=0?DOM[a]+' '+MON[MOY[a]]:null;
}
// With totals, the log overview adds a line for the share of each year still needing an ID (0 at
// the axis, 100% at the top), and the linear detail draws all records as faint bars behind. Years with
// fewer than SHARE_MIN records in all get no point, so a lone early record cannot draw a spike.
var SHARE_MIN=30;
function bars(cv,e,h,log,u){
  var w=cv.clientWidth,ax=13,r=devicePixelRatio||1,c=cv.getContext('2d'),n=e.length-1,sw=w/n;
  cv.width=w*r;cv.height=h*r;c.setTransform(r,0,0,r,0,0);c.clearRect(0,0,w,h);
  var v=[],tv=[],m=1,k,H=h-ax-2,bw=Math.max(sw-(sw>3?1:0),1);
  for(k=0;k<n;k++){v.push(count(e[k],e[k+1]-1));tv.push(total(e[k],e[k+1]-1));
    m=Math.max(m,v[k],log?0:tv[k]||0);}
  if(!log){c.fillStyle=tok('--total');
    for(k=0;k<n;k++)if(tv[k]){var ty=Math.max(1.5,tv[k]/m*H);
      c.globalAlpha=on(e[k],e[k+1]-1)?1:.25;c.fillRect(k*sw,h-ax-ty,bw,ty);}}
  c.fillStyle=tok('--bar');
  for(k=0;k<n;k++){
    var f=log?Math.log(1+v[k])/Math.log(1+m):v[k]/m,y=v[k]?Math.max(1.5,f*H):0;
    c.globalAlpha=on(e[k],e[k+1]-1)?1:.25;c.fillRect(k*sw,h-ax-y,bw,y);
  }
  if(log){c.globalAlpha=1;c.strokeStyle=c.fillStyle=tok('--share');c.lineWidth=1.5;c.beginPath();
    var pen=false;
    for(k=0;k<n;k++){if(!(tv[k]>=SHARE_MIN)){pen=false;continue;}
      var x=k*sw+bw/2,sy=h-ax-Math.min(1,v[k]/tv[k])*H;
      if(pen)c.lineTo(x,sy);else c.moveTo(x,sy);pen=true;}
    c.stroke();}
  c.globalAlpha=1;c.fillStyle=tok('--muted');c.font='10px system-ui,sans-serif';c.textAlign='left';
  var per=u==='year'?1:u==='month'?12:0,step=1,end=-1e9;
  if(per)step=[1,2,5,10,20,25,50].find(function(s){return s*per*sw>=32;})||100;
  for(k=0;k<n;k++){
    var t=tickLabel(u,e,k,step),x=k*sw;if(!t)continue;
    var tw=c.measureText(t).width;if(x<end+6||x+tw>w)continue;
    c.fillRect(x,h-ax,1,3);c.fillText(t,x+2,h-2);end=x+tw+2;
  }
}
function draw(){
  if(!drag)VIEW=viewOf();
  HU=unitOf(VIEW);HE=edges(HU,VIEW[0],VIEW[1]);
  bars(over,OE,34,true,'year');bars(hist,HE,64,false,HU);
  var cap='One bar per '+HU+', '+dlabel(VIEW[0])+' to '+dlabel(VIEW[1])+'.'+
    (o.tc()&&(HU==='day'||HU==='week')?' Faint all-record bars show only with bars per month or year.':'');
  $('unit').textContent=cap;hist.setAttribute('aria-label',cap+' Drag to pick a period.');
}
function binAt(cv,e,x){var n=e.length-1;return Math.max(0,Math.min(n-1,Math.floor(x/(cv.clientWidth/n))));}
function brush(cv,get){
  var st=null;
  cv.addEventListener('pointerdown',function(ev){cv.setPointerCapture(ev.pointerId);
    st={x:ev.offsetX,moved:false,e:get().e};if(cv===hist)drag=st;});
  cv.addEventListener('pointermove',function(ev){
    var g=get(),e=st?st.e:g.e,k=binAt(cv,e,ev.offsetX);
    var nk=count(e[k],e[k+1]-1),tk=total(e[k],e[k+1]-1);
    htip.textContent=binLabel(g.u,e[k])+': '+nf.format(nk)+(tk?' of '+nf.format(tk)+' still need an ID ('+
      pct(nk,tk)+')':'');
    // Clamp by the tip's own width so it never pokes past the chart: overflow there adds a page
    // scrollbar, which shrinks the map and shifts its view.
    htip.hidden=false;htip.style.top=(cv.offsetTop-4)+'px';
    var hw=htip.offsetWidth/2;
    htip.style.left=Math.max(hw,Math.min(ev.offsetX,cv.clientWidth-hw))+'px';
    if(!st)return;
    if(Math.abs(ev.offsetX-st.x)>3)st.moved=true;
    if(st.moved){var a=binAt(cv,e,Math.min(st.x,ev.offsetX)),z=binAt(cv,e,Math.max(st.x,ev.offsetX));
      S.lo=e[a];S.hi=e[z+1]-1;render();}
  });
  cv.addEventListener('pointerup',function(ev){
    if(st&&!st.moved){var k=binAt(cv,st.e,ev.offsetX);S.lo=st.e[k];S.hi=st.e[k+1]-1;}
    st=null;drag=null;htip.hidden=true;render();});
  cv.addEventListener('pointerleave',function(){htip.hidden=true;});
  cv.addEventListener('dblclick',function(){S.lo=0;S.hi=LAST;render();});
}
brush(over,function(){return {e:OE,u:'year'};});
brush(hist,function(){return {e:HE,u:HU};});

// Controls.
var PRESETS=[
  ['Last 30 days',function(){return [clamp(LAST-29),LAST];}],
  ['Last 12 months',function(){return [clamp(LAST-364),LAST];}],
  ['This year',function(){return [clamp(dayOf(iso(LAST).slice(0,4)+'-01-01')),LAST];}],
  ['All dates',function(){return [0,LAST];}]
].map(function(p){var b=document.createElement('button');b.type='button';b.textContent=p[0];
  b.onclick=function(){var r=p[1]();S.lo=r[0];S.hi=r[1];render();};$('presets').appendChild(b);
  return {el:b,range:p[1]};});
$('from').min=$('to').min=iso(0);$('from').max=$('to').max=iso(LAST);
$('from').onchange=function(){var d=dayOf(this.value);if(d!=null){S.lo=clamp(d);
  if(S.lo>S.hi)S.hi=S.lo;render();}};
$('to').onchange=function(){var d=dayOf(this.value);if(d!=null){S.hi=clamp(d);
  if(S.hi<S.lo)S.lo=S.hi;render();}};
$('byObs').onclick=function(){S.up=false;refilter();};
$('byUp').onclick=function(){S.up=true;refilter();};
function chip(box,label,pressed,onclick,title){var b=document.createElement('button');
  b.type='button';b.textContent=label;if(title)b.title=title;
  b.setAttribute('aria-pressed',String(pressed));
  b.onclick=function(){b.setAttribute('aria-pressed',String(onclick()));refilter();};
  $(box).appendChild(b);return b;}
// Like the months: with no group picked every group shows. The list's rows pick and leave out groups.
var GL=GroupList({box:$('groups'),bar:$('gbar'),keep:$('gkeep'),mine:$('mine'),S:S,META:META,nf:nf,changed:refilter,taxa:o.taxa,P:o.P,
  pass:o.pass,inside:o.inside,pk:function(){return PK;}}),showGroups=GL.show;
$('gall').onclick=function(){S.groups={};showGroups();refilter();};
var MB_=MON.map(function(m,i){var b=chip('months',m,!!(S.months>>i&1),
  function(){S.months^=1<<i;return !!(S.months>>i&1);});b.setAttribute('aria-label',MONTH[i]);
  return b;});
function showMonths(){MB_.forEach(function(b,i){b.setAttribute('aria-pressed',String(!!(S.months>>i&1)));});}
$('mclear').onclick=function(){S.months=0;showMonths();refilter();};
// Introduced and threatened can be left out too. The location accuracy is one choice of several, so its
// chips exclude each other, and a click on the chosen one clears it; a pool without accuracy has none.
var ONLYDEF=MF.ONLYDEF,
  ONLY=ONLYDEF.map(function(d){return CH.chip($('flags'),d[0],d[1],function(){return S.only;},true,
    d[3],refilter);}),
  ACCDEF=META.flags.indexOf('accuracy')<0?[]:MF.ACCDEF,
  ACC=ACCDEF.map(function(d){var b=document.createElement('button');b.type='button';b.title=d[2]+'. Click to pick.';
    b.onclick=function(){S.acc=S.acc===d[0]?'':d[0];showOnly();refilter();};$('acc').appendChild(b);return b;});
function accLabel(){var d=ACCDEF.filter(function(a){return a[0]===S.acc;})[0];return d?d[1]:'';}
function showOnly(){ONLY.forEach(function(b,j){CH.show(b,ONLYDEF[j][1],S.only[ONLYDEF[j][0]]||'');});
  ACC.forEach(function(b,j){CH.show(b,ACCDEF[j][1],S.acc===ACCDEF[j][0]?'inc':'');});}
showOnly();
if(!ONLY.length&&!ACC.length)$('flagbox').hidden=true;
if(!ACC.length)$('acc').hidden=$('acclbl').hidden=true;
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
// The selection bar lists every chip; its Clear all clears them, and reset also the dates.
function redraw(){showGroups();showMonths();showOnly();refilter();}
function clearAll(){S.months=0;S.groups={};S.only={};S.acc='';S.picks.length=0;S.split=[];$('q').value='';showClades();
  o.search();o.area().clear();PJ.reset();redraw();}
$('reset').onclick=function(){S.lo=0;S.hi=LAST;S.up=false;clearAll();o.reset();};
var BAR=CH.bar({box:$('selbar'),clear:clearAll,fallback:$('q')});
function items(){return CH.items({S:S,meta:META,terms:TX.terms({T:o.taxa(),picks:S.picks,groups:[],meta:META,n:0,split:S.split}),
  picker:PK,pj:PJ,months:MONTH,only:ONLYDEF,acc:{label:accLabel(),clear:function(){S.acc='';}},area:o.area(),redraw:redraw}).concat(o.extra());}
// Each folding section's summary counts its active chips, so a folded one still says what it holds.
function tally(){var n=function(st){var c=0;for(var k in st)if(st[k])c++;return c;},m=0,i,e;
  for(i=0;i<12;i++)m+=S.months>>i&1;
  [['ntaxa',S.picks.length],['nonly',n(S.only)+(S.acc?1:0)],['nproj',PJ.items().length],['ngroups',n(S.groups)],
    ['nmonths',m]].forEach(function(d){e=$(d[0]);if(e)e.textContent=d[1]?String(d[1]):'';});}
// Groups, Taxa and Show only start open, Projects and Months folded; a section opens as the viewer
// last left it, and one a link filters on opens regardless (projects only know theirs once loaded).
var FOLD='wtid-map-fold';
(function(){var saved={};try{saved=JSON.parse(localStorage.getItem(FOLD))||{};}catch(e){}
  var open={grpsec:CH.any(S.groups),monsec:!!S.months,flagbox:CH.any(S.only)||!!S.acc,projbox:/(^|[#&])projects=/.test(location.hash)};
  [].forEach.call(document.querySelectorAll('details.sec'),function(d){
    if(open[d.id])d.open=true;else if(d.id in saved)d.open=saved[d.id];
    d.addEventListener('toggle',function(){saved[d.id]=d.open;
      try{localStorage.setItem(FOLD,JSON.stringify(saved));}catch(e){}});});})();

// Brings the controls up to date with S and the counts, after every recount.
function update(){
  $('from').value=iso(S.lo);$('to').value=iso(S.hi);
  $('byObs').setAttribute('aria-pressed',String(!S.up));
  $('byUp').setAttribute('aria-pressed',String(S.up));
  PRESETS.forEach(function(p){var r=p.range();
    p.el.setAttribute('aria-pressed',String(r[0]===S.lo&&r[1]===S.hi));});
  $('reset').hidden=!o.sel().length;  // nothing to reset until a filter is set
  BAR.set(items());tally();draw();
}
return {update:update,draw:draw,total:total,pct:pct,oldQuery:oldQuery,groups:GL,
  showGroups:showGroups,showMonths:showMonths,showOnly:showOnly,showClades:showClades};
}
return FilterBar;
})();
