// Photo search page: query -> index search or precomputed neighbours -> live iNaturalist cards -> Identify.
(function(){
'use strict';
var CFG=ATLAS_SEARCH_CONFIG,Meta=AtlasSearchMeta,Enc=AtlasEncoder;
var K=200,NPROBE=32;
var qs=new URLSearchParams(location.search);
var DATA=new URL(CFG.dataUrl,location.href).href.replace(/\/*$/,'/');
var S={index:null,encoder:null,cache:new Map(),hits:[],state:null,run:0,include:[],exclude:[]};
var EXAMPLES=['a bird eating a frog','a spider with prey','mushrooms growing on a log'];

function $(id){return document.getElementById(id);}
function el(tag,attrs,kids){
  var e=document.createElement(tag);
  Object.keys(attrs||{}).forEach(function(k){if(attrs[k]!==null&&attrs[k]!==undefined)e.setAttribute(k,attrs[k]);});
  (kids||[]).forEach(function(c){e.appendChild(typeof c==='string'?document.createTextNode(c):c);});
  return e;
}
function status(text){$('status').textContent=text;}
function getIndex(){
  if(!S.index)S.index=AtlasSearchIndex.open(DATA);
  return S.index;
}
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
      ' MB, once. It is stored in this browser afterwards. Searching by observation link needs no download.';
    $('gate').hidden=false;$('gobtn').focus();
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
  var enc=await encoderFor(state,confirmed);
  if(!enc)return {gated:true};
  status('Searching...');
  var q=await enc.encode(state.text);
  return {hits:await idx.search(q,{k:K,nprobe:+qs.get('nprobe')||NPROBE})};
}

async function start(state,confirmed){
  var run=++S.run;
  S.state=state;$('gate').hidden=true;
  if(!state){render();return;}
  $('q').value=state.kind==='id'?String(state.id):state.text;
  status('Searching...');
  try{
    var r=await hitsFor(state,confirmed);
    if(run!==S.run||r.gated)return;
    if(r.error){S.hits=[];render(r.error);return;}
    status('Loading photo details from iNaturalist...');
    S.hits=r.hits;
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

function render(message){
  var res=Meta.build(S.hits,S.cache,{include:S.include.map(taxonId),exclude:S.exclude.map(taxonId)}),grid=$('grid');
  grid.textContent='';
  $('results').hidden=!S.state;
  if(!S.state)return;
  var st=S.state;
  var head=st.kind==='id'?'Photos like observation '+st.id:'Photos matching "'+st.text+'"';
  $('rh').textContent=head+' ('+res.cards.length+')';
  var bits=[];
  if(res.notNeedsId)bits.push(res.notNeedsId+' no longer need an ID');
  if(res.missing)bits.push(res.missing+' no longer returned by iNaturalist');
  if(res.filtered)bits.push(res.filtered+' outside the taxon filter');
  $('dropped').textContent=bits.length?'Left out: '+bits.join(', ')+'.':'';
  status(message||(res.cards.length?'':'No matching photos.'));
  res.cards.forEach(function(c){grid.appendChild(cardEl(c));});
  var actions=$('actions');actions.textContent='';
  if(!res.cards.length)return;
  var batches=IdentifyLinks.prepare(res.cards.map(function(c){return c.id;})).batches;
  batches.forEach(function(b){
    var label=batches.length>1?'Identify '+b.n+' (IDs '+b.lo+' to '+b.hi+')':'Open in iNaturalist Identify ('+b.n+')';
    actions.appendChild(el('a',{'class':'btn primary',href:b.url,target:'_blank',rel:'noopener'},[label]));
  });
}

function cardEl(c){
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
    el('span',{'class':'muted'},['Similarity '+c.score.toFixed(3)]),
    el('div',{'class':'links'},[more,
      el('a',{'class':'btn',href:CFG.mapUrl+'#record='+c.id,target:'_blank',rel:'noopener'},['Show on map'])])
  ]);
  return el('li',{'class':'card'},[
    el('a',{'class':'photo',href:obsUrl(c.id),target:'_blank',rel:'noopener',
      'aria-label':'Open observation '+c.id+' on iNaturalist: '+alt},[img]),body]);
}

// Setting the hash is the navigation: back/forward and shared links all arrive through start().
function go(state){
  var h=Meta.toHash(state);
  if(h===location.hash||(!h&&!location.hash))start(state);else location.hash=h;
}

function chips(){
  var ul=$('chips');ul.textContent='';
  [['include',S.include],['exclude',S.exclude]].forEach(function(p){
    p[1].forEach(function(t,i){
      var rm=el('button',{type:'button','aria-label':'Remove '+t.name+' filter'},['×']);
      rm.addEventListener('click',function(){p[1].splice(i,1);chips();render();});
      ul.appendChild(el('li',{'class':'chip'+(p[0]==='exclude'?' not':'')},[
        (p[0]==='exclude'?'Not ':'')+t.name,rm]));
    });
  });
}
function addTaxon(list,t){
  if(S.include.concat(S.exclude).some(function(x){return x.id===t.id;}))return;
  list.push(t);chips();render();
}
var timer=0;
function suggest(){
  var q=$('tq').value.trim(),ul=$('sugg');
  clearTimeout(timer);
  if(q.length<2){ul.textContent='';return;}
  timer=setTimeout(async function(){
    try{
      var found=await Meta.autocomplete(q,function(u){return fetch(u);});
      ul.textContent='';
      found.forEach(function(t){
        var label=t.name+(t.common?' ('+t.common+')':'');
        var keep=el('button',{type:'button','aria-label':'Keep only '+label},['Keep']);
        var drop=el('button',{type:'button','aria-label':'Leave out '+label},['Leave out']);
        keep.addEventListener('click',function(){addTaxon(S.include,t);});
        drop.addEventListener('click',function(){addTaxon(S.exclude,t);});
        ul.appendChild(el('li',{},[el('span',{'class':'muted'},[label+' ']),keep,drop]));
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
  if(!same(s,S.state))start(s);
});
start(Meta.parseHash(location.hash));
})();
