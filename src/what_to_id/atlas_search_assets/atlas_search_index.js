// Browser reader for the static IVF-PQ atlas index (layout v1, see atlas_index_io.py) over HTTP Range.
// Mirrors atlas_index.search and atlas_neighbors.lookup_neighbors: score = <q,c_l> + sum_j LUT[j][code_j].
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.AtlasSearchIndex=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var KSUB=256;

// IEEE half to float, including subnormals, infinities and NaN.
function f16ToF32(h){
  var s=(h&0x8000)?-1:1,e=(h>>10)&0x1f,f=h&0x3ff;
  if(e===0)return s*f*Math.pow(2,-24);
  if(e===31)return f?NaN:s*Infinity;
  return s*(1+f/1024)*Math.pow(2,e-15);
}
function decodeF16(u16){
  var out=new Float32Array(u16.length);
  for(var i=0;i<u16.length;i++)out[i]=f16ToF32(u16[i]);
  return out;
}
// LUT[j*256+k] = <q_j, pq[j][k]>, pq laid out (m,256,dsub) as in pq.f32.
function buildLut(q,pq,m){
  var dsub=q.length/m,lut=new Float32Array(m*KSUB);
  for(var j=0;j<m;j++)for(var k=0;k<KSUB;k++){
    var base=(j*KSUB+k)*dsub,qo=j*dsub,s=0;
    for(var d=0;d<dsub;d++)s+=q[qo+d]*pq[base+d];
    lut[j*KSUB+k]=s;
  }
  return lut;
}
function coarseScores(q,centroids,nlist){
  var dims=q.length,out=new Float32Array(nlist);
  for(var l=0;l<nlist;l++){var s=0,o=l*dims;for(var d=0;d<dims;d++)s+=q[d]*centroids[o+d];out[l]=s;}
  return out;
}
// Indices of the n highest scores, highest first, ties by lower index (a stable descending sort).
function topIndices(scores,n){
  var idx=[];
  for(var i=0;i<scores.length;i++)idx.push(i);
  idx.sort(function(a,b){return scores[b]-scores[a]||a-b;});
  return idx.slice(0,n);
}
// ADC for one list's rows: base + sum_j lut[j][code]; codes is (rows,m) uint8.
function adc(base,lut,codes,m,out,at){
  var rows=codes.length/m;
  for(var r=0;r<rows;r++){
    var s=base,o=r*m;
    for(var j=0;j<m;j++)s+=lut[j*KSUB+codes[o+j]];
    out[at+r]=s;
  }
}
// Streaming top-k over (score,id) candidates; earlier candidates win ties, like a stable argsort.
function Topk(k){this.k=k;this.ids=[];this.scores=[];}
Topk.prototype.push=function(score,id){
  var n=this.scores.length;
  if(n===this.k&&!(score>this.scores[n-1]))return;
  var i=n<this.k?n:n-1;
  while(i>0&&this.scores[i-1]<score){
    if(i<this.k){this.scores[i]=this.scores[i-1];this.ids[i]=this.ids[i-1];}
    i--;
  }
  this.scores[i]=score;this.ids[i]=id;
};
Topk.prototype.result=function(){
  return this.ids.map(function(id,i){return {id:id,score:this.scores[i]};},this);
};
function topk(scores,ids,k){
  var t=new Topk(k);
  for(var i=0;i<scores.length;i++)t.push(scores[i],ids[i]);
  return t.result();
}
// Merge sorted [start,end) ranges whose gap is at most `gap` bytes.
function coalesce(ranges,gap){
  var s=ranges.filter(function(r){return r[1]>r[0];}).sort(function(a,b){return a[0]-b[0];}),out=[];
  s.forEach(function(r){
    var last=out[out.length-1];
    if(last&&r[0]-last[1]<=(gap||0))last[1]=Math.max(last[1],r[1]);else out.push([r[0],r[1]]);
  });
  return out;
}

function join(base,name){return base.replace(/\/*$/,'/')+name;}

function Index(base,opts){
  this.base=base;this.fetch=opts.fetch;this.gap=opts.gap||0;this.whole=opts.whole||0;
  this.offsets={};this.lists={};this.dir={};this.urls={};this.files={};
}
// Fetch bytes [start,end) of a file; a server that ignores Range (200) is sliced.
// A redirect target (Hugging Face sends large files to a signed CDN URL) is reused for later ranges,
// so only the first read of a file counts against the host's rate limit; an expired one is re-resolved.
Index.prototype.bytes=async function(name,start,end){
  var headers={},url=join(this.base,name),cached=this.urls[name];
  if(start!==undefined)headers.Range='bytes='+start+'-'+(end-1);
  var res=await this.fetch(cached||url,{headers:headers});
  if(!res.ok&&cached){
    delete this.urls[name];cached=null;
    res=await this.fetch(url,{headers:headers});
  }
  if(!res.ok){
    var err=new Error('Could not load '+name+' ('+res.status+')');
    err.stale=res.status===404;  // replaced by a newer index; reload the manifest
    throw err;
  }
  if(!cached&&res.redirected&&res.url)this.urls[name]=res.url;
  var buf=await res.arrayBuffer();
  if(start!==undefined&&res.status===200)buf=buf.slice(start,end);
  return buf;
};
// Whole-file read, cached; used for parts small enough that one request beats many ranges.
Index.prototype.file=function(name){
  if(!this.files[name])this.files[name]=this.bytes(name);
  return this.files[name];
};
Index.prototype.init=async function(){
  var res=await this.fetch(join(this.base,'manifest.json'),{cache:'no-cache'});
  if(!res.ok)throw new Error('Could not load the search index ('+res.status+')');
  var m=this.manifest=JSON.parse(await res.text());
  if(m.version!==1)throw new Error('Unsupported index version '+m.version);
  return this;
};
// Centroids and codebooks, needed by text search but not by neighbour lookups.
Index.prototype.core=function(){
  var self=this,mf=this.manifest;
  if(!this._core)this._core=Promise.all([
    this.bytes('centroids.f16'),this.bytes('pq.f32')
  ]).then(function(r){
    var c=decodeF16(new Uint16Array(r[0]));
    if(c.length!==mf.nlist*mf.dims)throw new Error('centroids.f16 has the wrong size');
    var pq=new Float32Array(r[1]);
    if(pq.length!==mf.m*KSUB*(mf.dims/mf.m))throw new Error('pq.f32 has the wrong size');
    self.centroids=c;self.pq=pq;
  });
  return this._core;
};
Index.prototype.partOffsets=function(part){
  var self=this;
  if(!this.offsets[part.name])this.offsets[part.name]=this.bytes(part.name+'.offsets.u32').then(function(b){
    return new Uint32Array(b);
  });
  return this.offsets[part.name].then(function(o){
    if(o.length!==self.manifest.nlist+1)throw new Error(part.name+'.offsets.u32 has the wrong size');
    return o;
  });
};
// Make sure ids and codes of every wanted list of one part are cached, in as few requests as possible.
Index.prototype.loadLists=async function(part,lists){
  var m=this.manifest.m,off=await this.partOffsets(part),self=this,cache=this.lists;
  var need=lists.filter(function(l){return !cache[part.name+':'+l]&&off[l+1]>off[l];});
  if(!need.length)return;
  var idR=need.map(function(l){return [off[l]*4,off[l+1]*4];});
  var cdR=need.map(function(l){return [off[l]*m,off[l+1]*m];});
  var small=part.count*(4+m)<=this.whole;  // daily delta parts: fetch each file once, whole
  var idC=small?[[0,part.count*4]]:coalesce(idR,this.gap),cdC=small?[[0,part.count*m]]:coalesce(cdR,this.gap);
  var got=await Promise.all(small?[this.file(part.name+'.ids.u32'),this.file(part.name+'.codes.u8')]:
    idC.map(function(r){return self.bytes(part.name+'.ids.u32',r[0],r[1]);})
      .concat(cdC.map(function(r){return self.bytes(part.name+'.codes.u8',r[0],r[1]);})));
  function slice(ranges,bufs,lo,hi){
    for(var i=0;i<ranges.length;i++)if(ranges[i][0]<=lo&&hi<=ranges[i][1])
      return bufs[i].slice(lo-ranges[i][0],hi-ranges[i][0]);
    throw new Error('internal: range not fetched');
  }
  need.forEach(function(l){
    cache[part.name+':'+l]={
      ids:new Uint32Array(slice(idC,got.slice(0,idC.length),off[l]*4,off[l+1]*4)),
      codes:new Uint8Array(slice(cdC,got.slice(idC.length),off[l]*m,off[l+1]*m))
    };
  });
};
// Top-k {id,score} for a unit query: nprobe lists per part, ADC, merged across parts.
Index.prototype.search=async function(q,opts){
  var mf=this.manifest,k=(opts&&opts.k)||10,nprobe=Math.min((opts&&opts.nprobe)||32,mf.nlist);
  if(!(q instanceof Float32Array)||q.length!==mf.dims)throw new Error('Query must be a Float32Array of '+mf.dims+' values.');
  await this.core();
  var coarse=coarseScores(q,this.centroids,mf.nlist),probe=topIndices(coarse,nprobe);
  var lut=buildLut(q,this.pq,mf.m),top=new Topk(k),self=this;
  var parts=mf.parts.filter(function(p){return p.count>0;});
  await Promise.all(parts.map(function(p){return self.loadLists(p,probe);}));
  parts.forEach(function(p){
    probe.forEach(function(l){
      var e=self.lists[p.name+':'+l];
      if(!e)return;
      var s=new Float32Array(e.ids.length);
      adc(coarse[l],lut,e.codes,mf.m,s,0);
      for(var i=0;i<s.length;i++)top.push(s[i],e.ids[i]);
    });
  });
  return top.result();
};
Index.prototype.neighborSets=function(name){
  var sets=(this.manifest.neighbors||[]).filter(function(e){return !name||e.name===name;});
  if(!sets.length)throw new Error('This index has no precomputed neighbours.');
  return sets;
};
// Precomputed neighbours as [{id,score}], or null when the observation is not in the index.
// Without a name every set is tried newest first, so a daily delta set overrides the base set.
Index.prototype.neighbors=async function(obsId,name){
  var sets=this.neighborSets(name);
  for(var i=sets.length-1;i>=0;i--){
    var found=await this.neighborsIn(sets[i],obsId);
    if(found)return found;
  }
  return null;
};
Index.prototype.neighborsIn=async function(set,obsId){
  var k=set.k||12,rec=4+6*k;
  if(!this.dir[set.name])this.dir[set.name]=this.bytes(set.name+'.dir.u32').then(function(b){
    return new Uint32Array(b);
  });
  var dir=await this.dir[set.name],lo=0,hi=dir.length-1,b=-1;
  while(lo<=hi){var mid=(lo+hi)>>1;if(dir[mid]<=obsId){b=mid;lo=mid+1;}else hi=mid-1;}
  if(b<0)return null;
  var first=b*set.block,last=Math.min(first+set.block,set.count);
  var buf=await this.bytes(set.name+'.bin',first*rec,last*rec),dv=new DataView(buf);
  var n=last-first;lo=0;hi=n-1;
  while(lo<=hi){
    var mi=(lo+hi)>>1,id=dv.getUint32(mi*rec,true);
    if(id===obsId){
      var out=[];
      for(var i=0;i<k;i++)out.push({
        id:dv.getUint32(mi*rec+4+4*i,true),
        score:f16ToF32(dv.getUint16(mi*rec+4+4*k+2*i,true))
      });
      return out;
    }
    if(id<obsId)lo=mi+1;else hi=mi-1;
  }
  return null;
};

// open(baseUrl, {fetch, gap, whole}) -> Promise<Index>; fetch defaults to the global one, parts of at most
// `whole` id+code bytes are read in full.
function open(base,opts){
  opts=opts||{};
  var f=opts.fetch||(typeof fetch!=='undefined'?fetch.bind(globalThis):null);
  if(!f)throw new Error('No fetch available.');
  return new Index(base,{fetch:f,gap:opts.gap,whole:opts.whole}).init();
}
return {open:open,f16ToF32:f16ToF32,decodeF16:decodeF16,buildLut:buildLut,coarseScores:coarseScores,
  topIndices:topIndices,adc:adc,topk:topk,Topk:Topk,coalesce:coalesce};
});
