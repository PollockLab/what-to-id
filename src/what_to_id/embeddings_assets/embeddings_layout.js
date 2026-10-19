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
// One map shard (already gunzipped), every column the map filters on (page_map._decode_shard has the order).
function decodeShard(buf,n){
  if(buf.byteLength!==SHARD_BYTES*n)throw new Error('shard holds '+buf.byteLength+' bytes, expected '+SHARD_BYTES*n);
  var u=new Uint8Array(buf);
  return {n:n,id:unstep(column(u,0,n,Uint32Array,4)),qlon:column(u,4*n,n,Uint16Array,2),
    qlat:column(u,6*n,n,Uint16Array,2),obs:column(u,8*n,n,Uint16Array,2),up:column(u,10*n,n,Uint16Array,2),
    tax:column(u,12*n,n,Uint16Array,2),grp:column(u,14*n,n,Uint8Array,1),ids:column(u,15*n,n,Uint8Array,1),flags:column(u,16*n,n,Uint8Array,1)};
}
// Every record the layout parts hold, before the shards are known: ids sorted, a later part overriding an earlier one.
// Returns {n,id,pos,start} like join, without the group and taxon columns.
function layoutOnly(parts,layoutBbox){
  var lx=layoutBbox[0],ly=layoutBbox[1],sx=(layoutBbox[2]-lx||1)/Q,sy=(layoutBbox[3]-ly||1)/Q;
  var id=new Uint32Array(0),qx=new Uint16Array(0),qy=new Uint16Array(0);
  parts.forEach(function(p){
    var m=id.length+p.n,nid=new Uint32Array(m),nx=new Uint16Array(m),ny=new Uint16Array(m),i=0,j=0,o=0;
    while(i<id.length||j<p.n){
      var a=i<id.length?id[i]:Infinity,b=j<p.n?p.id[j]:Infinity;
      if(b<=a){nid[o]=b;nx[o]=p.qx[j];ny[o]=p.qy[j];if(a===b)i++;j++;}
      else{nid[o]=a;nx[o]=qx[i];ny[o]=qy[i];i++;}
      o++;
    }
    id=nid.subarray(0,o);qx=nx.subarray(0,o);qy=ny.subarray(0,o);
  });
  var pos=new Float32Array(2*id.length);
  for(var k=0;k<id.length;k++){pos[2*k]=lx+qx[k]*sx;pos[2*k+1]=ly+qy[k]*sy;}
  return {n:id.length,id:id,pos:pos,start:[0,id.length]};
}
// Place every shard record that some layout part holds. Ids are sorted in a shard and in a part, so
// each pair is one merge pass; a later part overrides an earlier one (a delta replaces the base).
// Returns {n,id,pos,lonlat,obs,up,grp,tax,ids,flags,start} where start[k] is the first row of shard k.
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
    grp:new Uint8Array(total),tax:new Uint16Array(total),obs:new Uint16Array(total),up:new Uint16Array(total),
    ids:new Uint8Array(total),flags:new Uint8Array(total),start:[]};
  var o=0;
  shards.forEach(function(s,k){
    out.start.push(o);
    placed[k].rows.forEach(function(r){
      out.id[o]=s.id[r];out.grp[o]=s.grp[r];out.tax[o]=s.tax[r];
      out.obs[o]=s.obs[r];out.up[o]=s.up[r];out.ids[o]=s.ids[r];out.flags[o]=s.flags[r];
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
return {gunzip:gunzip,decodePart:decodePart,decodeShard:decodeShard,layoutOnly:layoutOnly,join:join,find:find,parseMapMeta:parseMapMeta,fidelity:fidelity};
});
