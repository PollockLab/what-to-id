// Photo search page: query -> index search or precomputed neighbours -> live iNaturalist cards -> Identify.
(function(){
'use strict';
var CFG=ATLAS_SEARCH_CONFIG,Meta=AtlasSearchMeta,Enc=AtlasEncoder;
var K=200,WHOLE=4<<20;  // parts up to 4 MB load whole: one request, not 32 ranges
var qs=new URLSearchParams(location.search);
var DATA=new URL(CFG.dataUrl,location.href).href.replace(/\/*$/,'/');
var S={index:null,encoder:null,cache:new Map(),hits:[],parts:[],state:null,run:0,include:[],exclude:[],qvec:null,picks:new Set(),picked:0};
var EXAMPLES=['a nudibranch','a hummingbird feeding at a flower','colourful mushrooms on moss','a jellyfish'];

function $(id){return document.getElementById(id);}
function el(tag,attrs,kids){
  var e=document.createElement(tag);
  Object.keys(attrs||{}).forEach(function(k){if(attrs[k]!==null&&attrs[k]!==undefined)e.setAttribute(k,attrs[k]);});
  (kids||[]).forEach(function(c){e.appendChild(typeof c==='string'?document.createTextNode(c):c);});
  return e;
}
function status(text){$('status').textContent=text;}
function getIndex(){
  if(!S.index)S.index=AtlasSearchIndex.open(DATA,{whole:WHOLE});
  return S.index;
}
// CLIP text towers match captions best, so a bare query gets the caption template the search test used.
function caption(text){return /^(an? )?(photo|picture|image)\b/i.test(text)?text:'a photo of '+text;}
function obsUrl(id){return 'https://www.inaturalist.org/observations/'+id;}
function taxonId(t){return t.id;}
function same(a,b){return a&&b&&a.kind===b.kind&&(a.kind==='id'?a.id===b.id:a.text===b.text);}

// The encoder is a test fake, an already loaded model, or the real ONNX model after the user agrees to the download.
async function encoderFor(state,confirmed){
  if(window.AtlasEncoderOverride)return window.AtlasEncoderOverride;
  if(S.encoder)return S.encoder;
  var mf=(await getIndex()).manifest,spec=mf.text_encoder;
  if(!spec)throw new Error('This index has no text search model yet. Use "More like this" on a photo instead.');
  var mb=Enc.megabytes(spec);
  if(!confirmed&&!await Enc.isCached(new URL(spec.onnx,DATA).href)){
    S.pending=state;
    $('gatetext').textContent='Text search needs a search model. Downloading search model, about '+mb+
      ' MB, once, best on Wi-Fi. It is stored in this browser afterwards. Searching by observation link needs no download.';
    $('gate').hidden=false;$('gobtn').focus();
    $('results').hidden=true;  // the last query's cards would sit under a prompt about the new one
    status('');
    return null;
  }
  $('gate').hidden=true;
  var bar=$('progress');bar.hidden=false;bar.value=0;
  status('Downloading search model, about '+mb+' MB, once...');
  try{
    S.encoder=await Enc.load(mf,DATA,{onProgress:function(f){bar.value=f;}});
  }finally{bar.hidden=true;}
  return S.encoder;
}

// The daily update renames files it replaces, so a 404 means the manifest is stale: reload it once.
async function hitsFor(state,confirmed){
  try{return await hitsFrom(state,confirmed);}
  catch(e){
    if(!e.stale)throw e;
    S.index=null;
    return hitsFrom(state,confirmed);
  }
}
async function hitsFrom(state,confirmed){
  var idx=await getIndex();
  if(state.kind==='id'){
    var nb=await idx.neighbors(state.id);
    if(!nb)return {error:'Observation '+state.id+' is not in the index. It may be new, or no longer need an ID.'};
    return {hits:nb};
  }
  var opts={k:K,nprobe:+qs.get('nprobe')||undefined};  // nprobe and shortlist default to the manifest's
  var q=await idx.taxonVector(state.text);  // a taxon name has a precomputed vector: no model, no download
  if(q){S.qvec=q;return {hits:await idx.search(q,opts)};}
  var enc=await encoderFor(state,confirmed);
  if(!enc)return {gated:true};
  status('Searching...');
  var parts=Meta.subjects(state.text);
  if(parts.length===1){S.qvec=await enc.encode(caption(state.text));return {hits:await idx.search(S.qvec,opts)};}
  // every subject (and the whole sentence) is searched on its own, then min-fused: deeper lists so
  // the fused top K has candidates scored in all of them
  var texts=[state.text].concat(parts),deep={k:K*3,nprobe:opts.nprobe};
  var lists=await Promise.all(texts.map(async function(t,i){
    var v=(await idx.taxonVector(t))||(await enc.encode(caption(t)));
    if(i===0)S.qvec=v;
    return idx.search(v,deep);
  }));
  return {hits:Meta.fuse(lists,K),parts:parts};
}

// The taxon filter lives in the hash with the query, so a shared link carries it; chips mirror it.
function setFilters(state){S.include=state.include||[];S.exclude=state.exclude||[];chips();}
async function start(state,confirmed){
  var run=++S.run;
  S.state=state;S.parts=[];S.qvec=null;S.picks.clear();S.picked=0;$('gate').hidden=true;
  if(!state){render();return;}
  setFilters(state);
  $('q').value=state.kind==='id'?String(state.id):state.text;
  status('Searching...');
  try{
    var r=await hitsFor(state,confirmed);
    if(run!==S.run||r.gated)return;
    if(r.error){S.hits=[];render(r.error);return;}
    status('Loading photo details from iNaturalist...');
    S.hits=r.hits;S.parts=r.parts||[];
    await Meta.fetchObservations(S.hits.map(function(h){return h.id;}),function(u){return fetch(u);},S.cache);
    if(run!==S.run)return;
    render();
    $('rh').focus();
  }catch(e){
    if(run!==S.run)return;
    S.hits=[];render();
    status('Something went wrong: '+e.message);
  }
}

// Rocchio relevance feedback: the query moves toward the mean of the picked photos' vectors
// (reconstructed from their index codes) and the search runs again. Not in the link.
async function refine(){
  var run=++S.run,idx=await getIndex(),ids=Array.from(S.picks);
  status('Searching again with '+ids.length+' picked photo'+(ids.length>1?'s':'')+'...');
  try{
    var tags=S.hits.filter(function(h){return S.picks.has(h.id);}).map(function(h){return h.tag;});
    var vs=await Promise.all(tags.map(function(t){return idx.vector(t);})),q=new Float32Array(S.qvec.length),n=0;
    for(var i=0;i<q.length;i++){var s=S.qvec[i];for(var j=0;j<vs.length;j++)s+=vs[j][i]/vs.length;q[i]=s;n+=s*s;}
    n=Math.sqrt(n);
    for(i=0;i<q.length;i++)q[i]/=n;
    var hits=await idx.search(q,{k:K,nprobe:+qs.get('nprobe')||undefined});
    if(run!==S.run)return;
    S.qvec=q;S.hits=hits;S.parts=[];S.picked=ids.length;S.picks.clear();
    status('Loading photo details from iNaturalist...');
    await Meta.fetchObservations(hits.map(function(h){return h.id;}),function(u){return fetch(u);},S.cache);
    if(run!==S.run)return;
    render();
    $('rh').focus();
  }catch(e){
    if(run!==S.run)return;
    status('Something went wrong: '+e.message);
  }
}

function render(message){
  var res=Meta.build(S.hits,S.cache,{include:S.include.map(taxonId),exclude:S.exclude.map(taxonId)}),grid=$('grid');
  grid.textContent='';
  $('results').hidden=!S.state;
  if(!S.state)return;
  var st=S.state;
  var head=st.kind==='id'?'Photos like observation '+st.id:'Photos matching "'+st.text+'"';
  if(S.picked)head+=' and '+S.picked+' picked photo'+(S.picked>1?'s':'');
  $('rh').textContent=head+' ('+res.cards.length+')';
  var bits=[];
  if(res.notNeedsId)bits.push(res.notNeedsId+' no longer need an ID');
  if(res.missing)bits.push(res.missing+' no longer returned by iNaturalist');
  if(res.filtered)bits.push(res.filtered+' outside the taxon filter');
  $('dropped').textContent=bits.length?'Left out: '+bits.join(', ')+'.':'';
  var parts=(st.kind==='text'&&S.parts)||[];
  $('how').textContent=parts.length>1?'Each photo matches all of: '+parts.join(', ')+'. The search sees what is in the photo, not who does what to whom. Similarity is the weaker subject\'s.':'';
  var none=res.filtered&&!res.cards.length?'None of the best '+S.hits.length+' matches are inside your taxon filter. Name the taxon in your words instead.':'No matching photos.';
  status(message||(res.cards.length?'':none));
  res.cards.forEach(function(c,i){grid.appendChild(cardEl(c,i));});
  var actions=$('actions');actions.textContent='';
  if(!res.cards.length)return;
  if(S.qvec){
    var n=S.picks.size,again=el('button',{type:'button','class':'btn',id:'again',disabled:n?null:''},
      [n?'Search again with '+n+' picked photo'+(n>1?'s':''):'Tick photos that match, then search again']);
    again.addEventListener('click',refine);
    actions.appendChild(again);
  }
  var batches=IdentifyLinks.prepare(res.cards.map(function(c){return c.id;})).batches;
  batches.forEach(function(b){
    var label=batches.length>1?'Identify '+b.n+' (IDs '+b.lo+' to '+b.hi+')':'Open in iNaturalist Identify ('+b.n+')';
    actions.appendChild(el('a',{'class':'btn primary',href:b.url,target:'_blank',rel:'noopener'},[label]));
  });
}

function cardEl(c,i){
  var title=c.common||c.name||'Unidentified',alt=title+(c.common&&c.name?' ('+c.name+')':'');
  var img=c.photo?el('img',{src:c.photo,alt:alt,loading:'lazy'}):el('span',{'class':'muted'},['No photo']);
  var more=el('button',{type:'button'},['More like this']);
  more.setAttribute('aria-label','More photos like observation '+c.id);
  more.addEventListener('click',function(){go({kind:'id',id:c.id});});
  var body=el('div',{'class':'body'},[
    el('a',{'class':'name',href:obsUrl(c.id),target:'_blank',rel:'noopener'},[c.name||'Unidentified']),
    el('span',{'class':'common'},[c.common]),
    el('span',{},[c.date||'Date unknown']),
    el('span',{'class':'muted'},[c.place||'Place unknown']),
    el('span',{'class':'muted',title:'How close the photo is to the query, 0 to 1. Compare within this list only: a sentence scores lower than a photo-to-photo search.'},
      ['#'+(i+1)+' · Similarity '+c.score.toFixed(3)]),
    el('div',{'class':'links'},[more,pick(c),
      el('a',{'class':'btn',href:CFG.mapUrl+'#record='+c.id,target:'_blank',rel:'noopener'},['Show on map'])])
  ]);
  return el('li',{'class':'card'},[
    el('a',{'class':'photo',href:obsUrl(c.id),target:'_blank',rel:'noopener',
      'aria-label':'Open observation '+c.id+' on iNaturalist: '+alt},[img]),body]);
}

// A "Matches" tick on a text-search card; the button under the grid counts the ticks.
function pick(c){
  if(!S.qvec||c.tag===undefined)return el('span');
  var box=el('input',{type:'checkbox','aria-label':'Observation '+c.id+' matches'});
  box.checked=S.picks.has(c.id);
  box.addEventListener('change',function(){
    if(box.checked)S.picks.add(c.id);else S.picks.delete(c.id);
    var n=S.picks.size,b=$('again');
    if(!b)return;
    b.disabled=!n;
    b.textContent=n?'Search again with '+n+' picked photo'+(n>1?'s':''):'Tick photos that match, then search again';
  });
  return el('label',{'class':'pick'},[box,' Matches']);
}
// Setting the hash is the navigation: back/forward and shared links all arrive through start().
function go(state){
  if(state)state=Object.assign({},state,{include:S.include,exclude:S.exclude});
  var h=Meta.toHash(state);
  if(h===location.hash||(!h&&!location.hash))start(state);else location.hash=h;
}

function chips(){
  var ul=$('chips');ul.textContent='';
  [['include',S.include],['exclude',S.exclude]].forEach(function(p){
    p[1].forEach(function(t,i){
      var rm=el('button',{type:'button','aria-label':'Remove '+t.name+' filter'},['×']);
      rm.addEventListener('click',function(){p[1].splice(i,1);filtersChanged();});
      ul.appendChild(el('li',{'class':'chip'+(p[0]==='exclude'?' not':'')},[
        (p[0]==='exclude'?'Not ':'')+t.name,rm]));
    });
  });
}
function addTaxon(list,t){
  if(S.include.concat(S.exclude).some(function(x){return x.id===t.id;}))return;
  list.push(t);filtersChanged();
}
function filtersChanged(){chips();if(S.state)go(S.state);else render();}
var timer=0;
function suggest(){
  var q=$('tq').value.trim(),ul=$('sugg');
  clearTimeout(timer);
  if(q.length<2){ul.textContent='';return;}
  timer=setTimeout(async function(){
    try{
      var found=await Meta.autocomplete(q,function(u){return fetch(u);});
      if($('tq').value.trim()!==q)return;  // a slower reply for an older prefix must not win
      ul.textContent='';
      found.forEach(function(t){
        var label=t.name+(t.common?' ('+t.common+')':''),rank=t.rank?', '+t.rank:'';
        var keep=el('button',{type:'button','aria-label':'Keep only '+label},['Keep']);
        var drop=el('button',{type:'button','aria-label':'Leave out '+label},['Leave out']);
        keep.addEventListener('click',function(){addTaxon(S.include,t);});
        drop.addEventListener('click',function(){addTaxon(S.exclude,t);});
        ul.appendChild(el('li',{},[el('span',{'class':'muted'},[label+rank+' ']),keep,drop]));
      });
      if(!found.length)ul.appendChild(el('li',{'class':'muted'},['No taxa found.']));
    }catch(e){ul.textContent='';status('Taxon search failed: '+e.message);}
  },300);
}

$('form').addEventListener('submit',function(ev){
  ev.preventDefault();
  go(Meta.parseInput($('q').value));
});
$('gobtn').addEventListener('click',function(){if(S.pending)start(S.pending,true);});
$('tq').addEventListener('input',suggest);
EXAMPLES.forEach(function(t){
  var b=el('button',{type:'button'},[t]);
  b.addEventListener('click',function(){$('q').value=t;go({kind:'text',text:t});});
  $('examples').appendChild(b);
});
window.addEventListener('hashchange',function(){
  var s=Meta.parseHash(location.hash);
  if(!same(s,S.state))start(s);else{setFilters(s);render();}
});
start(Meta.parseHash(location.hash));
})();
