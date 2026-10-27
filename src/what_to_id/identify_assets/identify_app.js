// The Identify page: every pool record at its level (pool-levels.bin, format in pool_levels.py) as a narrow column
// of cards. The selection is the map's: MapFilter's keep and rest over the pool shards, the group chips' verdict,
// the area and the lasso's ids (SpaceMask). Up to PER_SPECIES cards per species, best first, are drawn at view time;
// their photos come from iNaturalist 200 ids to a request as the cards are drawn.
(function(){
'use strict';
var CFG=IDENTIFY_CONFIG,L=EmbeddingsLayout,Meta=AtlasSearchMeta,PER_SPECIES=3,LIMIT=12,STEPS=16,NO_LOOK=65535,NOTAX=65535;
var MAP=new URL(CFG.mapUrl,location.href).href,nf=new Intl.NumberFormat('en-CA'),OBS='https://www.inaturalist.org/observations/';
var META=null,TAXA=null,P=null,LEVEL=null,Q=null,LOOKS=null,MF=null,TF=null,PEND=null,S={},KEEPIDS=null,SUBIDS=null,AREA='',SEL=null,view=[],shown=[],CACHE=new Map();
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function status(t){$('status').textContent=t;}
function get(url){return fetch(url).then(function(r){
  if(!r.ok)throw new Error('Could not load '+String(url).split('/').pop().split('?')[0]+' ('+r.status+')');
  return r.arrayBuffer();}).then(L.gunzip);}

// The records the selection keeps, 1 each in SEL: MapFilter.keep for the taxa, the group chips' verdict, MapFilter.rest
// for the dates, months, show only and accuracy, then the area and the lasso's ids.
function select(){
  var n=P.n,i;
  SEL=MF.keep(TF,MF.groupSet(S,TF),P.tax,P.grp,n,new Uint8Array(n));
  var ok=CH.groupPass(S.groups,META.groups,!!TF.inc);
  for(i=0;i<n;i++)if(!ok[P.grp[i]])SEL[i]=0;
  MF.rest(S,P.obs,P.up,P.flags,n,SEL);
  var I=SpaceMask.areaIndex(AREA),m=[I&&SpaceMask.area(I,P),KEEPIDS&&SpaceMask.ids(KEEPIDS,P),SUBIDS&&SpaceMask.ids(SUBIDS,P)];
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
// The line under a card's photo: its label, and for a close call or a record above species what it looks like.
function title(i,lv){
  var t=P.tax[i]!==NOTAX&&TAXA[P.tax[i]],box=el('div','name'),lab=el('i',null,t?t[0]:'Unidentified'),lk=looksOf(i);
  box.appendChild(lab);
  if(lv===3&&lk)box.append(', probably ',el('i',null,lk));
  else if(lv===2&&lk)box.append('. Often confused with ',el('i',null,lk),'.');
  if(t&&t[1])box.appendChild(el('span','muted',' '+t[1]));
  return box;
}
function card(i,lv){
  var id=P.id[i],li=el('li','card'),ph=el('a','ph','Loading photo');
  li.dataset.id=id;ph.href=OBS+id;ph.target='_blank';ph.rel='noopener';
  li.append(ph,title(i,lv));
  var links=el('div','links'),a=el('a','btn','Identify');
  a.href=IdentifyLinks.batches([id])[0].url;a.target='_blank';a.rel='noopener';links.appendChild(a);
  links.appendChild(el('span','muted'));li.appendChild(links);
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
      var p=o.photos&&o.photos[0],ph=li.querySelector('.ph');
      ph.textContent='';
      if(p){var img=el('img');img.loading='lazy';img.alt='Photo of '+li.querySelector('i').textContent;
        img.src=String(p.url).replace('/square.','/medium.');ph.appendChild(img);}else ph.textContent='No photo on iNaturalist now';
      li.querySelector('.links .muted').textContent=(o.observed_on||'Date unknown')+' · '+(o.place_guess||'Place unknown');
    });
  }).catch(function(e){status('Could not load the photos: '+e.message);});
}
function more(lv){
  var sec=$('lv'+lv),ol=sec.querySelector('ol'),rows=view[lv],from=sec.drawn,to=Math.min(rows.length,shown[lv]);
  var lis=[];
  for(var j=from;j<to;j++){var li=card(rows[j],lv);ol.appendChild(li);lis.push(li);}
  sec.drawn=to;
  var b=sec.querySelector('button');
  b.hidden=rows.length<=to;b.textContent='Show more ('+nf.format(rows.length-to)+' left)';
  if(lis.length)photos(lis);
}
function sections(){
  var box=$('sections');box.textContent='';
  CFG.levels.forEach(function(x){
    var lv=x[0],sec=el('section','lv'),h=el('h2',null,x[1]);sec.id='lv'+lv;sec.drawn=0;
    var n=view[lv].length,all=S.total[lv];
    sec.append(h,el('p','muted',x[2]),
      el('p','count',nf.format(all)+(all===1?' record':' records')+(n<all?', '+nf.format(n)+' to look at, up to '+PER_SPECIES+' per species':'')+'.'),
      el('ol'));
    var b=el('button','more');b.type='button';b.onclick=function(){shown[lv]+=LIMIT;more(lv);};sec.appendChild(b);
    box.appendChild(sec);shown[lv]=LIMIT;
    if(n)more(lv);else b.hidden=true;
  });
}
function refresh(){
  select();build();
  var kept=0,levelled=0;
  for(var i=0;i<P.n;i++)if(SEL[i]){kept++;if(LEVEL[i])levelled++;}
  S.kept=kept;S.levelled=levelled;
  status(nf.format(kept)+' of '+nf.format(P.n)+' records selected; '+nf.format(levelled)+' have a level.');
  sections();
}
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
    total:function(){return S.total;}};
}
inbox();
load().catch(function(e){status('Could not load the records: '+e.message);});
})();
