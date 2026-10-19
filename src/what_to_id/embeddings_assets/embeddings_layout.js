// Readers for the photo-space page: the layout parts on the atlas repo, the map's pool shards, and the
// join of the two by observation id. Formats: layout parts in atlas_layout.py, shards in page_map.py.
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.EmbeddingsLayout=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var Q=65535,SHARD_BYTES=17;

// Gunzip a buffer; one that is not gzip (a host that already decoded it) is returned as it is.
async function gunzip(buf){
  var u=new Uint8Array(buf,0,Math.min(2,buf.byteLength));
  if(u[0]!==0x1f||u[1]!==0x8b)return buf;
  return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
}
// n values of width w bytes stored byte-planar from `off`: every low byte, then the next byte, and so on.
function column(u8,off,n,T,w){
  if(w===1)return u8.slice(off,off+n);
  var a=new T(n),v=new Uint8Array(a.buffer);
  for(var j=0;j<w;j++,off+=n)for(var k=0;k<n;k++)v[k*w+j]=u8[off+k];
  return a;
}
function unstep(id){for(var s=0,i=0;i<id.length;i++)id[i]=s=(s+id[i])>>>0;return id;}

// One layout part (already gunzipped): 8 bytes per record, ids as steps, then x, then y as uint16.
function decodePart(buf,n){
  if(buf.byteLength!==8*n)throw new Error('layout part holds '+buf.byteLength+' bytes, expected '+8*n);
  var u=new Uint8Array(buf);
  return {n:n,id:unstep(column(u,0,n,Uint32Array,4)),qx:column(u,4*n,n,Uint16Array,2),qy:column(u,6*n,n,Uint16Array,2)};
}
// One map shard (already gunzipped); only the columns this page uses are kept.
function decodeShard(buf,n){
  if(buf.byteLength!==SHARD_BYTES*n)throw new Error('shard holds '+buf.byteLength+' bytes, expected '+SHARD_BYTES*n);
  var u=new Uint8Array(buf);
  return {n:n,id:unstep(column(u,0,n,Uint32Array,4)),qlon:column(u,4*n,n,Uint16Array,2),
    qlat:column(u,6*n,n,Uint16Array,2),tax:column(u,12*n,n,Uint16Array,2),grp:column(u,14*n,n,Uint8Array,1)};
}
// Place every shard record that some layout part holds. Ids are sorted in a shard and in a part, so
// each pair is one merge pass; a later part overrides an earlier one (a delta replaces the base).
// Returns {n,id,pos,lonlat,grp,tax,start} where start[k] is the first row of shard k.
function join(shards,parts,layoutBbox,mapBbox){
  var lx=layoutBbox[0],ly=layoutBbox[1],sx=(layoutBbox[2]-lx||1)/Q,sy=(layoutBbox[3]-ly||1)/Q;
  var mx=mapBbox[0],my=mapBbox[1],tx=(mapBbox[2]-mx||1)/Q,ty=(mapBbox[3]-my||1)/Q;
  var placed=shards.map(function(s){
    var qx=new Uint16Array(s.n),qy=new Uint16Array(s.n),has=new Uint8Array(s.n);
    parts.forEach(function(p){
      for(var i=0,j=0;i<s.n&&j<p.n;){
        var a=s.id[i],b=p.id[j];
        if(a<b)i++;else if(a>b)j++;else{qx[i]=p.qx[j];qy[i]=p.qy[j];has[i]=1;i++;j++;}
      }
    });
    var rows=[];for(var r=0;r<s.n;r++)if(has[r])rows.push(r);
    return {rows:rows,qx:qx,qy:qy};
  });
  var total=placed.reduce(function(t,p){return t+p.rows.length;},0);
  var out={n:total,id:new Uint32Array(total),pos:new Float32Array(2*total),lonlat:new Float32Array(2*total),
    grp:new Uint8Array(total),tax:new Uint16Array(total),start:[]};
  var o=0;
  shards.forEach(function(s,k){
    out.start.push(o);
    placed[k].rows.forEach(function(r){
      out.id[o]=s.id[r];out.grp[o]=s.grp[r];out.tax[o]=s.tax[r];
      out.pos[2*o]=lx+placed[k].qx[r]*sx;out.pos[2*o+1]=ly+placed[k].qy[r]*sy;
      out.lonlat[2*o]=mx+s.qlon[r]*tx;out.lonlat[2*o+1]=my+s.qlat[r]*ty;o++;
    });
  });
  out.start.push(o);
  return out;
}
// Row of an observation id, or -1: ids are sorted inside each shard's rows, not across shards.
function find(P,id){
  for(var k=0;k+1<P.start.length;k++){
    var lo=P.start[k],hi=P.start[k+1]-1;
    while(lo<=hi){var m=(lo+hi)>>1,v=P.id[m];if(v===id)return m;if(v<id)lo=m+1;else hi=m-1;}
  }
  return -1;
}
// The map's META lives only inline in map.html (page_map.render_map writes `var META={...};var BASEMAPS=`),
// so read it from there; a test pins that marker against render_map.
function parseMapMeta(html){
  var a=html.indexOf('var META='),b=a<0?-1:html.indexOf(';var BASEMAPS=',a);
  if(b<0)throw new Error('Could not read the map data description from the map page.');
  return JSON.parse(html.slice(a+9,b));
}
// The plot's accuracy as one sentence part, from manifest.layout.fidelity (see atlas_projection.projection_fidelity).
function fidelity(f){
  if(typeof f==='number')return {value:f,k:12};
  if(!f||typeof f!=='object')return null;
  var v=typeof f.mean_neighbor_recall==='number'?f.mean_neighbor_recall:
    Object.keys(f).map(function(k){return f[k];}).find(function(x){return typeof x==='number'&&x>=0&&x<=1;});
  return v===undefined?null:{value:v,k:f.k||12};
}
return {gunzip:gunzip,decodePart:decodePart,decodeShard:decodeShard,join:join,find:find,parseMapMeta:parseMapMeta,fidelity:fidelity};
});
