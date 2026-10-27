(function(){
'use strict';
function $(id){return document.getElementById(id);}
var dark=matchMedia('(prefers-color-scheme: dark)').matches;
var MF=MapFilter(META),DAY=MF.DAY,D0=MF.D0,NO=MF.NO,NOTAX=MF.NOTAX,LAST=MF.LAST;
var FLAG=MF.FLAG,ONLYFLAG=MF.ONLYFLAG,ONLYKEYS=MF.ONLYKEYS,nf=new Intl.NumberFormat('en-CA'),
  iso=MF.iso;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
  return '&#'+c.charCodeAt(0)+';';});}

// The subtitle names the build date; say how old that is, and warn once it is stale.
var STALE_DAYS=2;
(function(){
  var el=$('updated'),t=el?Date.parse(el.getAttribute('datetime')+'T00:00:00Z'):NaN;
  if(isNaN(t))return;
  var n=new Date(),days=Math.floor((Date.UTC(n.getUTCFullYear(),n.getUTCMonth(),n.getUTCDate())-t)/DAY),
    before=el.previousSibling,after=el.nextSibling;
  if(!before||!after||before.nodeType!==3||after.nodeType!==3)return;
  if(days>STALE_DAYS){before.nodeValue='Last updated ';
    el.textContent=days+' days ago';after.nodeValue=after.nodeValue.replace(/^\./,'; some records may have an ID by now.');}
  else{before.nodeValue=before.nodeValue.replace(/ on $/,', updated ');
    el.textContent=days<=0?'today':days===1?'yesterday':days+' days ago';}
})();

var M0=MF.M0;

// What the viewer picked. Written to the URL hash so a view can be shared or bookmarked.
// Groups and show only hold chip states (see map_chips.js): {Insecta:'inc', Aves:'not'}.
var S=Object.assign({split:[],rec:null,at:null,fly:false},MF.read(new URLSearchParams(location.hash.slice(1))));
(function readHash(){
  var h=new URLSearchParams(location.hash.slice(1));
  S.rec=+h.get('record')||null;
  var at=(h.get('at')||'').split('/').map(Number);if(at.length===3&&at.every(isFinite))S.at=at;
  S.fly=!!S.rec&&!S.at;
})();
var PJ=projectFilter({meta:META,hash:new URLSearchParams(location.hash.slice(1)),changed:function(){refilter();}});
var hashTimer=0;
// The split view hands the selection over live; the area and projects are not part of it yet.
var SYNC=MapFilter.sync({key:function(){return MF.write(S).join('&');},apply:function(str){
  var r=MF.read(new URLSearchParams(str)),was=taxaKey();
  ['up','lo','hi','months','groups','only','acc'].forEach(function(k){S[k]=r[k];});
  S.picks.length=0;r.picks.forEach(function(p){S.picks.push(p);});S.split=[];
  // before the taxa and records are in, refilter runs once they are
  if(TAXA){search();FB.showClades();}
  FIT=taxaKey()!==was&&taxaKey()!=='';  // a taxon or group picked in the tree or photo space brings its records into view
  FB.showGroups();FB.showMonths();FB.showOnly();if(P.n)refilter();render();}});
function taxaKey(){return MF.write(S).filter(function(t){return /^(taxa|groups)=/.test(t);}).join('&');}
// The selection: the hash without the open record and the view.
function sel(){
  var h=MF.write(S);
  if(AREA.hash())h.push(AREA.hash());if(PJ.hash())h.push(PJ.hash());
  return h;}
function writeHash(){SYNC.send();clearTimeout(hashTimer);hashTimer=setTimeout(function(){
  var h=sel();
  if(P.n&&SEL>=0)h.push('record='+P.id[SEL]);else if(S.rec)h.push('record='+S.rec);
  var c=map.getCenter();h.push('at='+map.getZoom().toFixed(1)+'/'+c.lat.toFixed(3)+'/'+
    c.lng.toFixed(3));
  history.replaceState(null,'','#'+h.join('&'));},250);}

// Records, concatenated as shards arrive.
var P={n:0,id:new Uint32Array(0),pos:new Float32Array(0),obs:new Uint16Array(0),
  up:new Uint16Array(0),tax:new Uint16Array(0),grp:new Uint8Array(0),ids:new Uint8Array(0),
  fl:new Uint8Array(0)};
var TAXA=null,TF=TX.filter(null,[]),GONE={},GONE_NEW=false,KEEP=new Uint8Array(0),SEL=-1,NBR=[],
  CUM=new Float64Array(META.days+1),TOT=META.totals||null,TC=null,NODAY=0,PER=null,ALT=0,FIT=false;
function cat(a,b){var c=new a.constructor(a.length+b.length);c.set(a);c.set(b,a.length);return c;}
function unzip(buf){
  var u=new Uint8Array(buf,0,Math.min(2,buf.byteLength));
  if(u[0]!==0x1f||u[1]!==0x8b)return Promise.resolve(buf);
  return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip')))
    .arrayBuffer();
}
function get(url){return fetch(url).then(function(r){
  if(!r.ok)throw new Error('HTTP '+r.status);return r.arrayBuffer();}).then(unzip);}
// A shard stores each wider column byte by byte (every value's low byte, then the next), and ids
// as steps from the previous id.
function addShard(buf,n){
  if(buf.byteLength!==17*n)throw new Error('unexpected size');
  var b=META.bbox,sx=(b[2]-b[0])/65535,sy=(b[3]-b[1])/65535,o=0,u=new Uint8Array(buf);
  function col(T,w){if(w===1){o+=n;return u.slice(o-n,o);}
    var a=new T(n),v=new Uint8Array(a.buffer);
    for(var j=0;j<w;j++,o+=n)for(var k=0;k<n;k++)v[k*w+j]=u[o+k];return a;}
  var id=col(Uint32Array,4),qx=col(Uint16Array,2),qy=col(Uint16Array,2),obs=col(Uint16Array,2),
    up=col(Uint16Array,2),tax=col(Uint16Array,2),grp=col(Uint8Array,1),ids=col(Uint8Array,1),
    fl=col(Uint8Array,1),pos=new Float32Array(2*n);
  for(var s=0,i=0;i<n;i++)id[i]=s=(s+id[i])>>>0;
  for(i=0;i<n;i++){pos[2*i]=b[0]+qx[i]*sx;pos[2*i+1]=b[1]+qy[i]*sy;}
  P={n:P.n+n,id:cat(P.id,id),pos:cat(P.pos,pos),obs:cat(P.obs,obs),up:cat(P.up,up),
    tax:cat(P.tax,tax),grp:cat(P.grp,grp),ids:cat(P.ids,ids),fl:cat(P.fl,fl)};
}

// The map filters on the GPU. Each record carries its observed and uploaded day (-1 for none) as
// filter values, and four categories: group, observed month, uploaded month (12 for no date) and a
// status value, bit 1 introduced, 2 threatened, 4 outside the location accuracy choice, 8 kept by the taxon picks
// and the area and not deleted, 16 one record in ten. Group, month, status and date changes then
// only change the filter settings; the data is uploaded again only when records arrive, the picks,
// the area or deletions change, or the groups change while a taxon is included (the groups and
// included taxa are one set, so the kept bit then carries the groups too).
var SUB=null,SUBL='',SUBV=0;  // the split view's photo search: a Set of ids, its label, a version for PD_KEY
var ST_KEEP=MF.ST_KEEP,ST_INEXACT=MF.ST_INEXACT,PD=null,PD_KEY=null,PD_GONE=-1,PD_CAT=0,
  OUT=new Uint8Array(0),RC=null,PJW=null,FK=null,FKV=0,FKM=null,PJP='',KV=0,CNP='',CNT=0;
// The photo space's lasso: the ids it keeps, or null; the mask is built once per list and shard count.
function fmask(n){
  if(!FKM||FKM.v!==FKV||FKM.m.length!==n){var m=new Uint8Array(n);projMask(P.id,[FK],m,0,n);FKM={v:FKV,m:m};}
  return FKM.m;}
function inc(){return !!TF.inc;}
function pointData(){
  PJ.sync(P);
  var n=P.n,gone=Object.keys(GONE).length,i,key=[TF,inc()?CH.picked(S.groups,META.groups,'inc').join():'',AREA.ver(),PJ.key(),SUBV,FKV,S.acc];
  if(PD&&PD.length===n&&PD_KEY&&PD_KEY.every(function(k,j){return k===key[j];})&&PD_GONE===gone)return;
  var same=PD&&PD.length===n,days=same?PD.days:new Float32Array(2*n),
    cat=same?PD.attributes.getFilterCategory.value.slice():new Uint8Array(4*n);
  if(!same)for(i=0;i<n;i++)MF.record(days,cat,i,P.grp[i],P.obs[i],P.up[i],P.fl[i]);
  // only the kept bit follows the picks, the groups beside them, the area, projects, the lasso and deletions,
  // and the accuracy bit the location accuracy choice
  // OUT keeps the records out for any reason but the area, for the Identify box count; PJW marks
  // the records Identify opens when it cannot say the projects exactly (see map_projects.js)
  var kb=MF.keep(TF,MF.groupSet(S,TF),P.tax,P.grp,n,new Uint8Array(n)),id=P.id,am=AREA.mask(n),wide=PJ.wide(),
    fm=FK&&fmask(n);
  if(OUT.length!==n)OUT=new Uint8Array(n);PJW=wide?new Uint8Array(n):null;
  for(i=0;i<n;i++){var keep=kb[i]===1;
    if(gone>0&&GONE[id[i]]===1)keep=false;
    if(SUB&&!SUB.has(id[i]))keep=false;
    if(wide&&keep&&(am===null||am[i]))PJW[i]=wide(i)?1:0;if(keep&&(PJ.drop(i)||(fm&&!fm[i])))keep=false;
    OUT[i]=keep?0:1;cat[4*i+3]=cat[4*i+3]&~(ST_KEEP|ST_INEXACT)|(keep&&(am===null||am[i])?ST_KEEP:0)|MF.accOut(S.acc,P.fl[i]);}
  // a new pick, area or deletion swaps only the categories, so deck.gl uploads only those
  if(same){PD.attributes.getFilterCategory={value:cat,size:4};PD_CAT++;}
  else{var col=new Uint8Array(4*n),gc=META.groups.map(function(g,j){return MapFilter.color(g,j);});for(i=0;i<n;i++){var c=gc[P.grp[i]];
      col[4*i]=c[0];col[4*i+1]=c[1];col[4*i+2]=c[2];col[4*i+3]=110;}
    PD={length:n,days:days,attributes:{getPosition:{value:P.pos,size:2},
    getFilterValue:{value:days,size:2},getFilterCategory:{value:cat,size:4},
    getFillColor:{value:col,size:4,normalized:true}}};}
  PD_KEY=key;PD_GONE=gone;
}
function categories(thin){return MF.categories(S,inc(),thin);}
// The counts behind the histograms, header and share run on the CPU after the map has redrawn.
var CT=0;
function refilter(){
  pointData();layers();clearTimeout(CT);CT=setTimeout(recount,0);
}
function recount(){
  var n=P.n,day=S.up?P.up:P.obs,c=categories(),gm=0,mm=0,sm=0,nd=0,cat=PD.attributes.getFilterCategory.value,
    ch=S.up?2:1,g=CH.groupPass(S.groups,META.groups,false),m=S.months;
  c[0].forEach(function(j){gm|=1<<j;});c[ch].forEach(function(j){mm|=1<<j;});c[3].forEach(function(j){sm|=1<<j;});
  RC={gm:gm,mm:mm,sm:sm,ch:ch};KV++;
  if(KEEP.length!==n)KEEP=new Uint8Array(n);
  if(!PER)PER=new Float64Array(META.days);else PER.fill(0);
  for(var i=0;i<n;i++){
    var k=(gm>>cat[4*i]&1)&(mm>>cat[4*i+ch]&1)&(sm>>cat[4*i+3]&1);KEEP[i]=k;
    if(k){var d=day[i];if(d!==NO)PER[d]++;else nd++;}
  }
  NODAY=nd;ALT=0;
  if(PJW)for(i=0;i<n;i++)if(PJW[i]&&(gm>>cat[4*i]&1)&(mm>>cat[4*i+ch]&1)&(sm>>(cat[4*i+3]|ST_KEEP)&1)&&
    (day[i]===NO?full():day[i]>=S.lo&&day[i]<=S.hi))ALT++;
  VC=null;CUM=new Float64Array(META.days+1);
  for(var d=0;d<META.days;d++)CUM[d+1]=CUM[d]+PER[d];
  // One picked status filter reads its own totals; two together, a left-out one, an area or a lasso have none
  var on=Object.keys(S.only).concat(S.acc?'acc_'+S.acc:[]),
    tt=!TOT||S.picks.length||AREA.on()||PJ.active()||FK||on.length>1||S.only[on[0]]==='not'?null:
      on.length?TOT.only&&TOT.only[on[0]]:TOT;
  TC=null;
  if(tt){var rows=tt[S.up?'up':'obs'],nm=rows[0].length;TC=new Float64Array(nm+1);
    for(var k=0;k<nm;k++){var v=0;if(!m||m>>(M0+k)%12&1)for(var j=0;j<rows.length;j++)if(g[j])v+=rows[j][k];
      TC[k+1]=TC[k]+v;}}
  if(SEL>=0&&!KEEP[SEL])closeCard();
  // the photo space beside the map keeps the records the projects keep; it has no project file of its own
  if(parent!==window&&PJP!==PJ.key()+':'+n){PJP=PJ.key()+':'+n;parent.postMessage({type:'wtid-projects',ids:PJ.ids(P)},location.origin);}
  render();
  if(FIT){FIT=false;fitTo(function(i){var d=day[i];return KEEP[i]&&(d===NO?full():d>=S.lo&&d<=S.hi);});}
}
function full(){return S.lo===0&&S.hi===LAST;}
// records without a date show only over all dates, as the GPU filter does
function nShown(){return CUM[S.hi+1]-CUM[S.lo]+(full()?NODAY:0);}
function fitTo(keep){
  var w=Infinity,s=Infinity,e=-Infinity,n=-Infinity,x,y;
  if(map)for(var i=0;i<P.n;i++)if(keep(i)){x=P.pos[2*i];y=P.pos[2*i+1];
    if(x<w)w=x;if(x>e)e=x;if(y<s)s=y;if(y>n)n=y;}
  // the new count can rewrap the bar above the map; MapLibre sees the new size only a frame later, so a fit
  // to the old one sits off centre
  if(w<=e){map.resize();map.fitBounds([[w,s],[e,n]],{padding:40,maxZoom:14});}}
var VC=null;  // kept records dated in S.lo..S.hi like CUM and inside the viewport; null for the world
function inView(){
  var n=P.n,b=map.getBounds(),w=b.getWest(),e=b.getEast(),s=b.getSouth(),t=b.getNorth(),key=[w,e,s,t,S.lo,S.hi,S.up,n].join();
  if(!n||KEEP.length!==n||e-w>=360)return null;
  if(VC&&VC.k===key)return VC.c;
  var q=function(v){return Math.round(v*MapArea.Q)/MapArea.Q;};  // the precision of the view sent to the other panes, so their counts agree
  w=q(w);e=q(e);s=q(s);t=q(t);
  w=(w+540)%360-180;e=(e+540)%360-180;  // wrap into [-180,180); w>e then means the view crosses the antimeridian
  var day=S.up?P.up:P.obs,pos=P.pos,all=full(),c=0,i,x,y,d;
  for(i=0;i<n;i++){
    if(!KEEP[i])continue;y=pos[2*i+1];if(y<s||y>t)continue;x=pos[2*i];
    if(w<=e?x<w||x>e:x<w&&x>e)continue;
    d=day[i];if(d===NO?all:d>=S.lo&&d<=S.hi)c++;}
  VC={k:key,c:c};return c;}
function render(){
  var shown=nShown();
  var iv=P.n&&!AREA.invalid()?inView():null;
  $('count').textContent=AREA.invalid()?'Area unresolved · '+nf.format(shown)+' records available to browse':
    P.n?iv!==null&&iv<shown?nf.format(iv)+' in view of '+nf.format(shown)+' records':
      nf.format(shown)+' of '+nf.format(META.n)+' records':'Loading';
  var all=P.n&&!$('more').textContent?FB.total(S.lo,S.hi):null;
  $('share').textContent=all&&!AREA.invalid()?nf.format(Math.min(shown,all))+' of '+nf.format(all)+
    ' BC records with photos '+(full()&&!S.months&&!CH.any(S.groups)&&!CH.any(S.only)&&!S.acc?
    '':'matching these filters ')+'still need an ID ('+
    FB.pct(shown,all)+'). All-record counts from '+TOT.on+'.':'';
  $('hint').textContent=TC?HINT_TOT:HINT;
  PJ.note(P.n?shown:null,ALT);FB.update();layers();link();writeHash();counts();
}
// The tree beside the map counts what the map shows: how many shown records carry each taxon, sent once the filters
// have settled for 150 ms and only when they changed (KV counts the recounts of KEEP, which holds the months too).
function counts(){
  if(parent===window||!TAXA)return;clearTimeout(CNT);CNT=setTimeout(function(){
    var k=[KV,S.lo,S.hi,S.up].join();if(k===CNP)return;CNP=k;
    var own=new Float64Array(TAXA.length),day=S.up?P.up:P.obs,all=full(),t=0,d;
    for(var i=0;i<P.n;i++)if(KEEP[i]&&((d=day[i])===NO?all:d>=S.lo&&d<=S.hi)){t++;if(P.tax[i]<own.length)own[P.tax[i]]++;}
    parent.postMessage({type:'wtid-counts',own:own,total:t},location.origin);},150);}
// Whether record i matches the filters with the area left out, as recount() reads them
function match(i){if(!RC||i>=OUT.length)return 0;var c=PD.attributes.getFilterCategory.value,s=c[4*i+3]&~ST_KEEP|(OUT[i]?0:ST_KEEP);
  return (RC.gm>>c[4*i]&1)&(RC.mm>>c[4*i+RC.ch]&1)&(RC.sm>>s&1);}
function link(){
  var b=map.getBounds(),m=[],u=null;for(var i=0;i<12;i++)if(S.months>>i&1)m.push(i+1);
  // with a taxon included, the picked groups go in as their taxa, which iNaturalist adds to the picks;
  // left-out groups go in as taxa to leave out (see CH.groupLink)
  var gl=CH.groupLink(S.groups,META.groups,META.group_ids||{},TF.ids.length>0),
    taxa=gl.inc.length?null:TF.ids.concat(gl.taxa);
  var st={groups:gl.groups,
    all:META.groups.length,up:S.up,d1:S.lo>0?iso(S.lo):'',d2:S.hi<LAST?iso(S.hi):'',months:m,taxa:taxa,
    not:TF.not.concat(gl.not),only:S.only,acc:S.acc};
  // with an area on, the link may list the records by id instead, and then u stays null
  var a=$('identify'),href=AREA.link({w:b.getWest(),s:b.getSouth(),e:b.getEast(),n:b.getNorth()},
    function(v,p,side){var r=TX.identifyUrl(st,v,META,Object.assign({},PJ.params(),p));if(!side)u=r;return r.url;},match);
  if(AREA.invalid()){a.removeAttribute('href');a.setAttribute('aria-disabled','true');
    a.title='Wait for the selected areas to load, or explicitly clear or replace unresolved areas.';
    $('idprev').disabled=$('idnext').disabled=true;
    $('idnote').hidden=false;$('idnote').textContent='Identify is unavailable until every selected area is restored. Wait for loading, or explicitly clear or replace unresolved areas.';
    return;}
  a.removeAttribute('aria-disabled');a.href=href;
  a.title='Opens these records in the iNaturalist Identify page.';
  // say when Identify cannot show the same records, and what it opens instead
  var why=[],lost=u?u.lost:[];function gn(gs){return gs.map(gname).join(' and ');}
  if(u&&gl.inc.length)why.push('Identify cannot add the '+gn(gl.inc)+' group to picked taxa, so it opens every taxon');
  if(u&&gl.out.length)why.push('Identify cannot leave out the '+gn(gl.out)+' group beside picked taxa, so it keeps it');
  if(lost.indexOf('taxa')>=0)why.push('too many taxa for one link, so it opens every taxon');
  if(lost.indexOf('not')>=0)why.push('too many taxa left out for one link, so it keeps them');
  if(u&&PJ.inexact())why.push(PJ.inexact());
  var nt=$('idnote'),pf=u?PJ.uncounted():'';nt.hidden=!why.length&&!pf;nt.textContent=(why.length?'Identify shows '+
    'more records than the map: '+why.join('; ')+'. ':'')+pf;
}
// The filter extension is kept between calls, as the point data is in pointData(), so deck.gl
// uploads nothing when only the filter settings change. deck.gl would also run every category
// through a lookup in JS and upload the result as 32-bit values; ours are already small numbers,
// so the lookup is the identity and the bytes go up as they are.
class Filter extends deck.DataFilterExtension{
  static componentName='Filter';
  initializeState(context,extension){super.initializeState(context,extension);
    var a=this.getAttributeManager().attributes.filterCategoryValues;if(a)a.settings.transform=null;}
  _getCategoryKey(category){return category;}
}
var EXT=null;
function layers(){
  if(!P.n||!PD)return;
  EXT=EXT||new Filter({filterSize:2,categorySize:4});
  var r=[full()?-1:S.lo,S.hi],any=[-1,LAST];
  // fewer than 5,000 records grow up to 3.5x with an outline, so a handful stay findable at BC-wide zoom
  var sh=PER?nShown():Infinity,k=!(sh<5000)?1:sh<=50?3.5:1+2.5*Math.log(5000/sh)/Math.log(100);
  var L=[new deck.ScatterplotLayer({id:'pts',data:PD,
    radiusUnits:'pixels',getRadius:1.5*k,radiusMinPixels:k,
    radiusMaxPixels:6*k,stroked:k>1,lineWidthUnits:'pixels',getLineWidth:1,
    getLineColor:dark?[255,255,255]:[29,29,27],pickable:true,
    extensions:[EXT],updateTriggers:{getFilterCategory:PD_CAT},filterRange:[S.up?any:r,S.up?r:any],filterCategories:categories(THIN)})];
  var at=function(d){return [P.pos[2*d.i],P.pos[2*d.i+1]];};
  if(NBR.length)L.push(new deck.ScatterplotLayer({id:'nbr',data:NBR,getPosition:at,radiusUnits:'pixels',getRadius:11,
    getFillColor:[27,94,76],stroked:true,lineWidthUnits:'pixels',getLineWidth:2,getLineColor:[255,255,255]}),
    new deck.TextLayer({id:'nbr-rank',data:NBR,getPosition:at,getText:function(d){return String(d.r);},getSize:12,
      sizeUnits:'pixels',getColor:[255,255,255],fontWeight:'bold',getTextAnchor:'middle',getAlignmentBaseline:'center'}));
  if(SEL>=0)L.push(new deck.ScatterplotLayer({id:'halo',data:[SEL],
    getPosition:function(i){return [P.pos[2*i],P.pos[2*i+1]];},radiusUnits:'pixels',getRadius:13,
    filled:false,stroked:true,lineWidthUnits:'pixels',getLineWidth:3,getLineColor:[233,168,50]}));
  if(SEL>=0)L.push(new deck.ScatterplotLayer({id:'sel',data:[SEL],
    getPosition:function(i){return [P.pos[2*i],P.pos[2*i+1]];},radiusUnits:'pixels',getRadius:8,
    filled:false,stroked:true,lineWidthUnits:'pixels',getLineWidth:2.5,
    getLineColor:dark?[255,255,255]:[29,29,27]}));
  overlay.setProps({layers:L,onHover:tip,onClick:pick});
}

// The filter bar (filter_bar.js) draws the histograms and chips; the map hands it the records and the recount.
var FB=FilterBar({S:S,META:META,mf:MF,nf:nf,pj:PJ,sel:sel,P:function(){return P;},taxa:function(){return TAXA;},
  area:function(){return AREA;},cum:function(){return CUM;},tc:function(){return TC;},search:search,
  refilter:refilter,render:render,reset:function(){
    if(parent!==window)parent.postMessage({type:'wtid-reset'},location.origin);},  // the photo space beside it zooms out
  extra:function(){return SUB?[{label:'Photo search: "'+SUBL+'" ('+SUB.size+')',
    remove:function(){parent.postMessage({type:'wtid-subset',ids:null},location.origin);}}]:[];}});
function search(){TF=TX.filter(TAXA,S.picks);}
function gname(g){return META.names[g]||g;}
$('toggle').onclick=function(){var o=$('side').classList.toggle('open');
  this.setAttribute('aria-expanded',String(o));};

// Hover and click.
function names(i){var t=TAXA&&P.tax[i]!==NOTAX?TAXA[P.tax[i]]:null,g=META.groups[P.grp[i]];
  return {common:t&&t[1]||'',latin:t&&t[0]||META.names[g]||g,group:META.names[g]||g,
    rank:t&&t[3]!==255?META.ranks[t[3]]:''};}
function badges(i){var f=P.fl[i],out=[];
  if(f&FLAG.introduced)out.push(['Introduced','']);if(f&FLAG.threatened)out.push(['Threatened','']);
  if(f&FLAG.obscured)out.push(['Location hidden','warn']);
  else if(MF.accClass(f)===1)out.push(['Location over 1 km uncertain','warn']);
  return out.map(function(b){return '<span class="badge '+b[1]+'">'+b[0]+'</span>';}).join('');}
function idText(i){var n=P.ids[i]&15,a=P.ids[i]>>4;
  return n?(n>=15?'15+':n)+(n===1?' ID':' IDs')+(a?', '+(a>=15?'15+':a)+' agreeing':''):'No IDs yet';}
function when(v,early){return v===NO?'unknown':early?'before 1900':iso(v);}
// The hover tip sits below right of the pointer and flips to the other side of it near the window's
// right or bottom edge. It is fixed to the window above the record card, so neither the map's
// edges, the time bar nor an open card hide it.
var ptip=document.createElement('div');ptip.className='ptip';ptip.hidden=true;
function tip(o){
  if(!P.n||o.index<0||!o.layer||o.layer.id!=='pts'||AREA.busy()){ptip.hidden=true;return;}
  var i=o.index,t=names(i);
  ptip.innerHTML='<b>'+esc(t.common||t.latin)+'</b>'+(t.common?'<br><i>'+esc(t.latin)+'</i>':'')+
    '<br>'+esc(t.group)+' · observed '+when(P.obs[i],P.fl[i]&FLAG.earlyObs)+'<br>'+idText(i)+'<div class="badges">'+
    badges(i)+'</div>';
  ptip.hidden=false;
  var r=map.getContainer().getBoundingClientRect(),px=r.left+o.x,py=r.top+o.y,
    w=ptip.offsetWidth,h=ptip.offsetHeight,g=12,
    x=px+g+w>innerWidth-4?px-g-w:px+g,y=py+g+h>innerHeight-4?py-g-h:py+g;
  ptip.style.left=Math.max(4,x)+'px';ptip.style.top=Math.max(4,y)+'px';
}
var ctl=null,card=$('card');
function pick(o){if(!P.n||o.index<0||o.layer.id!=='pts'||AREA.busy())return;openCard(o.index);}
// A record deleted from iNaturalist leaves the map once its card closes, so the card can say why.
// The card opens beside its point, on the side with room, and follows the point as the map moves.
// It is fixed to the window, so the time bar and the map's edges never clip it. On a phone it is a
// bottom sheet instead.
var NARROW=matchMedia('(max-width:760px)');
function place(){
  if(SEL<0||card.hidden)return;var s=card.style;
  if(NARROW.matches){s.left=s.top=s.right='';return;}
  var r=map.getContainer().getBoundingClientRect(),p=map.project([P.pos[2*SEL],P.pos[2*SEL+1]]),
    x=r.left+p.x,y=r.top+p.y,w=card.offsetWidth,h=card.offsetHeight,g=14,m=8,
    left=x+g+w<=innerWidth-m?x+g:x-g-w>=m?x-g-w:innerWidth-m-w;
  s.right='auto';s.left=Math.max(m,left)+'px';
  s.top=Math.max(m,Math.min(y-h/2,innerHeight-m-h))+'px';
}
function closeCard(){SEL=-1;NBR=[];card.hidden=true;if(ctl)ctl.abort();
  if(GONE_NEW){GONE_NEW=false;refilter();}else{layers();writeHash();}
  tell(null);}
// The split view mirrors the picked record in the photo space by id. A record picked there is ringed
// here without a card, and the map pans to it only when it is off screen.
function tell(id){if(parent!==window)parent.postMessage({type:'wtid-record',id:id},location.origin);}
function mark(i){
  SEL=i;NBR=[];card.hidden=true;if(ctl)ctl.abort();layers();
  var c=[P.pos[2*i],P.pos[2*i+1]];if(!map.getBounds().contains(c))map.easeTo({center:c});
}
// The photo space sends the closest matches of the picked record; those that are on the map get a ring.
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-matches'||SEL<0||
    e.data.id!==P.id[SEL])return;
  var rank={};e.data.hits.forEach(function(h,k){rank[h.id]=k+1;});
  NBR=[];for(var i=0;i<P.n;i++)if(rank[P.id[i]])NBR.push({i:i,r:rank[P.id[i]]});
  layers();
});
// Hovering a tile in the photo space brings its match into view; nothing else changes.
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-focus')return;
  for(var i=0;i<P.n;i++)if(P.id[i]===e.data.id){var c=[P.pos[2*i],P.pos[2*i+1]];
    if(!map.getBounds().contains(c))map.easeTo({center:c});return;}
});
// The photo space's lasso keeps the same records here; nothing marks it but the count.
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-keep')return;
  var ids=e.data.ids;if(ids!==null&&!(ids instanceof Uint32Array))return;
  FK=ids&&ids.sort();FKV++;if(P.n)refilter();
});
// The photo search of the split view: a set of ids (null clears it); before the taxa load, their refilter applies it.
addEventListener('message',function(e){
  var d=e.data;
  if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-subset')return;
  SUB=d.ids?new Set(d.ids):null;SUBL=d.label;SUBV++;if(TAXA)refilter();
  if(SUB)fitTo(function(i){return SUB.has(P.id[i]);});  // zoom to the hits that are loaded, as the area does
});
addEventListener('message',function(e){
  if(e.origin!==location.origin||e.source!==parent||!e.data||e.data.type!=='wtid-record')return;
  var id=e.data.id;
  if(id==null){S.rec=S.mark=null;if(SEL>=0){SEL=-1;NBR=[];card.hidden=true;if(ctl)ctl.abort();layers();}return;}
  for(var i=0;i<P.n;i++)if(P.id[i]===id){if(i!==SEL)mark(i);return;}
  S.rec=id;S.fly=false;S.mark=true;  // the shards that hold it have not loaded yet
});
function openCard(i){
  SEL=i;NBR=[];tell(P.id[i]);var t=names(i),id=P.id[i],lag=P.obs[i]!==NO&&P.up[i]!==NO&&!(P.fl[i]&(FLAG.earlyObs|FLAG.earlyUp))?P.up[i]-P.obs[i]:null;
  card.innerHTML='<button type="button" class="x" aria-label="Close">×</button>'+
    '<div class="ph" id="ph">Loading photo</div><div class="body">'+
    '<h2>'+esc(t.common||t.latin)+'</h2><p class="latin"><i>'+esc(t.latin)+'</i>'+
    (t.rank?' ('+esc(t.rank)+')':'')+'</p><div class="badges">'+badges(i)+'</div><dl>'+
    '<dt>Group</dt><dd>'+esc(t.group)+'</dd><dt>Observed</dt><dd>'+when(P.obs[i],P.fl[i]&FLAG.earlyObs)+'</dd>'+
    '<dt>Uploaded</dt><dd>'+when(P.up[i],P.fl[i]&FLAG.earlyUp)+(lag>0?' ('+nf.format(lag)+(lag===1?' day':' days')+
    ' later)':'')+'</dd><dt>IDs</dt><dd>'+idText(i)+'</dd><dt>Place</dt><dd id="place">…</dd></dl>'+
    '<div id="now"></div><a class="btn" target="_blank" rel="noopener" '+
    'href="https://www.inaturalist.org/observations/'+id+'">Help identify on iNaturalist</a>'+
    '<p class="attr" id="attr"></p></div>';
  card.hidden=false;card.querySelector('.x').onclick=closeCard;card.querySelector('.x').focus();
  place();
  layers();writeHash();
  if(ctl)ctl.abort();ctl=new AbortController();
  fetch('https://api.inaturalist.org/v1/observations/'+id,{signal:ctl.signal})
    .then(function(r){if(r.status===404)return {results:[]};
      if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
    .then(function(j){
      var o=j.results&&j.results[0];
      if(!o){$('ph').textContent='This record is no longer on iNaturalist, so it leaves the map';
        $('place').textContent='';GONE[id]=1;GONE_NEW=true;return;}
      var ph=o.photos&&o.photos[0];
      if(ph){var img=new Image();img.alt='Photo of '+(t.common||t.latin);
        img.onload=place;img.src=String(ph.url).replace('/square.','/medium.');$('ph').textContent='';
        $('ph').appendChild(img);$('attr').textContent=ph.attribution||'';}
      else $('ph').textContent='No photo on iNaturalist now';
      $('place').textContent=o.place_guess||'Not given';
      var now=[],ot=o.taxon||{};
      if(o.quality_grade&&o.quality_grade!=='needs_id')now.push('Now '+
        (o.quality_grade==='research'?'Research Grade':'casual')+', so it no longer needs an ID.');
      if(ot.name&&ot.name!==t.latin)now.push('Now identified as '+
        (ot.preferred_common_name?ot.preferred_common_name+' (':'')+ot.name+
        (ot.preferred_common_name?')':'')+'.');
      if(now.length){var p=document.createElement('p');p.className='now';p.textContent=
        'Since this map was built: '+now.join(' ');$('now').appendChild(p);}
      place();
    }).catch(function(e){if(e.name==='AbortError')return;
      $('ph').textContent='Could not load the photo';$('place').textContent='Unknown';});
}
addEventListener('keydown',function(e){if(e.key==='Escape'&&!card.hidden)closeCard();});

// Map, then data: names and the recent shard first, older shards after.
var b=META.bbox,opts={container:'map',style:dark?BASEMAPS.dark:BASEMAPS.light,
  attributionControl:{compact:true}};
if(S.at){opts.center=[S.at[2],S.at[1]];opts.zoom=S.at[0];}
else{opts.bounds=[[b[0],b[1]],[b[2],b[3]]];opts.fitBoundsOptions={padding:20};}
var map=new maplibregl.Map(opts);document.body.appendChild(ptip);
map.addControl(new maplibregl.NavigationControl({showCompass:false}));
var overlay=new deck.MapboxOverlay({interleaved:false,pickingRadius:8,layers:[]});map.addControl(overlay);
var AREA=MapArea({map:map,S:S,LAST:LAST,hash:S.area,park:S.park,bcpark:S.bcpark,fit:!S.at,
  place:META.place_id,parks:META.parks,get:get,P:function(){return P;},keep:function(){return KEEP;},
  change:refilter,sel:function(){return sel().join('&');},
  step:IdStep({a:$('identify'),prev:$('idprev'),next:$('idnext'),build:iso(LAST)})});
// Guard activation before IdStep's handlers, including a stale batch or keyboard activation.
function stopInvalidIdentify(e){if(AREA.invalid()){e.preventDefault();e.stopImmediatePropagation();}}
['identify','idprev','idnext'].forEach(function(id){var el=$(id);
  el.addEventListener('click',stopInvalidIdentify,true);el.addEventListener('auxclick',stopInvalidIdentify,true);
  el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' ')stopInvalidIdentify(e);},true);});
// Zoomed out, blending millions of overlapping dots takes about 250 ms a frame, so while the map
// moves it draws one record in ten, spread across BC by the id order, and all of them once it stops.
var THIN=false,THIN_BELOW=8;
map.on('move',function(){if(!THIN&&map.getZoom()<THIN_BELOW){THIN=true;layers();}});
map.on('move',place);
// The viewport masks the photo space beside the map; a view of the whole world masks nothing.
function view(){if(parent===window)return;var b=map.getBounds(),w=b.getWest(),e=b.getEast(),
  c=function(v,m){return Math.max(-m,Math.min(m,v));},s=c(b.getSouth(),85),n=c(b.getNorth(),85);
  w=c(w,180);e=c(e,180);
  parent.postMessage({type:'wtid-view',area:b.getEast()-b.getWest()>=360?'':MapArea.encode([[w,s,e,s,e,n,w,n]])},location.origin);}
map.once('load',view);
map.on('moveend',function(){if(THIN){THIN=false;layers();}link();writeHash();view();if(P.n&&CUM)render();});
map.getContainer().addEventListener('pointerleave',function(){ptip.hidden=true;});
addEventListener('resize',function(){FB.draw();place();});
var HINT=$('hint').textContent,HINT_TOT='Top: records still needing an ID per year, on a log scale; the line is the '+
  'share of all BC records with photos that still need one. Click or drag across years to zoom in. Bottom: '+
  'the period in view, faint bars all records, solid bars those still needing an ID. Drag to pick a period, '+
  'click a bar to zoom into it, double-click for all dates.';
render();
PJ.load(get);
var names0=get(META.taxa).then(function(buf){TAXA=JSON.parse(new TextDecoder().decode(buf));
  FB.oldQuery();search();FB.showClades();refilter();});
// One shard downloads at a time, so on a slow link the recent shard gets all the bandwidth.
var chain=Promise.resolve(),prev=Promise.resolve();
META.shards.forEach(function(s,k){
  var got=prev.then(function(){return get(s.file);});prev=got;
  chain=chain.then(function(){return got;}).then(function(buf){
    addShard(buf,s.n);
    $('more').textContent=k<META.shards.length-1?'Loading older records…':'';
    if(k===0)return names0;
  }).then(function(){
    refilter();
    if(S.rec&&SEL<0){for(var i=0;i<P.n;i++)if(P.id[i]===S.rec){S.rec=null;if(S.mark){S.mark=false;mark(i);break;}openCard(i);
      if(S.fly){S.fly=false;map.flyTo({center:[P.pos[2*i],P.pos[2*i+1]],zoom:12});}break;}}
    if(k===META.shards.length-1&&S.rec){S.rec=null;writeHash();}
  });
});
chain.catch(function(e){$('count').textContent='Could not load the records ('+e.message+')';});
})();
