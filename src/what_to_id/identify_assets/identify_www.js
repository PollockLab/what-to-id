// The At risk, Invasive and Group by suggested species toggles. At risk and Invasive (hash risk=1, inv=1) keep
// cards by their suggested species (else the record's own taxon): At risk from the map's META.value list (at_risk_bc_taxa.json, listed in Canada
// or BC S1-S3), Invasive from META.invasive (invasive_bc_taxa.json, introduced in BC per iNaturalist), both at once. Only a map
// without META.invasive asks /v1/taxa/<ids>?preferred_place_id=7085 (30 ids a request, cached by taxon id for a week) and hides a
// suggestion not yet looked up until its answer lands. A lookup that fails (429) stays unknown and is asked again after a growing wait;
// while any is pending body[data-checking] holds how many (the result line says "Checking N species…").
// score(i) is At risk's order on level 3, not its filter: the expected at-risk value over the suggestion and its runner-up (why(i), optional).
// IdentifyWWW(ctx), ctx {look(i), why(i) [name, margin in thousandths, 255 none] or null, taxa(), value (META.value), invasive (META.invasive, optional), redraw()}.
var IdentifyWWW=(function(){
'use strict';
var LS='wtid-status',WEEK=7*864e5,RISK=1,INV=2,TEMP=0.02;  // TEMP: the cosine margin of a softmax over the two matches (a margin of 0.04, a clear one, leaves the runner-up 12%)
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function invasive(t){var m=t.establishment_means||{};
  return /introduced|invasive/.test(m.establishment_means||'')&&(!m.place||m.place.id===7085)?INV:0;}
return function(ctx){
  var api=inatGate({gap:1000}),ids=new Map(),cache={},want=new Set(),busy=new Set(),T=0,out=0,nn=0,fails=0,RT=0,need=0,tier=new Map((ctx.value||[]).map(function(r){return [r[0],r[1]];})),risk=new Set(tier.keys()),bc=ctx.invasive?new Set(ctx.invasive):null;
  try{var c=JSON.parse(localStorage.getItem(LS))||{};if(Date.now()-c.at<WEEK)cache=c.f||{};}catch(e){}
  function on(k){return new RegExp('(^|&)'+k+'=1(&|$)').test(location.hash.slice(1));}
  function keep(k,v){var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf(k+'=')!==0;});if(v)t.push(k+'=1');
    history.replaceState(null,'','#'+t.join('&'));}
  function save(){try{localStorage.setItem(LS,JSON.stringify({at:Date.now(),f:cache}));}catch(e){}}
  function show(){var n=need?(need&INV?want.size+busy.size:0)+nn:0;if(n)document.body.dataset.checking=n;else delete document.body.dataset.checking;}
  function ask(){
    var todo=[...want].filter(function(id){return !busy.has(id)&&!(id in cache);});want.clear();
    for(var k=0;k<todo.length;k+=30)(function(b){var bad=0;b.forEach(function(id){busy.add(id);});out++;show();
      api('taxa/'+b.join(',')+'?preferred_place_id=7085').then(function(j){
        b.forEach(function(id){cache[id]=0;});(j.results||[]).forEach(function(t){cache[t.id]=invasive(t);});save();fails=0;
      }).catch(function(){bad=1;}).then(function(){
        b.forEach(function(id){busy.delete(id);if(bad)want.add(id);});out--;
        if(bad){clearTimeout(RT);RT=setTimeout(ask,Math.min(2e3*Math.pow(2,fails++),6e4));}  // asked again, 2 s, 4 s, 8 s… up to a minute
        show();settled();});})(todo.slice(k,k+30));
    show();
  }
  // a suggestion the taxa table lacks: its id by an exact name search, 0 for none
  // one redraw once every lookup in flight has answered: a redraw per answer (one a second) made the grid flicker
  function settled(){clearTimeout(T);if(!out)T=setTimeout(ctx.redraw,300);}
  function named(nm){ids.set(nm,0);out++;nn++;show();api('taxa?rank=species&per_page=1&q='+encodeURIComponent(nm)).then(function(j){
    var x=(j.results||[])[0];if(x&&x.name===nm)ids.set(nm,x.id);}).catch(function(){}).then(function(){out--;nn--;show();settled();});}
  // records pass unless a toggle is on and their suggestion fails it
  function pass(i){
    if(!need)return true;
    if(!ids.size)ctx.taxa().forEach(function(t){if(t[2])ids.set(t[0],t[2]);});
    var nm=ctx.look(i),id=ids.get(nm);
    if(!id){if(nm&&id===undefined)named(nm);return false;}
    if(need&RISK&&risk.has(id))return true;
    if(!(need&INV))return false;
    if(bc)return bc.has(id);
    if(!(id in cache)){if(!want.size)setTimeout(ask,0);want.add(id);show();return false;}
    return (cache[id]&INV)!==0;
  }
  // 1 at risk | 2 invasive for the record's suggestion, whatever the filters say; inv asks iNaturalist for the ones not yet read
  function flag(i,inv){
    if(!ids.size)ctx.taxa().forEach(function(t){if(t[2])ids.set(t[0],t[2]);});
    var id=ids.get(ctx.look(i)),f=id&&risk.has(id)?1:0;
    if(!id||!inv)return f;
    if(bc)return bc.has(id)?f|INV:f;
    if(id in cache)return f|cache[id]&INV;
    if(!want.size)setTimeout(ask,0);want.add(id);show();return f;
  }
  // the at-risk value 0..1 of a species by name (tier 1 listed in Canada 1, tier 2 2/3, tier 3 1/3), 0 for one not listed or not in the taxa table
  function val(nm){var t=tier.get(ids.get(nm));return t?(4-t)/3:0;}
  // the expected at-risk value over the suggestion and its runner-up, their weights a softmax of the two cosine scores (only their margin is known): 0..1
  function score(i){
    if(!ids.size)ctx.taxa().forEach(function(t){if(t[2])ids.set(t[0],t[2]);});
    var y=ctx.why&&ctx.why(i),w=y&&y[1]!==255?1/(1+Math.exp(y[1]/1000/TEMP)):0;
    return (1-w)*val(ctx.look(i))+w*val(y&&y[0]);
  }
  // a card whose own taxon (id) is not listed but whose likely species are: at risk is only possible
  function maybe(i,id){return !risk.has(id)&&score(i)>0;}
  function toggle(k,label){
    var l=el('label','tog'),b=el('input');b.type='checkbox';if(k==='run')b.setAttribute('role','switch');b.checked=on(k);
    b.onchange=function(){keep(k,b.checked);sync();ctx.redraw();};l.append(b,' '+label);return l;
  }
  function sync(){need=(on('risk')?RISK:0)|(on('inv')?INV:0);if(risk_){risk_.firstChild.checked=!!(need&RISK);inv_.firstChild.checked=!!(need&INV);}show();}
  // At risk and Introduced are one-tap chips under the search bar; the grouping toggle sits with Sort
  var risk_=toggle('risk','At risk'),inv_=toggle('inv','Introduced');risk_.className=inv_.className='tog qchip';inv_.title='Introduced to BC, per iNaturalist';
  $('qchips').append(risk_,inv_);$('frun').append(toggle('run','Group by suggested species'));$('frun').firstChild.className='swt';
  sync();
  return {pass:pass,flag:flag,score:score,maybe:maybe,sync:sync,need:function(){return need;},active:function(){return on('risk')||on('inv');}};
};
})();
