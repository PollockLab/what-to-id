// Live iNaturalist metadata for search hits: input parsing, observation cards, taxon filter.
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.AtlasSearchMeta=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var API='https://api.inaturalist.org/v1/';
var BATCH=200;

// "123", "#123", or an iNaturalist observation URL -> {kind:'id',id}; anything else is a text query.
function parseInput(raw){
  var t=String(raw||'').trim();
  if(!t)return null;
  var m=/^#?(\d{1,10})$/.exec(t)||/^https?:\/\/(?:[\w-]+\.)?inaturalist\.(?:org|ca)\/observations\/(\d{1,10})(?:[/?#]|$)/i.exec(t);
  if(m&&+m[1]>0&&+m[1]<=4294967295)return {kind:'id',id:+m[1]};
  return {kind:'text',text:t};
}
// Hash <-> state: #q=<text> or #id=<obs>.
function parseHash(hash){
  var p=new URLSearchParams(String(hash||'').replace(/^#/,'')),id=p.get('id'),q=p.get('q');
  if(id&&/^\d+$/.test(id)&&+id>0)return {kind:'id',id:+id};
  if(q&&q.trim())return {kind:'text',text:q.trim()};
  return null;
}
function toHash(state){
  if(!state)return '';
  return state.kind==='id'?'#id='+state.id:'#q='+encodeURIComponent(state.text).replace(/%20/g,'+');
}
function smallPhoto(url){return url?String(url).replace(/\/square(\.\w+)/,'/small$1'):'';}

// Sequential, polite fetch of up to 200 ids per request; ``cache`` maps id -> observation.
async function fetchObservations(ids,fetchFn,cache){
  var need=ids.filter(function(id){return !cache.has(id);});
  for(var i=0;i<need.length;i+=BATCH){
    var chunk=need.slice(i,i+BATCH);
    var res=await fetchFn(API+'observations?id='+chunk.join(',')+'&per_page='+BATCH);
    if(!res.ok)throw new Error('iNaturalist returned '+res.status+' while loading the photos.');
    var data=await res.json();
    chunk.forEach(function(id){cache.set(id,null);});
    (data.results||[]).forEach(function(o){cache.set(o.id,o);});
  }
}
function card(o,hit){
  var t=o.taxon||{},ph=o.photos&&o.photos[0];
  return {
    id:o.id,score:hit.score,grade:o.quality_grade,
    photo:ph?smallPhoto(ph.url):'',
    name:t.name||'',common:t.preferred_common_name||'',rank:t.rank||'',
    date:o.observed_on||'',place:o.place_guess||'',
    ancestors:t.ancestor_ids||[]
  };
}
function taxonOk(c,include,exclude){
  var inAny=function(ids){return ids.some(function(id){return c.ancestors.indexOf(id)>=0;});};
  if(exclude.length&&inAny(exclude))return false;
  return !include.length||inAny(include);
}
// Hits in rank order -> cards, dropping observations that left Needs ID, vanished, or miss the taxon filter.
function build(hits,cache,filter){
  var inc=(filter&&filter.include)||[],exc=(filter&&filter.exclude)||[];
  var out={cards:[],notNeedsId:0,missing:0,filtered:0};
  hits.forEach(function(h){
    var o=cache.get(h.id);
    if(!o){out.missing++;return;}
    if(o.quality_grade!=='needs_id'){out.notNeedsId++;return;}
    var c=card(o,h);
    if(!taxonOk(c,inc,exc)){out.filtered++;return;}
    out.cards.push(c);
  });
  return out;
}
async function autocomplete(q,fetchFn){
  var res=await fetchFn(API+'taxa/autocomplete?per_page=8&q='+encodeURIComponent(q));
  if(!res.ok)throw new Error('iNaturalist returned '+res.status+' for the taxon search.');
  var data=await res.json();
  return (data.results||[]).map(function(t){
    return {id:t.id,name:t.name,common:t.preferred_common_name||'',rank:t.rank||''};
  });
}
return {BATCH:BATCH,parseInput:parseInput,parseHash:parseHash,toHash:toHash,smallPhoto:smallPhoto,
  fetchObservations:fetchObservations,build:build,autocomplete:autocomplete};
});
