// Reading the shards: gunzip, append a shard to the records, and find a record by id.
var MapShard=(function(){
'use strict';
function cat(a,b){var c=new a.constructor(a.length+b.length);c.set(a);c.set(b,a.length);return c;}
function unzip(buf){
  var u=new Uint8Array(buf,0,Math.min(2,buf.byteLength));
  if(u[0]!==0x1f||u[1]!==0x8b)return Promise.resolve(buf);
  return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip')))
    .arrayBuffer();
}
// A shard stores each wider column byte by byte (every value's low byte, then the next), and ids
// as steps from the previous id.
function append(P,buf,n,b){
  if(buf.byteLength!==17*n)throw new Error('unexpected size');
  var sx=(b[2]-b[0])/65535,sy=(b[3]-b[1])/65535,o=0,u=new Uint8Array(buf);
  function col(T,w){if(w===1){o+=n;return u.slice(o-n,o);}
    var a=new T(n),v=new Uint8Array(a.buffer);
    for(var j=0;j<w;j++,o+=n)for(var k=0;k<n;k++)v[k*w+j]=u[o+k];return a;}
  var id=col(Uint32Array,4),qx=col(Uint16Array,2),qy=col(Uint16Array,2),obs=col(Uint16Array,2),
    up=col(Uint16Array,2),tax=col(Uint16Array,2),grp=col(Uint8Array,1),ids=col(Uint8Array,1),
    fl=col(Uint8Array,1),pos=new Float32Array(2*n);
  for(var s=0,i=0;i<n;i++)id[i]=s=(s+id[i])>>>0;
  for(i=0;i<n;i++){pos[2*i]=b[0]+qx[i]*sx;pos[2*i+1]=b[1]+qy[i]*sy;}
  return {n:P.n+n,id:cat(P.id,id),pos:cat(P.pos,pos),obs:cat(P.obs,obs),up:cat(P.up,up),
    tax:cat(P.tax,tax),grp:cat(P.grp,grp),ids:cat(P.ids,ids),fl:cat(P.fl,fl),start:P.start.concat(P.n+n)};
}
// Row of an observation id, or -1: ids are sorted inside each shard, not across shards.
function rowOf(P,id){
  for(var k=0;k+1<P.start.length;k++){
    var lo=P.start[k],hi=P.start[k+1]-1;
    while(lo<=hi){var m=(lo+hi)>>1,v=P.id[m];if(v===id)return m;if(v<id)lo=m+1;else hi=m-1;}
  }
  return -1;
}
return {unzip:unzip,append:append,rowOf:rowOf};
})();
