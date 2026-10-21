// Photo space: every observation that needs an ID, drawn at its layout position (see embeddings_layout.js).
// Points are the join of the atlas repo's layout parts with the map's pool shards, so names and groups come
// from the map data and observations that left Needs ID drop out on their own.
(function(){
'use strict';
var LOADING='Loading groups and names…';
var CFG=EMBEDDINGS_CONFIG,Meta=AtlasSearchMeta,L=EmbeddingsLayout;
var WHOLE=4<<20,THIN_ABOVE=200000,FEW=50,nf=new Intl.NumberFormat('en-CA');
var DATA=new URL(CFG.dataUrl,location.href).href.replace(/\/*$/,'/');
var MAP=new URL(CFG.mapUrl,location.href).href;
var S={idx:null,P:null,META:null,TAXA:null,groups:{},picks:[],split:[],extra:[],keep:null,sel:-1,nbr:[],thin:false,cache:new Map(),run:0,deck:null,vs:null,PD:null,ring:null,lasso:null,lassoV:0};

var MF=null,TF=null,TR=null,PASS=['park','bcpark','projects'],MAPONLY={park:'Park',bcpark:'BC park',projects:'Projects'},
  AREA_IN=null,VIEW_IN=null;
function $(id){return document.getElementById(id);}
var X=SpaceSelect(S,$,picked,layers),areaIndex=X.areaIndex,viewBox=X.viewBox,areaMask=X.areaMask,projMask=X.projMask,lasso=X.lasso,lassoDrag=X.lassoDrag,moved=X.moved;
var LV=LifeView({S:S,$:$,MAP:MAP,frame:frame,redraw:layers,status:status,color:color,writeHash:writeHash});
function el(tag,attrs,kids){
  var e=document.createElement(tag);
  Object.keys(attrs||{}).forEach(function(k){if(attrs[k]!==null&&attrs[k]!==undefined)e.setAttribute(k,attrs[k]);});
  (kids||[]).forEach(function(c){e.appendChild(typeof c==='string'?document.createTextNode(c):c);});
  return e;
}
function status(t){$('status').textContent=t;}
function color(g){return MapFilter.color(S.META.groups[g],g);}
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
  if(S.subset&&S.deck)fit();else if(S.deck&&S.vs===S.home)goHome();
  if(S.sel>=0&&S.relabel)S.relabel();
  LV.joined();
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
  if(SYNC)SYNC.send();
  // before the join the selection is only in the hash, so it stays as it is
  var h=S.P.grp?MF.write(S).concat(S.area?['area='+S.area]:[],S.extra):location.hash.slice(1).split('&').filter(function(t){
    return t&&t.indexOf('id=')!==0;});
  h=LV.hash(h);
  // the split view keeps the map of life's tokens in its own address, so a reload or a shared link keeps the view
  if(parent!==window)parent.postMessage({type:'wtid-life',tokens:LV.hash([])},location.origin);
  if(S.sel>=0)h.push('id='+S.P.id[S.sel]);
  history.replaceState(null,'',h.length?'#'+h.join('&'):location.pathname+location.search);
}
// The selection as the split view hands it over (the dates, months, groups, show only and taxa; the area and
// the filters left to the map stay as they are). Before the join it only goes into the hash, chips() reads it.
function selKey(){return S.P&&S.P.grp?MF.write(S).join('&'):MapFilter.tokens(location.hash);}
var SYNC=null;
function applySel(str){
  if(!(S.P&&S.P.grp)){
    var h=location.hash.slice(1).split('&').filter(function(t){return t&&MapFilter.tokens(t)==='';});
    history.replaceState(null,'','#'+h.concat(str?str.split('&'):[]).join('&'));return;}
  var r=MF.read(new URLSearchParams(str));
  ['up','lo','hi','months','groups','only','acc'].forEach(function(k){S[k]=r[k];});
  S.picks.length=0;r.picks.forEach(function(p){S.picks.push(p);});S.split=[];
  picked();
}
SYNC=MapFilter.sync({key:selKey,apply:applySel});
// In the split view the map holds the filters, so the side panel folds into a count over the plot; the shell
// says when this view is alone. The "i" button shows the page's warning note over the plot.
addEventListener('message',function(e){
  if(e.origin===location.origin&&e.source===parent&&e.data&&e.data.type==='wtid-layout')
    {document.documentElement.classList.toggle('peer',!!e.data.peer);resized();}});
// The map's Reset all filters also shows the whole space again, which takes the view's cut off the map.
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-reset'||!S.deck)return;
  if(!LV.home())goHome();
});
// In the split view the map owns the area: its drawn shape and resolved parks arrive as one ring list, '' for none.
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-area'||typeof e.data.area!=='string')return;
  AREA_IN=e.data.area;if(S.P&&S.P.grp){S.area=AREA_IN;picked();}
});
// The map's viewport arrives the same way and masks the same way, but is only the map's to change.
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-view'||typeof e.data.area!=='string')return;
  VIEW_IN=e.data.area;if(S.P&&S.P.grp){S.view=VIEW_IN;picked();}
});
$('info').addEventListener('click',function(){
  $('info').setAttribute('aria-expanded',document.documentElement.classList.toggle('about'));});
// CH.show rewrites the label, so the colour dot goes back in after it.
function paint(b){
  var j=+b.getAttribute('data-g'),dot=el('i',{});dot.style.background='rgb('+color(j).join(',')+')';
  CH.show(b,gname(j)+' '+nf.format(S.count[j]),S.groups[S.META.groups[j]]||'');b.insertBefore(dot,b.firstChild);
}
function baseKey(){return [S.lo,S.hi,S.up,S.months,JSON.stringify(S.only),S.acc,S.area,S.view,S.lassoV].join('|');}
function applyBase(){
  var P=S.P,key=baseKey();
  if(S.baseKey===key&&S.base&&S.base.length===P.n)return;
  S.baseKey=key;S.base=new Uint8Array(P.n).fill(1);
  if(P.grp){
    MF.rest(S,P.obs,P.up,P.flags,P.n,S.base);
    var M=areaMask();
    if(M)for(var i=0;i<P.n;i++)S.base[i]&=M[i];
    var V=viewBox();
    if(V){var L=P.lonlat;for(var v=0;v<P.n;v++){var lo=L[2*v],la=L[2*v+1];
      if(!(lo>=V[0]&&lo<=V[2]&&la>=V[1]&&la<=V[3]))S.base[v]=0;}}
    if(S.lasso&&S.lasso.length===P.n)for(var k=0;k<P.n;k++)S.base[k]&=S.lasso[k];
  }
  var count=S.count=new Array(S.META?S.META.groups.length:0).fill(0);
  if(P.grp)for(var j=0;j<P.n;j++)if(S.base[j])count[P.grp[j]]++;
  if(TR)TR.refresh();
}
// Which points the filters keep: the taxon picks with the picked groups beside them (see MapFilter.keep),
// and the rest of the selection.
function applyKeep(){
  var P=S.P;
  applyBase();
  if(!S.keep||S.keep.length!==P.n)S.keep=new Uint8Array(P.n);
  if(P.grp){MF.keep(TF,MF.groupSet(S,TF),P.tax,P.grp,P.n,S.keep);
    for(var k=0;k<P.n;k++)S.keep[k]&=S.base[k];}
  else S.keep.fill(1);
  if(S.subset)for(var j=0;j<P.n;j++)if(!S.subset.has(P.id[j]))S.keep[j]=0;
  var pm=projMask();if(pm)for(var q=0;q<P.n;q++)S.keep[q]&=pm[q];
  if(S.PD){var c=S.PD.attributes.getFilterCategory.value;
    for(var i=0;i<P.n;i++)c[3*i+2]=S.keep[i];
    S.PD.attributes.getFilterCategory={value:c,size:3};S.PDV=(S.PDV||0)+1;}
}
function update(){
  var s=S.shown=shown(),P=S.P,total=S.META?S.META.n:P.n;
  S.few=null;  // a handful of kept points gets rings, so it is found on the map of life
  if(P.grp&&s<=FEW){var ok=passing();S.few=[];for(var i=0;i<P.n;i++)if(ok[P.grp[i]]&&S.keep[i])S.few.push(i);}
  $('count').textContent=P.grp?nf.format(s)+' shown of '+nf.format(P.n):nf.format(P.n)+' points';
  $('more').textContent=P.grp&&P.n<total?'('+nf.format(total-P.n)+' of the map’s '+nf.format(total)+
    ' records are not placed yet)':'';
  [].forEach.call($('groups').querySelectorAll('button[data-g]'),paint);
  if(BAR)BAR.set(items());if(TR)TR.render();layers();
}
// A pick, a left-out or a removal anywhere: the groups beside included taxa change which points are kept.
function picked(){
  TF=TX.filter(S.TAXA,S.picks);applyKeep();update();writeHash();$('gfit').hidden=!items().length;
}
var PK=null,BAR=null;
// The map's selection bar plus a date chip (the map keeps dates in its inputs) and, marked "map only", the
// filters this page leaves to the map. The area applies here when it reads; in the split view it is the map's
// to clear, so its chip has no ×.
function alabel(){return parent!==window?'Map area':'Drawn area';}
function items(){
  var L=MF.LAST,out=CH.items({S:S,meta:S.META,terms:TX.terms({T:S.TAXA,picks:S.picks,groups:[],meta:S.META,n:0,split:S.split}),
    picker:PK,pj:{items:function(){return [];}},months:MF.MONTH,only:MF.ONLYDEF,
    acc:{label:(MF.ACCDEF.filter(function(a){return a[0]===S.acc;})[0]||[])[1]||'',clear:function(){S.acc='';}},
    area:{term:function(){return S.area?{label:alabel()}:null;},clear:parent===window&&function(){S.area='';picked();}},redraw:picked});
  if(S.lo>0||S.hi<L)out.push({label:(S.up?'Uploaded ':'Observed ')+(S.lo>0?MF.iso(S.lo):'start')+' to '+(S.hi<L?MF.iso(S.hi):'now'),
    remove:function(){S.lo=0;S.hi=L;S.up=false;picked();}});
  if(S.area&&!areaIndex())out.forEach(function(t){if(t.label===alabel())t.tag='map only';});
  if(viewBox())out.push({label:'Map view'});
  if(S.proj)out.push({label:'Map projects',tag:'map only'});
  if(S.ring)out.push({label:'Lasso',remove:function(){lasso(null);}});
  if(S.subset)out.push({label:'Photo search: "'+S.subLabel+'" ('+S.subset.size+')',
    remove:function(){parent.postMessage({type:'wtid-subset',ids:null},location.origin);}});
  S.extra.forEach(function(t){var k=t.split('=')[0];
    out.push({label:MAPONLY[k]+': '+decodeURIComponent(t.slice(k.length+1)).replace(/,/g,', '),tag:'map only',
      remove:function(){S.extra=S.extra.filter(function(x){return x!==t;});picked();}});});
  return out;
}
function clearAll(){S.groups={};S.only={};S.acc='';S.months=0;S.lo=0;S.hi=MF.LAST;S.up=false;S.area='';S.extra=[];
  S.picks.length=0;S.split=[];$('q').value='';if(S.ring)lasso(null);else picked();}
// The box [x0,y0,x1,y1] between the t and 1-t quantiles of the points, so a few stray points do not flatten the view.
function span(xs,ys,t){
  function q(a){a=Float32Array.from(a).sort();return [a[Math.floor(t*(a.length-1))],a[Math.ceil((1-t)*(a.length-1))]];}
  var x=q(xs),y=q(ys);return [x[0],y[0],x[1],y[1]];
}
// Shows the box in the plot; beside the map, below the panel that floats over the plot's top.
function frame(b){
  var box=$('plot'),top=document.documentElement.classList.contains('peer')?
      Math.max(0,document.querySelector('.side').getBoundingClientRect().bottom-box.getBoundingClientRect().top):0,
    z=Math.log2(Math.min(Math.max(box.clientWidth,1)/(b[2]-b[0]||1),Math.max(box.clientHeight-top,1)/(b[3]-b[1]||1))*.9);
  z=Math.min(Math.max(z,S.vs.minZoom),S.vs.maxZoom);
  S.vs=Object.assign({},S.vs,{target:[(b[0]+b[2])/2,(b[1]+b[3])/2+top/2/Math.pow(2,z),0],zoom:z});
  S.deck.setProps({viewState:S.vs});moved();S.framed={b:b,vs:S.vs};
}
function fit(){
  var P=S.P,ok=passing(),xs=[],ys=[];
  for(var i=0;i<P.n;i++)if(ok[P.grp[i]]&&S.keep[i]){xs.push(P.pos[2*i]);ys.push(P.pos[2*i+1]);}
  if(xs.length)frame(span(xs,ys,.01));
}
// Home shows all the points. A framed view holds until it is moved, so a resize or a panel that grows refits it.
function goHome(){
  var P=S.P;
  if(!S.homeBox||S.homeBox.P!==P){var xs=new Float32Array(P.n),ys=new Float32Array(P.n);
    for(var i=0;i<P.n;i++){xs[i]=P.pos[2*i];ys[i]=P.pos[2*i+1];}
    S.homeBox={P:P,b:span(xs,ys,.001)};}
  frame(S.homeBox.b);S.home=S.vs;
}
function resized(){if(S.deck&&S.framed&&S.vs===S.framed.vs)frame(S.framed.b);else moved();}
$('gfit').addEventListener('click',fit);
function chips(){
  var P=S.P,count=new Array(S.META.groups.length).fill(0);
  for(var i=0;i<P.n;i++)count[P.grp[i]]++;
  var box=$('groups');box.textContent='';
  MF=MF||MapFilter(S.META);
  Object.assign(S,MF.read(new URLSearchParams(location.hash.slice(1))));
  if(AREA_IN!==null)S.area=AREA_IN;
  if(VIEW_IN!==null)S.view=VIEW_IN;
  S.extra=location.hash.slice(1).split('&').filter(function(t){return PASS.indexOf(t.split('=')[0])>=0;});
  TF=TX.filter(S.TAXA,S.picks);S.baseKey=null;applyBase();
  TR=S.TAXA&&TT.make({T:S.TAXA,tax:S.P.tax,grp:S.P.grp,n:S.P.n,groups:S.META.groups.length,ranks:S.META.ranks,
    nf:nf,box:$('tree'),label:gname,pass:function(){return S.base;},onOpen:function(){TR.render();},
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
  applyKeep();$('gfit').hidden=!items().length;$('ldraw').disabled=false;
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
  var P=S.P,cat=new Uint8Array(3*P.n),col=new Uint8Array(4*P.n),g0=neutral(),gc=P.grp?S.META.groups.map(function(g,j){return color(j);}):null;
  for(var i=0;i<P.n;i++){
    var c=P.grp?gc[P.grp[i]]:g0;
    cat[3*i]=P.grp?P.grp[i]:0;cat[3*i+1]=i%10===0?1:0;cat[3*i+2]=S.keep[i];
    col[4*i]=c[0];col[4*i+1]=c[1];col[4*i+2]=c[2];col[4*i+3]=150;
  }
  return {length:P.n,attributes:{getPosition:{value:P.pos,size:2},getFilterCategory:{value:cat,size:3},
    getFillColor:{value:col,size:4,normalized:true}}};
}
// Over the map of life the points show, and take clicks, while the filters hold some back or once the view is
// close enough to tell them apart; otherwise a click on the map zooms into its clade.
function filtered(){return S.shown!=null&&S.shown<S.P.n;}
function dots(){return filtered()||S.vs.zoom>=S.zoom0+3;}
function layers(){
  var P=S.P;
  if(!P||!S.deck)return;
  EXT=EXT||new Filter({filterSize:1,categorySize:3});
  S.PD=S.PD||pointData();
  var groups=[0];
  if(P.grp){groups=[];passing().forEach(function(v,j){if(v)groups.push(j);});}
  var thin=S.thin&&P.n>THIN_ABOVE,d=dots();
  var pts=new deck.ScatterplotLayer({id:'pts',data:S.PD,radiusUnits:'pixels',getRadius:1.5,radiusMinPixels:1,radiusMaxPixels:3,
    stroked:false,pickable:true,visible:!LV.on()||d,extensions:[EXT],updateTriggers:{getFilterCategory:S.PDV},
    filterCategories:[groups,thin?[1]:[0,1],[1]]});
  var lyr=LV.on()?LV.layers(pts,d,filtered(),groups):[pts];
  function ring(id,rows,px,rgb,w){
    return new deck.ScatterplotLayer({id:id,data:rows,getPosition:function(i){return [P.pos[2*i],P.pos[2*i+1]];},
      radiusUnits:'pixels',getRadius:px,filled:false,stroked:true,lineWidthUnits:'pixels',getLineWidth:w,getLineColor:rgb});
  }
  if(LV.on()&&S.few)lyr.push(ring('few',S.few,9,[29,29,27],2.5));
  if(S.nbr.length)lyr.push(ring('nbr',S.nbr,6,[230,110,30],2));
  if(S.sel>=0)lyr.push(ring('sel',[S.sel],9,[29,29,27],2.5));
  if(S.ring)lyr.push(new deck.PathLayer({id:'lasso',data:[S.ring],getPath:function(r){return r;},positionFormat:'XY',
    widthUnits:'pixels',getWidth:1.5,getColor:[29,29,27,200]}));
  S.deck.setProps({layers:lyr});
}

// Hover and click.
var ptip=el('div',{'class':'ptip',hidden:''});document.body.appendChild(ptip);
function tip(o){
  var lt=o.layer&&o.layer.id==='pts'?null:LV.text(o);
  if(lt===''||lt===null&&(!S.P||o.index<0||!o.layer||o.layer.id!=='pts')){ptip.hidden=true;return;}
  var t=lt===null&&names(o.index);
  ptip.textContent=lt!==null?lt:t.common||t.latin?(t.common||t.latin)+' · '+t.group:t.group||'Loading names…';
  ptip.hidden=false;
  var g=12,x=o.x+$('plot').getBoundingClientRect().left,y=o.y+$('plot').getBoundingClientRect().top;
  ptip.style.left=Math.max(4,x+g+ptip.offsetWidth>innerWidth-4?x-g-ptip.offsetWidth:x+g)+'px';
  ptip.style.top=Math.max(4,y+g+ptip.offsetHeight>innerHeight-4?y-g-ptip.offsetHeight:y+g)+'px';
}
function pick(o){if(S.P&&o.index>=0&&o.layer&&o.layer.id==='pts')select(o.index,false);else LV.click(o);}

function closeCard(){
  S.sel=-1;S.nbr=[];S.run++;$('card').hidden=true;
  writeHash();layers();tell(null);
}
// The split view's photo search hands over a set of ids (null clears it); one that arrives before the join waits for it.
addEventListener('message',function(e){
  var d=e.data;
  if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-subset')return;
  S.subset=d.ids?new Set(d.ids):null;S.subLabel=d.label;
  if(S.P&&S.P.grp){applyKeep();update();$('gfit').hidden=!items().length;if(S.subset&&S.deck)fit();}
});
// The map's projects keep the same records here (null clears them); the map is the place to change them.
addEventListener('message',function(e){
  var d=e.data;if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-projects')return;
  S.proj=d.ids instanceof Uint32Array?d.ids:null;if(S.P&&S.P.grp){applyKeep();update();$('gfit').hidden=!items().length;}
});
// The split view mirrors the picked record in the other frame by id; a remote pick is not posted back.
var remote=false;
function tell(id){if(parent!==window&&!remote)parent.postMessage({type:'wtid-record',id:id},location.origin);}
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-record'||!S.P)return;
  var id=e.data.id,i=id==null?-1:Array.prototype.indexOf.call(S.P.id,id);
  if(i===S.sel||(id!=null&&i<0))return;
  remote=true;try{if(i<0)closeCard();else select(i,true);}finally{remote=false;}
});
// Esc cancels what is in progress, as on the map; a finished lasso goes only with its Clear button or chip.
addEventListener('keydown',function(e){if(e.key!=='Escape')return;X.cancel();X.draw(false);if(!$('card').hidden)closeCard();});
// The card's left edge: drag it, or use the arrow keys; a double click goes back to the default. The width is remembered.
function cardWidth(w){
  var c=$('card');if(w==null){c.style.width='';localStorage.removeItem('wtid-card');return;}
  w=Math.max(240,Math.min(innerWidth*0.7,w));c.style.width=w+'px';localStorage.setItem('wtid-card',w);
}
if(+localStorage.getItem('wtid-card'))cardWidth(+localStorage.getItem('wtid-card'));
function resizer(){
  var rz=el('button',{type:'button','class':'rz','aria-label':'Resize the card'});
  // preventDefault: otherwise the photo under the edge starts a native image drag and cancels the pointer
  rz.addEventListener('pointerdown',function(e){e.preventDefault();rz.setPointerCapture(e.pointerId);rz.classList.add('on');});
  rz.addEventListener('pointermove',function(e){if(rz.classList.contains('on'))cardWidth($('card').getBoundingClientRect().right-e.clientX);});
  rz.addEventListener('pointerup',function(){rz.classList.remove('on');});
  rz.addEventListener('dblclick',function(){cardWidth(null);});
  rz.addEventListener('keydown',function(e){
    var d={ArrowLeft:20,ArrowRight:-20}[e.key];if(d){cardWidth($('card').getBoundingClientRect().width+d);e.preventDefault();}
    else if(e.key==='Home'){cardWidth(null);e.preventDefault();}});
  return rz;
}
async function neighborsOf(id){
  try{return await S.idx.neighbors(id);}
  catch(e){  // the daily update renamed files: reload the manifest once
    if(!e.stale)throw e;
    S.idx=await openIndex();return S.idx.neighbors(id);
  }
}
// Keeps this group alone, or, when it already is the only one, goes back to all groups.
function onlyGroup(g){
  var name=S.META.groups[g],b=el('button',{type:'button','class':'btn'},['']);
  function solo(){var on=Object.keys(S.groups).filter(function(k){return S.groups[k];});return on.length===1&&S.groups[name]==='inc';}
  function label(){b.textContent=solo()?'All groups':'Only '+gname(g);}
  b.addEventListener('click',function(){var s=solo();S.groups={};if(!s)S.groups[name]='inc';picked();label();});
  label();return b;
}
function select(i,fly){
  var P=S.P,id=P.id[i],run=++S.run,t=names(i),card=$('card');
  S.sel=i;S.nbr=[];tell(id);
  if(fly){
    var z=Math.max(S.vs.zoom,S.zoom0+3);
    S.vs=Object.assign({},S.vs,{target:[P.pos[2*i],P.pos[2*i+1],0],zoom:z});S.deck.setProps({viewState:S.vs});moved();
  }
  writeHash();
  var x=el('button',{type:'button','class':'x','aria-label':'Close'},['×']);x.addEventListener('click',closeCard);
  var ph=el('div',{'class':'ph'},['Loading photo']),sub=el('p',{'class':'muted'},[t.group||LOADING]),place=el('p',{'class':'muted'},['']);
  var nb=el('ul',{'class':'nbrs','aria-label':'Closest matches'}),nbNote=el('p',{'class':'muted'},['Finding closest matches…']);
  var link=function(href,text,cls){return el('a',{'class':'btn '+(cls||''),href:href,target:'_blank',rel:'noopener'},[text]);};
  var actions=el('div',{'class':'actions'},[
    link('https://www.inaturalist.org/observations/'+id,'Help identify on iNaturalist','primary'),
    link(CFG.searchUrl+'#id='+id,'More like this'),link(CFG.mapUrl+'#record='+id,'Show on map')]);
  var tx=S.TAXA&&P.tax&&P.tax[i]!==65535&&S.TAXA[P.tax[i]];
  if(tx&&tx.length>5)actions.appendChild(link('tree.html#sel='+tx[2],'Show in tree'));  // counts ship only with the tree page
  if(P.grp)actions.appendChild(onlyGroup(P.grp[i]));
  var title=el('h2',{},[t.common||t.latin||t.group||'Observation '+id]);
  card.textContent='';
  [resizer(),x,ph,el('div',{'class':'body'},[title,sub,place,actions,el('p',{'class':'muted'},['Closest matches, from the full image space']),nbNote,nb])]
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
    if(hits)hits.sort(function(a,b){return b.score-a.score;});  // rank 1 is the highest cosine
    if(!hits){nbNote.textContent='Its closest matches are not computed yet; the index may predate this observation.';}
    else{
      S.nbr=hits.map(function(h){return L.find(S.P,h.id);}).filter(function(r){return r>=0;});
      layers();
      if(parent!==window)parent.postMessage({type:'wtid-matches',id:id,
        hits:hits.map(function(h){return {id:h.id,score:h.score};})},location.origin);
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
    var res=Meta.build(hits,S.cache),left=[],score={},rank={};
    hits.forEach(function(h,k){score[h.id]=h.score;rank[h.id]=k+1;});
    if(res.notNeedsId)left.push(res.notNeedsId+' no longer need an ID');
    if(res.missing)left.push(res.missing+' no longer on iNaturalist');
    nbNote.textContent=(left.length?'Left out: '+left.join(', ')+'. ':'')+'1 = most similar. Numbers match the map markers.';
    res.cards.forEach(function(c){
      var label=(c.common||c.name||'Unidentified'),row=L.find(S.P,c.id);
      var img=c.photo?el('img',{src:c.photo,alt:label,loading:'lazy'}):label;
      var b=el('button',{type:'button','aria-label':'Jump to '+label+(row<0?' (not in the plot)':''),'data-id':c.id},[img]);
      b.addEventListener('click',function(){row=L.find(S.P,c.id);if(row>=0)select(row,true);else window.open('https://www.inaturalist.org/observations/'+c.id,'_blank','noopener');});
      var sc=el('span',{'class':'score'},['Cosine '+score[c.id].toFixed(3)]);
      sc.title='cosine similarity '+score[c.id];
      b.addEventListener('mouseenter',function(){
        if(parent!==window)parent.postMessage({type:'wtid-focus',id:c.id},location.origin);});
      nb.appendChild(el('li',{},[b,el('span',{'class':'rank'},[String(rank[c.id])]),sc]));
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
    return S.idx.parallel(p.name+'.bin').then(L.gunzip).then(function(b){return L.decodePart(b,p.count);});}));
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
    status('');  // before the join, which may start drawing the map
    applyJoin(L.join(g.shards,layout,lay.bbox,g.meta.bbox),g.taxa);
  }catch(e){status('Colours and names are unavailable: '+e.message);}
}
function start(bbox){
  var box=$('plot'),w=Math.max(box.clientWidth,1),h=Math.max(box.clientHeight,1),sx=bbox[2]-bbox[0]||1,sy=bbox[3]-bbox[1]||1;
  S.zoom0=Math.log2(Math.min(w/sx,h/sy)*0.95);
  S.vs={target:[(bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2,0],zoom:S.zoom0,minZoom:S.zoom0-1,maxZoom:S.zoom0+16};
  S.deck=new deck.Deck({parent:box,views:new deck.OrthographicView({id:'photo-space',flipY:false}),controller:true,
    viewState:S.vs,pickingRadius:4,
    onViewStateChange:function(e){S.vs=e.viewState;S.deck.setProps({viewState:S.vs});moved();
      var k=Math.round(S.vs.zoom*4)+(dots()?'d':'');if(k!==S.zk){S.zk=k;layers();}},  // labels and points by zoom
    // while the view moves it draws one record in ten, and all of them once it stops
    onInteractionStateChange:function(st){
      var t=!!(st.isDragging||st.isZooming||st.isPanning);
      if(t!==S.thin){S.thin=t;layers();}
    },
    onHover:tip,onClick:pick,layers:[]});
  box.addEventListener('pointerleave',function(){ptip.hidden=true;});
  lassoDrag(box);goHome();new ResizeObserver(resized).observe(box);  // the split's divider changes what is in view
}
load().catch(function(e){
  $('count').textContent='Could not load the photo space';status(e.message);
});
})();
