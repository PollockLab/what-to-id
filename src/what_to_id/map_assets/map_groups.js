// The Life groups setting: iNaturalist's one Plantae (the default) or the pool's split plants (taxonomy.PLANT_GROUPS).
// The data holds the split group of each record, so iNaturalist mode merges the split groups into Plantae when the page
// loads: MapGroups(META) rewrites META.groups, names and group_ids and sets META.gmap (old group index to new, or
// absent when nothing merged) for MapShard.append and MapGroups.totals. The choice is the URL's plants=inat|split, else
// the one kept in localStorage (which may be blocked).
var MapGroups=(function(){
'use strict';
var KEY='wtid-plants',SPLIT=['Tracheophyta','Bryophytes','Algae'];
function mode(){var m=/[?&]plants=(inat|split)(&|#|$)/.exec(location.search);
  if(m)return m[1];try{return localStorage.getItem(KEY)==='split'?'split':'inat';}catch(e){return 'inat';}}
function MapGroups(META){
  var G=META.groups,out=[];
  META.plants=mode();META.canSplit=SPLIT.some(function(g){return G.indexOf(g)>=0;});
  if(!META.canSplit||META.plants==='split')return META;
  META.gmap=Uint8Array.from(G.map(function(g){var k=SPLIT.indexOf(g)>=0?'Plantae':g;
    if(out.indexOf(k)<0)out.push(k);return out.indexOf(k);}));
  META.groups=out;META.names=Object.assign({},META.names,{Plantae:'Plants (Plantae)'});
  META.group_ids=Object.assign({},META.group_ids,{Plantae:(META.group_ids||{}).Plantae||47126});
  return META;}
// The totals file's rows are per old group: add the merged ones.
MapGroups.totals=function(META,T){
  if(!META.gmap||!T)return T;
  function rows(r){var o=META.groups.map(function(){return null;});
    r.forEach(function(row,j){var k=META.gmap[j];o[k]=o[k]?o[k].map(function(v,i){return v+row[i];}):row.slice();});
    return o;}
  var f=['obs','up'];f.forEach(function(k){T[k]=rows(T[k]);});
  Object.keys(T.only||{}).forEach(function(s){f.forEach(function(k){T.only[s][k]=rows(T.only[s][k]);});});
  return T;};
// The two buttons of box (hidden when the data has no split plants); a click keeps the choice and reloads with it.
MapGroups.ui=function(META,box){
  box.hidden=!META.canSplit;
  [].forEach.call(box.querySelectorAll('button'),function(b){
    b.setAttribute('aria-pressed',String(b.dataset.m===META.plants));
    b.onclick=function(){if(b.dataset.m===META.plants)return;
      try{localStorage.setItem(KEY,b.dataset.m);}catch(e){}
      var q=location.search.replace(/([?&])plants=[^&#]*&?/,'$1').replace(/[?&]$/,'');
      location.search=q+(q?'&':'?')+'plants='+b.dataset.m;};});};
return MapGroups;
})();
