(function(){
'use strict';
function $(id){return document.getElementById(id);}
var css=getComputedStyle(document.documentElement);
function tok(n){return css.getPropertyValue(n).trim();}
var dark=matchMedia('(prefers-color-scheme: dark)').matches,DOT=tok('--dot').split(',').map(Number);
var DAY=864e5,D0=Date.parse(META.day0+'T00:00:00Z'),NO=65535,NOTAX=65535,LAST=META.days-1;
var MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
var MONTH=['January','February','March','April','May','June','July','August','September',
  'October','November','December'];
var FLAG={introduced:1,threatened:2,obscured:4,imprecise:8},nf=new Intl.NumberFormat('en-CA');
function iso(d){return new Date(D0+d*DAY).toISOString().slice(0,10);}
function dayOf(s){var t=Date.parse(s+'T00:00:00Z');return isNaN(t)?null:Math.round((t-D0)/DAY);}
function clamp(d){return Math.max(0,Math.min(LAST,d));}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
  return '&#'+c.charCodeAt(0)+';';});}

// Calendar lookups by day: month of year, month bin since day0, and each bin's first day.
var Y0=new Date(D0).getUTCFullYear(),MOY=new Uint8Array(META.days),MB=new Uint16Array(META.days);
for(var d=0;d<META.days;d++){var t=new Date(D0+d*DAY);MOY[d]=t.getUTCMonth();
  MB[d]=(t.getUTCFullYear()-Y0)*12+t.getUTCMonth();}
var NB=MB[LAST]+1,START=new Int32Array(NB+1),H0=MB[META.hist0],EARLY=META.hist0>0?1:0;
for(d=META.days-1;d>=0;d--)START[MB[d]]=d;
START[NB]=META.days;

// What the viewer picked. Written to the URL hash so a view can be shared or bookmarked.
var S={up:false,lo:0,hi:LAST,months:0,groups:META.groups.map(function(){return true;}),
  only:{},q:'',rec:null,at:null};
(function readHash(){
  var h=new URLSearchParams(location.hash.slice(1));
  S.up=h.get('by')==='uploaded';
  var f=dayOf(h.get('from')||''),t=dayOf(h.get('to')||'');
  if(f!=null)S.lo=clamp(f);if(t!=null)S.hi=clamp(t);
  (h.get('months')||'').split(',').forEach(function(m){if(+m>=1&&+m<=12)S.months|=1<<(m-1);});
  if(h.get('groups')!=null){var gs=h.get('groups').split(',');
    S.groups=META.groups.map(function(g){return gs.indexOf(g)>=0;});}
  (h.get('only')||'').split(',').forEach(function(k){if(k)S.only[k]=true;});
  S.q=h.get('q')||'';S.rec=+h.get('record')||null;
  var at=(h.get('at')||'').split('/').map(Number);if(at.length===3&&at.every(isFinite))S.at=at;
})();
var hashTimer=0;
function writeHash(){clearTimeout(hashTimer);hashTimer=setTimeout(function(){
  var h=[];if(S.up)h.push('by=uploaded');
  if(S.lo>0)h.push('from='+iso(S.lo));if(S.hi<LAST)h.push('to='+iso(S.hi));
  if(S.months){var ms=[];for(var m=0;m<12;m++)if(S.months>>m&1)ms.push(m+1);h.push('months='+ms);}
  if(!S.groups.every(Boolean))h.push('groups='+META.groups.filter(function(g,i){
    return S.groups[i];}).map(encodeURIComponent).join(','));
  var only=Object.keys(S.only).filter(function(k){return S.only[k];});
  if(only.length)h.push('only='+only.join(','));
  if(S.q)h.push('q='+encodeURIComponent(S.q));
  if(P.n&&SEL>=0)h.push('record='+P.id[SEL]);
  var c=map.getCenter();h.push('at='+map.getZoom().toFixed(1)+'/'+c.lat.toFixed(3)+'/'+
    c.lng.toFixed(3));
  history.replaceState(null,'','#'+h.join('&'));},250);}

// Records, concatenated as shards arrive.
var P={n:0,id:new Uint32Array(0),pos:new Float32Array(0),obs:new Uint16Array(0),
  up:new Uint16Array(0),tax:new Uint16Array(0),grp:new Uint8Array(0),rank:new Uint8Array(0),
  ids:new Uint8Array(0),fl:new Uint8Array(0)};
var TAXA=null,TAXOK=null,KEEP=new Uint8Array(0),FV=new Float32Array(0),SEL=-1,BINS=[];
function cat(a,b){var c=new a.constructor(a.length+b.length);c.set(a);c.set(b,a.length);return c;}
function unzip(buf){
  var u=new Uint8Array(buf,0,Math.min(2,buf.byteLength));
  if(u[0]!==0x1f||u[1]!==0x8b)return Promise.resolve(buf);
  return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip')))
    .arrayBuffer();
}
function get(url){return fetch(url).then(function(r){
  if(!r.ok)throw new Error('HTTP '+r.status);return r.arrayBuffer();}).then(unzip);}
function addShard(buf,n){
  if(buf.byteLength!==18*n)throw new Error('unexpected size');
  var b=META.bbox,sx=(b[2]-b[0])/65535,sy=(b[3]-b[1])/65535,o=0;
  function col(T,sz){var a=new T(buf.slice(o,o+sz*n));o+=sz*n;return a;}
  var id=col(Uint32Array,4),qx=col(Uint16Array,2),qy=col(Uint16Array,2),obs=col(Uint16Array,2),
    up=col(Uint16Array,2),tax=col(Uint16Array,2),grp=col(Uint8Array,1),rank=col(Uint8Array,1),
    ids=col(Uint8Array,1),fl=col(Uint8Array,1),pos=new Float32Array(2*n);
  for(var i=0;i<n;i++){pos[2*i]=b[0]+qx[i]*sx;pos[2*i+1]=b[1]+qy[i]*sy;}
  P={n:P.n+n,id:cat(P.id,id),pos:cat(P.pos,pos),obs:cat(P.obs,obs),up:cat(P.up,up),
    tax:cat(P.tax,tax),grp:cat(P.grp,grp),rank:cat(P.rank,rank),ids:cat(P.ids,ids),
    fl:cat(P.fl,fl)};
}

// Filters other than the date range run here; the date range runs on the GPU.
function refilter(){
  var n=P.n,day=S.up?P.up:P.obs,req=0,hide=0,m=S.months,g=S.groups;
  if(S.only.introduced)req|=FLAG.introduced;if(S.only.threatened)req|=FLAG.threatened;
  if(S.only.exact)hide=FLAG.obscured|FLAG.imprecise;
  KEEP=new Uint8Array(n);FV=new Float32Array(2*n);BINS=new Float64Array(NB);
  for(var i=0;i<n;i++){
    var d=day[i];FV[2*i]=d===NO?-1:d;
    if(!g[P.grp[i]]||(req&&(P.fl[i]&req)!==req)||(P.fl[i]&hide))continue;
    if(TAXOK&&(P.tax[i]===NOTAX||!TAXOK[P.tax[i]]))continue;
    if(m&&(d===NO||!(m>>MOY[d]&1)))continue;
    KEEP[i]=1;FV[2*i+1]=1;if(d!==NO)BINS[MB[d]]++;
  }
  if(SEL>=0&&!KEEP[SEL])closeCard();
  render();
}
function render(){
  var day=S.up?P.up:P.obs,shown=0,kept=0;
  for(var i=0;i<P.n;i++)if(KEEP[i]){kept++;var d=day[i];if(d!==NO&&d>=S.lo&&d<=S.hi)shown++;}
  $('count').textContent=P.n?nf.format(shown)+' of '+nf.format(META.n)+' records':'Loading';
  $('from').value=iso(S.lo);$('to').value=iso(S.hi);
  $('byObs').setAttribute('aria-pressed',String(!S.up));
  $('byUp').setAttribute('aria-pressed',String(S.up));
  PRESETS.forEach(function(p){var r=p.range();
    p.el.setAttribute('aria-pressed',String(r[0]===S.lo&&r[1]===S.hi));});
  draw();layers();writeHash();
}
function layers(){
  if(!P.n)return;
  var L=[new deck.ScatterplotLayer({id:'pts',
    data:{length:P.n,attributes:{getPosition:{value:P.pos,size:2},getFilterValue:{value:FV,size:2}}},
    getFillColor:[DOT[0],DOT[1],DOT[2],110],radiusUnits:'pixels',getRadius:1.5,radiusMinPixels:1,
    radiusMaxPixels:6,stroked:false,pickable:true,
    extensions:[new deck.DataFilterExtension({filterSize:2})],filterRange:[[S.lo,S.hi],[1,1]]})];
  if(SEL>=0)L.push(new deck.ScatterplotLayer({id:'sel',data:[SEL],
    getPosition:function(i){return [P.pos[2*i],P.pos[2*i+1]];},radiusUnits:'pixels',getRadius:8,
    filled:false,stroked:true,lineWidthUnits:'pixels',getLineWidth:2.5,
    getLineColor:dark?[255,255,255]:[29,29,27]}));
  overlay.setProps({layers:L,getTooltip:tip,onClick:pick});
}

// The month histogram: one bar per month from META.hist0, plus one bar for everything earlier.
var hist=$('hist'),htip=$('htip'),SLOTS=EARLY+NB-H0;
function slotW(){return hist.clientWidth/SLOTS;}
function slotAt(x){return Math.max(0,Math.min(SLOTS-1,Math.floor(x/slotW())));}
function slotRange(s){if(EARLY&&s===0)return [0,START[H0]-1];var b=H0+s-EARLY;
  return [START[b],Math.min(LAST,START[b+1]-1)];}
function slotCount(s){if(EARLY&&s===0){var c=0;for(var b=0;b<H0;b++)c+=BINS[b]||0;return c;}
  return BINS[H0+s-EARLY]||0;}
function slotOn(s){var r=slotRange(s);if(r[1]<S.lo||r[0]>S.hi)return false;
  return !S.months||(EARLY&&s===0)||(S.months>>MOY[r[0]]&1)===1;}
function draw(){
  var w=hist.clientWidth,h=64,ax=14,r=devicePixelRatio||1,c=hist.getContext('2d');
  hist.width=w*r;hist.height=h*r;c.setTransform(r,0,0,r,0,0);c.clearRect(0,0,w,h);
  var sw=w/SLOTS,m=1,s;
  for(s=0;s<SLOTS;s++)m=Math.max(m,slotCount(s));
  c.fillStyle=tok('--bar');
  for(s=0;s<SLOTS;s++){
    var v=slotCount(s),y=v?Math.max(1,v/m*(h-ax-2)):0;c.globalAlpha=slotOn(s)?1:.25;
    c.fillRect(s*sw,h-ax-y,Math.max(sw-(sw>3?1:0),1),y);
  }
  c.globalAlpha=1;c.fillStyle=tok('--muted');c.font='10px system-ui,sans-serif';c.textAlign='left';
  var step=[1,2,5,10,20].find(function(k){return k*12*sw>=34;})||25;
  if(EARLY)c.fillText('earlier',0,h-2);
  for(var b=H0;b<NB;b++)if(b%12===0){var yr=Y0+b/12;if(yr%step)continue;
    var x=(b-H0+EARLY)*sw;if(EARLY&&x<40)continue;c.fillRect(x,h-ax,1,3);c.fillText(yr,x+2,h-2);}
}
var drag=null;
hist.addEventListener('pointerdown',function(e){hist.setPointerCapture(e.pointerId);
  drag={x:e.offsetX,moved:false};});
hist.addEventListener('pointermove',function(e){
  var s=slotAt(e.offsetX),r=slotRange(s),lab=EARLY&&s===0?'Before '+iso(START[H0]).slice(0,4):
    MON[MOY[r[0]]]+' '+iso(r[0]).slice(0,4);
  htip.hidden=false;htip.style.left=Math.min(Math.max(e.offsetX,50),hist.clientWidth-50)+'px';
  htip.textContent=lab+': '+nf.format(slotCount(s));
  if(!drag)return;
  if(Math.abs(e.offsetX-drag.x)>3)drag.moved=true;
  if(drag.moved){var a=slotAt(Math.min(drag.x,e.offsetX)),z=slotAt(Math.max(drag.x,e.offsetX));
    S.lo=slotRange(a)[0];S.hi=slotRange(z)[1];render();}
});
hist.addEventListener('pointerup',function(e){
  if(drag&&!drag.moved){var r=slotRange(slotAt(e.offsetX));S.lo=r[0];S.hi=r[1];render();}
  drag=null;});
hist.addEventListener('pointerleave',function(){htip.hidden=true;});
hist.addEventListener('dblclick',function(){S.lo=0;S.hi=LAST;render();});

// Controls.
var PRESETS=[
  ['Last 30 days',function(){return [clamp(LAST-29),LAST];}],
  ['Last 12 months',function(){return [clamp(LAST-364),LAST];}],
  ['This year',function(){return [clamp(dayOf(iso(LAST).slice(0,4)+'-01-01')),LAST];}],
  ['All dates',function(){return [0,LAST];}]
].map(function(p){var b=document.createElement('button');b.type='button';b.textContent=p[0];
  b.onclick=function(){var r=p[1]();S.lo=r[0];S.hi=r[1];render();};$('presets').appendChild(b);
  return {el:b,range:p[1]};});
$('from').min=$('to').min=iso(0);$('from').max=$('to').max=iso(LAST);
$('from').onchange=function(){var d=dayOf(this.value);if(d!=null){S.lo=clamp(d);
  if(S.lo>S.hi)S.hi=S.lo;render();}};
$('to').onchange=function(){var d=dayOf(this.value);if(d!=null){S.hi=clamp(d);
  if(S.hi<S.lo)S.lo=S.hi;render();}};
$('byObs').onclick=function(){S.up=false;refilter();};
$('byUp').onclick=function(){S.up=true;refilter();};
function chip(box,label,pressed,onclick,title){var b=document.createElement('button');
  b.type='button';b.textContent=label;if(title)b.title=title;
  b.setAttribute('aria-pressed',String(pressed));
  b.onclick=function(){b.setAttribute('aria-pressed',String(onclick()));refilter();};
  $(box).appendChild(b);return b;}
var GB=META.groups.map(function(g,i){return chip('groups',META.names[g]||g,S.groups[i],
  function(){return S.groups[i]=!S.groups[i];});});
function setGroups(v){S.groups=S.groups.map(function(){return v;});
  GB.forEach(function(b){b.setAttribute('aria-pressed',String(v));});refilter();}
$('gall').onclick=function(){setGroups(true);};$('gnone').onclick=function(){setGroups(false);};
var MB_=MON.map(function(m,i){var b=chip('months',m,!!(S.months>>i&1),
  function(){S.months^=1<<i;return !!(S.months>>i&1);});b.setAttribute('aria-label',MONTH[i]);
  return b;});
function clearMonths(){S.months=0;MB_.forEach(function(b){b.setAttribute('aria-pressed','false');});}
$('mclear').onclick=function(){clearMonths();refilter();};
var ONLY=[['introduced','Introduced to BC','introduced','Species not native to BC'],
  ['threatened','Threatened','threatened','Species with a threatened status'],
  ['exact','Exact location','obscured','Hide records whose place is hidden or over 1 km uncertain']]
  .filter(function(o){return META.flags.indexOf(o[2])>=0;})
  .map(function(o){return chip('flags',o[1],!!S.only[o[0]],
    function(){return S.only[o[0]]=!S.only[o[0]];},o[3]);});
if(!ONLY.length)$('flagbox').hidden=true;
var qt=0;$('q').value=S.q;
$('q').addEventListener('input',function(){clearTimeout(qt);var v=this.value;
  qt=setTimeout(function(){S.q=v.trim();search();refilter();},200);});
function search(){
  var q=S.q.toLowerCase();
  if(q.length<2||!TAXA){TAXOK=null;$('qn').textContent=q.length===1?'Type one more letter':'';return;}
  var ok=new Uint8Array(TAXA.length),k=0;
  for(var i=0;i<TAXA.length;i++)if(TAXA[i][0].toLowerCase().indexOf(q)>=0||
    TAXA[i][1].toLowerCase().indexOf(q)>=0){ok[i]=1;k++;}
  TAXOK=ok;$('qn').textContent=k?nf.format(k)+(k===1?' taxon matches':' taxa match'):
    'No taxon matches';
}
$('reset').onclick=function(){S.lo=0;S.hi=LAST;S.up=false;clearMonths();setGroups(true);
  S.only={};ONLY.forEach(function(b){b.setAttribute('aria-pressed','false');});
  S.q='';$('q').value='';search();refilter();};
$('toggle').onclick=function(){var o=$('side').classList.toggle('open');
  this.setAttribute('aria-expanded',String(o));};

// Hover and click.
function names(i){var t=TAXA&&P.tax[i]!==NOTAX?TAXA[P.tax[i]]:null,g=META.groups[P.grp[i]];
  return {common:t&&t[1]||'',latin:t&&t[0]||META.names[g]||g,group:META.names[g]||g,
    rank:P.rank[i]===255?'':META.ranks[P.rank[i]]};}
function badges(i){var f=P.fl[i],out=[];
  if(f&FLAG.introduced)out.push(['Introduced','']);if(f&FLAG.threatened)out.push(['Threatened','']);
  if(f&FLAG.obscured)out.push(['Location hidden','warn']);
  else if(f&FLAG.imprecise)out.push(['Location over 1 km uncertain','warn']);
  return out.map(function(b){return '<span class="badge '+b[1]+'">'+b[0]+'</span>';}).join('');}
function idText(i){var n=P.ids[i]&15,a=P.ids[i]>>4;
  return n?(n>=15?'15+':n)+(n===1?' ID':' IDs')+(a?', '+(a>=15?'15+':a)+' agreeing':''):'No IDs yet';}
function when(v){return v===NO?'unknown':iso(v);}
function tip(o){
  if(!P.n||o.index<0||o.layer&&o.layer.id!=='pts')return null;
  var i=o.index,t=names(i);
  return {html:'<b>'+esc(t.common||t.latin)+'</b>'+(t.common?'<br><i>'+esc(t.latin)+'</i>':'')+
    '<br>'+esc(t.group)+' · observed '+when(P.obs[i])+'<br>'+idText(i)+'<div class="badges">'+
    badges(i)+'</div>',
    style:{background:'var(--panel)',color:'var(--ink)',border:'1px solid var(--line)',
      borderRadius:'8px',fontSize:'12px',padding:'6px 8px',maxWidth:'260px'}};
}
var ctl=null,card=$('card');
function pick(o){if(!P.n||o.index<0||o.layer.id!=='pts')return;openCard(o.index);}
function closeCard(){SEL=-1;card.hidden=true;if(ctl)ctl.abort();layers();writeHash();}
function openCard(i){
  SEL=i;var t=names(i),id=P.id[i],lag=P.obs[i]!==NO&&P.up[i]!==NO?P.up[i]-P.obs[i]:null;
  card.innerHTML='<button type="button" class="x" aria-label="Close">×</button>'+
    '<div class="ph" id="ph">Loading photo</div><div class="body">'+
    '<h2>'+esc(t.common||t.latin)+'</h2><p class="latin"><i>'+esc(t.latin)+'</i>'+
    (t.rank?' ('+esc(t.rank)+')':'')+'</p><div class="badges">'+badges(i)+'</div><dl>'+
    '<dt>Group</dt><dd>'+esc(t.group)+'</dd><dt>Observed</dt><dd>'+when(P.obs[i])+'</dd>'+
    '<dt>Uploaded</dt><dd>'+when(P.up[i])+(lag>0?' ('+nf.format(lag)+(lag===1?' day':' days')+
    ' later)':'')+'</dd><dt>IDs</dt><dd>'+idText(i)+'</dd><dt>Place</dt><dd id="place">…</dd></dl>'+
    '<div id="now"></div><a class="btn" target="_blank" rel="noopener" '+
    'href="https://www.inaturalist.org/observations/'+id+'">Help identify on iNaturalist</a>'+
    '<p class="attr" id="attr"></p></div>';
  card.hidden=false;card.querySelector('.x').onclick=closeCard;card.querySelector('.x').focus();
  layers();writeHash();
  if(ctl)ctl.abort();ctl=new AbortController();
  fetch('https://api.inaturalist.org/v1/observations/'+id,{signal:ctl.signal})
    .then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
    .then(function(j){
      var o=j.results&&j.results[0];
      if(!o){$('ph').textContent='This record is no longer on iNaturalist';$('place').textContent='';
        return;}
      var ph=o.photos&&o.photos[0];
      if(ph){var img=new Image();img.alt='Photo of '+(t.common||t.latin);
        img.src=String(ph.url).replace('/square.','/medium.');$('ph').textContent='';
        $('ph').appendChild(img);$('attr').textContent=ph.attribution||'';}
      $('place').textContent=o.place_guess||'Not given';
      var now=[],ot=o.taxon||{};
      if(o.quality_grade&&o.quality_grade!=='needs_id')now.push('Now '+
        (o.quality_grade==='research'?'Research Grade':'casual')+', so it no longer needs an ID.');
      if(ot.name&&ot.name!==t.latin)now.push('Now identified as '+
        (ot.preferred_common_name?ot.preferred_common_name+' (':'')+ot.name+
        (ot.preferred_common_name?')':'')+'.');
      if(now.length){var p=document.createElement('p');p.className='now';p.textContent=
        'Since this map was built: '+now.join(' ');$('now').appendChild(p);}
    }).catch(function(e){if(e.name==='AbortError')return;
      $('ph').textContent='Could not load the photo';$('place').textContent='Unknown';});
}
addEventListener('keydown',function(e){if(e.key==='Escape'&&!card.hidden)closeCard();});

// Map, then data: names and the recent shard first, older shards after.
var b=META.bbox,opts={container:'map',style:dark?BASEMAPS.dark:BASEMAPS.light,
  attributionControl:{compact:true}};
if(S.at){opts.center=[S.at[2],S.at[1]];opts.zoom=S.at[0];}
else{opts.bounds=[[b[0],b[1]],[b[2],b[3]]];opts.fitBoundsOptions={padding:20};}
var map=new maplibregl.Map(opts);
map.addControl(new maplibregl.NavigationControl({showCompass:false}));
var overlay=new deck.MapboxOverlay({interleaved:false,pickingRadius:8,layers:[]});map.addControl(overlay);
map.on('moveend',writeHash);
addEventListener('resize',draw);
render();
var names0=get(META.taxa).then(function(buf){TAXA=JSON.parse(new TextDecoder().decode(buf));
  search();});
var chain=Promise.resolve();
META.shards.forEach(function(s,k){
  var got=get(s.file);
  chain=chain.then(function(){return got;}).then(function(buf){
    addShard(buf,s.n);
    $('more').textContent=k<META.shards.length-1?'Loading older records…':'';
    if(k===0)return names0;
  }).then(function(){
    refilter();
    if(S.rec&&SEL<0){for(var i=0;i<P.n;i++)if(P.id[i]===S.rec){openCard(i);S.rec=null;break;}}
  });
});
chain.catch(function(e){$('count').textContent='Could not load the records ('+e.message+')';});
})();
