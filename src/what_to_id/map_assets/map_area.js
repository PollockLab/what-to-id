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
// A park is an area too. The park picker lists BC's parks, reserves, protected areas and
// conservancies (page_map.py ships the list next to the page), and the hash carries bcpark=<ORCS number>.
// A park that matches an iNaturalist place takes that place's own boundary, fetched when picked, so
// the map and the Identify link (which filters by place_id) count the same place; a park without one
// takes its BC Parks boundary from the list and an Identify link as a drawn area gets. park=<place
// id> from older links still loads.
var MapArea=(function(){
'use strict';
var Q=1e4,MAXV=1500,MAXMB=50,BATCH=200,MAXB=50,BOXQ={per_page:BATCH,reviewed:'false'},MAXROWS=200,
  API='https://api.inaturalist.org/v1/places/',B64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

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
// The park picker's search. Names fold to lower case without accents or punctuation, and the query
// drops the designation words, so "Garibaldi Park" and "garibaldi" find the same parks.
var DESIG=/\b(provincial|park|ecological reserve|protected area|conservancy|recreation area)\b/g,
  TAG={Park:'PP','Ecological reserve':'ER','Protected area':'PA','Recreation area':'RA',Conservancy:'Conservancy'};
function fold(s){return String(s||'').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}
// s folded, and for each of its characters the index in s it came from, to bold a match in place
function folded(s){var f='',at=[],i,j,c;
  for(i=0;i<s.length;i++){c=s[i].normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]/g,' ');
    for(j=0;j<c.length;j++)if(c[j]!==' '||f&&f[f.length-1]!==' '){f+=c[j];at.push(i);}}
  if(f[f.length-1]===' '){f=f.slice(0,-1);at.pop();}
  return {s:f,at:at};}
// A row of the park list ([key, name, kind, place, bbox, rings, other names]) as the picker uses it.
function entry(r,kinds){var k=kinds[r[2]];return {key:r[0],name:r[1],kind:k,tag:TAG[k]||k,place:r[3],bb:r[4],
  rings:r[5],n:folded(r[1]),alt:fold(r[6])};}
// How a park matches the text t: rank 0 at the start of a word of its name, 1 elsewhere in it, 2 in
// its other names, with a and b the name's matched characters; null for no match.
function match(p,t){var w=fold(t),c=w.replace(DESIG,' ').replace(/ +/g,' ').trim()||w,i;
  if(!c)return {rank:0};
  i=(' '+p.n.s).indexOf(' '+c);if(i<0)i=p.n.s.indexOf(c);
  if(i>=0)return {rank:p.n.s[i-1]===' '||!i?0:1,a:p.n.at[i],b:p.n.at[i+c.length-1]+1};
  return p.alt.indexOf(c)>=0?{rank:2}:null;}
// The picker's rows, in groups: with no text, the selected parks, then those in view, then the rest,
// each by name; with text, the matches by rank, then name. parks is in name order. At most MAXROWS
// rows; n counts them all, more those left out.
function listing(parks,t,sel,view){var g=[],n=0,left=MAXROWS;
  function put(label,rows){n+=rows.length;rows=rows.slice(0,left);left-=rows.length;
    if(rows.length)g.push({label:label,rows:rows});}
  if(!fold(t)){var s=[],v=[],o=[];parks.forEach(function(p){(sel(p)?s:view(p)?v:o).push({p:p});});
    put('Selected',s);put('In view',v);put('All parks',o);}
  else{var h=[];parks.forEach(function(p){var m=match(p,t);if(m){m.p=p;h.push(m);}});
    h.sort(function(x,y){return x.rank-y.rank;});put('',h);}
  return {groups:g,n:n,more:n-MAXROWS+left};}

// ctx: map, S, LAST, P() and keep() (the current records and kept flags), change() to refilter,
// hash, park and bcpark (the area, place ids and parks from the URL, ids comma-separated), fit (no
// view in the URL, so fit the map to the parks from it), place (the region's iNaturalist place id),
// parks (the park list's file), get(url) (an ArrayBuffer promise, gunzipped), sel() (the selection
// as text) and step (the Identify button, an IdStep).
//
// The area is one drawn or loaded shape, or one or more parks, which combine with OR: a record
// inside any of them is kept. Picking a park replaces a shape, and a shape replaces the parks.
function MapArea(ctx){
  // AREAS: {key (BC park, '' for none), place (iNaturalist place id, 0 for none), label, drawn,
  // rings and idx (null while the place's boundary loads)}
  var map=ctx.map,AREAS=[],VER=0,MASK=null,NOTE='',LINK='',LINKS=[],BOX=null,PEND='',SEQ=0,CHIPS='',UID='apark'+(++MapArea.n),
    mode=false,ended=0,pts=[],cursor=null,ready=false,color=getComputedStyle(document.documentElement)
      .getPropertyValue('--share').trim()||'#c2410c',nf=new Intl.NumberFormat('en-CA');
  var box=document.createElement('div');box.className='maplibregl-ctrl area';
  box.innerHTML='<div class="abtns"><button type="button" data-a="draw">Draw area</button>'+
    '<label class="afile">Load GeoJSON<input type="file" accept=".geojson,.json,application/geo+json,'+
    'application/json"></label><button type="button" data-a="finish" hidden>Finish</button>'+
    '<button type="button" data-a="cancel" hidden>Cancel</button><button type="button" data-a="clear" '+
    'hidden>Clear area</button></div><div class="apark"><div class="acombo"><input type="text" '+
    'role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="'+UID+'" placeholder='+
    '"Find BC parks" aria-label="BC parks and protected areas" autocomplete="off" spellcheck="false">'+
    '<button type="button" class="atog" tabindex="-1" aria-label="Show the parks" aria-controls="'+UID+'">'+
    '▾</button></div><div class="apanel" hidden><div class="ahdr"><span></span><button type="button">'+
    'Clear all</button></div><div class="alist" id="'+UID+'" role="listbox" aria-multiselectable="true" '+
    'aria-label="BC parks"></div><p class="amore" hidden></p></div></div><div class="achips" hidden></div>'+
    '<p class="anote" aria-live="polite" hidden></p><a class="abox" target="_blank" rel="noopener" hidden></a>'+
    '<p class="alive" aria-live="polite"></p>';
  function el(a){return box.querySelector('[data-a="'+a+'"]');}
  var note=box.querySelector('.anote'),file=box.querySelector('.afile input'),q=box.querySelector('.acombo input'),
    tog=box.querySelector('.atog'),panel=box.querySelector('.apanel'),hdr=box.querySelector('.ahdr'),
    list=box.querySelector('.alist'),more=box.querySelector('.amore'),live=box.querySelector('.alive'),
    chips=box.querySelector('.achips'),abox=box.querySelector('.abox');
  map.addControl({onAdd:function(){return box;},onRemove:function(){}},'top-left');
  function loaded(){return AREAS.filter(function(a){return a.idx;});}
  function drawn(){return AREAS.length&&AREAS[0].drawn;}
  function names(a){var l=a.map(function(x){return x.label;});
    return l.length<2?l.join(''):l.slice(0,-1).join(', ')+' and '+l[l.length-1];}
  function ui(){
    el('draw').hidden=mode;box.querySelector('.afile').hidden=mode;box.querySelector('.apark').hidden=mode;el('finish').hidden=!mode;
    if(mode)close();
    el('cancel').hidden=!mode;el('clear').hidden=mode||!AREAS.length;el('finish').disabled=pts.length<3;
    var own=AREAS.filter(function(a){return a.key&&!a.place&&a.idx;}),
      t=mode?(pts.length<3?'Click or tap the map to add corners.':'Double-click, tap the first corner '+
      'or press Finish to close the area.')+' Esc cancels.':(NOTE+' '+(own.length?'iNaturalist has no place for '+
      names(own)+', so the map uses '+(own.length>1?'their BC Parks boundaries. ':'its BC Parks boundary. '):'')+LINK).trim();
    note.textContent=t;note.hidden=!t;abox.hidden=mode||!BOX;
    if(BOX){abox.href=BOX.url;abox.textContent='Or open the box around '+(drawn()?'the shape':names(loaded()))+
      ' in one link, about '+nf.format(BOX.m)+' records';}
    sync();var ps=drawn()?[]:AREAS,sig=ps.map(function(a){return a.key+' '+a.place+' '+!!a.idx+' '+a.label;}).join('|');
    chips.hidden=mode||!ps.length;if(sig===CHIPS)return;CHIPS=sig;chips.innerHTML='';
    ps.forEach(function(a){var c=document.createElement('span'),x=document.createElement('button');
      c.className='achip'+(a.idx?'':' aload');c.textContent=a.label||'Park '+a.place;
      x.type='button';x.textContent='×';x.setAttribute('aria-label','Remove '+(a.label||'this park'));
      x.onclick=function(){remove(a);};c.appendChild(x);chips.appendChild(c);});
  }
  function paint(){
    if(!ready)return;var f=[];
    loaded().forEach(function(a){a.rings.forEach(function(r){var c=[];for(var i=0;i<r.length;i+=2)c.push([r[i],r[i+1]]);
      c.push(c[0]);f.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:c}});});});
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
  // The areas changed: a new mask, and a refilter unless quiet.
  function refresh(quiet){VER++;MASK=null;performance.mark('area');paint();ui();if(!quiet)ctx.change();}
  // Sets a drawn or loaded shape in place of any area, or clears the area with null.
  function set(rings,msg,quiet){SEQ++;PEND='';NOTE=msg||'';
    AREAS=rings&&rings.length?[{key:'',place:0,label:'',drawn:true,rings:rings,idx:index(rings)}]:[];
    refresh(quiet);
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
    f.text().then(function(t){var p=prepare(fromGeoJSON(JSON.parse(t)));set(p.rings,p.msg);fit(bbox());})
      .catch(function(e){NOTE='Could not use '+f.name+': '+(e instanceof SyntaxError?'it is not JSON.':e.message);
        ui();});};
  // iNaturalist answers a busy moment with an error that carries no CORS header, so try twice more
  function get(u,n){return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
    .catch(function(e){if(!n)throw e;return new Promise(function(ok){setTimeout(ok,1500);})
      .then(function(){return get(u,n-1);});});}
  function bbox(){var bb=[Infinity,Infinity,-Infinity,-Infinity];
    loaded().forEach(function(a){var b=a.idx.bb;bb=[Math.min(bb[0],b[0]),Math.min(bb[1],b[1]),
      Math.max(bb[2],b[2]),Math.max(bb[3],b[3])];});return bb;}
  function fit(b){map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:40,maxZoom:14});}
  // Adds a park to the area: b is a park from the list, or {place, name} for another iNaturalist
  // place. A park that matches a place takes the place's own boundary, fetched now, so the map and
  // the Identify link (which filters by place_id) count the same place; zoom fits the map to the parks.
  function add(b,zoom){var was=drawn();if(was)AREAS=[];
    if(AREAS.some(function(a){return b.key?a.key===b.key:!a.key&&a.place===b.place;}))return;
    var a={key:b.key||'',place:b.place||0,label:b.name||'',drawn:false,rings:null,idx:null};AREAS.push(a);NOTE='';
    if(!a.place){a.rings=prepare(decode(b.rings)).rings;a.idx=index(a.rings);refresh();if(zoom)fit(bbox());return;}
    if(was)refresh();else ui();
    get(API+a.place,2).then(function(j){
      var pl=j.results&&j.results[0];if(AREAS.indexOf(a)<0)return;
      if(!pl||!pl.geometry_geojson)throw new Error('no boundary');
      a.rings=prepare(fromGeoJSON(pl.geometry_geojson)).rings;a.idx=index(a.rings);a.label=a.label||pl.name;
      refresh();if(zoom)fit(bbox());})
      .catch(function(){if(AREAS.indexOf(a)<0)return;AREAS.splice(AREAS.indexOf(a),1);
        NOTE='Could not load '+(a.label||'that park')+' from iNaturalist.';refresh(true);});}
  function remove(a){var i=AREAS.indexOf(a);if(i<0)return;AREAS.splice(i,1);NOTE='';refresh();}
  // The park list, fetched once, when first needed, in name order.
  var PARKS=null,PARKP=null,ROWS=[],ACT=-1,OPEN=false,LT=0,coll=new Intl.Collator('en');
  function parks(){if(!PARKP)PARKP=ctx.get(ctx.parks).then(function(buf){
      var j=JSON.parse(new TextDecoder().decode(buf));
      PARKS=j.parks.map(function(r){return entry(r,j.kinds);}).sort(function(a,b){return coll.compare(a.name,b.name);});
      return PARKS;})
      .catch(function(e){PARKP=null;throw e;});
    return PARKP;}
  function find(key){var k=String(key).trim(),b=PARKS.filter(function(p){return p.key===k;})[0];
    if(!b&&/^\d{1,3}$/.test(k))return find(('000'+k).slice(-4));return b;}
  // The park picker: a combobox over the park list. Focus stays in the box, the highlighted row is
  // its aria-activedescendant. Enter, Space or a click ticks or unticks a park and keeps the list
  // open; a park ticked after typing selects the text, so typing again starts a new search.
  function picked(p){return AREAS.some(function(a){return !a.drawn&&a.key===p.key;});}
  function parked(){return AREAS.filter(function(a){return !a.drawn;});}
  function inView(p){var v=map.getBounds(),b=p.bb;
    return b[0]<=v.getEast()&&b[2]>=v.getWest()&&b[1]<=v.getNorth()&&b[3]>=v.getSouth();}
  function say(t){live.textContent='';setTimeout(function(){live.textContent=t;},50);}
  function parksN(n){return n===1?'1 park':nf.format(n)+' parks';}
  function span(cls,text){var e=document.createElement('span');e.className=cls;e.textContent=text;return e;}
  function option(r){var li=document.createElement('div'),p=r.p,nm=span('anm','');li.id=UID+'-'+ROWS.length;
    li.setAttribute('role','option');li.appendChild(span('acheck',''));
    if(r.b){nm.appendChild(document.createTextNode(p.name.slice(0,r.a)));
      nm.appendChild(document.createElement('b')).textContent=p.name.slice(r.a,r.b);
      nm.appendChild(document.createTextNode(p.name.slice(r.b)));}else nm.textContent=p.name;
    li.appendChild(nm);var k=li.appendChild(span('akind',p.tag));k.title=p.kind;
    if(!p.place){k=li.appendChild(span('adrawn','drawn'));k.title='iNaturalist has no place for this park; '+
      'the map uses its BC Parks boundary';}
    li.onclick=function(){ACT=ROWS.indexOf(r);active();toggle(p);};ROWS.push(r);r.li=li;return li;}
  function render(){var o=listing(PARKS,q.value,picked,inView);ROWS=[];list.textContent='';
    o.groups.forEach(function(g,i){var to=list;
      if(g.label){to=list.appendChild(document.createElement('div'));var h=to.appendChild(span('ahead',g.label));
        h.id=UID+'g'+i;h.setAttribute('role','presentation');to.setAttribute('role','group');
        to.setAttribute('aria-labelledby',h.id);}
      g.rows.forEach(function(r){to.appendChild(option(r));});});
    more.textContent=o.n?'Keep typing to narrow: '+parksN(o.more)+' more.':'No BC park matches.';
    more.hidden=o.n&&!o.more;ACT=-1;active();sync();return o;}
  function sync(){if(!OPEN)return;var n=parked().length;
    ROWS.forEach(function(r){r.li.setAttribute('aria-selected',picked(r.p));});
    hdr.firstChild.textContent=nf.format(n)+' selected · ';hdr.lastChild.hidden=!n;}
  function active(){ROWS.forEach(function(r,i){r.li.classList.toggle('aact',i===ACT);});
    if(ACT<0){q.removeAttribute('aria-activedescendant');return;}
    q.setAttribute('aria-activedescendant',ROWS[ACT].li.id);ROWS[ACT].li.scrollIntoView({block:'nearest'});}
  function toggle(p){var a=AREAS.filter(function(x){return !x.drawn&&x.key===p.key;})[0];
    if(a)remove(a);else add(p,true);if(q.value)q.select();
    say(p.name+(a?' removed':' selected')+', '+parksN(parked().length)+' selected.');}
  // Below 480px the list is a full-width panel just under the box.
  function open(){if(OPEN||mode)return;OPEN=true;panel.hidden=false;q.setAttribute('aria-expanded','true');
    panel.style.top=matchMedia('(max-width:479px)').matches?q.getBoundingClientRect().bottom+4+'px':'';
    if(PARKS){render();return;}
    list.textContent='';more.textContent='Loading the list of BC parks.';more.hidden=false;
    parks().then(function(){if(OPEN)render();})
      .catch(function(){more.textContent='Could not load the list of BC parks.';});}
  function close(){if(!OPEN)return;OPEN=false;panel.hidden=true;q.setAttribute('aria-expanded','false');
    ACT=-1;q.removeAttribute('aria-activedescendant');}
  q.onfocus=open;q.onclick=open;
  q.oninput=function(){if(!OPEN)open();else if(PARKS)render();clearTimeout(LT);
    LT=setTimeout(function(){if(OPEN&&PARKS){var o=listing(PARKS,q.value,picked,inView);
      say(o.n?parksN(o.n)+(q.value.trim()?' match.':'.'):'No BC park matches.');}},600);};
  q.onkeydown=function(e){var k=e.key,n=ROWS.length,ps;
    if(k==='ArrowDown'||k==='ArrowUp'){e.preventDefault();if(!OPEN){open();return;}
      if(n){ACT=k==='ArrowDown'?Math.min(ACT+1,n-1):Math.max(ACT-1,0);active();}}
    else if((k==='Home'||k==='End')&&OPEN&&n){e.preventDefault();ACT=k==='Home'?0:n-1;active();}
    else if(k==='Enter'){e.preventDefault();if(!OPEN){open();return;}
      if(ACT<0&&q.value.trim()&&n)ACT=0;if(ACT>=0){active();toggle(ROWS[ACT].p);}}
    else if(k===' '&&OPEN&&ACT>=0){e.preventDefault();toggle(ROWS[ACT].p);}
    else if(k==='Escape'&&OPEN){e.preventDefault();close();}
    else if(k==='Backspace'&&!q.value&&(ps=parked()).length){e.preventDefault();remove(ps[ps.length-1]);
      say(ps[ps.length-1].label+' removed, '+parksN(ps.length-1)+' selected.');}
    else if(k==='Tab')close();};
  // clicks in the list and on the toggle keep the focus in the box
  [panel,tog].forEach(function(e){e.onmousedown=function(ev){ev.preventDefault();};});
  tog.onclick=function(){if(OPEN)close();else{q.focus();open();}};
  hdr.lastChild.onclick=function(){set(null);say('No parks selected.');};
  document.addEventListener('pointerdown',function(e){if(!box.contains(e.target))close();});
  function ids(s){return String(s||'').split(',').map(function(x){return x.trim();}).filter(Boolean);}
  var keys=ids(ctx.bcpark),places=ids(ctx.park).map(Number).filter(function(x){return x>0;});
  if(keys.length||places.length){
    places.forEach(function(id){add({place:id},ctx.fit);});
    if(keys.length){var seq0=SEQ;PEND=['bcpark='+keys.map(encodeURIComponent).join(','),
      places.length?'park='+places.join(','):''].filter(Boolean).join('&');NOTE='Loading the park list.';ui();
      parks().then(function(){if(seq0!==SEQ)return;PEND='';NOTE='';var gone=[];
        keys.forEach(function(k){var b=find(k);if(b)add(b,ctx.fit);else gone.push(k);});
        if(gone.length)NOTE='The list of BC parks has no park '+gone.join(', ')+'.';ui();})
        .catch(function(){if(seq0===SEQ){PEND='';NOTE='Could not load the list of BC parks.';ui();}});}}
  else if(ctx.hash){try{set(decode(ctx.hash),'',true);}catch(e){NOTE='The area in this link could not be read.';ui();}}
  else ui();
  // the hash parameters: area=<rings>, or bcpark=<keys> and park=<place ids> for the parks; while
  // the park list loads, the parks the URL names
  function hash(){if(PEND)return PEND;if(drawn())return 'area='+encode(AREAS[0].rings);
    var k=[],p=[];AREAS.forEach(function(a){if(a.key)k.push(encodeURIComponent(a.key));else p.push(a.place);});
    return [k.length?'bcpark='+k.join(','):'',p.length?'park='+p.join(','):''].filter(Boolean).join('&');}
  // The area as a filter term: what it keeps, and what iNaturalist can say of it. iNaturalist takes
  // several place ids as OR, so parks that all match a place are exact.
  function term(){var a=loaded();if(!a.length)return null;var exact=!drawn()&&a.every(function(x){return x.place;});
    return {dim:'area',kind:drawn()?'polygon':'parks',id:hash(),label:drawn()?'Drawn area':names(a),n:a.length,
      exclude:false,mask:function(){return api.mask(ctx.P().n);},
      inat:function(){return exact?{params:{place_id:a.map(function(x){return x.place;}).join(',')},exact:true}:
        {params:{},exact:false};}};}
  var api={
    on:function(){return loaded().length>0;},
    // true while drawing and briefly after, so the closing tap opens no record's tip
    busy:function(){return mode||performance.now()-ended<500;},
    ver:function(){return VER;},
    hash:hash,
    term:term,
    clear:function(){if(mode)stop();close();if(AREAS.length||NOTE||PEND)set(null);},
    // 1 for each record inside any of the areas, null without one; extended as shards arrive.
    mask:function(n){var I=loaded().map(function(a){return a.idx;});if(!I.length)return null;
      if(MASK&&MASK.length===n)return MASK;
      var pos=ctx.P().pos,m=new Uint8Array(n),i=0,j;if(MASK){m.set(MASK);i=MASK.length;}
      for(;i<n;i++)for(j=0;j<I.length;j++)if(inside(I[j],pos[2*i],pos[2*i+1])){m[i]=1;break;}
      MASK=m;return m;},
    // The Identify link, through ctx.step, which steps through the batches when there are several.
    link:function(v,url,match){var u=link(v,url,match);return ctx.step.set(ctx.sel(),LINKS,u);}
  };
  // What iNaturalist can filter (the parks' place_ids) goes into the link as is. Otherwise it lists
  // the records by id, in LINKS, batches of BATCH, and offers the areas' bounding box as one link
  // beside them. Past MAXB batches the note asks for a narrower selection, and until then the link
  // opens the box. url(box, params) builds the link; a null box leaves it out.
  function link(v,url,match){var t=term();LINKS=[];BOX=null;
    if(!t||!ctx.P().n){LINK='';ui();return url(v);}
    var P=ctx.P(),keep=ctx.keep(),S=ctx.S,day=S.up?P.up:P.obs,full=S.lo===0&&S.hi===ctx.LAST,
      ids=[],n=0,i,d,q=t.inat(),one=t.n===1;
    function dated(i){d=day[i];return d===65535?full:d>=S.lo&&d<=S.hi;}
    for(i=0;i<P.n;i++){if(!keep[i]||!dated(i))continue;if(++n<=BATCH*MAXB)ids.push(P.id[i]);}
    if(q.exact){LINK='Identify is exact: it uses the iNaturalist place'+(one?'':'s')+' for '+t.label+'. '+
      (n===1?'1 record on this map is':nf.format(n)+' records on this map are')+' inside '+
      (one?'its boundary.':'them.');ui();
      return url(null,q.params);}
    if(!n){LINK='No records inside this area match these filters.';ui();return url(v);}
    if(n<=BATCH*MAXB){LINKS=batches(ids);var k=LINKS.length;
      LINK='Exact: '+(k>1?nf.format(n)+' records in '+k+' batches of up to '+BATCH:n===1?'this record by id':
        'these '+nf.format(n)+' records by id')+(n>1?', less any identified since.':'.');
      if(k>1)BOX=boxlink(v,url,match,dated,true);ui();return LINKS[0].url;}
    var o=boxlink(v,url,match,dated);
    LINK=nf.format(n)+' records: too many to open exactly (limit '+nf.format(BATCH*MAXB)+'). Make the '+
      'area smaller or add filters. Identify now opens the box around '+(drawn()?'the shape':t.label)+
      ', about '+nf.format(o.m)+' records.';ui();
    return o.url;}
  // One Identify link for the areas' box, with the batches' page size and review filter. side marks
  // the link offered beside the batches, so the button's own link is left alone.
  function boxlink(v,url,match,dated,side){
    var o=boxed(v,bbox(),ctx.P(),function(i){return dated(i)&&match(i);});
    return {url:url(o.box,BOXQ,side),m:o.m};}
  return api;
}
MapArea.encode=encode;MapArea.decode=decode;MapArea.fromGeoJSON=fromGeoJSON;MapArea.simplify=simplify;
MapArea.index=index;MapArea.inside=inside;MapArea.order=order;MapArea.batches=batches;
MapArea.boxed=boxed;MapArea.BOXQ=BOXQ;MapArea.fold=fold;MapArea.entry=entry;MapArea.match=match;
MapArea.listing=listing;MapArea.n=0;
return MapArea;
})();
