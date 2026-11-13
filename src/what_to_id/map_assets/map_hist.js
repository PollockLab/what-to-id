// The date histograms: an overview with one bar per year over every date, on a log scale, and a detail of the
// period in view. Clicking or dragging across bars sets S.lo and S.hi. The filter bar draws them in the map and the
// Identify page draws them in its When panel. o: S, META, mf (MapFilter(META)), nf, over, hist (the canvases), htip,
// unit (the caption), cum() (day counts: c[b+1]-c[a] records on days a..b), tc() (the totals, or null), render() (the
// dates changed), sub (optional {cum(), name()}: the day counts of a subset, named in the tooltip), drag() (the dates
// moved mid-brush: move only the GPU range, optional).
// Returns draw(), total(a,b) and pct(v,t).
var MapHist=(function(){
'use strict';
var MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function MapHist(o){
var S=o.S,META=o.META,MF=o.mf,nf=o.nf,render=o.render,
  LAST=MF.LAST,DOM=MF.DOM,MOY=MF.MOY,DOW=MF.DOW,MI=MF.MI,MONTH=MF.MONTH,iso=MF.iso,clamp=MF.clamp,
  css=getComputedStyle(document.documentElement);
function tok(n){return css.getPropertyValue(n).trim();}
// Two histograms. The overview has one bar per year over every date, on a log scale so that sparse
// early years still show. The detail shows the period in view, with bars sized to it (days, weeks,
// months or years) and scaled to its tallest bar. Picking a period in either zooms the detail to it.
var hist=o.hist,over=o.over,htip=o.htip,VIEW=[0,LAST],HE=[0,LAST+1],HU='year',drag=null;
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
  o.unit.textContent=cap;hist.setAttribute('aria-label',cap+' Drag to pick a period.');
}
function binAt(cv,e,x){var n=e.length-1;return Math.max(0,Math.min(n-1,Math.floor(x/(cv.clientWidth/n))));}
// A drag redraws the histograms and the map's date range once a frame; the counts, hash and sync wait for pointerup.
var dragRaf=0;
function preview(){if(dragRaf)return;dragRaf=requestAnimationFrame(function(){dragRaf=0;draw();o.drag();});}
function brush(cv,get){
  var st=null;
  cv.addEventListener('pointerdown',function(ev){cv.setPointerCapture(ev.pointerId);
    st={x:ev.offsetX,moved:false,e:get().e};if(cv===hist)drag=st;});
  cv.addEventListener('pointermove',function(ev){
    var g=get(),e=st?st.e:g.e,k=binAt(cv,e,ev.offsetX);
    var nk=count(e[k],e[k+1]-1),tk=total(e[k],e[k+1]-1);
    htip.textContent=binLabel(g.u,e[k])+': '+nf.format(nk)+(tk?' of '+nf.format(tk)+' still need an ID ('+
      pct(nk,tk)+')':'')+(o.sub?', '+nf.format(o.sub.cum()[e[k+1]]-o.sub.cum()[e[k]])+' in '+o.sub.name():'');
    // Clamp by the tip's own width so it never pokes past the chart: overflow there adds a page
    // scrollbar, which shrinks the map and shifts its view.
    htip.hidden=false;htip.style.top=(cv.offsetTop-4)+'px';
    var hw=htip.offsetWidth/2;
    htip.style.left=Math.max(hw,Math.min(ev.offsetX,cv.clientWidth-hw))+'px';
    if(!st)return;
    if(Math.abs(ev.offsetX-st.x)>3)st.moved=true;
    if(st.moved){var a=binAt(cv,e,Math.min(st.x,ev.offsetX)),z=binAt(cv,e,Math.max(st.x,ev.offsetX));
      S.lo=e[a];S.hi=e[z+1]-1;if(o.drag)preview();else render();}
  });
  cv.addEventListener('pointerup',function(ev){
    if(st&&!st.moved){var k=binAt(cv,st.e,ev.offsetX);S.lo=st.e[k];S.hi=st.e[k+1]-1;}
    cancelAnimationFrame(dragRaf);dragRaf=0;st=null;drag=null;htip.hidden=true;render();});
  cv.addEventListener('pointerleave',function(){htip.hidden=true;});
  cv.addEventListener('dblclick',function(){S.lo=0;S.hi=LAST;render();});
}
brush(over,function(){return {e:OE,u:'year'};});
brush(hist,function(){return {e:HE,u:HU};});
return {draw:draw,total:total,pct:pct};
}
// The all-record counts as running sums per month, for the groups g (a flag per group) and the months S.months, from
// the totals file TOT. One picked status filter reads its own totals; two together, a left-out one, picked taxa or
// anything else in blocked have none: null.
MapHist.tc=function(TOT,S,MF,g,blocked){
  var on=Object.keys(S.only).concat(S.acc?'acc_'+S.acc:[]),
    tt=!TOT||S.picks.length||blocked||on.length>1||S.only[on[0]]==='not'?null:on.length?TOT.only&&TOT.only[on[0]]:TOT;
  if(!tt)return null;
  var rows=tt[S.up?'up':'obs'],nm=rows[0].length,m=S.months,TC=new Float64Array(nm+1);
  for(var k=0;k<nm;k++){var v=0;if(!m||m>>(MF.M0+k)%12&1)for(var j=0;j<rows.length;j++)if(g[j])v+=rows[j][k];
    TC[k+1]=TC[k]+v;}
  return TC;
};
return MapHist;
})();
