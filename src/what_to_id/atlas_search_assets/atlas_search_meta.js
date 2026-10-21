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
// Hash <-> state: #q=<text> or #id=<obs>, plus the taxon filter as keep=<id>:<name> and drop=<id>:<name>,
// one param per taxon, so a shared link carries the filter and its chips.
function parseTaxa(vals){
  return vals.map(function(v){var m=/^(\d+)(?::(.*))?$/.exec(v);return m&&+m[1]>0?{id:+m[1],name:m[2]||('taxon '+m[1])}:null;})
    .filter(Boolean);
}
function parseHash(hash){
  var p=new URLSearchParams(String(hash||'').replace(/^#/,'')),id=p.get('id'),q=p.get('q');
  var f={include:parseTaxa(p.getAll('keep')),exclude:parseTaxa(p.getAll('drop'))};
  if(id&&/^\d+$/.test(id)&&+id>0)return {kind:'id',id:+id,include:f.include,exclude:f.exclude};
  if(q&&q.trim())return {kind:'text',text:q.trim(),include:f.include,exclude:f.exclude};
  return null;
}
function enc(text){return encodeURIComponent(text).replace(/%20/g,'+');}
function toHash(state){
  if(!state)return '';
  var h=state.kind==='id'?'#id='+state.id:'#q='+enc(state.text);
  [['keep',state.include],['drop',state.exclude]].forEach(function(p){
    (p[1]||[]).forEach(function(t){h+='&'+p[0]+'='+t.id+':'+enc(t.name);});
  });
  return h;
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
    id:o.id,score:hit.score,tag:hit.tag,grade:o.quality_grade,
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
// CLIP text towers score a sentence much like its bag of words, so "a bird eating a frog" ranks lone
// frogs and lone birds high. Connectives that put a second organism or object in frame split the query
// into subjects the page searches separately and fuses with min: every subject must be in the photo.
// "with" and "and" stay whole: "a bird with a red head" and "black and white" describe one subject.
var LINK=/\b(?:eating|eats|preying on|catching|carrying|holding|feeding (?:on|at|from)|pollinating|visiting|perched on|sitting on|resting on|growing on|covered (?:in|with)|infected (?:by|with)|parasiti[sz]ed by|attacked by|on)\b/i;
function subjects(text){
  var raw=String(text||'').trim().replace(/^(?:an? )?(?:photo|picture|image) of /i,'');
  var parts=raw.split(LINK).map(function(p){return p.trim().replace(/[,;.!?]+$/,'');}).filter(function(p){return p.length>2;});
  return parts.length>1?parts:[raw];
}
// Min-fuse ranked lists of {id,score}, the first being the whole query's: an id missing from a list
// takes that list's lowest score, the tightest bound the list gives. Highest fused score first, then
// the whole query's score (ids outside one subject's list share its floor), then lower id.
function fuse(lists,k){
  var floors=lists.map(function(l){return l.length?l[l.length-1].score:-1;});
  var maps=lists.map(function(l){var m=new Map();l.forEach(function(h){m.set(h.id,h.score);});return m;});
  var out=[],seen=new Set();
  lists.forEach(function(l){
    l.forEach(function(h){
      if(seen.has(h.id))return;
      seen.add(h.id);
      var s=Infinity;
      maps.forEach(function(m,i){s=Math.min(s,m.has(h.id)?m.get(h.id):floors[i]);});
      out.push({id:h.id,score:s,tag:h.tag,whole:maps[0].has(h.id)?maps[0].get(h.id):floors[0]});
    });
  });
  out.sort(function(a,b){return b.score-a.score||b.whole-a.whole||a.id-b.id;});
  return out.slice(0,k).map(function(h){return {id:h.id,score:h.score,tag:h.tag};});
}
return {BATCH:BATCH,parseInput:parseInput,parseHash:parseHash,toHash:toHash,smallPhoto:smallPhoto,
  fetchObservations:fetchObservations,build:build,autocomplete:autocomplete,subjects:subjects,fuse:fuse};
});
