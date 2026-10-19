// Photo space: every observation that needs an ID, drawn at its layout position (see embeddings_layout.js).
// Points are the join of the atlas repo's layout parts with the map's pool shards, so names and groups come
// from the map data and observations that left Needs ID drop out on their own.
(function(){
'use strict';
var LOADING='Loading groups and names…';
var CFG=EMBEDDINGS_CONFIG,Meta=AtlasSearchMeta,L=EmbeddingsLayout;
var WHOLE=4<<20,THIN_ABOVE=200000,nf=new Intl.NumberFormat('en-CA');
var DATA=new URL(CFG.dataUrl,location.href).href.replace(/\/*$/,'/');
var MAP=new URL(CFG.mapUrl,location.href).href;
// One colour per life group, in the order of the map's groups: 16 distinct hues, each at least 2:1 against
// both the light and the dark page. The map draws no per-group colour, so this is the only palette.
var PAL=[[0,114,178],[213,94,0],[0,158,115],[190,160,0],[204,121,167],[86,180,233],[230,70,70],[120,60,170],[110,110,110],[160,60,40],[150,130,200],[40,120,60],[140,200,50],[70,90,220],[255,140,100],[0,190,190]];
var S={idx:null,P:null,META:null,TAXA:null,groups:{},picks:[],split:[],extra:[],keep:null,sel:-1,nbr:[],thin:false,cache:new Map(),run:0,deck:null,vs:null,PD:null};

var MF=null,TF=null,PASS=['area','park','bcpark','projects'];
function $(id){return document.getElementById(id);}
function el(tag,attrs,kids){
  var e=document.createElement(tag);
  Object.keys(attrs||{}).forEach(function(k){if(attrs[k]!==null&&attrs[k]!==undefined)e.setAttribute(k,attrs[k]);});
  (kids||[]).forEach(function(c){e.appendChild(typeof c==='string'?document.createTextNode(c):c);});
  return e;
}
function status(t){$('status').textContent=t;}
function color(g){return PAL[g%PAL.length];}
// Colour of every point until the shards give groups: grey that reads on the current theme.
function neutral(){return matchMedia('(prefers-color-scheme: dark)').matches?[190,190,184]:[95,95,90];}
function gname(g){var m=S.META;return m.names&&m.names[m.groups[g]]||m.groups[g];}
function names(i){
  var P=S.P;
  if(!P.grp)return {common:'',latin:'',group:''};
  var t=S.TAXA&&P.tax[i]!==65535?S.TAXA[P.tax[i]]:null;
  return {common:t&&t[1]||'',latin:t&&t[0]||'',group:gname(P.grp[i])};
}
function okFetch(url,init){return fetch(url,init).then(function(r){
  if(!r.ok)throw new Error('Could not load '+String(url).split('/').pop().split('?')[0]+' ('+r.status+')');return r;});}
// Once the shards are joined: new rows replace the neutral ones, and the card and rings follow by id.
function applyJoin(P,taxa){
  var old=S.P,sel=S.sel>=0?old.id[S.sel]:0,nbr=S.nbr.map(function(r){return old.id[r];});
  S.P=P;S.TAXA=taxa;S.PD=null;
  S.sel=sel?L.find(P,sel):-1;
  S.nbr=nbr.map(function(i){return L.find(P,i);}).filter(function(r){return r>=0;});
  chips();update();
  if(S.sel>=0&&S.relabel)S.relabel();
}
function openIndex(){return AtlasSearchIndex.open(DATA,{whole:WHOLE});}

// Counter: records the group chips leave in view, out of those the layout places.
function inc(){return !!(TF&&TF.inc);}
function passing(){return CH.groupPass(S.groups,S.META.groups,inc());}
function shown(){
  var P=S.P,n=0;
  if(!P.grp)return P.n;
  var ok=passing();
  for(var i=0;i<P.n;i++)if(ok[P.grp[i]]&&S.keep[i])n++;
  return n;
}
// The hash keeps the map's selection (map_filter.js writes it as the map does) beside the selected id.
// Filters this page does not apply yet go back untouched, so a link round-trips through it.
function writeHash(){
  // before the join the selection is only in the hash, so it stays as it is
  var h=S.P.grp?MF.write(S).concat(S.extra):location.hash.slice(1).split('&').filter(function(t){
    return t&&t.indexOf('id=')!==0;});
  if(S.sel>=0)h.push('id='+S.P.id[S.sel]);
  history.replaceState(null,'',h.length?'#'+h.join('&'):location.pathname+location.search);
}
// CH.show rewrites the label, so the colour dot goes back in after it.
function paint(b){
  var j=+b.getAttribute('data-g'),dot=el('i',{});dot.style.background='rgb('+color(j).join(',')+')';
  CH.show(b,gname(j)+' '+nf.format(S.count[j]),S.groups[S.META.groups[j]]||'');b.insertBefore(dot,b.firstChild);
}
// Which points the taxon picks keep, with the picked groups beside them (see MapFilter.keep).
function applyKeep(){
  var P=S.P;
  if(!S.keep||S.keep.length!==P.n)S.keep=new Uint8Array(P.n);
  if(P.grp)MF.keep(TF,MF.groupSet(S,TF),P.tax,P.grp,P.n,S.keep);else S.keep.fill(1);
  if(S.PD){var c=S.PD.attributes.getFilterCategory.value;
    for(var i=0;i<P.n;i++)c[3*i+2]=S.keep[i];
    S.PD.attributes.getFilterCategory={value:c,size:3};S.PDV=(S.PDV||0)+1;}
}
var TR=null;
function update(){
  var s=shown(),P=S.P,total=S.META?S.META.n:P.n;
  $('count').textContent=P.grp?nf.format(s)+' shown of '+nf.format(P.n):nf.format(P.n)+' points';
  $('more').textContent=P.grp&&P.n<total?'('+nf.format(total-P.n)+' of the map’s '+nf.format(total)+
    ' records are not placed yet)':'';
  [].forEach.call($('groups').querySelectorAll('button[data-g]'),paint);
  if(BAR)BAR.set(items());if(TR)TR.render();layers();
}
// A pick, a left-out or a removal anywhere: the groups beside included taxa change which points are kept.
function picked(){
  TF=TX.filter(S.TAXA,S.picks);applyKeep();update();writeHash();$('gfit').hidden=!(CH.any(S.groups)||S.picks.length);
}
var PK=null,BAR=null;
function items(){
  return CH.items({S:S,meta:S.META,terms:TX.terms({T:S.TAXA,picks:S.picks,groups:[],meta:S.META,n:0,split:S.split}),
    picker:PK,pj:{items:function(){return [];}},months:[],only:[],two:[],area:{term:function(){return null;}},
    redraw:picked});
}
function clearAll(){S.groups={};S.picks.length=0;S.split=[];$('q').value='';picked();}
// Zooms to the 1st-99th percentile box of the points that pass, so a few stray points do not flatten it.
function fit(){
  var P=S.P,ok=passing(),xs=[],ys=[],box=$('plot');
  for(var i=0;i<P.n;i++)if(ok[P.grp[i]]&&S.keep[i]){xs.push(P.pos[2*i]);ys.push(P.pos[2*i+1]);}
  if(!xs.length)return;
  function span(a){a=Float32Array.from(a).sort();return [a[Math.floor(.01*(a.length-1))],a[Math.ceil(.99*(a.length-1))]];}
  var x=span(xs),y=span(ys),sx=x[1]-x[0]||1,sy=y[1]-y[0]||1,
    z=Math.log2(Math.min(Math.max(box.clientWidth,1)/sx,Math.max(box.clientHeight,1)/sy)*.9);
  S.vs=Object.assign({},S.vs,{target:[(x[0]+x[1])/2,(y[0]+y[1])/2,0],zoom:Math.min(Math.max(z,S.vs.minZoom),S.vs.maxZoom)});
  S.deck.setProps({viewState:S.vs});
}
$('gfit').addEventListener('click',fit);
function chips(){
  var P=S.P,count=S.count=new Array(S.META.groups.length).fill(0);
  for(var i=0;i<P.n;i++)count[P.grp[i]]++;
  var box=$('groups');box.textContent='';
  MF=MF||MapFilter(S.META);
  Object.assign(S,MF.read(new URLSearchParams(location.hash.slice(1))));
  S.extra=location.hash.slice(1).split('&').filter(function(t){return PASS.indexOf(t.split('=')[0])>=0;});
  TF=TX.filter(S.TAXA,S.picks);
  TR=S.TAXA&&TT.make({T:S.TAXA,tax:S.P.tax,grp:S.P.grp,n:S.P.n,groups:S.META.groups.length,ranks:S.META.ranks,
    nf:nf,box:$('tree'),label:gname,pass:function(){return null;},onOpen:function(){TR.render();},
    state:function(id){return PK.state([id]);},cycle:function(id){PK.cycle([id]);},
    inside:function(r){return !!TF.inc&&TF.inc[r]===1;}});
  S.META.groups.forEach(function(g,j){
    if(!count[j])return;
    var b=CH.chip(box,g,'',function(){return S.groups;},true,'',picked);
    b.setAttribute('data-g',j);paint(b);if(TR)TR.attach(b,j);
  });
  PK=TX.picker({input:$('q'),list:$('sugg'),msg:$('qn'),picks:S.picks,ranks:S.META.ranks,nf:nf,
    taxa:function(){return S.TAXA;},counts:function(){return TX.counts(S.TAXA,S.P.tax,S.P.n);},onChange:picked,
    onPick:function(r){if(TR)TR.reveal(r);}});
  BAR=CH.bar({box:$('selbar'),clear:clearAll,fallback:$('q')});
  applyKeep();$('gfit').hidden=!(CH.any(S.groups)||S.picks.length);
  if(TR)TR.render();
}
$('gall').addEventListener('click',function(){S.groups={};picked();});

// The filter extension as map.js uses it: categories are already small numbers, so deck.gl uploads them as they are
// instead of running three million values through a lookup.
class Filter extends deck.DataFilterExtension{
  static componentName='Filter';
  initializeState(context,extension){super.initializeState(context,extension);
    var a=this.getAttributeManager().attributes.filterCategoryValues;if(a)a.settings.transform=null;}
  _getCategoryKey(category){return category;}
}
var EXT=null;
function pointData(){
  if(!S.keep||S.keep.length!==S.P.n)applyKeep();
  var P=S.P,cat=new Uint8Array(3*P.n),col=new Uint8Array(4*P.n),g0=neutral();
  for(var i=0;i<P.n;i++){
    var c=P.grp?color(P.grp[i]):g0;
    cat[3*i]=P.grp?P.grp[i]:0;cat[3*i+1]=i%10===0?1:0;cat[3*i+2]=S.keep[i];
    col[4*i]=c[0];col[4*i+1]=c[1];col[4*i+2]=c[2];col[4*i+3]=150;
  }
  return {length:P.n,attributes:{getPosition:{value:P.pos,size:2},getFilterCategory:{value:cat,size:3},
    getFillColor:{value:col,size:4,normalized:true}}};
}
function layers(){
  var P=S.P;
  if(!P||!S.deck)return;
  EXT=EXT||new Filter({filterSize:1,categorySize:3});
  S.PD=S.PD||pointData();
  var groups=[0];
  if(P.grp){groups=[];passing().forEach(function(v,j){if(v)groups.push(j);});}
  var thin=S.thin&&P.n>THIN_ABOVE;
  var lyr=[new deck.ScatterplotLayer({id:'pts',data:S.PD,radiusUnits:'pixels',getRadius:1.5,radiusMinPixels:1,radiusMaxPixels:3,
    stroked:false,pickable:true,extensions:[EXT],updateTriggers:{getFilterCategory:S.PDV},
    filterCategories:[groups,thin?[1]:[0,1],[1]]})];
  function ring(id,rows,px,rgb,w){
    return new deck.ScatterplotLayer({id:id,data:rows,getPosition:function(i){return [P.pos[2*i],P.pos[2*i+1]];},
      radiusUnits:'pixels',getRadius:px,filled:false,stroked:true,lineWidthUnits:'pixels',getLineWidth:w,getLineColor:rgb});
  }
  if(S.nbr.length)lyr.push(ring('nbr',S.nbr,6,[230,110,30],2));
  if(S.sel>=0)lyr.push(ring('sel',[S.sel],9,[29,29,27],2.5));
  S.deck.setProps({layers:lyr});
}

// Hover and click.
var ptip=el('div',{'class':'ptip',hidden:''});document.body.appendChild(ptip);
function tip(o){
  if(!S.P||o.index<0||!o.layer||o.layer.id!=='pts'){ptip.hidden=true;return;}
  var t=names(o.index);
  ptip.textContent=t.common||t.latin?(t.common||t.latin)+' · '+t.group:t.group||'Loading names…';
  ptip.hidden=false;
  var g=12,x=o.x+$('plot').getBoundingClientRect().left,y=o.y+$('plot').getBoundingClientRect().top;
  ptip.style.left=Math.max(4,x+g+ptip.offsetWidth>innerWidth-4?x-g-ptip.offsetWidth:x+g)+'px';
  ptip.style.top=Math.max(4,y+g+ptip.offsetHeight>innerHeight-4?y-g-ptip.offsetHeight:y+g)+'px';
}
function pick(o){if(S.P&&o.index>=0&&o.layer&&o.layer.id==='pts')select(o.index,false);}

function closeCard(){
  S.sel=-1;S.nbr=[];S.run++;$('card').hidden=true;
  writeHash();layers();
}
addEventListener('keydown',function(e){if(e.key==='Escape'&&!$('card').hidden)closeCard();});
async function neighborsOf(id){
  try{return await S.idx.neighbors(id);}
  catch(e){  // the daily update renamed files: reload the manifest once
    if(!e.stale)throw e;
    S.idx=await openIndex();return S.idx.neighbors(id);
  }
}
function select(i,fly){
  var P=S.P,id=P.id[i],run=++S.run,t=names(i),card=$('card');
  S.sel=i;S.nbr=[];
  if(fly){
    var z=Math.max(S.vs.zoom,S.zoom0+3);
    S.vs=Object.assign({},S.vs,{target:[P.pos[2*i],P.pos[2*i+1],0],zoom:z});S.deck.setProps({viewState:S.vs});
  }
  writeHash();
  var x=el('button',{type:'button','class':'x','aria-label':'Close'},['×']);x.addEventListener('click',closeCard);
  var ph=el('div',{'class':'ph'},['Loading photo']),sub=el('p',{'class':'muted'},[t.group||LOADING]),place=el('p',{'class':'muted'},['']);
  var nb=el('ul',{'class':'nbrs','aria-label':'Closest matches'}),nbNote=el('p',{'class':'muted'},['Finding closest matches…']);
  var link=function(href,text,cls){return el('a',{'class':'btn '+(cls||''),href:href,target:'_blank',rel:'noopener'},[text]);};
  var actions=el('div',{'class':'actions'},[
    link('https://www.inaturalist.org/observations/'+id,'Help identify on iNaturalist','primary'),
    link(CFG.searchUrl+'#id='+id,'More like this'),link(CFG.mapUrl+'#record='+id,'Show on map')]);
  var title=el('h2',{},[t.common||t.latin||t.group||'Observation '+id]);
  card.textContent='';
  [x,ph,el('div',{'class':'body'},[title,sub,place,actions,el('p',{'class':'muted'},['Closest matches, from the full image space']),nbNote,nb])]
    .forEach(function(c){card.appendChild(c);});
  card.hidden=false;x.focus();
  // the shards arrived after this card opened: fill in what they know, unless iNaturalist's answer already did
  S.relabel=function(){
    var n=names(S.sel);if(sub.textContent!==LOADING)return;
    sub.textContent=n.group;title.textContent=n.common||n.latin||n.group;
  };
  layers();
  (async function(){
    var hits;
    try{hits=await neighborsOf(id);}catch(e){if(run===S.run)nbNote.textContent='Could not load matches: '+e.message;return;}
    if(run!==S.run)return;
    if(!hits){nbNote.textContent='Its closest matches are not computed yet; the index may predate this observation.';}
    else{
      S.nbr=hits.map(function(h){return L.find(S.P,h.id);}).filter(function(r){return r>=0;});
      layers();
    }
    var ids=[id].concat((hits||[]).map(function(h){return h.id;}));
    try{await Meta.fetchObservations(ids,function(u){return fetch(u);},S.cache);}
    catch(e){if(run===S.run){ph.textContent='Could not load the photo';nbNote.textContent=e.message;}return;}
    if(run!==S.run)return;
    var o=S.cache.get(id);
    if(!o){ph.textContent='This record is no longer on iNaturalist';}
    else{
      var p=o.photos&&o.photos[0],ot=o.taxon||{};
      if(p){ph.textContent='';ph.appendChild(el('img',{src:String(p.url).replace('/square.','/medium.'),alt:'Photo of '+(t.common||t.latin||t.group)}));}
      else ph.textContent='No photo on iNaturalist now';
      if(ot.name)title.textContent=ot.preferred_common_name||ot.name;
      place.textContent=(o.observed_on||'Date unknown')+' · '+(o.place_guess||'Place unknown');
      if(o.quality_grade&&o.quality_grade!=='needs_id')sub.textContent=t.group+' · now '+o.quality_grade+', so it no longer needs an ID';
    }
    if(!hits)return;
    var res=Meta.build(hits,S.cache),left=[];
    if(res.notNeedsId)left.push(res.notNeedsId+' no longer need an ID');
    if(res.missing)left.push(res.missing+' no longer on iNaturalist');
    nbNote.textContent=left.length?'Left out: '+left.join(', ')+'.':'';
    res.cards.forEach(function(c){
      var label=(c.common||c.name||'Unidentified'),row=L.find(S.P,c.id);
      var img=c.photo?el('img',{src:c.photo,alt:label,loading:'lazy'}):label;
      var b=el('button',{type:'button','aria-label':'Jump to '+label+(row<0?' (not in the plot)':''),'data-id':c.id},[img]);
      b.addEventListener('click',function(){row=L.find(S.P,c.id);if(row>=0)select(row,true);else window.open('https://www.inaturalist.org/observations/'+c.id,'_blank','noopener');});
      nb.appendChild(el('li',{},[b]));
    });
  })();
}

async function load(){
  status('Reading the index…');
  // the map page and the index manifest are independent, so ask for both at once
  var mapText=okFetch(MAP).then(function(r){return r.text();});
  mapText.catch(function(){});
  S.idx=await openIndex();
  var lay=S.idx.manifest.layout;
  if(!lay||!lay.parts||!lay.parts.length)throw new Error('This index has no photo-space layout yet.');
  var f=L.fidelity(lay.fidelity);
  $('fid').textContent=f?'Measured on the layout: on average '+Math.round(f.value*100)+'% of a photo’s '+f.k+
    ' true closest matches are among its '+f.k+' nearest points here.':'';
  var get=function(u){return okFetch(u).then(function(r){return r.arrayBuffer();}).then(L.gunzip);};
  var parts=Promise.all(lay.parts.map(function(p){
    return S.idx.file(p.name+'.bin').then(L.gunzip).then(function(b){return L.decodePart(b,p.count);});}));
  status('Downloading the layout…');
  var layout=await parts;
  // groups and names: fetched once the layout is in, so the two do not share the connection's bandwidth
  var groups=mapText.then(function(html){
    var meta=L.parseMapMeta(html);
    var taxa=get(new URL(meta.taxa,MAP)).then(function(b){return JSON.parse(new TextDecoder().decode(b));});
    var shards=meta.shards.map(function(s){return get(new URL(s.file,MAP)).then(function(b){return L.decodeShard(b,s.n);});});
    return Promise.all([Promise.all(shards),taxa]).then(function(g){return {meta:meta,shards:g[0],taxa:g[1]};});
  });
  groups.catch(function(){});
  S.P=L.layoutOnly(layout,lay.bbox);
  status(LOADING);
  start(lay.bbox);
  update();
  var want=+new URLSearchParams(location.hash.slice(1)).get('id');
  var row=want?L.find(S.P,want):-1;
  if(row>=0)select(row,true);
  try{
    var g=await groups;
    S.META=g.meta;
    applyJoin(L.join(g.shards,layout,lay.bbox,g.meta.bbox),g.taxa);
    status('');
  }catch(e){status('Colours and names are unavailable: '+e.message);}
}
function start(bbox){
  var box=$('plot'),w=Math.max(box.clientWidth,1),h=Math.max(box.clientHeight,1),sx=bbox[2]-bbox[0]||1,sy=bbox[3]-bbox[1]||1;
  S.zoom0=Math.log2(Math.min(w/sx,h/sy)*0.95);
  S.vs={target:[(bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2,0],zoom:S.zoom0,minZoom:S.zoom0-1,maxZoom:S.zoom0+16};
  S.deck=new deck.Deck({parent:box,views:new deck.OrthographicView({id:'photo-space',flipY:false}),controller:true,
    viewState:S.vs,pickingRadius:4,
    onViewStateChange:function(e){S.vs=e.viewState;S.deck.setProps({viewState:S.vs});},
    // while the view moves it draws one record in ten, and all of them once it stops
    onInteractionStateChange:function(st){
      var t=!!(st.isDragging||st.isZooming||st.isPanning);
      if(t!==S.thin){S.thin=t;layers();}
    },
    onHover:tip,onClick:pick,layers:[]});
  box.addEventListener('pointerleave',function(){ptip.hidden=true;});
}
load().catch(function(e){
  $('count').textContent='Could not load the photo space';status(e.message);
});
})();
