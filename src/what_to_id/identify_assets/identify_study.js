// The Batches tab: the study's batches (study.json, page_rotation.py), served in turn as Identify cards.
// Each press of Next batch takes the next list in this browser's turn order, drawn once at random, so every
// list gets the same share of the browser's batches; inside a list and group the browser starts at its own
// random batch and wraps around. The page knows lists only by letter. The pure functions come first, for node.
var IdentifyStudy=(function(){
'use strict';
var SKEY='what-to-id-rotation',GKEY='what-to-id-rotation-group',LOG='wtid-study-log',KEEP=500;
// state {perm, progress[group] {step, pointers, served}, offsets[label][group], build, cur[group] {label, index}}
function nextBatch(state,data,group){
  var perm=state.perm,K=perm.length,progress=state.progress||{};
  var prev=progress[group]||{step:0,pointers:{},served:0},pointers=Object.assign({},prev.pointers);
  var attempt,label,idx,list,foundLabel=null,foundIdx=-1;
  for(attempt=0;attempt<K;attempt++){
    label=perm[(prev.step+attempt)%K];idx=pointers[label]||0;
    list=(data[label]&&data[label][group])||[];
    if(idx<list.length){foundLabel=label;foundIdx=idx;break;}
  }
  var next=Object.assign({},progress);
  if(foundLabel===null){
    next[group]={step:prev.step+K,pointers:pointers,served:prev.served};
    return {state:Object.assign({},state,{progress:next}),index:null,label:null,done:true,batchNumber:prev.served};
  }
  pointers[foundLabel]=foundIdx+1;
  var n=data[foundLabel][group].length,offset=((state.offsets||{})[foundLabel]||{})[group]||0,served=prev.served+1;
  next[group]={step:prev.step+attempt+1,pointers:pointers,served:served};
  return {state:Object.assign({},state,{progress:next}),index:(offset+foundIdx)%n,label:foundLabel,done:false,batchNumber:served};
}
function leftInGroup(data,state,group){
  var pointers=((state.progress||{})[group]||{}).pointers||{},left=0;
  Object.keys(data).forEach(function(label){
    var list=(data[label]&&data[label][group])||[];
    left+=Math.max(0,list.length-(pointers[label]||0));
  });
  return left;
}
// Counts batches over all lists together, so it says nothing about any one list.
function groupProgress(state,data,group){
  var total=0;
  Object.keys(data).forEach(function(label){total+=((data[label]&&data[label][group])||[]).length;});
  var left=leftInGroup(data,state,group);
  return {opened:total-left,left:left,total:total};
}
// Puts one group's batches back; the turn order and start batches stay.
function startOver(state,group){
  var progress=Object.assign({},state.progress||{}),cur=Object.assign({},state.cur||{});
  delete progress[group];delete cur[group];
  return Object.assign({},state,{progress:progress,cur:cur});
}
// The browser's state for this build: a turn order once, kept across builds; a new build re-cuts every list, so
// its places and start batches start afresh. renewed: a returning browser had batches to lose.
function fresh(state,data,build,rand){
  var labels=Object.keys(data).sort(),s=state,renewed=false;
  if(!s||!Array.isArray(s.perm)||s.perm.length!==labels.length||s.perm.some(function(l){return !data[l];})){
    var a=labels.slice();
    for(var i=a.length-1;i>0;i--){var j=Math.floor(rand()*(i+1)),t=a[i];a[i]=a[j];a[j]=t;}
    s={perm:a,progress:{}};
  }
  if(s.build!==build){renewed=Object.keys(s.progress||{}).length>0;s={perm:s.perm,progress:{},build:build};}
  if(!s.offsets){
    s=Object.assign({},s,{offsets:{}});
    labels.forEach(function(l){s.offsets[l]={};Object.keys(data[l]).forEach(function(g){
      s.offsets[l][g]=Math.floor(rand()*data[l][g].length);});});
  }
  return {state:s,renewed:renewed};
}
function load(k,d){try{var v=localStorage.getItem(k);return v==null?d:JSON.parse(v);}catch(e){return d;}}
function save(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
// The trace of served batches in this browser: only here, until the viewer downloads it.
function served(){var l=load(LOG,[]);return Array.isArray(l)?l:[];}
function logServed(entry){save(LOG,served().concat([entry]).slice(-KEEP));}  // shortcut: keeps the last KEEP batches, raise it if people serve more
function posted(id,taxon,user){
  var l=served();
  for(var k=l.length-1;k>=0;k--)if(l[k].ids&&l[k].ids.indexOf(id)>=0){
    (l[k].posts=l[k].posts||[]).push({id:id,taxon:taxon,user:user&&user.id,at:new Date().toISOString()});save(LOG,l);return;}
}
// ctx {data: study.json less its methods, draw(ids), count(text), active(), track(name)}
function tab(ctx){
  var D=ctx.data,L=D.lists,groups=[];
  Object.keys(L).forEach(function(l){Object.keys(L[l]).forEach(function(g){if(groups.indexOf(g)<0)groups.push(g);});});
  function name(g){return D.names[g]||g;}
  groups.sort(function(a,b){return name(a).localeCompare(name(b));});
  var f=fresh(load(SKEY,null),L,D.build,Math.random),st=f.state,renewed=f.renewed,group=null;
  try{group=localStorage.getItem(GKEY);}catch(e){}
  if(groups.indexOf(group)<0)group=null;
  function $(id){return document.getElementById(id);}
  var sel=$('sgroup'),next=$('snext'),prog=$('sprog'),all=$('sall'),done=$('sdone');
  sel.add(new Option('Pick a group',''));
  groups.forEach(function(g){sel.add(new Option(name(g),g));});
  function keep(){save(SKEY,st);try{if(group)localStorage.setItem(GKEY,group);}catch(e){}}
  function current(){var c=(st.cur||{})[group];return c&&L[c.label]&&(L[c.label][group]||[])[c.index]||null;}
  function serve(){
    var r=nextBatch(st,L,group);st=r.state;
    if(!r.done){
      var cur=Object.assign({},st.cur);cur[group]={label:r.label,index:r.index};st=Object.assign({},st,{cur:cur});
      logServed({day:D.day,build:D.build,label:r.label,group:group,index:r.index,ids:L[r.label][group][r.index],at:new Date().toISOString()});
      ctx.track('serve');
    }
    keep();show();
  }
  function show(){
    sel.value=group||'';
    if(!group){prog.textContent='';next.disabled=true;all.hidden=done.hidden=true;ctx.count('');ctx.draw([]);return;}
    var p=groupProgress(st,L,group),ids=current();
    if(!ids&&p.left){serve();return;}  // a group starts with a batch on screen
    next.disabled=!p.left;done.hidden=!!p.left;all.hidden=!ids;
    prog.textContent=(renewed?'New batches today. ':'')+(ids?'Batch '+p.opened+' of '+p.total:'');
    if(ids){var b=IdentifyLinks.batches(ids,true)[0];all.href=b.url;all.textContent='Open these '+b.n+' on iNaturalist';}
    ctx.count(String(p.total));ctx.draw(ids||[]);
  }
  sel.onchange=function(){group=sel.value||null;renewed=false;keep();show();};
  next.onclick=function(){renewed=false;serve();};
  $('sover').onclick=function(){st=startOver(st,group);keep();show();};
  $('sexport').onclick=function(){
    var a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([JSON.stringify(served(),null,1)],{type:'application/json'}));
    a.download='what-to-id-batches.json';document.body.appendChild(a);a.click();a.remove();
    setTimeout(function(){URL.revokeObjectURL(a.href);},0);
  };
  // N takes the next batch. Held keys do not repeat, so one press is one batch.
  document.addEventListener('keydown',function(e){
    if((e.key!=='n'&&e.key!=='N')||e.repeat||e.ctrlKey||e.metaKey||e.altKey)return;
    if(/^(INPUT|TEXTAREA|SELECT)$/.test((e.target||{}).tagName||'')||!ctx.active()||next.disabled)return;
    e.preventDefault();next.click();
  });
  return {show:show,state:function(){return st;}};
}
return {nextBatch:nextBatch,leftInGroup:leftInGroup,groupProgress:groupProgress,startOver:startOver,fresh:fresh,
  served:served,posted:posted,tab:tab};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=IdentifyStudy;
