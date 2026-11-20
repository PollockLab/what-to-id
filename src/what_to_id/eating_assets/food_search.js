// Live photo search for the Food web question: "a photo of a {predator} eating a {prey}" against the serverless atlas index
// (atlas_search_*.js: BioCLIP text tower in onnxruntime-web, IVF-PQ index over HTTP Range, photos from iNaturalist at view time).
// Inlined only when the page is built with a data URL. Nothing is downloaded until the reader clicks. FoodSearch.ask({q, x, y}).
var FoodSearch=(function(){
'use strict';
var K=60,SHOW=12,OBS='https://www.inaturalist.org/observations/';
var E=EatingCore,Meta=AtlasSearchMeta,Enc=AtlasEncoder,CFG=EATING_CONFIG.search||{},DATA=new URL(CFG.dataUrl||'./',location.href).href.replace(/\/*$/,'/');
var S={index:null,enc:null,cache:new Map(),run:0,text:''},box=document.getElementById('fsearch'),btn,msg,out;
function query(h){
  if(!(h.q==='eats'||h.q==='does')||!h.x)return '';
  return 'a photo of a '+E.label(h.x)+' eating'+(h.q==='does'&&h.y?' a '+E.label(h.y):'');
}
function say(t,err){msg.textContent=t;msg.className='muted'+(err?' err':'');}
async function encoder(){
  if(window.AtlasEncoderOverride)return window.AtlasEncoderOverride;
  if(S.enc)return S.enc;
  var mf=S.index.manifest;
  if(!mf.text_encoder)throw new Error('This index has no text search model yet.');
  var mb=Enc.megabytes(mf.text_encoder),fresh=!await Enc.isCached(new URL(mf.text_encoder.onnx,DATA).href);
  if(fresh)say('Downloading the search model, about '+mb+' MB, once. It is kept in this browser.');
  S.enc=await Enc.load(mf,DATA,{onProgress:function(f){if(fresh)say(f<1?'Downloading the search model, about '+mb+' MB, once: '+Math.round(f*100)+'%.':'Starting the search model...');}});
  return S.enc;
}
// each subject on its own, then min-fused (the photo must show both animals), as the photo-search page does
async function hits(text){
  var parts=Meta.subjects(text),texts=parts.length>1?[text].concat(parts):[text],enc=await encoder(),opts={k:parts.length>1?K*3:K};
  say('Searching photos...');
  var lists=await Promise.all(texts.map(async function(t,i){
    var v=(i&&await S.index.taxonVector(t))||await enc.encode(i?'a photo of a '+t.replace(/^an? /i,''):t);
    return S.index.search(v,opts);}));
  return parts.length>1?Meta.fuse(lists,K):lists[0];
}
async function search(){
  var run=++S.run,text=S.text;
  btn.disabled=true;out.replaceChildren();say('Opening the photo index...');
  try{
    if(!S.index)S.index=await AtlasSearchIndex.open(DATA,{whole:4<<20});
    var h=await hits(text);
    if(run!==S.run)return;
    say('Loading photos from iNaturalist...');
    await Meta.fetchObservations(h.map(function(x){return x.id;}),function(u){return fetch(u);},S.cache);
    if(run!==S.run)return;
    var cards=Meta.build(h,S.cache).cards.slice(0,SHOW);
    cards.forEach(function(c){
      var a=E.el('a'),name=c.common||c.name||'Unidentified',li=E.el('li');
      a.href=OBS+c.id;a.target='_blank';a.rel='noopener';a.title=name+' · '+(c.date||'Date unknown');a.setAttribute('aria-label','Open observation '+c.id+' on iNaturalist: '+name);
      if(c.photo){var i=E.el('img');i.src=c.photo;i.alt=name;i.loading='lazy';a.append(i);}else a.append(name);
      li.append(a);out.append(li);});
    say(cards.length?E.pl(cards.length,'photo')+' that look like "'+text+'". They match by appearance and are not confirmed feeding records.':'No matching photos.');
  }catch(e){
    if(run!==S.run)return;
    S.index=null;say('Photo search failed: '+e.message,true);  // a stale manifest or a dropped download: the next click starts over
  }finally{if(run===S.run)btn.disabled=false;}
}
function ask(h){
  S.run++;S.text=query(h);box.hidden=!S.text;btn.disabled=false;out.replaceChildren();
  say(S.text?'Looks for "'+S.text+'" in photos. The first search downloads a search model.':'');
}
if(box&&CFG.dataUrl){
  btn=E.el('button','btn quiet','Search photos');btn.type='button';btn.onclick=search;
  msg=E.el('p','muted');msg.setAttribute('aria-live','polite');out=E.el('ul','thumbs');
  box.append(btn,msg,out);
}
return {ask:function(h){if(btn)ask(h);}};
})();
