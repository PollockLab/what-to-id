// The time subset's controls: Observed or Uploaded, the period presets, the from and to dates, the month chips and
// Any month. The filter bar draws them in the map and the Identify page in its When panel. o: S, mf (MapFilter(META)),
// the elements byObs, byUp, presets, from, to, months and mclear, render() (the dates changed) and refilter() (another
// filter changed). Returns update() (the inputs and chips follow S), showMonths() and presets, each {el, range()}.
var MapTime=(function(){
'use strict';
var MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function MapTime(o){
var S=o.S,MF=o.mf,LAST=MF.LAST,MONTH=MF.MONTH,iso=MF.iso,dayOf=MF.dayOf,clamp=MF.clamp,from=o.from,to=o.to;
var PRESETS=[
  ['Last 7 days',function(){return [clamp(LAST-6),LAST];}],
  ['Last 30 days',function(){return [clamp(LAST-29),LAST];}],
  ['Last 12 months',function(){return [clamp(LAST-364),LAST];}],
  ['This year',function(){return [clamp(dayOf(iso(LAST).slice(0,4)+'-01-01')),LAST];}],
  ['All dates',function(){return [0,LAST];}]
].map(function(p){var b=document.createElement('button');b.type='button';b.textContent=p[0];
  b.onclick=function(){var r=p[1]();S.lo=r[0];S.hi=r[1];o.render();};o.presets.appendChild(b);
  return {el:b,range:p[1]};});
from.min=to.min=iso(0);from.max=to.max=iso(LAST);
from.onchange=function(){var d=dayOf(this.value);if(d!=null){S.lo=clamp(d);
  if(S.lo>S.hi)S.hi=S.lo;o.render();}};
to.onchange=function(){var d=dayOf(this.value);if(d!=null){S.hi=clamp(d);
  if(S.hi<S.lo)S.lo=S.hi;o.render();}};
o.byObs.onclick=function(){S.up=false;o.refilter();};
o.byUp.onclick=function(){S.up=true;o.refilter();};
var MB_=MON.map(function(m,i){var b=document.createElement('button');
  b.type='button';b.textContent=m;b.setAttribute('aria-label',MONTH[i]);b.setAttribute('aria-pressed',String(!!(S.months>>i&1)));
  b.onclick=function(){S.months^=1<<i;b.setAttribute('aria-pressed',String(!!(S.months>>i&1)));o.refilter();};
  o.months.appendChild(b);return b;});
function showMonths(){MB_.forEach(function(b,i){b.setAttribute('aria-pressed',String(!!(S.months>>i&1)));});}
o.mclear.onclick=function(){S.months=0;showMonths();o.refilter();};
function update(){
  from.value=iso(S.lo);to.value=iso(S.hi);
  o.byObs.setAttribute('aria-pressed',String(!S.up));
  o.byUp.setAttribute('aria-pressed',String(S.up));
  PRESETS.forEach(function(p){var r=p.range();
    p.el.setAttribute('aria-pressed',String(r[0]===S.lo&&r[1]===S.hi));});
}
return {update:update,showMonths:showMonths,presets:PRESETS};
}
return MapTime;
})();
