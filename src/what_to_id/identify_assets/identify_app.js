// The Identify page: every pool record at its level (pool-levels.bin, format in pool_levels.py) as a grid
// of cards under one tab per level. The selection is the map's: MapFilter's keep and rest over the pool shards, the group chips' verdict,
// the area and the lasso's ids (SpaceMask). Up to PER_SPECIES cards per species, best first, are drawn at view time;
// their photos come from iNaturalist 200 ids to a request as the cards are drawn, a batch at a time as the list scrolls.
(function(){
'use strict';
var CFG=IDENTIFY_CONFIG,L=EmbeddingsLayout,Meta=AtlasSearchMeta,PER_SPECIES=3,LIMIT=12,STEPS=16,NO_LOOK=65535,NOTAX=65535,LS='wtid-identify-level',IO=null,T=0;
var MAP=new URL(CFG.mapUrl,location.href).href,nf=new Intl.NumberFormat('en-CA'),OBS='https://www.inaturalist.org/observations/';
var META=null,TAXA=null,P=null,LEVEL=null,Q=null,LOOKS=null,MF=null,TF=null,PEND=null,S={},KEEPIDS=null,SUBIDS=null,AREA='',VIEW='',SEL=null,view=[],shown=0,drawn=0,LV=0,LINKS=[],BI=0,CACHE=new Map();
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function status(t){$('status').textContent=t;}
function get(url){return fetch(url).then(function(r){
  if(!r.ok)throw new Error('Could not load '+String(url).split('/').pop().split('?')[0]+' ('+r.status+')');
  return r.arrayBuffer();}).then(L.gunzip);}

// The records the selection keeps, 1 each in SEL: MapFilter.keep for the taxa, the group chips' verdict, MapFilter.rest
// for the dates, months, show only and accuracy, then the area, the map's viewport and the lasso's ids.
function select(){
  var n=P.n,i;
  SEL=MF.keep(TF,MF.groupSet(S,TF),P.tax,P.grp,n,new Uint8Array(n));
  var ok=CH.groupPass(S.groups,META.groups,!!TF.inc);
  for(i=0;i<n;i++)if(!ok[P.grp[i]])SEL[i]=0;
  MF.rest(S,P.obs,P.up,P.flags,n,SEL);
  var I=SpaceMask.areaIndex(AREA),V=SpaceMask.areaIndex(VIEW),m=[I&&SpaceMask.area(I,P),V&&SpaceMask.area(V,P),KEEPIDS&&SpaceMask.ids(KEEPIDS,P),SUBIDS&&SpaceMask.ids(SUBIDS,P)];
  m.forEach(function(v){if(v)for(var j=0;j<n;j++)SEL[j]&=v[j];});
}
// Per level the kept records best first (quantized score, a bucket each), then at most PER_SPECIES of any one taxon.
function build(){
  var n=P.n,c=new Uint32Array(5*STEPS+1),i,k,lv;
  for(i=0;i<n;i++)if(SEL[i]&&LEVEL[i])c[LEVEL[i]*STEPS+Q[i]+1]++;
  for(k=1;k<c.length;k++)c[k]+=c[k-1];
  var at=c.slice(),order=new Int32Array(c[c.length-1]);
  for(i=0;i<n;i++)if(SEL[i]&&LEVEL[i])order[at[LEVEL[i]*STEPS+Q[i]]++]=i;
  var out=[],total=[];
  for(lv=1;lv<=4;lv++){
    var taken=new Uint8Array(65536),rows=[],a=c[lv*STEPS],b=c[(lv+1)*STEPS];
    for(k=b-1;k>=a;k--){i=order[k];if(taken[P.tax[i]]<PER_SPECIES){taken[P.tax[i]]++;rows.push(i);}}
    out[lv]=rows;total[lv]=b-a;
  }
  view=out;S.total=total;
}
function looksOf(i){
  if(!LOOKS)return null;
  var v=LOOKS.lo[i]|LOOKS.hi[i]<<8;
  return v===NO_LOOK?null:LOOKS.names[v];
}
// Under a card's photo: its label, and for a close call or a record above species what it looks like.
function title(i,lv){
  var t=P.tax[i]!==NOTAX&&TAXA[P.tax[i]],box=el('div','title'),nm=el('div','name'),lk=looksOf(i),l=el('div','look');
  nm.appendChild(el('i',null,t?t[0]:'Unidentified'));
  box.appendChild(nm);
  if(t&&t[1])box.appendChild(el('div','com',t[1]));
  if(lv===3&&lk)l.append('Probably ',el('i',null,lk));
  else if(lv===2&&lk)l.append('Often confused with ',el('i',null,lk));
  if(l.firstChild)box.appendChild(l);
  return box;
}
// A card tells the map which record it is on (hover and focus) and which was picked (click); links are left alone.
function tell(type,id){if(parent!==window)parent.postMessage({type:type,id:id},location.origin);}
function card(i,lv){
  var id=P.id[i],li=el('li','card'),ph=el('div','ph','Loading photo'),w=el('a','when','Date and place…'),a=el('a','btn','Identify');
  li.dataset.id=id;li.tabIndex=0;
  w.href=OBS+id;w.target='_blank';w.rel='noopener';
  a.href=IdentifyLinks.batches([id])[0].url;a.target='_blank';a.rel='noopener';a.setAttribute('aria-label','Identify this record on iNaturalist');
  li.append(ph,title(i,lv),w,a);
  li.onmouseenter=li.onfocus=function(){tell('wtid-focus',id);};
  li.onclick=function(e){if(!e.target.closest('a'))tell('wtid-record',id);};
  li.onkeydown=function(e){if(e.target===li&&(e.key==='Enter'||e.key===' ')){e.preventDefault();tell('wtid-record',id);}};
  return li;
}
// Fills the photos of the cards just drawn; a record that left Needs ID or iNaturalist since the pool was built drops out.
function photos(lis){
  var ids=lis.map(function(li){return +li.dataset.id;});
  Meta.fetchObservations(ids,function(u){return fetch(u);},CACHE).then(function(){
    lis.forEach(function(li){
      if(!li.isConnected)return;
      var o=CACHE.get(+li.dataset.id);
      if(!o||o.quality_grade!=='needs_id'){li.remove();return;}
      var p=o.photos&&o.photos[0],ph=li.querySelector('.ph'),w=li.querySelector('.when');
      ph.textContent='';
      if(p){var img=el('img');img.loading='lazy';img.alt='Photo of '+li.querySelector('i').textContent;
        img.src=String(p.url).replace('/square.','/medium.');ph.appendChild(img);}else ph.textContent='No photo on iNaturalist now';
      w.textContent=(o.observed_on||'Date unknown')+' · '+(o.place_guess||'Place unknown');w.title=w.textContent;
    });
  }).catch(function(e){status('Could not load the photos: '+e.message);});
}
// The next LIMIT cards of the chosen level; the button is the scroll sentinel and stays as the fallback.
function more(){
  var rows=view[LV]||[],ol=$('grid'),to=Math.min(rows.length,shown),lis=[],b=$('more');
  for(var j=drawn;j<to;j++){var li=card(rows[j],LV);ol.appendChild(li);lis.push(li);}
  drawn=to;
  b.hidden=rows.length<=to;b.textContent='Show more ('+nf.format(rows.length-to)+' left)';
  if(lis.length)photos(lis);
  if(IO&&!b.hidden){IO.unobserve(b);IO.observe(b);}  // observe again: a tall pane may still show it
}
// "Identify these": the listed records of the level, in batches of 200 as the map's button steps through them.
function batch(){
  var all=view[LV]||[],rows=all.slice(0,IdentifyLinks.MAX_IDS);
  LINKS=rows.length?IdentifyLinks.batches(rows.map(function(i){return P.id[i];})):[];BI=0;
  $('batch').hidden=!rows.length;
  if(rows.length){$('go').textContent='Identify these '+nf.format(rows.length);  // the tab already holds the level's total
    $('go').title=rows.length<all.length?'The first '+nf.format(rows.length)+' of '+nf.format(all.length)+' listed, up to '+PER_SPECIES+' per species':'Up to '+PER_SPECIES+' per species';}
  step(0);
}
function step(d){
  BI=Math.max(0,Math.min(LINKS.length-1,BI+d));
  if(LINKS.length)$('go').href=LINKS[BI].url;
  $('step').textContent=LINKS.length>1?(BI+1)+'/'+LINKS.length:'';$('step').title='Batch '+(BI+1)+' of '+LINKS.length;
  $('step').hidden=$('prev').hidden=$('next').hidden=LINKS.length<2;
  $('prev').disabled=BI===0;$('next').disabled=BI>=LINKS.length-1;
}
// Draws the chosen level from its first card.
function paint(){
  var x=CFG.levels.filter(function(l){return l[0]===LV;})[0];
  [].forEach.call($('tabs').children,function(t){var on=+t.dataset.lv===LV;t.setAttribute('aria-selected',on);t.tabIndex=on?0:-1;});
  $('desc').textContent=x[2];$('panel').setAttribute('aria-labelledby','tab'+LV);
  $('grid').textContent='';shown=LIMIT;drawn=0;
  empty();
  more();batch();scrollTo(0,0);
}
function counts(){
  [].forEach.call($('tabs').children,function(t){var n=S.total[+t.dataset.lv]||0;t.lastChild.textContent=nf.format(n);t.classList.toggle('zero',!n);});
}
// An empty level here points at the levels that do have records, rather than a dead end.
function empty(){
  var box=$('none'),others=CFG.levels.filter(function(l){return l[0]!==LV&&S.total[l[0]];});
  box.hidden=!!(view[LV]||[]).length;box.textContent='';if(box.hidden)return;
  box.append(others.length?'None at this level here. Try ':'No records here: zoom out or widen the filters.');
  others.forEach(function(l,k){var b=el('button',null,l[1]+' ('+nf.format(S.total[l[0]])+')');b.type='button';
    b.onclick=function(){choose(l[0]);};box.append(k?(k===others.length-1?' or ':', '):'',b);});
  if(others.length)box.append('.');
}
// The chosen level is kept in the hash (under a key the selection does not use) and in localStorage.
function choose(lv){
  LV=lv;
  try{localStorage.setItem(LS,lv);}catch(e){}
  var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf('lvl=')!==0;});t.push('lvl='+lv);
  history.replaceState(null,'','#'+t.join('&'));  // no hashchange, so no refresh
  paint();
}
function saved(){
  var m=/(?:^|&)lvl=(\d)/.exec(location.hash.slice(1)),v=m?+m[1]:0;
  try{v=v||+localStorage.getItem(LS);}catch(e){}
  return CFG.levels.some(function(l){return l[0]===v;})?v:0;
}
// With no saved level: Close calls, or the first level that has records.
function first(){
  if(S.total[2])return 2;
  return (CFG.levels.filter(function(l){return S.total[l[0]];})[0]||CFG.levels[1])[0];
}
function tabs(){
  var box=$('tabs');
  CFG.levels.forEach(function(x){
    var t=el('button','tab'),n=el('b',null,'');t.type='button';t.id='tab'+x[0];t.dataset.lv=x[0];
    t.setAttribute('role','tab');t.setAttribute('aria-controls','panel');t.append(el('span',null,x[1]),n);
    t.onclick=function(){if(P)choose(x[0]);};
    box.appendChild(t);
  });
  box.onkeydown=function(e){
    var k=['ArrowLeft','ArrowRight','Home','End'].indexOf(e.key),all=[].slice.call(box.children);
    if(k<0)return;e.preventDefault();
    var at=all.indexOf(document.activeElement),to=k===2?0:k===3?all.length-1:(at+(k?1:-1)+all.length)%all.length;
    all[to].focus();all[to].click();
  };
  IO=window.IntersectionObserver&&new IntersectionObserver(function(es){
    if(es.some(function(x){return x.isIntersecting;})){shown+=LIMIT;more();}},{rootMargin:'400px'});
  $('more').onclick=function(){shown+=LIMIT;more();};
  $('prev').onclick=function(){step(-1);};$('next').onclick=function(){step(1);};
}
function refresh(){
  select();build();
  var kept=0;
  for(var i=0;i<P.n;i++)if(SEL[i])kept++;
  S.kept=kept;
  // the leading number is the in-view count, which the split view's "to identify" reads
  status(nf.format(kept)+(VIEW?' in view':' records')+' · '+PER_SPECIES+' per species');
  counts();
  if(!LV)LV=saved()||first();
  paint();
}
// The map's viewport moves often: one refresh once it rests for a moment, on a frame.
function soon(){clearTimeout(T);T=setTimeout(function(){requestAnimationFrame(function(){if(P)refresh();});},100);}
// A selection: the dates, months, groups, show only, accuracy and taxa out of a hash string; the area only when asked.
function take(str,withArea){
  var r=MF.read(new URLSearchParams(str));
  ['up','lo','hi','months','groups','only','acc','picks'].forEach(function(k){S[k]=r[k];});
  if(withArea)AREA=r.area;
  TF=TX.filter(TAXA,S.picks);
  if(P)refresh();
}
function key(){return MF?MF.write(S).join('&'):'';}
function idsOf(){var out=[];for(var i=0;i<P.n;i++)if(SEL[i])out.push(P.id[i]);return out;}
function inbox(){
  addEventListener('message',function(e){
    var d=e.data;if(e.origin!==location.origin||e.source!==parent||!d)return;
    if(d.type==='wtid-area'&&typeof d.area==='string'){AREA=d.area;if(P)refresh();}
    else if(d.type==='wtid-view'&&typeof d.area==='string'){if(d.area!==VIEW){VIEW=d.area;soon();}}  // '' is no cut
    else if(d.type==='wtid-keep'&&(d.ids===null||d.ids instanceof Uint32Array)){KEEPIDS=d.ids&&d.ids.slice().sort();if(P)refresh();}
    else if(d.type==='wtid-subset'&&(d.ids===null||Array.isArray(d.ids))){SUBIDS=d.ids&&Uint32Array.from(d.ids).sort();if(P)refresh();}  // the photo search's hits
  });
  MapFilter.sync({key:key,apply:function(str){if(MF)take(str,false);else PEND=str;},hash:false});
  addEventListener('hashchange',function(){take(location.hash.slice(1),true);});
}
function looks(buf){
  var dv=new DataView(buf),size=dv.getUint32(0,true),n=P.n;
  if(buf.byteLength!==4+size+2*n)throw new Error('the look-alike file holds '+buf.byteLength+' bytes, expected '+(4+size+2*n));
  return {names:JSON.parse(new TextDecoder().decode(new Uint8Array(buf,4,size))).names,
    lo:new Uint8Array(buf,4+size,n),hi:new Uint8Array(buf,4+size+n,n)};
}
async function load(){
  status('Reading the map data…');
  var html=await fetch(MAP).then(function(r){if(!r.ok)throw new Error('Could not load the map page ('+r.status+')');return r.text();});
  META=L.parseMapMeta(html);
  var q=String(META.shards[0].file).split('?')[1],suffix=q?'?'+q:'';
  var taxa=get(new URL(META.taxa,MAP)).then(function(b){return JSON.parse(new TextDecoder().decode(b));});
  var shards=Promise.all(META.shards.map(function(s){return get(new URL(s.file,MAP)).then(function(b){return L.decodeShard(b,s.n);});}));
  var lev=get(new URL('pool-levels.bin'+suffix,MAP)),lk=get(new URL('pool-levels-looks.bin'+suffix,MAP)).catch(function(){return null;});
  status('Downloading the records…');
  var d=await Promise.all([shards,taxa,lev,lk]);
  P=L.pool(d[0],META.bbox);TAXA=d[1];
  var raw=new Uint8Array(d[2]);
  if(raw.length!==P.n)throw new Error('the levels file holds '+raw.length+' records, the map '+P.n);
  LEVEL=raw.map(function(v){return v&15;});Q=raw.map(function(v){return v>>4;});
  LOOKS=d[3]&&looks(d[3]);
  MF=MapFilter(META);
  take(location.hash.slice(1),AREA==='');
  if(PEND!==null){take(PEND,false);PEND=null;}
  window.__identify={ids:idsOf,view:function(){return view.map(function(r){return r&&Array.from(r.map(function(i){return P.id[i];}));});},
    total:function(){return S.total;},level:function(){return LV;},refresh:function(){var t=performance.now();select();build();return performance.now()-t;}};
}
tabs();inbox();
load().catch(function(e){status('Could not load the records: '+e.message);});
})();
