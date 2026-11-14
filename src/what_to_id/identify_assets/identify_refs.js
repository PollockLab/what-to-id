// One candidate species in the compare panel: its name, a row of its iNaturalist reference photos to step through, a small BC
// range map with the record's point on it, and the first sentence of its Wikipedia summary.
// IdentifyRefs(ctx), ctx {T (IdentifyText), size(url, name), link(a) (sends a link to the shared iNaturalist tab),
// range() the IdentifyRanges or null}. row(t, role, i) is the section for taxon t (iNaturalist API v1, whole) in the role's
// words, for the record with index i; paint(sec) draws its map once it is on the page; step(sec, d) moves its photos by one;
// repaint() draws the maps again (the theme changed).
var IdentifyRefs=(function(){
'use strict';
var TAXON='https://www.inaturalist.org/taxa/',MAXP=12;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function svg(d){var NS='http://www.w3.org/2000/svg',s=document.createElementNS(NS,'svg'),p=document.createElementNS(NS,'path');
  s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');p.setAttribute('d',d);s.appendChild(p);return s;}
// the first sentence of iNaturalist's Wikipedia summary as text, at most 140 characters, and the whole summary; null without one
function gist(html){
  var d=html?(new DOMParser().parseFromString(html,'text/html').body.textContent||'').trim():'',s=(/^.*?[.!?](?=\s|$)/.exec(d)||[d])[0];
  return d?[s.length>140?s.slice(0,139).trimEnd()+'…':s,d]:null;
}
return function(ctx){
  var T=ctx.T,maps=[],slow=matchMedia('(prefers-reduced-motion: reduce)');
  function strip(t,role){
    var ps=(t.taxon_photos||[]).map(function(x){return x.photo;}).filter(Boolean).slice(0,MAXP),w=el('div','cpphw'),s=el('div','cpph');
    if(!ps.length&&t.default_photo)ps=[t.default_photo];
    if(!ps.length)return [el('p','muted cpnone',T.noPhoto),null];
    s.tabIndex=0;s.setAttribute('role','group');s.setAttribute('aria-label',T.refGroup(t.name));
    ps.forEach(function(p){var img=el('img');img.loading='lazy';img.alt=T.refPhoto(role,t.name);
      img.src=ctx.size(p.url||p.square_url,'medium');img.title='Photo '+(p.attribution||'');s.appendChild(img);});
    var b=[['prv',T.prevPhotos,'M15 5l-7 7 7 7',-1],['nxt',T.nextPhotos,'M9 5l7 7-7 7',1]].map(function(x){
      var e=el('button','cpflip '+x[0]);e.type='button';e.setAttribute('aria-label',x[1]);e.tabIndex=-1;e.appendChild(svg(x[2]));
      e.onclick=function(ev){ev.stopPropagation();step(s,x[3]);};return e;});
    function edge(){b[0].hidden=s.scrollLeft<4;b[1].hidden=s.scrollLeft+s.clientWidth>=s.scrollWidth-4;}
    s.addEventListener('scroll',edge,{passive:true});setTimeout(edge,0);
    w.append(s,b[0],b[1]);w.edge=edge;
    return [w,s];
  }
  function step(s,d){
    var k=s.firstElementChild;if(!k)return;
    s.scrollBy({left:d*(k.offsetWidth+6),behavior:slow.matches?'auto':'smooth'});
  }
  function row(t,role,i){
    var c=el('section','cpref'),head=el('div','cphead'),h=el('h3'),tools=el('div','cptools'),body=el('div','cprow'),ph=strip(t,role),a,
      g=gist(t.wikipedia_summary),m=el('div','cpmap'),cv=el('canvas'),cap=el('p','cpmapcap');
    h.append(el('span','muted',role+' '),I18N.nm(t.name,t.preferred_common_name));if(t.preferred_common_name&&I18N.names==='both')h.append(' ',el('span','muted',t.preferred_common_name));
    if(t.id){a=el('a',null,T.taxonPage);a.href=TAXON+t.id;ctx.link(a);a.setAttribute('aria-label',T.taxonPageOf(t.name));tools.append(IdentifyNarrow.copy(t.name),a);}
    if(ph[1])tools.prepend(el('span','muted cpn',T.photos(ph[1].childElementCount)));
    body.append(ph[0]);m.append(cv,cap);body.append(m);
    head.append(h,tools);c.append(head,body);
    if(g){var w=el('p','cpsum muted',g[0]);w.title=g[1];c.append(w);}
    c.step=function(d){if(ph[1])step(ph[1],d);};
    c.paint=function(){
      var r=ctx.range(),x=r&&r.mini(cv,i,t.name);
      if(ph[0].edge)ph[0].edge();
      m.classList.toggle('none',!x);cv.hidden=!x;
      if(!x){cap.textContent=T.rangeNone;return;}
      cv.setAttribute('role','img');cv.setAttribute('aria-label',T.rangeLabel(t.name,x.inside));
      cap.textContent=x.inside?T.rangeIn:T.rangeOut;if(maps.indexOf(c)<0)maps.push(c);
    };
    return c;
  }
  return {row:row,paint:function(c){c.paint();},step:function(c,d){if(c)c.step(d);},
    repaint:function(){maps=maps.filter(function(c){return c.isConnected;});maps.forEach(function(c){c.paint();});}};
};
})();
