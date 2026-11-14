// The Identify page: every pool record at its level (pool-levels.bin, format in pool_levels.py) as a grid
// of cards under one tab per level. The selection is the map's: MapFilter's keep and rest over the pool shards, the group chips' verdict,
// the area and the lasso's ids (SpaceMask). Up to PER_SPECIES cards per species, best first, are drawn at view time;
// their photos come from iNaturalist 200 ids to a request as the cards are drawn, a batch at a time as the list scrolls.
// With the study (CFG.study) a Batches tab comes first and is the default: it draws the study's batches (identify_study.js)
// as the same cards, pool or not, and a viewer signed in with iNaturalist (identify_inat.js) can post an ID from a card.
(function(){
'use strict';
var CFG=IDENTIFY_CONFIG,L=EmbeddingsLayout,Meta=AtlasSearchMeta,PER_SPECIES=3,LIMIT=12,STEPS=16,NO_LOOK=65535,NOTAX=65535,LS='wtid-identify-tab',IO=null,T=0,TK=0,AB=null;
var MAP=new URL(CFG.mapUrl,location.href).href,nf=new Intl.NumberFormat('en-CA'),OBS='https://www.inaturalist.ca/observations/';
// one record opens its own page at the ID form; iNat's Identify grid would need a click on the tile first
function one(id){return OBS+id+'#comment-id-tabs';}
var CARD=IdentifyCard({ref:function(n){return CMP?CMP.ref(n):Promise.resolve(null);}}),TAB=[],SUBK=[],NK=1,KIND=null,SUB=null,KF=0,KC=[],UF=null,UON=false,MINE=[],CMP=null,BT=false,ST=null,SK='',IN=IdentifyInat(CFG.oauth);
// CFG.merge: the kinds (levels) a tab shows, in order; SUBK a kind's place in its tab
Object.keys(CFG.merge).forEach(function(t){CFG.merge[t].forEach(function(k,j){TAB[k]=+t;SUBK[k]=j;});NK=Math.max(NK,CFG.merge[t].length);});
var META=null,SYNC=null,MORE=new Map(),TAXA=null,P=null,BYID=null,LEVEL=null,Q=null,LOOKS=null,WHY=null,WHYF=null,RK=null,N3=0,GP=null,R=null,MF=null,TF=null,PEND=null,OX=null,PIDS=null,REC=-1,S={},KEEPIDS=null,SUBIDS=null,AREA='',VIEW='',SEL=null,view=[],shown=0,drawn=0,LV=0,LINKS=[],BI=0,ONE='',CACHE=new Map(),FIRST=null,SHOWN,STAY=false,X=null,WW=null,BAR=null;
var RKF=function(){},LKF=RKF,RKW=true;  // fetch rank (level 3) / look-alikes (levels 2, 3, 5, Batches, Compare) once; level 3's count waits for the rank under Best x%
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function status(t,err){var s=$('status');s.textContent=t;s.classList.toggle('err',!!err);}  // an error shows on Batches too
// A GoatCounter event when the page has its script (page_identify --goatcounter); never a login or record id.
function track(name){var g=window.goatcounter;if(g&&g.count)try{g.count({path:'identify/'+name,title:name,event:true});}catch(e){}}
function get(url){return fetchOnce(url).then(L.gunzip,function(e){
  throw new Error('Could not load '+String(url).split('/').pop().split('?')[0]+' ('+e.message+')');});}

// The records the selection keeps, 1 each in SEL: MapFilter.keep for the taxa, the group chips' verdict, MapFilter.rest
// for the dates, months, show only and accuracy, then the area, the map's viewport, the lasso's ids and the User filter.
// kept(st) is that for the selection st: the search bar counts with one group or date filter left out.
function kept(st){
  var n=P.n,i,out=MF.keep(TF,MF.groupSet(st,TF),P.tax,P.grp,n,new Uint8Array(n));
  var ok=CH.groupPass(st.groups,META.groups,!!TF.inc);
  for(i=0;i<n;i++)if(!ok[P.grp[i]])out[i]=0;
  MF.rest(st,P.obs,P.up,P.flags,n,out);OX.rest(st,out,PIDS);
  var I=SpaceMask.areaIndex(AREA),V=SpaceMask.areaIndex(VIEW),m=[I&&SpaceMask.area(I,P),V&&SpaceMask.area(V,P),KEEPIDS&&SpaceMask.ids(KEEPIDS,P),SUBIDS&&SpaceMask.ids(SUBIDS,P)];
  m.forEach(function(v){if(v)for(var j=0;j<n;j++)out[j]&=v[j];});
  for(i=0;i<n;i++)if(out[i]&&UF.drop(i))out[i]=0;
  return out;
}
function select(){UF.sync(P);SEL=kept(S);}
// kept(st) at the chosen level, as the bar's counts and histograms show it
function atLevel(st){var m=kept(st);for(var i=0;i<P.n;i++)if(m[i]&&(LV?LEVEL[i]!==LV:!LEVEL[i]))m[i]=0;return m;}
// Per level the kept records best first: each kind of the tab in CFG.merge's
// order, then the quantized score (a bucket each), newest (highest id) first within a bucket; then at most PER_SPECIES of any one
// taxon, none cut when the level holds one taxon only. The kind control (KF) keeps one kind of its tab; KC counts the kinds. MORE: for the first card of a cut taxon, how many records it left out.
// With the range file (R), a level's records also pass its outside-its-range chip.
// Each level's slice is then ordered by GP.sort: the weighted prioritizers (confidence, blitz gap, at risk, invasive, outside range), then the finer
// confidence order or the base order (newest first by default). The filters (GP.pass) drop level 3 records outside the Best x% and cells outside the survey days range.
// Rows in ascending id: each shard's rows are id-sorted, so a merge of the shards.
function byId(P){
  var s=P.start,k=s.length-1,pos=s.slice(0,k),out=new Uint32Array(P.n),t,j,b;
  for(t=0;t<P.n;t++){b=-1;for(j=0;j<k;j++)if(pos[j]<s[j+1]&&(b<0||P.id[pos[j]]<P.id[pos[b]]))b=j;out[t]=pos[b]++;}
  return out;
}
// What the per-species cap counts: the record's label, but on level 3 the suggested species (the label is a coarse rank there).
function ck(i,lv){var v=lv===3&&LOOKS?LOOKS.lo[i]|LOOKS.hi[i]<<8:NO_LOOK;return v===NO_LOOK?P.tax[i]:v;}
function RUN(){return /(^|&)run=1(&|$)/.test(location.hash.slice(1));}
function on(i){return SEL[i]&&LEVEL[i]&&(!R||R.pass(i,LEVEL[i]))&&(!X||X.pass(i))&&(!GP||GP.pass(i,KIND[i]))&&(!WW||KIND[i]!==3||WW.pass(i));}
// Under My taxa first the user's genera lead each level, each kind in turn, then the rest; MINE: how many cards they are, -1 without the mode.
function build(){
  var n=P.n,W=2*NK*STEPS,c=new Uint32Array(6*W+1),key=new Uint16Array(n),rk=UF.ranked(),i,k,lv;
  for(i=0;i<n;i++)if(on(i)){key[i]=LEVEL[i]*W+(rk&&UF.mine(i)?NK*STEPS:0)+(NK-1-SUB[i])*STEPS;c[key[i]+1]++;}
  for(k=1;k<c.length;k++)c[k]+=c[k-1];
  var at=c.slice(),order=new Int32Array(c[c.length-1]);
  for(k=0;k<n;k++){i=BYID[k];if(on(i))order[at[key[i]]++]=i;}
  if(GP)for(lv=1;lv<=5;lv++)GP.sort(order.subarray(c[lv*W],c[(lv+1)*W]),lv,key);  // the best last, as the cut reads from the end
  var out=[],total=[];MORE.clear();KC=[];
  for(lv=1;lv<=5;lv++){
    // the cut is per kind, so a merged tab lists each kind's level list in turn, as pool_levels writes them
    var tot=new Uint32Array(65536*NK),taken=new Uint32Array(65536*NK),rows=[],a=c[lv*W],b=c[(lv+1)*W],nd=[],cut,t,kf=KF&&TAB[KF]===lv?KF:0;
    for(k=a;k<b;k++){i=order[k];KC[KIND[i]]=(KC[KIND[i]]||0)+1;if(kf&&KIND[i]!==kf){order[k]=-1;continue;}
      if(!tot[SUB[i]*65536+ck(i,lv)]++)nd[SUB[i]]=(nd[SUB[i]]||0)+1;}
    for(k=b-1;k>=a;k--){i=order[k];if(i<0)continue;t=SUB[i]*65536+ck(i,lv);cut=nd[SUB[i]]===1||lv===3&&RUN()?Infinity:PER_SPECIES;
      if(taken[t]<cut){rows.push(i);if(!taken[t]++&&tot[t]>cut&&!(lv===3&&LOOKS))MORE.set(i,tot[t]-cut);}}
    // the #record= card leads its level, even past the per-species cut
    if(REC>=0&&LEVEL[REC]===lv&&on(REC)&&rows[0]!==REC){k=rows.indexOf(REC);if(k>0)rows.splice(k,1);rows.unshift(REC);}
    if(lv===3&&RUN()&&LOOKS)rows=IdentifyNarrow.runs(rows,looksOf);
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
// level 3's runner-up: [name, margin in thousandths, 255 none], or null; its place is in its suggestion's list
function whyOf(i){
  var v=WHY&&LOOKS?LOOKS.lo[i]|LOOKS.hi[i]<<8:NO_LOOK,c=WHY?WHY.lo[i]:255,r=v===NO_LOOK||c===255?null:WHY.runners[v];
  return r&&r[c]!=null?[WHY.names[r[c]],WHY.hi[i]===255?255:WHY.hi[i]*5]:null;
}
// Under a card's photo: its label, and for a close call, a likely mislabel or a record above species what it looks like.
function title(i,lv){
  var t=P.tax[i]!==NOTAX&&TAXA[P.tax[i]],box=el('div','title'),nm=el('div','name'),lk=looksOf(i),l=el('div','look');
  nm.appendChild(el('i',null,t?t[0]:'Unidentified'));
  box.appendChild(nm);
  if(t&&t[1])box.appendChild(el('div','com',t[1]));
  if(lv===3&&lk)l.append('Probably ',el('i',null,lk));
  if(lv===3&&lk&&!BT){var g=el('div','sugg'),cf=RK&&IdentifyNarrow.conf(RK[i],N3);g.appendChild(IdentifyNarrow.copy(lk));if(cf)g.appendChild(GP?GP.confBadge(i,cf):el('span','conf',cf));var gp=GP&&GP.badge(i);if(gp)g.appendChild(gp);}
  else if((lv===2||lv===5)&&lk)l.append('Looks more like ',el('i',null,lk));
  if(l.firstChild)box.appendChild(l);
  if(g){var y=whyOf(i);if(y)box.appendChild(IdentifyNarrow.why(y[0],y[1]));box.appendChild(g);}
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
// i<0: a batch record the pool does not hold, its name filled in with its photo
function card(i,lv,id){
  id=i<0?id:P.id[i];
  var li=el('li','card'),det=el('div','det'),ph=el('div','ph','Loading photo'),w=el('a','when','Date and place…'),a=el('a','btn','Identify');
  li.dataset.id=id;li.tabIndex=0;
  w.href=OBS+id;IdentifyFlow.link(w);
  a.href=one(id);a.setAttribute('aria-label','Identify this record on iNaturalist');
  li.append(CARD.car(ph),i<0?el('div','title'):title(i,lv),w);
  if(i>=0){li.dataset.i=i;li.dataset.lv=lv;}
  if(i>=0&&!BT){
    if(KIND&&CFG.merge[lv]&&!KF)li.insertBefore(el('div','kind',kindName(KIND[i])),w);
    if(UF&&UF.ranked()&&UF.mine(i))li.insertBefore(el('div','badge','Your genus'),w);
    if(MORE.has(i))det.appendChild(more_(i));
  }
  a.addEventListener('click',function(){track(BT?'study-card':'card-'+(KIND?KIND[i]:lv));});
  if(i>=0&&lv===3&&!BT)IdentifyFlow.identify(a,li);else IdentifyFlow.link(a);
  var row=R&&i>=0&&R.links(a,i,lv);li.append(a,det);if(row)det.prepend(row);  // the range words go with the detail
  li.onmouseenter=li.onfocus=function(){tell('wtid-focus',id);};
  // a click or Space opens the compare panel beside the list
  li.onclick=function(e){if(!e.target.closest('a,button')){if(CMP)CMP.open(li);else tell('wtid-record',id);}};
  li.onkeydown=function(e){if(e.target===li&&(e.key==='Enter'||e.key===' ')){e.preventDefault();if(e.key===' '&&CMP)CMP.open(li);else tell('wtid-record',id);}};
  IdentifyFlow.seen(li);CARD.face(li);CARD.keys(li);
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
      var p=o.photos&&o.photos[0],ph=li.querySelector('.ph'),w=li.querySelector('.when'),t=o.taxon;
      if(!li.dataset.i){var nm=el('div','name');nm.appendChild(el('i',null,t?t.name:'Unidentified'));
        li.querySelector('.title').replaceChildren(nm);if(t&&t.preferred_common_name)nm.after(el('div','com',t.preferred_common_name));}
      ph.textContent='';
      if(p){var img=el('img');img.loading='lazy';img.onerror=function(){img.removeAttribute('src');};img.alt='Photo of '+li.querySelector('i').textContent;
        img.src=String(p.url).replace('/square.','/medium.');ph.appendChild(img);}else ph.textContent='No photo on iNaturalist now';
      w.textContent=(o.observed_on||'Date unknown')+' · '+(o.place_guess||'Place unknown');w.title=w.textContent;CARD.face(li,o.place_guess||'');
      // level 3: an ID at species there would not be the first, so not an improving one
      if(li.dataset.lv==='3'&&IdentifyNarrow.taken(o)){li.remove();drop(+li.dataset.i);return;}
      if(IN.user()&&t&&t.id&&!li.querySelector('.acts'))acts(li,t);
      if(CMP)CMP.landed(li);
    });
  }).catch(function(e){if(!(sig&&sig.aborted))status('Could not load the photos: '+e.message,1);});
}
// a removed card leaves the list, so the caption, Show more and the batches count only cards that can show
function drop(i){var r=view[LV],k=r&&Array.isArray(r)?r.indexOf(i):-1;if(k<0)return;r.splice(k,1);if(r.n)r.n--;if(k<drawn)drawn--;
  var b=$('more');b.hidden=r.length<=drawn;b.textContent='Show more ('+nf.format(r.length-drawn)+' left)';var bi=BI;batch();BI=bi;step(0);}
// Signed in: Agree with the record's taxon, and on a card that names a look-alike, ID it as that. The Identify link stays.
function acts(li,t){
  var id=+li.dataset.id,pr=li.dataset.i&&CMP&&CMP.pair(+li.dataset.i),row=el('div','acts');
  function act(text,taxon,label){
    var b=el('button','act',text);b.type='button';b.setAttribute('aria-label',label);
    b.onclick=function(){b.disabled=true;b.textContent='Posting…';
      IN.identify(id,taxon).then(function(){b.textContent='Posted';IdentifyStudy.posted(id,taxon,IN.user());track('post');},
        function(){b.disabled=false;b.textContent='Not posted. Use Identify';signin();});};
    row.appendChild(b);
  }
  act('Agree',t.id,'Agree with '+t.name+' on iNaturalist');
  if(pr)act('ID as '+TAXA[pr[1]][0],TAXA[pr[1]][2],'Identify as '+TAXA[pr[1]][0]+' on iNaturalist');
  (li.querySelector('.det')||li).append(row);
}
function signin(){
  var box=$('sin');box.textContent='';if(!IN.on)return;
  var u=IN.user(),b=el('button','lnk',u?'Sign out':'Sign in with iNaturalist');b.type='button';
  b.onclick=function(){if(u){IN.out();signin();SK='';paint();}else IN.start();};
  box.append(u?'Signed in as '+u.login+'. ':'',b,u?'':' to post IDs from here');
}
// The Batches tab's cards: the batch newest first, each a pool card when the pool holds it; drawn again only when
// the batch or what a card can show (the pool, the look-alikes, the ranges, the sign in) changed.
function find(id){var lo=0,hi=P.n-1,m,v;while(lo<=hi){m=(lo+hi)>>1;v=P.id[BYID[m]];if(v===id)return BYID[m];if(v<id)lo=m+1;else hi=m-1;}return -1;}
function drawIds(ids){
  var k=ids.join()+[!!BYID,!!LOOKS,!!R,!!IN.user()].join();if(k===SK)return;SK=k;
  if(AB)AB.abort();AB=new AbortController();
  var ol=$('sgrid'),lis=IdentifyLinks.order(ids).map(function(id){var i=BYID?find(id):-1;return i>=0?card(i,LEVEL[i]):card(-1,0,id);});
  ol.replaceChildren.apply(ol,lis);
  if(lis.length){photos(lis);if(CMP&&LOOKS){CMP.fill(lis);lis.forEach(CARD.paint);}}
}
function mode(b){BT=b;document.body.classList.toggle('bt',b);if(!b)SK='';}  // leaving aborts the batch's photos
// Where the user's genera end in the list, under My taxa first: after n cards, or before the first when none are theirs.
// MINE counts cards (after the per-species cut), so both lines say cards.
function sep(n,top){var c=nf.format(n)+(n===1?' card':' cards');
  return el('li',top?'sep top':'sep',top?'Your genera first · '+c:n?'End of your genera · '+c:'None of your genera here. The rest follow.');}
// The next LIMIT cards of the chosen level; the button is the scroll sentinel and stays as the fallback.
function more(){
  var rows=view[LV]||[],ol=$('grid'),to=Math.min(rows.length,shown),lis=[],b=$('more');
  if(!drawn&&MINE[LV]>0)ol.appendChild(sep(MINE[LV],1));
  for(var j=drawn;j<to;j++){if(j===MINE[LV])ol.appendChild(sep(j));
    if(rows.size&&CMP&&looksOf(rows[j])!==(j?looksOf(rows[j-1]):null))ol.appendChild(IdentifyNarrow.head(looksOf(rows[j]),rows.size.get(looksOf(rows[j])),CMP.ref));var li=card(rows[j],LV);ol.appendChild(li);lis.push(li);}
  drawn=to;
  b.hidden=rows.length<=to;b.textContent='Show more ('+nf.format(rows.length-to)+' left)';
  if(lis.length){photos(lis);if(CMP&&LOOKS){CMP.fill(lis);lis.forEach(CARD.paint);}}
  if(IO&&!b.hidden){IO.unobserve(b);IO.observe(b);}  // observe again: a tall pane may still show it
}
// "Identify these N on iNaturalist" opens the current batch; with more than one, "Batch 2 of 50" and the arrows
// beside it pick which. Batches follow the card order.
function batch(){
  var all=view[LV]||[],t=all.n||all.length,rows=all.slice(0,IdentifyLinks.MAX_IDS),capped=rows.length<t;  // n: a first list's full length
  LINKS=rows.length?IdentifyLinks.batches(rows.map(function(i){return P.id[i];}),true):[];BI=0;
  $('batch').hidden=!rows.length;
  ONE=capped?'Identify the first '+nf.format(rows.length)+' on iNaturalist':null;
  $('cap').textContent=LV===3?IdentifyNarrow.line(t,S.total[3],[GP&&GP.label(),GP&&GP.gaplabel(),R&&R.label(3)],RUN()?'all':'up to '+PER_SPECIES):
    nf.format(t)+' cards (up to '+PER_SPECIES+' per species) · '+(capped?'first '+nf.format(rows.length):'all')+
    ' in '+LINKS.length+' batches of '+IdentifyLinks.BATCH+', in the order shown';
  $('go').title=(LV===3&&RUN()?'All':'Up to '+PER_SPECIES)+(LV===3?' per suggested species':' per species');
  step(0);
}
function step(d){
  BI=Math.max(0,Math.min(LINKS.length-1,BI+d));
  var b=LINKS[BI];
  if(b){$('go').href=b.n===1?one(b.lo):b.url;$('go').textContent=ONE&&LINKS.length<2?ONE:b.n===1?'Identify this record on iNaturalist':'Identify these '+nf.format(b.n)+' on iNaturalist';}
  $('bn').textContent=LINKS.length>1?'Batch '+(BI+1)+' of '+LINKS.length:'';
  $('prev').hidden=$('next').hidden=LINKS.length<2;
  $('prev').disabled=BI===0;$('next').disabled=BI>=LINKS.length-1;
}
// Draws the chosen level from its first card; STAY (the records replacing the first list) keeps the cards drawn and the scroll.
function paint(){
  if(BAR)BAR.update();
  [].forEach.call($('tabs').children,function(t){var on=BT?!t.dataset.lv:+t.dataset.lv===LV;t.setAttribute('aria-selected',on);t.tabIndex=on?0:-1;});
  if(BT){LKF();ST.show();return;}
  var x=CFG.levels.filter(function(l){return l[0]===LV;})[0];
  $('desc').textContent=x[2];kinds();$('panel').setAttribute('aria-labelledby','tab'+LV);
  var y=scrollY;  // a layout between the clear and the redraw clamps the scroll to the empty page
  if(AB)AB.abort();AB=new AbortController();  // the cards redrawn below replace those whose photos are still loading
  $('grid').textContent='';shown=STAY?Math.max(LIMIT,drawn):LIMIT;drawn=0;
  var kf=KF&&TAB[KF]===LV;  // the controls count the chosen kind, as the cards show it
  if(R)R.draw(kf?KF:LV,SEL,kf?KIND:LEVEL);
  if(X)X.draw(kf?KF:LV,SEL,kf?KIND:LEVEL);
  if(GP)GP.draw(LV);
  IdentifyFlow.draw(LV);
  empty();
  more();batch();scrollTo(0,STAY?y:0);STAY=false;
  if(LV===3&&WHYF)setTimeout(WHYF,0);
  if(LV===2||LV===3||LV===5)LKF();  // only these show a look-alike; level 3's order is by rank
  if(LV===3)RKF();
}
function redraw(late){if(late===true)STAY=true;build();counts();paint();}  // late: records that arrived, not a choice, keep the scroll
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
  [].forEach.call($('tabs').querySelectorAll('[data-lv]'),function(t){var n=S.total[+t.dataset.lv]||0,w=+t.dataset.lv===3&&GP&&RKW&&!RK&&GP.label();t.lastChild.textContent=w?'':nf.format(n);t.classList.toggle('zero',!n&&!w);});
}
// An empty level here points at the levels that do have records, rather than a dead end.
function empty(){
  var box=$('none'),others=CFG.levels.filter(function(l){return l[0]!==LV&&S.total[l[0]];});
  box.hidden=!!(view[LV]||[]).length;box.textContent='';if(box.hidden)return;
  if(!others.length&&UF&&UF.active()&&UF.flags().split(',').indexOf('observer')>=0){  // the map's advice (zoom out) does not fit here
    var f=el('button',null,'Show all records, your genera first');f.type='button';f.onclick=function(){UF.first();};
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
  LV=lv;mode(false);track('tab-'+lv);
  try{localStorage.setItem(LS,lv);}catch(e){}
  keep('lvl',lv);
  if(R){R.level(lv);redraw();}else paint();
}
// the kept tab: a level number, or b for Batches
function stored(){
  var m=/(?:^|&)lvl=(\w)/.exec(location.hash.slice(1)),v=m?m[1]:'';
  try{v=v||localStorage.getItem(LS)||'';}catch(e){}
  return v;
}
function saved(){var v=+stored();return CFG.levels.some(function(l){return l[0]===v;})?v:0;}
// With no saved level: Easy confirms, else Might be wrong, else the first level that has records.
function first(){
  if(S.total[1])return 1;
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
  counts();if(WW)WW.sync();$('unpick').hidden=parent!==window||!S.picks.length;
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
  if(!s){view=[];$('grid').textContent='';$('none').hidden=$('more').hidden=$('batch').hidden=true;
    [].forEach.call($('tabs').querySelectorAll('[data-lv]'),function(t){t.lastChild.textContent='';});status('Loading all the records for this selection…');return;}
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
// The address with the tokens drop() names replaced by add, standalone only: embedded, the split page holds it.
function rewrite(drop,add){
  if(parent===window)history.replaceState(null,'','#'+location.hash.slice(1).split('&').filter(function(x){return x&&!drop(x);}).concat(add).join('&'));
}
// The bar or the User box changed S: its part of the address follows S, then the split view and the cards.
function put(){
  TF=TX.filter(TAXA,S.picks);rewrite(MapFilter.tokens,MF.write(S).filter(MapFilter.tokens));SYNC.send();refresh();
}
function user(){
  var on=UF.active()||UF.ranked();if(on&&!UON)track('user-'+UF.flags().replace(/,/g,'-'));UON=on;
  put();
}
// The Where panel's area changed: its rings select, its hash keys (area, bcpark, park) are the address's.
function where(rings,h){AREA=rings;rewrite(function(x){return /^(area|park|bcpark)=/.test(x);},h?[h]:[]);refresh();}
function key(){return MF?MF.write(S).join('&'):PEND||'';}
function idsOf(){var out=[];for(var i=0;i<P.n;i++)if(SEL[i])out.push(P.id[i]);return out;}
function inbox(){
  addEventListener('message',function(e){
    var d=e.data;if(e.origin!==location.origin||e.source!==parent||!d)return;
    if(d.type==='wtid-area'&&typeof d.area==='string'){AREA=d.area;again();}
    else if(d.type==='wtid-view'&&typeof d.area==='string'){if(d.area!==VIEW){VIEW=d.area;soon();}}  // '' is no cut
    else if(d.type==='wtid-keep'&&(d.ids===null||d.ids instanceof Uint32Array)){KEEPIDS=d.ids&&d.ids.slice().sort();again();}
    else if(d.type==='wtid-projects'){PIDS=d.ids instanceof Uint32Array?d.ids:null;again();}  // the map's projects
    else if(d.type==='wtid-record'&&CMP)CMP.pick(d.id);  // the map's or the photo space's pick
    else if(d.type==='wtid-subset'&&(d.ids===null||Array.isArray(d.ids))){SUBIDS=d.ids&&Uint32Array.from(d.ids).sort();again();}  // the photo search's hits
  });
  SYNC=MapFilter.sync({key:key,apply:function(str){if(MF){clearTimeout(TK);TK=setTimeout(function(){take(str,false);},60);}else{PEND=str;again();}},hash:false});
  addEventListener('hashchange',function(){if(MF)take(location.hash.slice(1),true);else again();});
}
// the look-alike file (planes of one entry per level 2, 3, 5 record, expanded to all n by KIND), or (why) the runner-up file (planes of n)
function looks(buf,why){
  var dv=new DataView(buf),size=dv.getUint32(0,true),n=P.n,m=n,j,k=0,h,lo,hi,o=4+size,w=function(j){return KIND[j]===2||KIND[j]===3||KIND[j]===5;};if(!why){m=0;for(j=0;j<n;j++)if(w(j))m++;}
  if(buf.byteLength!==o+2*m)throw new Error('the '+(why?'runner-up':'look-alike')+' file holds '+buf.byteLength+' bytes, expected '+(o+2*m));
  h=JSON.parse(new TextDecoder().decode(new Uint8Array(buf,4,size)));lo=new Uint8Array(buf,o,m);hi=new Uint8Array(buf,o+m,m);if(!why){var l=new Uint8Array(n).fill(255),u=new Uint8Array(n).fill(255);for(j=0;j<n;j++)if(w(j)){l[j]=lo[k];u[j]=hi[k++];}lo=l;hi=u;}
  return {names:h.names,runners:h.runners,lo:lo,hi:hi};
}
async function load(){
  status('Reading the map data…');
  var drawn_=new Promise(function(ok){if(!CFG.first)return ok();setTimeout(ok,2000);  // the bulk files wait for the first cards' paint, or 2 s
    get(new URL(CFG.first,MAP)).then(function(b){if(!MF)firstOf(JSON.parse(new TextDecoder().decode(b)));}).catch(function(){}).then(ok);});  // optional
  META=await L.fetchMapMeta(MAP,fetch);
  WW=IdentifyWWW({value:META.value,taxa:function(){return TAXA;},look:looksOf,redraw:function(){if(P)redraw();}});
  function file(k){var f=META.files[k];return f?get(new URL(f,MAP)):Promise.reject(new Error('the map lists no '+k+' file'));}
  await drawn_;
  var taxa=get(new URL(META.taxa,MAP)).then(function(b){return JSON.parse(new TextDecoder().decode(b));});
  var shards=Promise.all(META.shards.map(function(s){return get(new URL(s.file,MAP)).then(function(b){return L.decodeShard(b,s.n);});}));
  var lev=file('levels'),lkp=null,rkp=null,rg=file('range').catch(function(){return null;});  // optional: no range maps without it
  function lk(){return lkp||(lkp=file('looks').catch(function(){return null;}));}function rk(){return rkp||(rkp=file('rank').catch(function(){return null;}).then(function(b){RKW=false;return b;}));}  // optional: level 3 by score bucket without it
  function rank(b){var m=0,j,k=0,r;for(j=0;j<P.n;j++)if(KIND[j]===3)m++;if(!b||b.byteLength!==4*m)return false;b=new Uint8Array(b);r=new Uint32Array(P.n);for(j=0;j<P.n;j++)if(KIND[j]===3){r[j]=(b[k]|b[m+k]<<8|b[2*m+k]<<16|b[3*m+k]<<24)>>>0;k++;}RK=r;N3=m;return true;}  // byte planes of the level-3 records only
  if(!FIRST)status('Downloading the records…');
  var d=await Promise.all([shards,taxa,lev,saved()===3?rk():null]);  // level 3 opens on its rank
  P=L.pool(d[0],META.bbox);BYID=byId(P);TAXA=d[1];LOOKS=null;
  var raw=new Uint8Array(d[2]);
  if(raw.length!==P.n)throw new Error('the levels file holds '+raw.length+' records, the map '+P.n);
  LEVEL=raw.map(function(v){return TAB[v&15]||v&15;});KIND=raw.map(function(v){return v&15;});SUB=raw.map(function(v){return SUBK[v&15]||0;});Q=raw.map(function(v){return v>>4;});
  rank(d[3]);
  GP=IdentifyGaps({P:P,groups:META.groups,keep:function(i){return LEVEL[i]>0;},band:function(i){return IdentifyNarrow.band(RK[i],N3);},
    pct:function(i){return RK?(RK[i]+1)/N3:null;},hasRank:function(){return !!RK;},
    conf:function(i,lv){return RK&&lv===3?3-IdentifyNarrow.band(RK[i],N3):Q[i]*3/(STEPS-1);},
    cont:function(i,lv){return RK&&lv===3?1-RK[i]/N3:Q[i]/(STEPS-1);},
    fine:function(i,lv){return RK&&lv===3?-RK[i]:Q[i];},
    flag:function(i,inv){return WW?WW.flag(i,inv):0;},hasOut:function(){return !!R;},out:function(i){return R?R.outside()[i]:0;},
    redraw:redraw});  // a failed or missing checklist leaves every gap at 0
  X=IdentifyUnconfirmed({P:P,taxa:TAXA,ranks:META.ranks,area:function(){return AREA;},redraw:redraw});
  // Not yet identified by me asks iNaturalist within the pool's extent: Identify has no map viewport of its own
  var b=META.bbox;UF=userFilter({S:S,meta:META,get:function(f){return get(new URL(f,MAP));},taxa:function(){return TAXA;},changed:user,
    bounds:function(){return {w:b[0],s:b[1],e:b[2],n:b[3]};}});
  CMP=IdentifyCompare({taxa:TAXA,tax:P.tax,look:looksOf,why:whyOf,obs:function(id){return CACHE.get(id);},range:function(){return R;},more:function(){shown+=LIMIT;more();},lend:CARD.lend});
  MF=MapFilter(META);Object.assign(S,MF.read(new URLSearchParams()));  // the defaults, until the address is read
  OX=IdentifyOnly({META:META,mf:MF,P:function(){return P;},taxa:function(){return TAXA;},range:function(){return R;},rewrite:rewrite,changed:refresh,embedded:parent!==window,get:function(f){return get(new URL(f,MAP));}});
  BAR=IdentifyBar({S:S,META:META,mf:MF,nf:nf,taxa:function(){return TAXA;},P:function(){return P;},tf:function(){return TF;},mask:atLevel,all:kept,tab:function(){var l=CFG.levels.filter(function(x){return x[0]===LV;})[0];return {name:l?l[1]:'',has:function(i){return LV?LEVEL[i]===LV:LEVEL[i]>0;}};},changed:put,blocked:function(){return !!(AREA||VIEW||KEEPIDS||SUBIDS||PIDS||UF.active());},
    where:where,get:function(u){return get(new URL(u,MAP));},map:MAP,key:key,embedded:parent!==window});
  RKF=function(){if(RK||rkp)return;LKF();Promise.all([rk(),lk()]).then(function(d){if(rank(d[0]))LV===3?redraw(true):(build(),counts());});};
  LKF=function(){if(lkp)return;lk().then(function(b){if(!b)return;LOOKS=looks(b);retitle();
    var cs=[].slice.call($('grid').querySelectorAll('.card'));CMP.fill(cs);cs.forEach(CARD.paint);if(BT)paint();
    if(LV===3){STAY=true;redraw();}else build();});};  // level 3's cap reads the suggestions
  var co=CMP.open;CMP.open=function(){LKF();return co.apply(this,arguments);};if(WW.active())LKF();
  STAY=!!SHOWN;take(location.hash.slice(1),AREA==='');
  if(PEND!==null){take(PEND,false);PEND=null;}
  function retitle(){[].forEach.call($('grid').children,function(li){var t=li.querySelector('.title');if(t&&li.dataset.i){t.replaceWith(title(+li.dataset.i,LV));CARD.face(li);}});}
  WHYF=function(){WHYF=null;  // the runner-up file is large and only level 3 shows it: fetched once its first cards are drawn
    Promise.all([lk(),file('why').catch(function(){return null;})]).then(function(b){if(b[0]&&b[1]){WHY=looks(b[1],1);if(LV===3)retitle();}});};
  if(LV===3&&!BT)setTimeout(WHYF,0);rg.then(RKF,RKF);  // the rank and look-alikes follow the records in the background: level 3's count reads both
  rg.then(function(b){if(!b)return;
    R=IdentifyRanges(b,{P:P,sdm:META.sdm,name:function(i){return P.tax[i]!==NOTAX&&TAXA[P.tax[i]]?TAXA[P.tax[i]][0]:null;},look:looksOf,redraw:redraw});
    // #record=<id> (the map's token): its level, its card first, its range popover open
    var rec=/(?:^|&)record=(\d+)(?:&|$)/.exec(location.hash.slice(1));
    for(var i=0;rec&&i<P.n;i++)if(P.id[i]===+rec[1]){REC=i;break;}
    if(REC>=0&&LEVEL[REC])LV=LEVEL[REC];
    R.level(LV,true);redraw(true);if(S.only.range)refresh();
    // once the checklist has settled: its redraw closes the popover
    GP.ready.then(function(){var li=REC>=0&&document.querySelector('.card[data-id="'+P.id[REC]+'"]'),c=li&&li.querySelector('.rchip');
      if(c){if(CMP)CMP.open(li);c.click();}});});
  window.__identify={ids:idsOf,view:function(){return view.map(function(r){return r&&Array.from(r.map(function(i){return P.id[i];}));});},
    total:function(){return S.total;},levelled:function(){var n=0;for(var i=0;i<P.n;i++)if(SEL[i]&&LEVEL[i])n++;return n;},level:function(){return LV;},gap:function(id){var i=find(id);return GP&&i>=0?GP.tier(i):0;},kind:function(){return KF;},kinds:function(){return KC.slice();},user:function(){return UF.active()||UF.ranked();},mine:function(){return MINE[LV];},ranges:function(){return !!R;},refresh:function(){var t=performance.now();select();build();return performance.now()-t;}};
}
var KD=/(?:^|&)kind=(\d)/.exec(location.hash.slice(1));KF=KD&&TAB[+KD[1]]?+KD[1]:0;
function start(){
  tabs();inbox();IdentifyProgress($('prog'),$('today'));IdentifyFlow.keys({level:function(){return BT?0:LV;},more:function(){shown+=LIMIT;more();}});
  if(CFG.study){
    ST=IdentifyStudy.tab({data:CFG.study,draw:drawIds,count:function(){},
      active:function(){return BT;},track:function(n){track('study-'+n);}});
    signin();
    // Batches only when the link names them (#lvl=b), never as the default
    if(!/(?:^|&)record=/.test(location.hash.slice(1))&&/(?:^|&)lvl=b(?:&|$)/.test(location.hash.slice(1))){mode(true);paint();}
  }
  load().catch(function(e){status('Could not load the records: '+e.message,1);});
}
if(IN.on&&/[?&]code=/.test(location.search))IN.finish().then(function(left){if(!left)start();});else start();
})();
