// "Why this card?" in the compare panel: what the page knows of why a card is where it is, one line each, from data already loaded.
// IdentifyWhy.fill(ul, d), d {rule: [level name, glossary key] | null, pct: place in the level 0..1 | null, look: [lead, name] | null,
// range: [label, words] | null (label '' for none), by and kept: [[glossary key, name, detail]] for the prioritizers and the filters}.
// The sentences of the rules and the terms are the glossary's (#explain-data, from glossary.py), each with its link to the How it works entry.
// Nothing here states a probability: a rank is a rank, a look-alike is what the photo looks most like.
var IdentifyWhy=(function(){
'use strict';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
var G=null;
function gloss(k){
  if(!G)try{G=JSON.parse(document.getElementById('explain-data').textContent);}catch(e){G={};}
  return G[k]||null;
}
// a line: its parts (a string or a node), then the link to the term's entry when it has one
function line(ul,key,name,parts){
  var li=el('li'),g=key&&gloss(key),a;
  li.append.apply(li,parts);
  if(g&&g[2]){a=el('a','cwl','How it works');a.href=g[2];a.target='_blank';a.rel='noopener';a.setAttribute('aria-label','How it works: '+name);li.append(' ',a);}
  ul.appendChild(li);
}
function fill(ul,d){
  var g,n;
  ul.replaceChildren();
  if(d.rule){g=gloss(d.rule[1]);line(ul,d.rule[1],d.rule[0],[el('b',null,d.rule[0]),': ',g?g[0]:'']);}
  if(d.pct!=null){n=Math.max(1,Math.ceil(d.pct*100));
    line(ul,'best-match','Best '+n+'%',['Ranks in the best '+n+'% of this level by how closely the photo points to one species. A rank, not a measured accuracy.']);}
  if(d.look)line(ul,'',d.look[0],[d.look[0]+' ',I18N.nm(d.look[1])]);
  if(d.range)line(ul,'',d.range[0],d.range[0]?[d.range[0],': ',d.range[1]]:[d.range[1]]);
  d.by.forEach(function(x){g=x[0]&&gloss(x[0]);line(ul,x[0],x[1],['Raised by ',el('b',null,x[1]),x[2]||g?': ':'',x[2]||(g?g[0]:'')]);});
  d.kept.forEach(function(x){line(ul,x[0],x[1],['Kept by ',el('b',null,x[1])]);});
  return ul.children.length;
}
return {fill:fill};
})();
