// An area filter for the map: the viewer draws a polygon or loads one from a GeoJSON file, and the
// map then keeps only the records inside it. map.js calls MapArea once with its map and state, and
// folds mask() into the status category's kept bit, so a new area costs one CPU pass and one upload
// of the categories, as a new taxon search does.
//
// An area is a list of rings, each a flat [lon, lat, lon, lat, ...] array on a 0.0001 degree grid,
// tested with the even-odd rule over all rings: holes and several polygons need no special case, and
// a self-intersecting drawing still has an inside. The URL hash carries the same rings, so a shared
// link restores the same area and the same count. Each ring is coded as zigzag varint steps from
// the previous corner, 5 bits to a base64url character, rings joined by '.'.
//
// A park is an area too. The park search reads BC's list of parks, reserves, protected areas and
// conservancies (page_map.py ships it next to the page), and the hash carries bcpark=<ORCS number>.
// A park that matches an iNaturalist place takes that place's own boundary, fetched when picked, so
// the map and the Identify link (which filters by place_id) count the same place; a park without one
// takes its BC Parks boundary from the list and an Identify link as a drawn area gets. park=<place
// id> from older links still loads, and iNaturalist's own park names follow the list's in the search.
var MapArea=(function(){
'use strict';
var Q=1e4,MAXV=1500,MAXMB=50,BATCH=200,MAXB=50,BOXQ={per_page:BATCH,reviewed:'false'},API='https://api.inaturalist.org/v1/places/',
  PARK=/park|protected area|ecological reserve|conservancy|recreation area/i,B64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

function encode(rings){
  return rings.map(function(r){var s='',px=0,py=0;
    for(var i=0;i<r.length;i++){var v=Math.round(r[i]*Q),d=v-(i%2?py:px);if(i%2)py=v;else px=v;
      var z=d<0?-2*d-1:2*d;while(z>=32){s+=B64[32|z%32];z=Math.floor(z/32);}s+=B64[z];}
    return s;}).join('.');
}
function decode(s){
  return clean(s.split('.').map(function(part){var r=[],v=0,m=1,px=0,py=0;
    for(var i=0;i<part.length;i++){var c=B64.indexOf(part[i]);if(c<0)throw new Error('bad character');
      v+=(c%32)*m;m*=32;if(c>=32)continue;
      var d=v%2?-(v+1)/2:v/2;v=0;m=1;
      if(r.length%2)r.push((py+=d)/Q);else r.push((px+=d)/Q);}
    if(v||r.length%2)throw new Error('cut short');
    return r;}));
}
// Rounds rings to the grid, drops repeated corners and the closing one, and rings with fewer than
// three corners left.
function clean(rings){
  var out=[];
  rings.forEach(function(r){var o=[];
    for(var i=0;i<r.length;i+=2){var x=Math.round(r[i]*Q)/Q,y=Math.round(r[i+1]*Q)/Q;
      if(!isFinite(x)||!isFinite(y))throw new Error('a corner is not a number');
      var n=o.length;if(n&&o[n-2]===x&&o[n-1]===y)continue;o.push(x,y);}
    var n=o.length;if(n>=4&&o[0]===o[n-2]&&o[1]===o[n-1])o.length=n-2;
    if(o.length>=6)out.push(o);});
  return out;
}
function corners(rings){return rings.reduce(function(a,r){return a+r.length/2;},0);}
// Keeps at most max corners over all rings. Each corner gets the distance at which Douglas-Peucker
// would still keep it (capped by its parent's, so the order nests); the max largest win. A ring's
// two anchor corners rank by the ring's size, so tiny islands drop out whole.
function simplify(rings,max){
  if(corners(rings)<=max)return rings;
  var w=rings.map(function(r){
    var n=r.length/2,imp=new Float64Array(n),f=0,fd=-1,i;
    for(i=1;i<n;i++){var dx=r[2*i]-r[0],dy=r[2*i+1]-r[1];if(dx*dx+dy*dy>fd){fd=dx*dx+dy*dy;f=i;}}
    var ext=Math.sqrt(fd);imp[0]=imp[f]=ext;
    var st=[[0,f,ext],[f,n,ext]];
    while(st.length){var s=st.pop(),a=s[0],b=s[1],ax=r[2*a],ay=r[2*a+1],bx=r[2*(b%n)],by=r[2*(b%n)+1],
        best=-1,k=-1,ux=bx-ax,uy=by-ay,L=ux*ux+uy*uy;
      for(i=a+1;i<b;i++){var px=r[2*i]-ax,py=r[2*i+1]-ay,t=L?Math.max(0,Math.min(1,(px*ux+py*uy)/L)):0,
          ex=px-t*ux,ey=py-t*uy,d=ex*ex+ey*ey;if(d>best){best=d;k=i;}}
      if(k<0)continue;var dk=Math.min(s[2],Math.sqrt(best));imp[k]=dk;st.push([a,k,dk],[k,b,dk]);}
    return imp;});
  var all=[];w.forEach(function(x){for(var i=0;i<x.length;i++)all.push(x[i]);});
  all.sort(function(a,b){return b-a;});var cut=all[max],out=[],live=[];
  rings.forEach(function(r,j){var o=[];
    for(var i=0;i<w[j].length;i++)if(w[j][i]>cut)o.push(r[2*i],r[2*i+1]);
    o=clean([o]);if(o.length){out.push(o[0]);live.push(r);}});
  // corners spent on rings that dropped out go to the rest
  return live.length&&live.length<rings.length?simplify(live,max):out;
}
// The polygons in a GeoJSON object (FeatureCollection, Feature, GeometryCollection, Polygon or
// MultiPolygon), as rings. GeoJSON is longitude and latitude in WGS 84; an older file that names
// another CRS, or holds coordinates beyond those ranges, is refused.
function fromGeoJSON(o){
  var crs=o&&o.crs&&o.crs.properties&&String(o.crs.properties.name||'');
  if(crs&&!/CRS84$|EPSG:+4326$/i.test(crs)){var code=crs.match(/EPSG:+(\d+)/i);
    throw new Error('This file is in '+(code?'EPSG:'+code[1]:crs)+', not longitude and latitude. '+
      'Save it again as GeoJSON in WGS 84 (EPSG:4326), e.g. in QGIS with Export, Save Features As.');}
  var rings=[];
  (function walk(g){if(!g||typeof g!=='object')return;
    if(g.type==='FeatureCollection')(g.features||[]).forEach(walk);
    else if(g.type==='Feature')walk(g.geometry);
    else if(g.type==='GeometryCollection')(g.geometries||[]).forEach(walk);
    else if(g.type==='Polygon')add(g.coordinates);
    else if(g.type==='MultiPolygon')(g.coordinates||[]).forEach(add);})(o);
  function add(poly){(poly||[]).forEach(function(ring){var r=[];
    (ring||[]).forEach(function(c){var x=+c[0],y=+c[1];
      if(!(Math.abs(x)<=180&&Math.abs(y)<=90))throw new Error('Coordinates such as '+c[0]+', '+c[1]+
        ' are not longitude and latitude; the file is likely in a projected CRS such as BC Albers '+
        '(EPSG:3005). Save it again as GeoJSON in WGS 84 (EPSG:4326).');
      r.push(x,y);});rings.push(r);});}
  if(!rings.length)throw new Error('This file holds no Polygon or MultiPolygon.');
  return rings;
}
// Edges sorted into horizontal bands, so a point is tested only against the edges crossing its band.
function index(rings){
  var ne=corners(rings),x0=new Float64Array(ne),y0=new Float64Array(ne),x1=new Float64Array(ne),
    y1=new Float64Array(ne),bb=[Infinity,Infinity,-Infinity,-Infinity],e=0;
  rings.forEach(function(r){var n=r.length/2;for(var i=0;i<n;i++){var j=(i+1)%n;
    x0[e]=r[2*i];y0[e]=r[2*i+1];x1[e]=r[2*j];y1[e]=r[2*j+1];e++;
    bb[0]=Math.min(bb[0],r[2*i]);bb[1]=Math.min(bb[1],r[2*i+1]);
    bb[2]=Math.max(bb[2],r[2*i]);bb[3]=Math.max(bb[3],r[2*i+1]);}});
  var nb=Math.max(1,Math.min(4096,ne)),h=(bb[3]-bb[1])/nb||1,cnt=new Int32Array(nb+1),k,b;
  function band(y){return Math.max(0,Math.min(nb-1,Math.floor((y-bb[1])/h)));}
  for(k=0;k<ne;k++)for(b=band(Math.min(y0[k],y1[k]));b<=band(Math.max(y0[k],y1[k]));b++)cnt[b+1]++;
  for(b=0;b<nb;b++)cnt[b+1]+=cnt[b];
  var list=new Int32Array(cnt[nb]),fill=cnt.slice(0,nb);
  for(k=0;k<ne;k++)for(b=band(Math.min(y0[k],y1[k]));b<=band(Math.max(y0[k],y1[k]));b++)list[fill[b]++]=k;
  return {x0:x0,y0:y0,x1:x1,y1:y1,bb:bb,band:band,start:cnt,list:list};
}
function inside(I,x,y){
  var bb=I.bb;if(x<bb[0]||x>bb[2]||y<bb[1]||y>bb[3])return 0;
  var b=I.band(y),c=0;
  for(var k=I.start[b];k<I.start[b+1];k++){var e=I.list[k],ya=I.y0[e],yb=I.y1[e];
    if((ya>y)!==(yb>y)&&x<I.x0[e]+(y-ya)*(I.x1[e]-I.x0[e])/(yb-ya))c^=1;}
  return c;
}
// Identify links that open these ids exactly, at most BATCH to a link and in order(): per_page shows
// a whole batch on one page, place_id=any keeps a viewer's default place from hiding any, and
// reviewed=false leaves out those the viewer has already reviewed. Each batch is {url, n, lo, hi}.
var IDS='https://www.inaturalist.org/observations/identify?quality_grade=needs_id&reviewed=false'+
  '&place_id=any&per_page='+BATCH+'&id=';
// The order the batches open in: newest first, as Identify lists them. A priority order can take
// its place here without touching the button.
function order(ids){return Array.prototype.slice.call(ids).sort(function(a,b){return b-a;});}
// The area's bounding box bb cut to the view v (the whole box when they do not meet), and how many
// of the records P that pass ok(i) fall inside it: what one Identify link for the box opens. Not
// exact, as the box also holds records outside the shape.
function boxed(v,bb,P,ok){
  var w=Math.max(v.w,bb[0]),s=Math.max(v.s,bb[1]),e=Math.min(v.e,bb[2]),n=Math.min(v.n,bb[3]),m=0,i;
  if(!(w<e&&s<n)){w=bb[0];s=bb[1];e=bb[2];n=bb[3];}
  for(i=0;i<P.n;i++){var x=P.pos[2*i],y=P.pos[2*i+1];if(x>=w&&x<=e&&y>=s&&y<=n&&ok(i))m++;}
  return {box:{w:w,s:s,e:e,n:n},m:m};
}
function batches(ids){
  var s=order(ids),out=[];
  for(var i=0;i<s.length;i+=BATCH){var b=s.slice(i,i+BATCH);
    out.push({url:IDS+b.join(','),n:b.length,lo:b[b.length-1],hi:b[0]});}
  return out;
}

// ctx: map, S, LAST, P() and keep() (the current records and kept flags), change() to refilter,
// hash, park and bcpark (the area, place id and park from the URL), fit (no view in the URL, so fit
// the map to a park from it), place (the region's iNaturalist place id), parks (the park list's
// file), get(url) (an ArrayBuffer promise, gunzipped), sel() (the selection as text) and step (the
// Identify button, an IdStep).
function MapArea(ctx){
  var map=ctx.map,RINGS=null,IDX=null,VER=0,MASK=null,NOTE='',LINK='',LINKS=[],BOX=null,PLACE=null,BC=null,PEND='',SEQ=0,QT=0,
    mode=false,ended=0,pts=[],cursor=null,ready=false,color=getComputedStyle(document.documentElement)
      .getPropertyValue('--share').trim()||'#c2410c',nf=new Intl.NumberFormat('en-CA');
  var box=document.createElement('div');box.className='maplibregl-ctrl area';
  box.innerHTML='<div class="abtns"><button type="button" data-a="draw">Draw area</button>'+
    '<label class="afile">Load GeoJSON<input type="file" accept=".geojson,.json,application/geo+json,'+
    'application/json"></label><button type="button" data-a="finish" hidden>Finish</button>'+
    '<button type="button" data-a="cancel" hidden>Cancel</button><button type="button" data-a="clear" '+
    'hidden>Clear area</button></div><div class="apark"><input type="search" placeholder="Find a BC park" '+
    'aria-label="Find a BC park or protected area" autocomplete="off"><ul class="alist" hidden></ul></div>'+
    '<p class="anote" aria-live="polite" hidden></p><a class="abox" target="_blank" rel="noopener" hidden></a>';
  function el(a){return box.querySelector('[data-a="'+a+'"]');}
  var note=box.querySelector('.anote'),file=box.querySelector('.afile input'),
    q=box.querySelector('.apark input'),list=box.querySelector('.alist'),abox=box.querySelector('.abox');
  map.addControl({onAdd:function(){return box;},onRemove:function(){}},'top-left');
  function ui(){
    el('draw').hidden=mode;box.querySelector('.afile').hidden=mode;box.querySelector('.apark').hidden=mode;el('finish').hidden=!mode;
    el('cancel').hidden=!mode;el('clear').hidden=mode||!RINGS;el('finish').disabled=pts.length<3;
    var t=mode?(pts.length<3?'Click or tap the map to add corners.':'Double-click, tap the first corner '+
      'or press Finish to close the area.')+' Esc cancels.':(NOTE+' '+LINK).trim();
    note.textContent=t;note.hidden=!t;abox.hidden=mode||!BOX;
    if(BOX){abox.href=BOX.url;abox.textContent='Or open the box around '+(BC?BC.label:'the shape')+' in one link, about '+
      nf.format(BOX.m)+' records';}
  }
  function paint(){
    if(!ready)return;var f=[];
    (RINGS||[]).forEach(function(r){var c=[];for(var i=0;i<r.length;i+=2)c.push([r[i],r[i+1]]);c.push(c[0]);
      f.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:c}});});
    if(mode&&pts.length){f.push({type:'Feature',properties:{},geometry:{type:'LineString',
      coordinates:cursor?pts.concat([cursor]):pts}});
      pts.forEach(function(p,i){f.push({type:'Feature',properties:{first:i===0},
        geometry:{type:'Point',coordinates:p}});});}
    map.getSource('area').setData({type:'FeatureCollection',features:f});
  }
  map.on('load',function(){
    map.addSource('area',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
    map.addLayer({id:'area-line',type:'line',source:'area',filter:['==',['geometry-type'],'LineString'],
      paint:{'line-color':color,'line-width':2.5}});
    map.addLayer({id:'area-pt',type:'circle',source:'area',filter:['==',['geometry-type'],'Point'],
      paint:{'circle-color':'#fff','circle-stroke-color':color,'circle-stroke-width':2,
        'circle-radius':['case',['get','first'],7,4]}});
    ready=true;paint();});
  // Sets the area, or clears it with null, and refilters; place {id, label} when it is an
  // iNaturalist place, bc {key, label} when it is a park from the list.
  function set(rings,msg,quiet,place,bc){
    RINGS=rings&&rings.length?rings:null;IDX=RINGS&&index(RINGS);VER++;MASK=null;NOTE=msg||'';
    PLACE=RINGS&&place||null;BC=RINGS&&bc||null;PEND='';if(!place&&!bc){SEQ++;q.value='';}
    performance.mark('area');paint();ui();if(!quiet)ctx.change();
  }
  function prepare(rings){
    var raw=corners(rings),r=simplify(clean(rings),MAXV),n=corners(r);
    if(!r.length)throw new Error('The area has no ring with three distinct corners.');
    return {rings:r,msg:raw>MAXV?'Simplified from '+nf.format(raw)+' to '+nf.format(n)+' corners. ':''};
  }
  function start(){mode=true;pts=[];cursor=null;map.doubleClickZoom.disable();
    map.getCanvas().style.cursor='crosshair';paint();ui();}
  function stop(){mode=false;ended=performance.now();pts=[];cursor=null;map.doubleClickZoom.enable();
    map.getCanvas().style.cursor='';paint();ui();}
  function finish(){if(pts.length<3)return;
    var r=[];pts.forEach(function(p){r.push(p[0],p[1]);});stop();
    try{var p=prepare([r]);set(p.rings,p.msg);}catch(e){NOTE=e.message;ui();}}
  function near(p,pt,px){var q=map.project(p);return Math.hypot(q.x-pt.x,q.y-pt.y)<=px;}
  map.on('click',function(e){if(!mode)return;
    if(pts.length>=3&&near(pts[0],e.point,14)){finish();return;}
    if(pts.length&&near(pts[pts.length-1],e.point,6))return;
    pts.push([e.lngLat.lng,e.lngLat.lat]);paint();ui();});
  map.on('dblclick',function(e){if(mode){e.preventDefault();finish();}});
  map.on('mousemove',function(e){if(mode&&pts.length){cursor=[e.lngLat.lng,e.lngLat.lat];paint();}});
  addEventListener('keydown',function(e){if(e.key==='Escape'&&mode)stop();});
  el('draw').onclick=start;el('cancel').onclick=stop;el('finish').onclick=finish;
  el('clear').onclick=function(){set(null);};
  file.onchange=function(){var f=file.files[0];file.value='';if(!f)return;
    if(f.size>MAXMB*1048576){NOTE='This file is over '+MAXMB+' MB.';ui();return;}
    f.text().then(function(t){var p=prepare(fromGeoJSON(JSON.parse(t)));set(p.rings,p.msg);
      var b=IDX.bb;map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:40,maxZoom:14});})
      .catch(function(e){NOTE='Could not use '+f.name+': '+(e instanceof SyntaxError?'it is not JSON.':e.message);
        ui();});};
  // iNaturalist answers a busy moment with an error that carries no CORS header, so try twice more
  function get(u,n){return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
    .catch(function(e){if(!n)throw e;return new Promise(function(ok){setTimeout(ok,1500);})
      .then(function(){return get(u,n-1);});});}
  function fit(b){map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:40,maxZoom:14});}
  // An iNaturalist place's boundary; bc, the park from the list it stands for, if any.
  function park(id,label,zoom,bc){var seq=++SEQ;NOTE='Loading '+(label||'the park')+'.';LINK='';LINKS=[];ui();
    get(API+id,2).then(function(j){
      var pl=j.results&&j.results[0];if(seq!==SEQ)return;
      if(!pl||!pl.geometry_geojson)throw new Error('no boundary');
      var p=prepare(fromGeoJSON(pl.geometry_geojson)),name=label||pl.name;q.value=name;
      set(p.rings,p.msg,false,{id:pl.id,label:name},bc&&{key:bc.key,label:name});
      if(zoom)fit(IDX.bb);})
      .catch(function(){if(seq!==SEQ)return;NOTE='Could not load that park from iNaturalist.';ui();});}
  // A park from the list by its own boundary.
  function local(b,zoom,msg){var p=prepare(decode(b.rings));q.value=b.name;
    set(p.rings,(msg||'')+p.msg,false,null,{key:b.key,label:b.name});if(zoom)fit(b.bb);}
  function choose(b,zoom){list.hidden=true;
    if(b.place)park(b.place,b.name,zoom,b);
    else{SEQ++;local(b,zoom,'iNaturalist has no place for this park, so the map uses its BC Parks boundary. ');}}
  // The park list, fetched once, when first needed.
  var PARKS=null,PARKP=null;
  function fold(s){return s.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}
  function parks(){if(!PARKP)PARKP=ctx.get(ctx.parks).then(function(buf){
      var j=JSON.parse(new TextDecoder().decode(buf));
      PARKS=j.parks.map(function(r){return {key:r[0],name:r[1],kind:j.kinds[r[2]],place:r[3],bb:r[4],
        rings:r[5],f:' '+fold(r[1]+' '+r[6])};});return PARKS;})
      .catch(function(e){PARKP=null;throw e;});
    return PARKP;}
  function find(key){var k=String(key).trim(),b=PARKS.filter(function(p){return p.key===k;})[0];
    if(!b&&/^\d{1,3}$/.test(k))return find(('000'+k).slice(-4));return b;}
  // Parks whose words start with the words typed, those whose name starts with them first; the whole
  // list, in order, for an empty box.
  function hits(t){var f=fold(t);if(!f)return PARKS.slice();var w=f.split(' '),a=[],b=[];
    PARKS.forEach(function(p){
      if(w.every(function(x){return p.f.indexOf(' '+x)>=0;}))(p.f.indexOf(' '+f)===0?a:b).push(p);
      else if(p.f.replace(/ /g,'').indexOf(f.replace(/ /g,''))>=0)b.push(p);});
    return a.concat(b);}
  function row(text,kind,go){var li=document.createElement('li');li.tabIndex=0;li.textContent=text;
    if(kind){var k=document.createElement('span');k.className='akind';k.textContent=kind;li.appendChild(k);}
    li.onclick=go;li.onkeydown=function(e){if(e.key==='Enter')go();
      else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();
        var n=e.key==='ArrowDown'?li.nextElementSibling:li.previousElementSibling;
        while(n&&!n.tabIndex)n=e.key==='ArrowDown'?n.nextElementSibling:n.previousElementSibling;
        (n||q).focus();}};
    list.appendChild(li);}
  function msg(text,cls){var li=document.createElement('li');li.className=cls||'anone';li.textContent=text;
    list.appendChild(li);}
  function search(){clearTimeout(QT);var t=q.value.trim();
    parks().then(function(){if(q.value.trim()!==t)return;var rows=hits(t);list.innerHTML='';
      rows.forEach(function(b){row(b.name,b.kind,function(){choose(b,true);});});
      if(!rows.length)msg('No BC park matches.');list.hidden=false;
      // then iNaturalist's other park names under the region, such as regional parks
      if(t.length>=3)QT=setTimeout(function(){more(t);},300);})
      .catch(function(){list.innerHTML='';msg('Could not load the list of BC parks.');list.hidden=false;});}
  function more(t){get(API+'autocomplete?per_page=30&q='+encodeURIComponent(t),1).then(function(j){
      if(q.value.trim()!==t)return;var known={},seen={};
      PARKS.forEach(function(p){if(p.place)known[p.place]=1;});
      var rows=(j.results||[]).filter(function(p){return p.admin_level==null&&PARK.test(p.name)&&!known[p.id]&&
        (p.ancestor_place_ids||[]).indexOf(+ctx.place)>=0;}).slice(0,8);
      if(!rows.length)return;
      var none=list.querySelector('.anone');if(none)none.remove();
      rows.forEach(function(p){seen[p.name]=(seen[p.name]||0)+1;});
      msg('More places on iNaturalist','ahead');
      rows.forEach(function(p){row(p.name+(seen[p.name]>1?' (place '+p.id+')':''),'',function(){
        list.hidden=true;park(p.id,p.name,true);});});}).catch(function(){});}
  q.oninput=search;q.onfocus=search;
  q.onkeydown=function(e){var f=list.querySelector('li[tabindex]');
    if(e.key==='ArrowDown'&&f){e.preventDefault();f.focus();}
    else if(e.key==='Enter'&&f)f.click();else if(e.key==='Escape')list.hidden=true;};
  document.addEventListener('pointerdown',function(e){if(!box.contains(e.target))list.hidden=true;});
  if(ctx.bcpark){var seq0=++SEQ;PEND='bcpark='+encodeURIComponent(ctx.bcpark);NOTE='Loading the park.';ui();
    parks().then(function(){if(seq0!==SEQ)return;var b=find(ctx.bcpark);
      if(b)choose(b,ctx.fit);else{PEND='';NOTE='The list of BC parks has no park '+ctx.bcpark+'.';ui();}})
      .catch(function(){if(seq0===SEQ){PEND='';NOTE='Could not load the list of BC parks.';ui();}});}
  else if(ctx.park){PEND='park='+ctx.park;park(ctx.park,'',ctx.fit);}
  else if(ctx.hash){try{set(decode(ctx.hash),'',true);}catch(e){NOTE='The area in this link could not be read.';ui();}}
  else ui();
  // The area as a filter term: what it keeps, and what iNaturalist can say of it.
  function term(){if(!RINGS)return null;
    return {dim:'area',kind:PLACE?'park':BC?'bcpark':'polygon',id:PLACE?PLACE.id:BC?BC.key:encode(RINGS),
      label:PLACE?PLACE.label:BC?BC.label:'Drawn area',exclude:false,mask:function(){return api.mask(ctx.P().n);},
      inat:function(){return PLACE?{params:{place_id:PLACE.id},exact:true}:{params:{},exact:false};}};}
  var api={
    on:function(){return !!RINGS;},
    // true while drawing and briefly after, so the closing tap opens no record's tip
    busy:function(){return mode||performance.now()-ended<500;},
    ver:function(){return VER;},
    // the hash parameter: bcpark=<key>, park=<place id> or area=<rings>; while a park from the
    // URL loads, the one it names
    hash:function(){return PEND||(!RINGS?'':BC?'bcpark='+encodeURIComponent(BC.key):
      PLACE?'park='+PLACE.id:'area='+encode(RINGS));},
    term:term,
    clear:function(){if(mode)stop();SEQ++;list.hidden=true;if(RINGS||NOTE)set(null);},
    // 1 for each record inside the area, null without one; extended as shards arrive.
    mask:function(n){if(!RINGS)return null;if(MASK&&MASK.length===n)return MASK;
      var pos=ctx.P().pos,m=new Uint8Array(n),i=0;if(MASK){m.set(MASK);i=MASK.length;}
      for(;i<n;i++)m[i]=inside(IDX,pos[2*i],pos[2*i+1]);MASK=m;return m;},
    // The Identify link, through ctx.step, which steps through the batches when there are several.
    link:function(v,url,match){var u=link(v,url,match);return ctx.step.set(ctx.sel(),LINKS,u);}
  };
  // What iNaturalist can filter (a park's place_id) goes into the link as is. Otherwise it lists the
  // records by id, in LINKS, batches of BATCH, and offers the bounding box as one link beside them.
  // Past MAXB batches the note asks for a narrower selection, and until then the link opens the box.
  // url(box, params) builds the link; a null box leaves it out.
  function link(v,url,match){var t=term();LINKS=[];BOX=null;
    if(!t||!ctx.P().n){LINK='';ui();return url(v);}
    var P=ctx.P(),keep=ctx.keep(),S=ctx.S,day=S.up?P.up:P.obs,full=S.lo===0&&S.hi===ctx.LAST,
      ids=[],n=0,i,d,q=t.inat();
    function dated(i){d=day[i];return d===65535?full:d>=S.lo&&d<=S.hi;}
    for(i=0;i<P.n;i++){if(!keep[i]||!dated(i))continue;if(++n<=BATCH*MAXB)ids.push(P.id[i]);}
    if(q.exact){LINK='Identify is exact: it uses the iNaturalist place for '+t.label+'. '+
      (n===1?'1 record on this map is':nf.format(n)+' records on this map are')+' inside its boundary.';ui();
      return url(null,q.params);}
    if(!n){LINK='No records inside this area match these filters.';ui();return url(v);}
    if(n<=BATCH*MAXB){LINKS=batches(ids);var k=LINKS.length;
      LINK='Exact: '+(k>1?nf.format(n)+' records in '+k+' batches of up to '+BATCH:n===1?'this record by id':
        'these '+nf.format(n)+' records by id')+(n>1?', less any identified since.':'.');
      if(k>1)BOX=boxlink(v,url,match,dated,true);ui();return LINKS[0].url;}
    var o=boxlink(v,url,match,dated);
    LINK=nf.format(n)+' records: too many to open exactly (limit '+nf.format(BATCH*MAXB)+'). Make the '+
      'area smaller or add filters. Identify now opens the box around '+(BC?BC.label:'the shape')+', about '+nf.format(o.m)+
      ' records.';ui();
    return o.url;}
  // One Identify link for the area's box, with the batches' page size and review filter. side marks
  // the link offered beside the batches, so the button's own link is left alone.
  function boxlink(v,url,match,dated,side){
    var o=boxed(v,IDX.bb,ctx.P(),function(i){return dated(i)&&match(i);});
    return {url:url(o.box,BOXQ,side),m:o.m};}
  return api;
}
MapArea.encode=encode;MapArea.decode=decode;MapArea.fromGeoJSON=fromGeoJSON;MapArea.simplify=simplify;
MapArea.index=index;MapArea.inside=inside;MapArea.order=order;MapArea.batches=batches;
MapArea.boxed=boxed;MapArea.BOXQ=BOXQ;
return MapArea;
})();
