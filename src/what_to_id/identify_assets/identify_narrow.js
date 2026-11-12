// Level 3 helpers: an improving ID there is the first at species, so a card carries its suggestion to iNaturalist
// (copy), says how high it ranks in its level (conf) and whether a record already has a species ID (taken).
var IdentifyNarrow=(function(){
'use strict';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// A button that copies the suggested name, its words saying whether it did.
function copy(name){
  var b=el('button','copy','Copy');b.type='button';b.setAttribute('aria-label','Copy '+name);b.setAttribute('aria-live','polite');
  b.onclick=function(){
    var c=navigator.clipboard,done=function(t){b.textContent=t;setTimeout(function(){b.textContent='Copy';},2000);};
    (c&&c.writeText?c.writeText(name):Promise.reject()).then(function(){done('Copied');},function(){done('Copy failed');});};
  return b;
}
// The confidence band of the record's place r (0 first) among n: 0 top 1%, 1 top 5%, 2 top 25%, 3 the rest.
function band(r,n){
  var p=(r+1)/n;
  return p<=0.01?0:p<=0.05?1:p<=0.25?2:3;
}
// "Top 1%" and so on from the record's place r (0 first) among n, else ''.
function conf(r,n){
  if(!n||r==null)return '';
  return ['Top 1%','Top 5%','Top 25%',''][band(r,n)];
}
// An observation (iNaturalist API v1) already at species or below, or with a current ID at species or below.
function taken(o){
  function sp(t){return !!(t&&t.rank_level&&t.rank_level<=10);}
  return sp(o.taxon)||(o.identifications||[]).some(function(d){return d.current!==false&&sp(d.taxon);});
}
return {copy:copy,band:band,conf:conf,taken:taken};
})();
