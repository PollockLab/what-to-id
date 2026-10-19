// Browser reader for the static IVF-OPQ-PQ atlas index (layout v2, see atlas_index_io.py) over HTTP Range.
// Mirrors atlas_index.search and atlas_neighbors.lookup_neighbors. Stage 1: score = <q,c_l> + sum_j LUT[j][code_j]
// with the LUT built from the OPQ-rotated query; stage 2 re-scores the shortlist with the refine codes.
(function(root,factory){
  var api=factory();
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.AtlasSearchIndex=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
var KSUB=256,REFINE_CONCURRENCY=24;

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
// A q for a row-major (dims x dims) rotation A: the query in the space the codebooks live in.
function rotate(A,q){
  var d=q.length,out=new Float32Array(d);
  for(var i=0;i<d;i++){var s=0,o=i*d;for(var j=0;j<d;j++)s+=A[o+j]*q[j];out[i]=s;}
  return out;
}
// Refined score of one row: s1 + <qr,lo> + sum_d level[d]*qr[d]*step[d]. `v` is qr*step and `c0` is <qr,lo>;
// levels are `bits` wide, little-endian, dimension d at bit d*bits of the row starting at buf[at].
function refineScore(s1,c0,v,bits,buf,at){
  var mask=(1<<bits)-1,s=c0;
  for(var d=0;d<v.length;d++){
    var p=d*bits,b=at+(p>>3);
    s+=(((buf[b]|(buf[b+1]<<8))>>(p&7))&mask)*v[d];
  }
  return s1+s;
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
// An optional tag travels with each candidate (the search stores where its refine row lives).
function Topk(k){this.k=k;this.ids=[];this.scores=[];this.tags=[];}
Topk.prototype.push=function(score,id,tag){
  var n=this.scores.length;
  if(n===this.k&&!(score>this.scores[n-1]))return;
  var i=n<this.k?n:n-1;
  while(i>0&&this.scores[i-1]<score){
    if(i<this.k){this.scores[i]=this.scores[i-1];this.ids[i]=this.ids[i-1];this.tags[i]=this.tags[i-1];}
    i--;
  }
  this.scores[i]=score;this.ids[i]=id;this.tags[i]=tag;
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

// Run the async task functions with at most `limit` in flight; results keep the task order.
async function pool(tasks,limit){
  var res=new Array(tasks.length),next=0;
  async function worker(){
    while(next<tasks.length){var i=next++;res[i]=await tasks[i]();}
  }
  var workers=[];
  for(var w=0;w<Math.min(limit,tasks.length);w++)workers.push(worker());
  await Promise.all(workers);
  return res;
}

function join(base,name){return base.replace(/\/*$/,'/')+name;}

function Index(base,opts){
  this.base=base;this.fetch=opts.fetch;this.gap=opts.gap||0;this.whole=opts.whole||0;this.concurrency=opts.concurrency||REFINE_CONCURRENCY;
  this.offsets={};this.lists={};this.dir={};this.urls={};this.files={};this.resolving={};this.first={};
}
// Fetch bytes [start,end) of a file; a server that ignores Range (200) is sliced.
// A redirect target (Hugging Face sends large files to a signed CDN URL) is reused for later ranges,
// so only the first read of a file counts against the host's rate limit (reads issued while it is in
// flight wait for it); an expired one is re-resolved.
// Range reads skip the HTTP cache: Chrome's cache lock queues parallel requests to one URL (a search
// took 10 to 18 s instead of 1 to 2 s against Hugging Face).
Index.prototype.bytes=async function(name,start,end){
  if(this.first[name])await this.first[name];
  var init={headers:{}},url=join(this.base,name),cached=this.urls[name],res,done;
  if(start!==undefined){init.headers.Range='bytes='+start+'-'+(end-1);init.cache='no-store';}
  if(!cached&&!this.first[name])this.first[name]=new Promise(function(r){done=r;});
  try{
    res=await this.fetch(cached||url,init);
    if(!cached&&res.ok&&res.redirected&&res.url)this.urls[name]=res.url;
  }finally{if(done)done();}
  if(!res.ok&&cached){
    if(this.urls[name]===cached)delete this.urls[name];
    if(!this.urls[name])await this.resolve(name);
    cached=this.urls[name]||null;
    res=await this.fetch(cached||url,init);
  }
  if(!res.ok){
    var err=new Error('Could not load '+name+' ('+res.status+')');
    err.stale=res.status===404;  // replaced by a newer index; reload the manifest
    throw err;
  }
  var buf=await res.arrayBuffer();
  if(start!==undefined&&res.status===200)buf=buf.slice(start,end);
  return buf;
};
// Re-resolve an expired CDN URL once for all reads of the file that failed at the same time.
Index.prototype.resolve=function(name){
  var self=this;
  if(!this.resolving[name])this.resolving[name]=this.fetch(join(this.base,name),{headers:{Range:'bytes=0-0'},cache:'no-store'})
    .then(function(res){if(res.ok&&res.redirected&&res.url)self.urls[name]=res.url;})
    .catch(function(){})
    .then(function(){delete self.resolving[name];});
  return this.resolving[name];
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
  if(m.version!==2)throw new Error('Unsupported index version '+m.version);
  return this;
};
// Centroids, rotation, codebooks and refine grid, needed by text search but not by neighbour lookups.
Index.prototype.core=function(){
  var self=this,mf=this.manifest;
  if(!this._core)this._core=Promise.all([
    this.bytes('centroids.f16'),this.bytes('pq.f32'),this.bytes('opq.f16'),this.bytes(mf.refine.params)
  ]).then(function(r){
    var c=decodeF16(new Uint16Array(r[0]));
    if(c.length!==mf.nlist*mf.dims)throw new Error('centroids.f16 has the wrong size');
    var pq=new Float32Array(r[1]);
    if(pq.length!==mf.m*KSUB*(mf.dims/mf.m))throw new Error('pq.f32 has the wrong size');
    var rot=decodeF16(new Uint16Array(r[2]));
    if(rot.length!==mf.dims*mf.dims)throw new Error('opq.f16 has the wrong size');
    var sq=new Float32Array(r[3]);
    if(sq.length!==2*mf.dims)throw new Error(mf.refine.params+' has the wrong size');
    self.centroids=c;self.pq=pq;self.rot=rot;self.sq=sq;
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
// Top-k {id,score} for a unit query. Stage 1: nprobe lists per part, ADC on the rotated query, merged
// across parts into a shortlist. Stage 2: the shortlist's refine codes are range-read and the rows
// re-ranked. opts: k, nprobe, shortlist (0 skips stage 2), onStage1(hits) called with the stage-1 top k.
Index.prototype.search=async function(q,opts){
  opts=opts||{};
  var mf=this.manifest,dfl=mf.defaults||{},k=opts.k||10,nprobe=Math.min(opts.nprobe||dfl.nprobe||64,mf.nlist);
  var shortlist=opts.shortlist===undefined?dfl.shortlist||500:opts.shortlist;
  if(!(q instanceof Float32Array)||q.length!==mf.dims)throw new Error('Query must be a Float32Array of '+mf.dims+' values.');
  await this.core();
  var coarse=coarseScores(q,this.centroids,mf.nlist),probe=topIndices(coarse,nprobe);
  var qr=rotate(this.rot,q),lut=buildLut(qr,this.pq,mf.m),self=this;
  var top=new Topk(shortlist>0?Math.max(shortlist,k):k);
  var parts=mf.parts.filter(function(p){return p.count>0;});
  await Promise.all(parts.map(function(p){return self.loadLists(p,probe);}));
  var offs=await Promise.all(parts.map(function(p){return self.partOffsets(p);}));
  parts.forEach(function(p,pi){
    probe.forEach(function(l){
      var e=self.lists[p.name+':'+l];
      if(!e)return;
      var s=new Float32Array(e.ids.length);
      adc(coarse[l],lut,e.codes,mf.m,s,0);
      for(var i=0;i<s.length;i++)top.push(s[i],e.ids[i],pi*4294967296+offs[pi][l]+i);
    });
  });
  if(!(shortlist>0))return top.result();
  if(opts.onStage1)opts.onStage1(top.result().slice(0,k));
  var refined=await this.refine(top,qr,parts);
  return topIndices(refined,k).map(function(i){return {id:top.ids[i],score:refined[i]};});
};
// Refined scores for a stage-1 shortlist (a Topk tagged with part index * 2^32 + row). Rows of one part
// are read as Range requests with adjacent rows merged, `concurrency` at a time.
Index.prototype.refine=async function(top,qr,parts){
  var mf=this.manifest,bits=mf.refine.bits,rb=mf.dims*bits/8,lo=this.sq.subarray(0,mf.dims),step=this.sq.subarray(mf.dims);
  var v=new Float32Array(mf.dims),c0=0,self=this,byPart=parts.map(function(){return [];});
  for(var d=0;d<mf.dims;d++){v[d]=qr[d]*step[d];c0+=qr[d]*lo[d];}
  top.tags.forEach(function(tag,i){
    var pi=Math.floor(tag/4294967296);
    byPart[pi].push({i:i,row:tag-pi*4294967296});
  });
  var pieces=parts.map(function(){return [];}),files=[];
  parts.forEach(function(p,pi){
    var rows=byPart[pi].sort(function(a,b){return a.row-b.row;});
    if(!rows.length)return;
    var name=p.name+'.refine.u8';
    if(p.count*rb<=self.whole){  // daily delta parts: one whole-file read
      files.push({tasks:[function(){return self.file(name).then(function(buf){pieces[pi].push({start:0,buf:new Uint8Array(buf)});});}]});
      return;
    }
    var ranges=coalesce(rows.map(function(r){return [r.row*rb,(r.row+1)*rb];}),0);
    files.push({tasks:ranges.map(function(r){
      return function(){return self.bytes(name,r[0],r[1]).then(function(buf){pieces[pi].push({start:r[0],buf:new Uint8Array(buf)});});};
    })});
  });
  await pool([].concat.apply([],files.map(function(f){return f.tasks;})),this.concurrency);
  var out=new Float32Array(top.scores.length);
  byPart.forEach(function(rows,pi){
    var ps=pieces[pi].sort(function(a,b){return a.start-b.start;}),j=0;
    rows.forEach(function(r){  // rows and pieces are both ascending
      var at=r.row*rb;
      while(at>=ps[j].start+ps[j].buf.length)j++;
      out[r.i]=refineScore(top.scores[r.i],c0,v,bits,ps[j].buf,at-ps[j].start);
    });
  });
  return out;
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

// Lookup key for a taxon name: case-insensitive, whitespace collapsed, a leading "a photo of " dropped.
function normName(text){return String(text).toLowerCase().trim().replace(/\s+/g,' ').replace(/^a photo of /,'');}
async function gunzipText(buf){
  var s=new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Response(s).text();
}
// name -> row for scientific names, then for common names that are unambiguous (-1 marks a shared one).
function nameRows(tsv){
  var sci=new Map(),com=new Map(),lines=tsv.split('\n');
  if(lines[lines.length-1]==='')lines.pop();
  lines.forEach(function(line,row){
    var p=line.split('\t'),k=normName(p[0]);
    if(k&&!sci.has(k))sci.set(k,row);
    var c=normName(p[1]||'');
    if(c)com.set(c,com.has(c)&&com.get(c)!==row?-1:row);
  });
  com.forEach(function(row,k){if(!sci.has(k)&&row>=0)sci.set(k,row);});
  return sci;
}
// Unit Float32Array for a query that names a taxon in the precomputed table, else null.
Index.prototype.taxonVector=async function(text){
  var t=this.manifest.taxa;
  if(!t)return null;
  if(!this._taxa)this._taxa=this.bytes(t.names).then(gunzipText).then(nameRows);
  var self=this;this._taxa.catch(function(){self._taxa=null;});
  var row=(await this._taxa).get(normName(text));
  if(row===undefined)return null;
  var size=t.dims*2,buf=await this.bytes(t.vectors,row*size,(row+1)*size);
  var q=decodeF16(new Uint16Array(buf)),n=0;
  for(var i=0;i<q.length;i++)n+=q[i]*q[i];
  n=Math.sqrt(n);
  for(i=0;i<q.length;i++)q[i]/=n;
  return q;
};

// open(baseUrl, {fetch, gap, whole, concurrency}) -> Promise<Index>; fetch defaults to the global one, parts of
// at most `whole` id+code (or refine) bytes are read in full, refine reads run `concurrency` (24) at a time.
function open(base,opts){
  opts=opts||{};
  var f=opts.fetch||(typeof fetch!=='undefined'?fetch.bind(globalThis):null);
  if(!f)throw new Error('No fetch available.');
  return new Index(base,{fetch:f,gap:opts.gap,whole:opts.whole,concurrency:opts.concurrency}).init();
}
return {open:open,f16ToF32:f16ToF32,decodeF16:decodeF16,buildLut:buildLut,coarseScores:coarseScores,rotate:rotate,refineScore:refineScore,
  normName:normName,nameRows:nameRows,topIndices:topIndices,adc:adc,topk:topk,Topk:Topk,coalesce:coalesce};
});
