// "Sort by conservation status": the Identify batches open the records of species at risk in BC first, listed
// in Canada (tier 1), then BC S1-S2 (2), then BC S3 (3), and the rest after them in map order. Within
// a tier each species gives at most PER records a round, so one common listed species cannot fill
// the first batches, and within a round the species with the fewest BC Research Grade records go
// first. META.value rows are [taxon id, tier, BC Research Grade count] (at_risk_bc_taxa.json).
var MapValue=(function(){
'use strict';
var PER=5;
// the value row of each TAXA row (TAXA rows hold the iNaturalist taxon id third), else null
function rows(taxa,value){var by={};value.forEach(function(r){by[r[0]]=r;});
  return taxa.map(function(t){return by[t[2]]||null;});}
// ix: record indices in map order; tax: each record's TAXA row; vr: rows(). Returns ix reordered.
function order(ix,tax,vr){var hit=[],rest=[],seen={},i,r,t;
  for(i=0;i<ix.length;i++){t=tax[ix[i]];r=vr[t];
    if(!r){rest.push(ix[i]);continue;}seen[t]=(seen[t]||0)+1;
    hit.push([r[1],Math.floor((seen[t]-1)/PER),r[2],i,ix[i]]);}
  hit.sort(function(a,b){return a[0]-b[0]||a[1]-b[1]||a[2]-b[2]||a[3]-b[3];});
  return hit.map(function(h){return h[4];}).concat(rest);}
return {rows:rows,order:order,PER:PER};
})();
