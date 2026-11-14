// The area filter's geometry, split from map_area.js: rings as flat [lon, lat, ...] arrays, their URL
// code, GeoJSON reading, corner thinning, and the banded point-in-rings test. No page or map needed.
var MapRings=(function(){
'use strict';
var Q=1e4,B64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

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

return {Q:Q,encode:encode,decode:decode,clean:clean,corners:corners,simplify:simplify,fromGeoJSON:fromGeoJSON,index:index,inside:inside};
})();
