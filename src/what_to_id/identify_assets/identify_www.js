// The At risk, Invasive and Group by suggested species toggles. At risk and Invasive (hash risk=1, inv=1) keep
// level 3 cards by their suggested species: At risk from the map's META.value list (at_risk_bc_taxa.json, listed in Canada
// or BC S1-S3), at once; Invasive when iNaturalist marks it introduced in BC, from /v1/taxa/<ids>?preferred_place_id=7085
// (30 ids a request), cached by taxon id for a week. A suggestion not yet looked up is hidden until its answer lands.
// IdentifyWWW(ctx), ctx {look(i), taxa(), value (META.value), redraw()}.
var IdentifyWWW=(function(){
'use strict';
var LS='wtid-status',WEEK=7*864e5,RISK=1,INV=2;
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function invasive(t){var m=t.establishment_means||{};
  return /introduced|invasive/.test(m.establishment_means||'')&&(!m.place||m.place.id===7085)?INV:0;}
return function(ctx){
  var api=inatGate({gap:1000}),ids=new Map(),cache={},want=new Set(),busy=new Set(),T=0,need=0,risk=new Set((ctx.value||[]).map(function(r){return r[0];}));
  try{var c=JSON.parse(localStorage.getItem(LS))||{};if(Date.now()-c.at<WEEK)cache=c.f||{};}catch(e){}
  function on(k){return new RegExp('(^|&)'+k+'=1(&|$)').test(location.hash.slice(1));}
  function keep(k,v){var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf(k+'=')!==0;});if(v)t.push(k+'=1');
    history.replaceState(null,'','#'+t.join('&'));}
  function save(){try{localStorage.setItem(LS,JSON.stringify({at:Date.now(),f:cache}));}catch(e){}}
  function ask(){
    var todo=[...want].filter(function(id){return !busy.has(id)&&!(id in cache);});want.clear();
    for(var k=0;k<todo.length;k+=30)(function(b){b.forEach(function(id){busy.add(id);});
      api('taxa/'+b.join(',')+'?preferred_place_id=7085').then(function(j){
        b.forEach(function(id){cache[id]=0;});(j.results||[]).forEach(function(t){cache[t.id]=invasive(t);});save();
      }).catch(function(){b.forEach(function(id){cache[id]=0;});}).then(function(){
        b.forEach(function(id){busy.delete(id);});clearTimeout(T);T=setTimeout(ctx.redraw,300);});})(todo.slice(k,k+30));
  }
  // a suggestion the taxa table lacks: its id by an exact name search, 0 for none
  function named(nm){ids.set(nm,0);api('taxa?rank=species&per_page=1&q='+encodeURIComponent(nm)).then(function(j){
    var x=(j.results||[])[0];if(x&&x.name===nm){ids.set(nm,x.id);clearTimeout(T);T=setTimeout(ctx.redraw,300);}}).catch(function(){});}
  // level 3 records pass unless a toggle is on and their suggestion fails it
  function pass(i){
    if(!need)return true;
    if(!ids.size)ctx.taxa().forEach(function(t){if(t[2])ids.set(t[0],t[2]);});
    var nm=ctx.look(i),id=ids.get(nm);
    if(!id){if(nm&&id===undefined)named(nm);return false;}
    if(need&RISK&&risk.has(id))return true;
    if(!(need&INV))return false;
    if(!(id in cache)){if(!want.size)setTimeout(ask,0);want.add(id);return false;}
    return (cache[id]&INV)!==0;
  }
  // 1 at risk | 2 invasive for the record's suggestion, whatever the filters say; inv asks iNaturalist for the ones not yet read
  function flag(i,inv){
    if(!ids.size)ctx.taxa().forEach(function(t){if(t[2])ids.set(t[0],t[2]);});
    var id=ids.get(ctx.look(i)),f=id&&risk.has(id)?1:0;
    if(!id||!inv)return f;
    if(id in cache)return f|cache[id]&INV;
    if(!want.size)setTimeout(ask,0);want.add(id);return f;
  }
  function toggle(k,label){
    var l=el('label','tog'),b=el('input');b.type='checkbox';if(k==='run')b.setAttribute('role','switch');b.checked=on(k);
    b.onchange=function(){keep(k,b.checked);sync();ctx.redraw();};l.append(b,' '+label);return l;
  }
  function sync(){need=(on('risk')?RISK:0)|(on('inv')?INV:0);}
  // At risk and Invasive are one-tap chips under the search bar; the grouping toggle sits with Sort
  var risk_=toggle('risk','At risk'),inv_=toggle('inv','Invasive');risk_.className=inv_.className='tog qchip';
  $('qchips').append(risk_,inv_);$('frun').append(toggle('run','Group by suggested species'));$('frun').firstChild.className='swt';
  sync();
  return {pass:pass,flag:flag,sync:sync,active:function(){return on('risk')||on('inv');}};
};
})();
