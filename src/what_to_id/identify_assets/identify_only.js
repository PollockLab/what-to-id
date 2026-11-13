// The map's filters that need more than the flags MapFilter.rest reads, on Identify's records: the Show only chips One ID from
// Research Grade and Outside usual range, and the projects. The projects box is the map's (map_projects.js); a split view's map
// holds them, so embedded there is no box and the map's ids come in as pids. Range waits for the range file (R), then refreshes.
// IdentifyOnly(o), o {META, mf, P(), taxa(), range() (IdentifyRanges or null), rewrite(drop, add), changed(), get(url), embedded}.
// Returns rest(st, out, pids) (clears from out what these leave out; pids the map's project ids or null).
// Needs map_projects.js, map_filter.js and space_mask.js.
var IdentifyOnly=(function(){
'use strict';
return function(o){
  var ONE=null,PJ=o.embedded?null:projectFilter({meta:o.META,hash:new URLSearchParams(location.hash.slice(1)),changed:function(){
    o.rewrite(function(x){return /^projects=/.test(x);},PJ.hash()?[PJ.hash()]:[]);o.changed();}});
  if(PJ)PJ.load(o.get);
  function rest(st,out,pids){
    var P=o.P(),n=P.n,R=o.range(),nv=st.only.oneid==='not'?1:0,rv=st.only.range==='not'?1:0,i,
      oo=st.only.oneid&&(ONE=ONE||o.mf.oneIds(P.ids,P.tax,o.taxa(),n)),ro=st.only.range&&R?R.outside():null,
      pm=pids&&SpaceMask.ids(pids,P);
    if(PJ)PJ.sync(P);
    for(i=0;i<n;i++)if(out[i]&&((oo&&oo[i]===nv)||(ro&&ro[i]===rv)||(pm&&!pm[i])||(PJ&&PJ.drop(i))))out[i]=0;
    return out;
  }
  return {rest:rest};
};
})();
