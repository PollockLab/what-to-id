// What narrows the records by where they are, as a verdict per record (1 keeps it), shared by the photo space
// and the Identify page. P is a record table as EmbeddingsLayout.join and .pool return it: n, id, lonlat and
// start (the first row of each shard). The area and the lasso are the map's: MapArea reads their rings.
var SpaceMask=(function(){
'use strict';
// The index of an area string, or null when it is empty or does not read (such an area is left to the map).
function areaIndex(str){
  if(!str)return null;
  try{var r=MapArea.decode(str);return r.length?MapArea.index(r):null;}catch(e){return null;}
}
// Per record: inside the area index I, by its longitude and latitude.
function area(I,P){
  var m=new Uint8Array(P.n);
  for(var i=0;i<P.n;i++)m[i]=MapArea.inside(I,P.lonlat[2*i],P.lonlat[2*i+1]);
  return m;
}
// Per record: its id is among the sorted ids (the map's projects, or a lasso's), found by walking each
// shard's sorted rows against them.
function ids(sorted,P){
  var m=new Uint8Array(P.n);
  for(var k=0;k+1<P.start.length;k++)for(var i=P.start[k],j=0;i<P.start[k+1]&&j<sorted.length;i++){
    var v=P.id[i];while(j<sorted.length&&sorted[j]<v)j++;if(sorted[j]===v)m[i]=1;}
  return m;
}
// Per record: its point xy (flat, as P.pos) is inside the closed ring. The records inside have their ids in
// idsOf, in row order, as the lasso hands them to the map.
function ring(r,xy,n){
  var I=MapArea.index([r]),m=new Uint8Array(n);
  for(var i=0;i<n;i++)if(MapArea.inside(I,xy[2*i],xy[2*i+1]))m[i]=1;
  return m;
}
function idsOf(mask,P){
  var k=0,i;for(i=0;i<P.n;i++)if(mask[i])k++;
  var out=new Uint32Array(k);k=0;for(i=0;i<P.n;i++)if(mask[i])out[k++]=P.id[i];
  return out;
}
return {areaIndex:areaIndex,area:area,ids:ids,ring:ring,idsOf:idsOf};
})();
