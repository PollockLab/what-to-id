// The Identify page: every pool record at its level (pool-levels.bin, format in pool_levels.py) as a grid
// of cards under one tab per level. The selection is the map's: MapFilter's keep and rest over the pool shards, the group chips' verdict,
// the area and the lasso's ids (SpaceMask). Up to PER_SPECIES cards per species, best first, are drawn at view time;
// their photos come from iNaturalist 200 ids to a request as the cards are drawn, a batch at a time as the list scrolls.
(function(){
'use strict';
var CFG=IDENTIFY_CONFIG,L=EmbeddingsLayout,Meta=AtlasSearchMeta,PER_SPECIES=3,LIMIT=12,STEPS=16,NO_LOOK=65535,NOTAX=65535,LS='wtid-identify-level',IO=null,T=0,TK=0,AB=null;
var MAP=new URL(CFG.mapUrl,location.href).href,nf=new Intl.NumberFormat('en-CA'),OBS='https://www.inaturalist.ca/observations/';
var TAB=[],SUBK=[],NK=1,KIND=null,SUB=null,KF=0,KC=[],UF=null,UON=false,MINE=[],CMP=null,SEEN='wtid-identify-seen';
// CFG.merge: the kinds (levels) a tab shows, in order; SUBK a kind's place in its tab
Object.keys(CFG.merge).forEach(function(t){CFG.merge[t].forEach(function(k,j){TAB[k]=+t;SUBK[k]=j;});NK=Math.max(NK,CFG.merge[t].length);});
var META=null,SYNC=null,MORE=new Map(),TAXA=null,P=null,BYID=null,LEVEL=null,Q=null,LOOKS=null,R=null,MF=null,TF=null,PEND=null,S={},KEEPIDS=null,SUBIDS=null,AREA='',VIEW='',SEL=null,view=[],shown=0,drawn=0,LV=0,LINKS=[],BI=0,ONE='',CACHE=new Map(),FIRST=null,SHOWN,STAY=false,X=null;
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function status(t){$('status').textContent=t;}
// A GoatCounter event when the page has its script (page_identify --goatcounter); never a login or record id.
function track(name){var g=window.goatcounter;if(g&&g.count)try{g.count({path:'identify/'+name,title:name,event:true});}catch(e){}}
function get(url){return fetch(url).then(function(r){
  if(!r.ok)throw new Error('Could not load '+String(url).split('/').pop().split('?')[0]+' ('+r.status+')');
  return r.arrayBuffer();}).then(L.gunzip);}

// The records the selection keeps, 1 each in SEL: MapFilter.keep for the taxa, the group chips' verdict, MapFilter.rest
// for the dates, months, show only and accuracy, then the area, the map's viewport, the lasso's ids and the User filter.
function select(){
  var n=P.n,i;UF.sync(P);
  SEL=MF.keep(TF,MF.groupSet(S,TF),P.tax,P.grp,n,new Uint8Array(n));
  var ok=CH.groupPass(S.groups,META.groups,!!TF.inc);
  for(i=0;i<n;i++)if(!ok[P.grp[i]])SEL[i]=0;
  MF.rest(S,P.obs,P.up,P.flags,n,SEL);
  var I=SpaceMask.areaIndex(AREA),V=SpaceMask.areaIndex(VIEW),m=[I&&SpaceMask.area(I,P),V&&SpaceMask.area(V,P),KEEPIDS&&SpaceMask.ids(KEEPIDS,P),SUBIDS&&SpaceMask.ids(SUBIDS,P)];
  m.forEach(function(v){if(v)for(var j=0;j<n;j++)SEL[j]&=v[j];});
  for(i=0;i<n;i++)if(SEL[i]&&UF.drop(i))SEL[i]=0;
}
// Per level the kept records best first: each kind of the tab in CFG.merge's
// order, then the quantized score (a bucket each), newest (highest id) first within a bucket; then at most PER_SPECIES of any one
// taxon, none cut when the level holds one taxon only. The kind control (KF) keeps one kind of its tab; KC counts the kinds. MORE: for the first card of a cut taxon, how many records it left out.
// With the range file (R), a level's records also pass its outside-its-range chip.
// Rows in ascending id: each shard's rows are id-sorted, so a merge of the shards.
function byId(P){
  var s=P.start,k=s.length-1,pos=s.slice(0,k),out=new Uint32Array(P.n),t,j,b;
  for(t=0;t<P.n;t++){b=-1;for(j=0;j<k;j++)if(pos[j]<s[j+1]&&(b<0||P.id[pos[j]]<P.id[pos[b]]))b=j;out[t]=pos[b]++;}
  return out;
}
function on(i){return SEL[i]&&LEVEL[i]&&(!R||R.pass(i,LEVEL[i]))&&(!X||X.pass(i));}
// Under My taxa first the user's genera lead each level, each kind in turn, then the rest; MINE: how many cards they are, -1 without the mode.
function build(){
  var n=P.n,W=2*NK*STEPS,c=new Uint32Array(6*W+1),key=new Uint16Array(n),rk=UF.ranked(),i,k,lv;
  for(i=0;i<n;i++)if(on(i)){key[i]=LEVEL[i]*W+(rk&&UF.mine(i)?NK*STEPS:0)+(NK-1-SUB[i])*STEPS+Q[i];c[key[i]+1]++;}
  for(k=1;k<c.length;k++)c[k]+=c[k-1];
  var at=c.slice(),order=new Int32Array(c[c.length-1]);
  for(k=0;k<n;k++){i=BYID[k];if(on(i))order[at[key[i]]++]=i;}
  var out=[],total=[];MORE.clear();KC=[];
  for(lv=1;lv<=5;lv++){
    // the cut is per kind, so a merged tab lists each kind's level list in turn, as pool_levels writes them
    var tot=new Uint32Array(65536*NK),taken=new Uint32Array(65536*NK),rows=[],a=c[lv*W],b=c[(lv+1)*W],nd=[],cut,t,kf=KF&&TAB[KF]===lv?KF:0;
    for(k=a;k<b;k++){i=order[k];KC[KIND[i]]=(KC[KIND[i]]||0)+1;if(kf&&KIND[i]!==kf){order[k]=-1;continue;}
      if(!tot[SUB[i]*65536+P.tax[i]]++)nd[SUB[i]]=(nd[SUB[i]]||0)+1;}
    for(k=b-1;k>=a;k--){i=order[k];if(i<0)continue;t=SUB[i]*65536+P.tax[i];cut=nd[SUB[i]]===1?Infinity:PER_SPECIES;
      if(taken[t]<cut){rows.push(i);if(!taken[t]++&&tot[t]>cut)MORE.set(i,tot[t]-cut);}}
    out[lv]=rows;total[lv]=b-a;
    for(k=0;rk&&k<rows.length&&UF.mine(rows[k]);k++);MINE[lv]=rk?k:-1;
  }
  view=out;S.total=total;
}
function looksOf(i){
  if(!LOOKS)return null;
  var v=LOOKS.lo[i]|LOOKS.hi[i]<<8;
  return v===NO_LOOK?null:LOOKS.names[v];
}
// Under a card's photo: its label, and for a close call, a likely mislabel or a record above species what it looks like.
function title(i,lv){
  var t=P.tax[i]!==NOTAX&&TAXA[P.tax[i]],box=el('div','title'),nm=el('div','name'),lk=looksOf(i),l=el('div','look');
  nm.appendChild(el('i',null,t?t[0]:'Unidentified'));
  box.appendChild(nm);
  if(t&&t[1])box.appendChild(el('div','com',t[1]));
  if(lv===3&&lk)l.append('Probably ',el('i',null,lk));
  else if((lv===2||lv===5)&&lk)l.append('Looks more like ',el('i',null,lk));
  if(l.firstChild)box.appendChild(l);
  return box;
}
// A card tells the map which record it is on (hover and focus) and which was picked (click); links are left alone.
function tell(type,id){if(parent!==window)parent.postMessage({type:type,id:id},location.origin);}
// "+N more <name>" on the first card of a cut species: picks that species in the shared selection, all its records.
function more_(i){
  var t=TAXA[P.tax[i]],nm=t[1]||t[0],b=el('button','sp','+'+nf.format(MORE.get(i))+' more '+nm);
  b.type='button';b.setAttribute('aria-label','Show '+nf.format(MORE.get(i))+' more records of '+nm);
  b.onclick=function(){pick([{id:t[2],not:false}]);};
  return b;
}
function pick(picks){
  if(MF){S.picks=picks;TF=TX.filter(TAXA,picks);}
  else PEND=[sel(),picks.length?'taxa='+TX.write(picks):''].filter(Boolean).join('&');  // taken once the records load
  if(parent===window)keep('taxa',TX.write(picks));  // embedded, the split page holds the address
  again();SYNC.send();
}
function card(i,lv){
  var id=P.id[i],li=el('li','card'),ph=el('div','ph','Loading photo'),w=el('a','when','Date and place…'),a=el('a','btn','Identify');
  li.dataset.id=id;li.dataset.i=i;li.tabIndex=0;
  w.href=OBS+id;w.target='_blank';w.rel='noopener';
  a.href=IdentifyLinks.batches([id])[0].url;a.target='_blank';a.rel='noopener';a.setAttribute('aria-label','Identify this record on iNaturalist');
  li.append(ph,title(i,lv),w);
  if(KIND&&CFG.merge[lv]&&!KF)li.insertBefore(el('div','kind',kindName(KIND[i])),w);
  if(UF&&UF.ranked()&&UF.mine(i))li.insertBefore(el('div','badge','Your genus'),w);
  if(MORE.has(i))li.appendChild(more_(i));
  a.addEventListener('click',function(){track('card-'+(KIND?KIND[i]:lv));});
  li.appendChild(R?R.links(a,i,lv):a);
  li.onmouseenter=li.onfocus=function(){tell('wtid-focus',id);};
  li.onclick=function(e){if(!e.target.closest('a,button'))tell('wtid-record',id);};
  li.onkeydown=function(e){if(e.target===li&&(e.key==='Enter'||e.key===' ')){e.preventDefault();tell('wtid-record',id);}};
  return li;
}
// Fills the photos of the cards just drawn; a record that left Needs ID or iNaturalist since the pool was built drops out.
function photos(lis){
  var ids=lis.map(function(li){return +li.dataset.id;});
  var sig=AB&&AB.signal;
  Meta.fetchObservations(ids,function(u){return fetch(u,{signal:sig});},CACHE).then(function(){
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
  }).catch(function(e){if(!(sig&&sig.aborted))status('Could not load the photos: '+e.message);});
}
// Where the user's genera end in the list, under My taxa first: after n cards, or before the first when none are theirs.
// MINE counts cards (after the per-species cut), so both lines say cards.
function sep(n,top){var c=nf.format(n)+(n===1?' card':' cards');
  return el('li',top?'sep top':'sep',top?'Your genera first · '+c:n?'End of your genera · '+c:'None of your genera here. The rest follow.');}
// The next LIMIT cards of the chosen level; the button is the scroll sentinel and stays as the fallback.
function more(){
  var rows=view[LV]||[],ol=$('grid'),to=Math.min(rows.length,shown),lis=[],b=$('more');
  if(!drawn&&MINE[LV]>0)ol.appendChild(sep(MINE[LV],1));
  for(var j=drawn;j<to;j++){if(j===MINE[LV])ol.appendChild(sep(j));var li=card(rows[j],LV);ol.appendChild(li);lis.push(li);}
  drawn=to;
  b.hidden=rows.length<=to;b.textContent='Show more ('+nf.format(rows.length-to)+' left)';
  if(lis.length){photos(lis);if(CMP&&LOOKS)CMP.fill(lis);}
  if(IO&&!b.hidden){IO.unobserve(b);IO.observe(b);}  // observe again: a tall pane may still show it
}
// "Identify N listed", or with more than one batch "Identify 200 · batch 2 of 50": the button
// names the batch it opens, since the arrows change only its link. Batches follow the card order.
function batch(){
  var all=view[LV]||[],t=all.n||all.length,rows=all.slice(0,IdentifyLinks.MAX_IDS),capped=rows.length<t;  // n: a first list's full length
  LINKS=rows.length?IdentifyLinks.batches(rows.map(function(i){return P.id[i];}),true):[];BI=0;
  $('batch').hidden=!rows.length;$('cap').hidden=LINKS.length<2;
  ONE=capped?'Identify the first '+nf.format(rows.length)+' of '+nf.format(t):'Identify '+nf.format(rows.length)+' listed';
  $('cap').textContent=(capped?'The first '+nf.format(rows.length)+' of '+nf.format(t):nf.format(rows.length))+
    ' listed, in the order shown, '+IdentifyLinks.BATCH+' per batch';
  $('go').title='Up to '+PER_SPECIES+' per species';
  step(0);
}
function step(d){
  BI=Math.max(0,Math.min(LINKS.length-1,BI+d));
  var b=LINKS[BI];
  if(b){$('go').href=b.url;$('go').textContent=LINKS.length>1?'Identify '+nf.format(b.n)+' · batch '+(BI+1)+' of '+LINKS.length:ONE;}
  $('prev').hidden=$('next').hidden=LINKS.length<2;
  $('prev').disabled=BI===0;$('next').disabled=BI>=LINKS.length-1;
}
// Draws the chosen level from its first card; STAY (the records replacing the first list) keeps the cards drawn and the scroll.
function paint(){
  var x=CFG.levels.filter(function(l){return l[0]===LV;})[0];
  [].forEach.call($('tabs').children,function(t){var on=+t.dataset.lv===LV;t.setAttribute('aria-selected',on);t.tabIndex=on?0:-1;});
  $('desc').textContent=x[2];kinds();$('panel').setAttribute('aria-labelledby','tab'+LV);
  if(AB)AB.abort();AB=new AbortController();  // the cards redrawn below replace those whose photos are still loading
  $('grid').textContent='';shown=STAY?Math.max(LIMIT,drawn):LIMIT;drawn=0;
  var kf=KF&&TAB[KF]===LV;  // the controls count the chosen kind, as the cards show it
  if(R)R.draw(kf?KF:LV,SEL,kf?KIND:LEVEL);
  if(X)X.draw(kf?KF:LV,SEL,kf?KIND:LEVEL);
  empty();
  more();batch();if(!STAY)scrollTo(0,0);STAY=false;
}
function redraw(){build();counts();paint();}
function kindName(k){return (CFG.kinds.filter(function(x){return x[0]===k;})[0]||[0,''])[1];}
// The kind control (All, then each kind) over a tab that shows several kinds; hash kind=.
function kinds(){
  var box=$('kind'),ks=CFG.merge[LV];
  box.hidden=!ks;box.textContent='';if(!ks)return;
  var g=el('div','seg');g.setAttribute('role','radiogroup');g.setAttribute('aria-label','Kind');
  [[0,'All']].concat(ks.map(function(k){return [k,kindName(k)];})).forEach(function(x){
    var b=el('button','segb',x[1]+' '+nf.format(x[0]?KC[x[0]]||0:S.total[LV]||0)),on=KF===x[0]||(!x[0]&&TAB[KF]!==LV);
    b.type='button';if(KX[x[0]])b.dataset.explain=KX[x[0]];b.setAttribute('role','radio');b.setAttribute('aria-checked',String(on));b.tabIndex=on?0:-1;
    b.onclick=function(){KF=x[0];keep('kind',KF||'');track('kind-'+KF);if(MF)redraw();else{SHOWN=null;early();}};
    g.appendChild(b);});
  g.onkeydown=function(e){var d={ArrowLeft:-1,ArrowRight:1}[e.key],all=[].slice.call(g.children),at=all.indexOf(document.activeElement);
    if(!d||at<0)return;e.preventDefault();all[(at+d+all.length)%all.length].click();
    var c=$('kind').querySelector('[aria-checked=true]');if(c)c.focus();};  // the click drew the control again
  box.append(el('span',null,'Kind: '),g);
}
function counts(){
  [].forEach.call($('tabs').children,function(t){var n=S.total[+t.dataset.lv]||0;t.lastChild.textContent=nf.format(n);t.classList.toggle('zero',!n);});
}
// An empty level here points at the levels that do have records, rather than a dead end.
function empty(){
  var box=$('none'),others=CFG.levels.filter(function(l){return l[0]!==LV&&S.total[l[0]];});
  box.hidden=!!(view[LV]||[]).length;box.textContent='';if(box.hidden)return;
  if(!others.length&&UF&&UF.active()&&UF.mode()==='observer'){  // the map's advice (zoom out) does not fit here
    var f=el('button',null,'Show My taxa first instead');f.type='button';f.onclick=function(){UF.first();};
    box.append('No records observed by '+S.user+' here. ',f);return;}
  box.append(others.length?'None at this level here. Try ':'No records here: zoom out or widen the filters.');
  others.forEach(function(l,k){var b=el('button',null,l[1]+' ('+nf.format(S.total[l[0]])+')');b.type='button';
    b.onclick=function(){choose(l[0]);};box.append(k?(k===others.length-1?' or ':', '):'',b);});
  if(others.length)box.append('.');
}
// The chosen level is kept in the hash (under a key the selection does not use) and in localStorage.
function keep(k,v){
  var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf(k+'=')!==0;});if(v)t.push(k+'='+v);
  history.replaceState(null,'','#'+t.join('&'));  // no hashchange, so no refresh
}
function choose(lv){
  LV=lv;track('tab-'+lv);
  try{localStorage.setItem(LS,lv);}catch(e){}
  keep('lvl',lv);
  if(R){R.level(lv);redraw();}else paint();
}
function saved(){
  var m=/(?:^|&)lvl=(\d)/.exec(location.hash.slice(1)),v=m?+m[1]:0;
  try{v=v||+localStorage.getItem(LS);}catch(e){}
  return CFG.levels.some(function(l){return l[0]===v;})?v:0;
}
// With no saved level: Easy confirms on a first visit (a quick start), else Might be wrong, else the first level that has records.
function first(){
  var seen=true;try{seen=!!localStorage.getItem(SEEN);localStorage.setItem(SEEN,'1');}catch(e){}
  if(!seen&&S.total[1])return 1;
  if(S.total[5])return 5;
  return (CFG.levels.filter(function(l){return S.total[l[0]];})[0]||CFG.levels[1])[0];
}
// each level tab explains itself from the glossary, by level number
var XK=[0,'level-clear-matches','level-close-calls','level-narrow-it-down','level-odd-shots','level-might-be-wrong'],
  KX=[0,0,'level-close-calls',0,'level-odd-shots','level-might-be-mislabelled'];  // a kind's own entry
function tabs(){
  var box=$('tabs');
  CFG.levels.forEach(function(x){
    var t=el('button','tab'),n=el('b',null,'');t.type='button';t.id='tab'+x[0];t.dataset.lv=x[0];
    t.dataset.explain=XK[x[0]];t.setAttribute('role','tab');t.setAttribute('aria-controls','panel');t.append(el('span',null,x[1]),n);
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
  $('unpick').onclick=function(){pick([]);};
  $('go').addEventListener('click',function(){track('batch-'+LV+(KF?'-'+KF:''));});
  $('prev').onclick=function(){step(-1);};$('next').onclick=function(){step(1);};
}
function refresh(){
  select();build();
  var kept=0,lev=0;
  for(var i=0;i<P.n;i++)if(SEL[i]){kept++;if(LEVEL[i])lev++;}
  S.kept=kept;
  // the leading number is the in-view count, which the split view's "to identify" reads
  status(nf.format(kept)+(VIEW?' in view':' records')+' · '+nf.format(lev)+' ');
  var why=el('a',null,'in a level');why.href='#about';why.onclick=function(e){e.preventDefault();$('about').open=true;$('about').scrollIntoView({block:'nearest'});};
  $('status').append(why,MORE.size?' · '+PER_SPECIES+' per species':'');
  counts();$('unpick').hidden=parent!==window||!S.picks.length;
  if(!LV)LV=saved()||first();
  paint();
}
// The map's viewport moves often: one refresh once it rests for a moment, on a frame.
function soon(){clearTimeout(T);T=setTimeout(function(){requestAnimationFrame(again);},100);}
function again(){if(MF)refresh();else if(FIRST)early();}
// Until the records load: the selection so far, as MapFilter writes it.
function sel(){return PEND!==null?PEND:MapFilter.tokens(location.hash);}
// The first lists (pool-levels-first.bin, format in pool_levels.py) as pool-like columns, P, TAXA and LOOKS until the records load.
function firstOf(F){
  var id=[],tax=[],lk=[];
  Object.keys(F.s).forEach(function(k){var s=F.s[k];s.rows=s.rows.map(function(r,lv){
    var out=r.map(function(x){var i=id.length;id.push(x[0]);tax.push(x[1]);lk.push(x[2]);if(x[3])MORE.set(i,x[3]);return i;});
    out.n=s.n[lv];return out;});});
  F.P={id:id,tax:tax,n:id.length};TAXA=F.taxa;LOOKS={names:F.looks,lo:lk,hi:new Uint8Array(id.length)};  // lo holds the whole index
  FIRST=F;early();
}
// The first list of the selection while the records load, when it is one built (no filter or one group) with no area, lasso,
// photo search or range toggle, and a map view that takes in every record: the split view's map posts its view on load,
// beside a phone it is hidden and posts ''. Any other selection waits for the records.
function early(){
  var h=location.hash.slice(1),b=FIRST.bbox,I=VIEW&&SpaceMask.areaIndex(VIEW),
    s=!AREA&&!KEEPIDS&&!SUBIDS&&!/(^|&)(area|out|rg)=/.test(h)&&(!VIEW||I&&[[0,1],[2,1],[2,3],[0,3]].every(function(c){
      return MapArea.inside(I,b[c[0]],b[c[1]]);}))&&FIRST.s[sel()]||null;
  if(s===SHOWN)return;SHOWN=s;P=s&&FIRST.P;
  if(!s){view=[];$('grid').textContent='';$('none').hidden=$('more').hidden=$('batch').hidden=$('cap').hidden=true;
    [].forEach.call($('tabs').children,function(t){t.lastChild.textContent='';});status('Loading all the records for this selection…');return;}
  // a tab of several kinds starts as its first kind's list (or the chosen kind's), its count their sum
  view=s.rows.slice();S.total=s.total.slice();KC=s.total.slice();MINE=[];
  Object.keys(CFG.merge).forEach(function(tb){var ks=CFG.merge[tb];
    S.total[tb]=ks.reduce(function(x,k){return x+(s.total[k]||0);},0);view[tb]=s.rows[KF&&TAB[KF]===+tb?KF:ks[0]];});
  counts();
  if(!LV)LV=saved()||first();
  status('Showing the top records, loading all of them…');paint();
}
// A selection: the dates, months, groups, show only, accuracy and taxa out of a hash string; the area only when asked.
function take(str,withArea){
  var r=MF.read(new URLSearchParams(str));
  ['up','lo','hi','months','groups','only','acc','picks','user','umode','umin'].forEach(function(k){S[k]=r[k];});
  if(withArea)AREA=r.area;
  TF=TX.filter(TAXA,S.picks);
  if(P)refresh();
}
// The User box changed S or finished a load: standalone its part of the hash follows S, then the split view and the cards.
function user(){
  var re=/^(user|umode|umin)=/;
  if(parent===window)history.replaceState(null,'','#'+location.hash.slice(1).split('&').filter(function(x){return x&&!re.test(x);})
    .concat(MF.write(S).filter(function(x){return re.test(x);})).join('&'));
  var on=UF.active()||UF.ranked();if(on&&!UON)track('user-'+UF.mode());UON=on;
  SYNC.send();refresh();
}
function key(){return MF?MF.write(S).join('&'):PEND||'';}
function idsOf(){var out=[];for(var i=0;i<P.n;i++)if(SEL[i])out.push(P.id[i]);return out;}
function inbox(){
  addEventListener('message',function(e){
    var d=e.data;if(e.origin!==location.origin||e.source!==parent||!d)return;
    if(d.type==='wtid-area'&&typeof d.area==='string'){AREA=d.area;again();}
    else if(d.type==='wtid-view'&&typeof d.area==='string'){if(d.area!==VIEW){VIEW=d.area;soon();}}  // '' is no cut
    else if(d.type==='wtid-keep'&&(d.ids===null||d.ids instanceof Uint32Array)){KEEPIDS=d.ids&&d.ids.slice().sort();again();}
    else if(d.type==='wtid-subset'&&(d.ids===null||Array.isArray(d.ids))){SUBIDS=d.ids&&Uint32Array.from(d.ids).sort();again();}  // the photo search's hits
  });
  SYNC=MapFilter.sync({key:key,apply:function(str){if(MF){clearTimeout(TK);TK=setTimeout(function(){take(str,false);},60);}else{PEND=str;again();}},hash:false});
  addEventListener('hashchange',function(){if(MF)take(location.hash.slice(1),true);else again();});
}
function looks(buf){
  var dv=new DataView(buf),size=dv.getUint32(0,true),n=P.n;
  if(buf.byteLength!==4+size+2*n)throw new Error('the look-alike file holds '+buf.byteLength+' bytes, expected '+(4+size+2*n));
  return {names:JSON.parse(new TextDecoder().decode(new Uint8Array(buf,4,size))).names,
    lo:new Uint8Array(buf,4+size,n),hi:new Uint8Array(buf,4+size+n,n)};
}
async function load(){
  status('Reading the map data…');
  if(CFG.first)get(new URL(CFG.first,MAP)).then(function(b){if(!MF)firstOf(JSON.parse(new TextDecoder().decode(b)));}).catch(function(){});  // optional
  var html=await fetch(MAP).then(function(r){if(!r.ok)throw new Error('Could not load the map page ('+r.status+')');return r.text();});
  META=L.parseMapMeta(html);
  function file(k){var f=META.files[k];return f?get(new URL(f,MAP)):Promise.reject(new Error('the map lists no '+k+' file'));}
  var taxa=get(new URL(META.taxa,MAP)).then(function(b){return JSON.parse(new TextDecoder().decode(b));});
  var shards=Promise.all(META.shards.map(function(s){return get(new URL(s.file,MAP)).then(function(b){return L.decodeShard(b,s.n);});}));
  var lev=file('levels'),lk=file('looks').catch(function(){return null;}),  // optional: cards fill in their look-alike once it lands
    rg=file('range').catch(function(){return null;});  // optional: no range maps without it
  if(!FIRST)status('Downloading the records…');
  var d=await Promise.all([shards,taxa,lev]);
  P=L.pool(d[0],META.bbox);BYID=byId(P);TAXA=d[1];LOOKS=null;
  var raw=new Uint8Array(d[2]);
  if(raw.length!==P.n)throw new Error('the levels file holds '+raw.length+' records, the map '+P.n);
  LEVEL=raw.map(function(v){return TAB[v&15]||v&15;});KIND=raw.map(function(v){return v&15;});SUB=raw.map(function(v){return SUBK[v&15]||0;});Q=raw.map(function(v){return v>>4;});
  X=IdentifyUnconfirmed({P:P,taxa:TAXA,ranks:META.ranks,area:function(){return AREA;},redraw:redraw});
  // Not yet identified by me asks iNaturalist within the pool's extent: Identify has no map viewport of its own
  var b=META.bbox;UF=userFilter({S:S,meta:META,get:function(f){return get(new URL(f,MAP));},taxa:function(){return TAXA;},changed:user,
    bounds:function(){return {w:b[0],s:b[1],e:b[2],n:b[3]};}});
  CMP=IdentifyCompare({taxa:TAXA,tax:P.tax,look:looksOf});
  MF=MapFilter(META);
  STAY=!!SHOWN;take(location.hash.slice(1),AREA==='');
  if(PEND!==null){take(PEND,false);PEND=null;}
  $('usrbox').open=!!S.user;
  lk.then(function(b){if(!b)return;LOOKS=looks(b);
    [].forEach.call($('grid').children,function(li){var t=li.querySelector('.title');if(t)t.replaceWith(title(+li.dataset.i,LV));});
    CMP.fill([].slice.call($('grid').querySelectorAll('.card')));});
  rg.then(function(b){if(!b)return;
    R=IdentifyRanges(b,{P:P,name:function(i){return P.tax[i]!==NOTAX&&TAXA[P.tax[i]]?TAXA[P.tax[i]][0]:null;},look:looksOf,redraw:redraw});
    R.level(LV,true);redraw();});
  window.__identify={ids:idsOf,view:function(){return view.map(function(r){return r&&Array.from(r.map(function(i){return P.id[i];}));});},
    total:function(){return S.total;},levelled:function(){var n=0;for(var i=0;i<P.n;i++)if(SEL[i]&&LEVEL[i])n++;return n;},level:function(){return LV;},kind:function(){return KF;},kinds:function(){return KC.slice();},user:function(){return UF.active()||UF.ranked();},mine:function(){return MINE[LV];},ranges:function(){return !!R;},refresh:function(){var t=performance.now();select();build();return performance.now()-t;}};
}
var KD=/(?:^|&)kind=(\d)/.exec(location.hash.slice(1));KF=KD&&TAB[+KD[1]]?+KD[1]:0;
tabs();inbox();
load().catch(function(e){status('Could not load the records: '+e.message);});
})();
