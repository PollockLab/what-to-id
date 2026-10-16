// Exact observation-ID handoff shared by the full map and frozen photo explorer.
var IdentifyLinks=(function(){
'use strict';
var BATCH=200,MAX_IDS=10000,MAX_URL_LENGTH=8000;
var IDS='https://www.inaturalist.org/observations/identify?quality_grade=needs_id&reviewed=false'+
  '&place_id=any&per_page='+BATCH+'&id=';
// Preserve the full map's newest-first order and {url,n,lo,hi} batch contract.
function order(ids){return Array.prototype.slice.call(ids).sort(function(a,b){return b-a;});}
function batches(ids){
  var s=order(ids),out=[];
  for(var i=0;i<s.length;i+=BATCH){var b=s.slice(i,i+BATCH);
    out.push({url:IDS+b.join(','),n:b.length,lo:b[b.length-1],hi:b[0]});}
  return out;
}
function prepare(ids){
  if(!Array.isArray(ids)&&!(ArrayBuffer.isView(ids)&&!(ids instanceof DataView)))
    throw new Error('Observation IDs must be an array or typed array.');
  var unique=new Set();
  for(var id of ids){
    if(!Number.isSafeInteger(id)||id<=0)
      throw new Error('Observation IDs must be positive safe integers.');
    unique.add(id);
    if(unique.size>MAX_IDS)throw new Error('Choose at most 10,000 unique observations.');
  }
  var sorted=order(Array.from(unique)),links=batches(sorted);
  if(links.some(function(batch){return batch.url.length>MAX_URL_LENGTH;}))
    throw new Error('An Identify link exceeds the supported URL length.');
  return {ids:sorted,batches:links,duplicateCount:ids.length-sorted.length};
}
return {BATCH:BATCH,MAX_IDS:MAX_IDS,MAX_URL_LENGTH:MAX_URL_LENGTH,order:order,batches:batches,prepare:prepare};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=IdentifyLinks;
