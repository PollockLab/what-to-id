// Text encoder for free-text search: CLIP BPE tokenizer + int8 ONNX text tower on onnxruntime-web (WASM).
// Interface the page expects (swappable, e.g. a test fake on window.AtlasEncoderOverride):
//   encoder.encode(text) -> Float32Array(1024) | Promise<Float32Array(1024)>, unit length
// Manifest: text_encoder:{onnx, vocab, input_name, output_name, bytes}, paths relative to the data URL.
(function(root,factory){
  var api=factory(root);
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.AtlasEncoder=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(root){
'use strict';
var ORT='https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/';
// SRI of ort.min.js 1.20.1, matches the npm tarball; change it with the version.
var ORT_SRI='sha384-RPL/K8tc0JVaNWsunkEmCzLeieefvFX2UCRLKLmLVChCI6P+CTKhzqF7VIeCc3Zp';
var CACHE='what-to-id-atlas-model-v1';

function join(base,name){return base.replace(/\/*$/,'/')+name;}
function megabytes(spec){return Math.round(((spec&&spec.bytes)||0)/1e6);}  // decimal MB, as browsers and phones report downloads

function loadScript(src,integrity){
  return new Promise(function(resolve,reject){
    var s=document.createElement('script');
    s.src=src;s.integrity=integrity;s.crossOrigin='anonymous';s.onload=resolve;
    s.onerror=function(){reject(new Error('Could not load onnxruntime-web from the CDN.'));};
    document.head.appendChild(s);
  });
}
async function loadOrt(){
  if(!root.ort)await loadScript(ORT+'ort.min.js',ORT_SRI);
  root.ort.env.wasm.wasmPaths=ORT;
  return root.ort;
}
async function cacheStore(){
  try{return typeof caches!=='undefined'?await caches.open(CACHE):null;}catch(e){return null;}
}
// True when the model is already stored locally, so no large download is about to happen.
async function isCached(url){
  var c=await cacheStore();
  return !!(c&&await c.match(url));
}
// Model bytes from Cache Storage or the network, reporting progress as a 0..1 fraction.
async function modelBytes(url,total,onProgress,fetchFn){
  var c=await cacheStore(),hit=c&&await c.match(url);
  if(hit)return new Uint8Array(await hit.arrayBuffer());
  var res=await fetchFn(url);
  if(!res.ok)throw new Error('Could not download the search model ('+res.status+').');
  total=+res.headers.get('content-length')||total;
  var buf=new Uint8Array(total||0),n=0,reader=res.body.getReader();
  for(;;){
    var r=await reader.read();
    if(r.done)break;
    if(n+r.value.length>buf.length){var g=new Uint8Array(Math.max(buf.length*2,n+r.value.length));g.set(buf.subarray(0,n));buf=g;}
    buf.set(r.value,n);n+=r.value.length;
    if(onProgress&&total)onProgress(Math.min(1,n/total));
  }
  buf=buf.subarray(0,n);
  if(c)try{await c.put(url,new Response(buf));}catch(e){/* quota: fine, fetched once more next visit */}
  return buf;
}
function normalize(v){
  var s=0,i;
  for(i=0;i<v.length;i++)s+=v[i]*v[i];
  s=Math.sqrt(s);
  if(!(s>0))throw new Error('The text encoder returned a zero vector.');
  var out=new Float32Array(v.length);
  for(i=0;i<v.length;i++)out[i]=v[i]/s;
  return out;
}
// Build an encoder from an onnx session and tokenizer; ort and tokenizer are injectable for tests.
function make(ort,session,tokenizer,spec){
  var inName=(spec&&spec.input_name)||'tokens',outName=(spec&&spec.output_name)||'embedding';
  return {
    encode:async function(text){
      var ids=tokenizer.tokenize(text),tokens=new BigInt64Array(ids.length);
      for(var i=0;i<ids.length;i++)tokens[i]=BigInt(ids[i]);
      var feeds={};feeds[inName]=new ort.Tensor('int64',tokens,[1,ids.length]);
      var out=await session.run(feeds);
      return normalize(Float32Array.from(out[outName].data));
    }
  };
}
async function load(manifest,base,opts){
  opts=opts||{};
  var spec=manifest.text_encoder;
  if(!spec)throw new Error('This index has no text search model yet. Use "More like this" on a photo instead.');
  var fetchFn=opts.fetch||fetch.bind(globalThis),Tok=opts.ClipTokenizer||root.ClipTokenizer;
  if(!Tok)throw new Error('The CLIP tokenizer is missing from this page.');
  var vocab=await (await fetchFn(join(base,spec.vocab))).text();
  var tokenizer=Tok.create(vocab);
  var ort=opts.ort||await loadOrt();
  var bytes=await modelBytes(join(base,spec.onnx),spec.bytes,opts.onProgress,fetchFn);
  var session=await ort.InferenceSession.create(bytes,{executionProviders:['wasm']});
  return make(ort,session,tokenizer,spec);
}
return {ORT:ORT,megabytes:megabytes,isCached:isCached,load:load,make:make,normalize:normalize};
});
