// Level 3 helpers: an improving ID there is the first at species, so a card carries its suggestion to iNaturalist
// (copy), says how high it ranks in its level (conf), what it beat and by how much (why) and whether a record already has
// a species ID (taken).
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
// The one count line of level 3: cards drawn, the records behind the tab's count, the filters on (empty tags drop out).
function line(cards,records,tags,per){
  var nf=new Intl.NumberFormat('en-CA'),t=tags.filter(Boolean);
  return nf.format(cards)+' cards to ID ('+nf.format(records)+' records'+(t.length?', '+t.join(', '):'')+'; up to '+per+' per suggested species)';
}
// Why the suggestion: the runner-up species in the clade and, in words, the margin over it (thousandths of cosine, 255 none).
function why(name,m){
  var d=el('div','why'),w=m===255?'':m<10?', close call':m<40?', fair margin':', clear margin';
  d.append('vs ',el('i',null,name),w);
  d.title='Second best: '+name+(m===255?'':'. Margin '+(m/1000).toFixed(3)+' cosine; under 0.010 a close call, under 0.040 fair, else clear');
  return d;
}
// Species runs: rows (best first) regrouped by key(i), each group where its best card stood; sizes per key.
function runs(rows,key){
  var at=new Map(),out=[];
  rows.forEach(function(i){var k=key(i),g=at.get(k);if(!g){g=[];at.set(k,g);out.push(g);}g.push(i);});
  var flat=[].concat.apply([],out);flat.size=new Map(out.map(function(g){return [key(g[0]),g.length];}));return flat;
}
// A run's header: the species, its card count and up to three of its reference photos (ref(name) gives the taxon).
function head(name,n,ref){
  var li=el('li','sep run'),p=el('span','rp');
  li.append(el('i',null,name),' · '+n+(n===1?' card':' cards'),p);
  ref(name).then(function(t){var ps=t&&t.taxon_photos?t.taxon_photos.map(function(x){return x.photo;}):t&&t.default_photo?[t.default_photo]:[];
    ps.slice(0,3).forEach(function(x){var im=el('img');im.alt='';im.loading='lazy';im.src=String(x.url||x.square_url).replace('/square.','/small.');p.append(im);});});
  return li;
}
return {copy:copy,band:band,conf:conf,taken:taken,line:line,why:why,runs:runs,head:head};
})();
