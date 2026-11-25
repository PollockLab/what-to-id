// The Life groups setting, one for every page that shows the pool's groups (map, Identify, photo space, tree,
// Explore): iNaturalist's one Plantae (the default) or the pool's split plants (taxonomy.PLANT_GROUPS).
// The data holds the split group of each record, so iNaturalist mode merges the split groups into Plantae when the page
// loads: MapGroups(META) rewrites META.groups, names and group_ids and sets META.gmap (old group index to new, or
// absent when nothing merged) for MapGroups.grp (a group column), MapGroups.sum (per-group counts or rows) and
// MapGroups.totals. The choice is the URL's plants=inat|split, else the one kept in localStorage (which may be
// blocked); the pages share the origin, so MapGroups.watch() reloads a page another page switched;
// an embedded page also tells its parent (Explore), which switches the other panes without storage.
var MapGroups=(function(){
'use strict';
var KEY='wtid-plants',SPLIT=['Tracheophyta','Bryophytes','Algae'];
function mode(){var m=/[?&]plants=(inat|split)(&|#|$)/.exec(location.search);
  if(m)return m[1];try{return localStorage.getItem(KEY)==='split'?'split':'inat';}catch(e){return 'inat';}}
// This page's address with plants=m (the hash kept).
function url(m){var u=new URL(location.href);u.searchParams.set('plants',m);return u.href;}  // absolute: a '//host' path can't redirect off-site
function MapGroups(META){
  var G=META.groups,out=[];
  META.plants=MapGroups.current=mode();META.canSplit=SPLIT.some(function(g){return G.indexOf(g)>=0;});
  if(!META.canSplit||META.plants==='split')return META;
  META.gmap=Uint8Array.from(G.map(function(g){var k=SPLIT.indexOf(g)>=0?'Plantae':g;
    if(out.indexOf(k)<0)out.push(k);return out.indexOf(k);}));
  META.groups=out;META.names=Object.assign({},META.names,{Plantae:'Plants (Plantae)'});
  META.group_ids=Object.assign({},META.group_ids,{Plantae:(META.group_ids||{}).Plantae||47126});
  SPLIT.forEach(function(g){delete META.group_ids[g];});
  if(META.presets)META.presets=META.presets.filter(function(c){return SPLIT.indexOf(c[0])<0;});  // a split group's chip
  return META;}
MapGroups.KEY=KEY;MapGroups.mode=mode;MapGroups.url=url;
// A group column (old indexes), merged in place.
MapGroups.grp=function(META,g){if(META.gmap)for(var i=0;i<g.length;i++)g[i]=META.gmap[g[i]];return g;};
// A list per old group (numbers, or rows of numbers) as one per group.
MapGroups.sum=function(META,a){
  if(!META.gmap||!a)return a;
  var o=META.groups.map(function(){return null;});
  a.forEach(function(v,j){var k=META.gmap[j];
    o[k]=o[k]==null?(Array.isArray(v)?v.slice():v):Array.isArray(v)?o[k].map(function(x,i){return x+v[i];}):o[k]+v;});
  return o;};
// The totals file's rows are per old group: add the merged ones.
MapGroups.totals=function(META,T){
  if(!META.gmap||!T)return T;
  var f=['obs','up'];f.forEach(function(k){T[k]=MapGroups.sum(META,T[k]);});
  Object.keys(T.only||{}).forEach(function(s){f.forEach(function(k){T.only[s][k]=MapGroups.sum(META,T.only[s][k]);});});
  return T;};
// Another page of the site switched: go(mode), by default this page reloads with it (in Explore every pane does).
MapGroups.watch=function(go){
  addEventListener('storage',function(e){if(e.key!==KEY)return;var m=e.newValue==='split'?'split':'inat';
    (go||function(m){if(m!==MapGroups.current)location.replace(url(m));})(m);});};
// The two buttons of box (hidden when the data has no split plants); a click keeps the choice and reloads with it.
MapGroups.ui=function(META,box){
  box.hidden=!META.canSplit;
  [].forEach.call(box.querySelectorAll('button'),function(b){
    b.setAttribute('aria-pressed',String(b.dataset.m===META.plants));
    b.onclick=function(){if(b.dataset.m===META.plants)return;
      try{localStorage.setItem(KEY,b.dataset.m);}catch(e){}
      if(parent!==window)parent.postMessage({type:'wtid-plants',m:b.dataset.m},location.origin);  // Explore switches the other panes, storage or not
      location.href=url(b.dataset.m);};});};
return MapGroups;
})();
