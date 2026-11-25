// The evidence search of the Food web page: shows the most promising BC observations for the question ten at a time, each with the
// pair it may show and why it was drawn, and the reader answers one question with four options (keys 1-4: not this predator, not eating,
// can't tell, eating), saved as the three checks (predator, prey, eating) the export has. Annotations,
// the annotations live in localStorage only (one key, read defensively); nothing goes to iNaturalist.
// The next ten come when the last card is answered, or on More photos.
// Rank = the pair's p in the metaweb x the evidence: 4 the field names the pair, 3 it names a coarse ancestor of one animal, 2 the
// description, tags or field text mention a candidate (common or Latin name), 1 they only talk about food or the field is empty.
// FoodLoop.init(E, onChange); FoodLoop.ask({x, y}) when the question changes; FoodLoop.state(pred, prey) is 'before', 'new' or ''.
var FoodLoop=(function(){
'use strict';
// the predator classes the filter offers: [iNaturalist class, button]; '' is all
var CLASSES=[['','All classes'],['Aves','Birds'],['Mammalia','Mammals'],['Reptilia','Reptiles'],['Amphibia','Amphibians'],['Insecta','Insects']],ANS=['yes','no','unsure'],
  // the four options of a card's question and the three checks each one saves; only eating shows it (and asks which animal when the field did not name it)
  OPTS=[['Not this predator',['no','unsure','unsure']],['Not eating',['yes','yes','no']],['Can’t tell',['unsure','unsure','unsure']],['Eating',['yes','yes','yes']]],
  KEY='wtid-loop',OBS='https://www.inaturalist.org/observations/',TEN=10,$=function(id){return document.getElementById(id);};
// #record=<id> (a shared card): read before the page rewrites its hash, drawn first once it fits the question
var WANT=+((/(?:^|&)record=(\d+)(?:&|$)/.exec(location.hash.slice(1))||[])[1]||0);
var S={ann:{},cls:''},H=null,E=null,Q={x:null,y:null},ITEMS=[],deck=[],cur=-1,change=function(){},TOK=new Map(),ready=false,booted=false;
function load(){
  try{var v=JSON.parse(localStorage.getItem(KEY));
    if(v&&typeof v==='object'){S.ann=v.ann&&typeof v.ann==='object'&&!Array.isArray(v.ann)?v.ann:{};
    S.cls=CLASSES.some(function(c){return c[0]===v.cls;})?v.cls:'';}}catch(e){}
}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S));}catch(e){}}
function lc(s){return String(s||'').toLowerCase();}
// the words that name a prey in a text: its Latin and common name, and the common name's last word ("vole")
function tokens(n){
  if(!TOK.has(n)){var t=[lc(n)],c=lc(E.label(n));if(c!==t[0]){t.push(c);var w=c.split(/[ -]/).pop();if(w.length>=4&&t.indexOf(w)<0)t.push(w);}TOK.set(n,t);}
  return TOK.get(n);
}
function mention(text,tok){for(var i=text.indexOf(tok);i>=0;i=text.indexOf(tok,i+1))if((i===0||!/[a-z]/.test(text[i-1]))&&/^(e?s)?([^a-z]|$)/.test(text.slice(i+tok.length)))return true;return false;}  // a plural may end the word ("voles"), not "shrewd"
// the pairs one record may show, each with its evidence tier and the reason, as [{pred, prey, tier, why}]
function entries(r){
  var o=r.o,eat=o.k!=='by',known=eat?r.pred:r.prey,named=eat?r.prey:r.pred,out=[];
  if(!known||known.indexOf(' ')<0)return out;
  var all=(eat?E.preys(known):E.preds(known)).map(function(q){return q[eat?1:0];}).filter(function(n,i,a){return a.indexOf(n)===i;}); // subspecies pairs repeat a partner
  function add(n,tier,why){out.push(eat?{pred:known,prey:n,tier:tier,why:why}:{pred:n,prey:known,tier:tier,why:why});}
  if(named&&!E.open(r,eat?'prey':'pred')){add(named,4,'The field names the pair');return out;}
  if(named){all.filter(function(n){return E.within(n,named);}).forEach(function(n){add(n,3,'The field names '+E.label(named)+', not a species');});return out;}
  var src=[['Description',o.d],['Tags',(o.g||[]).join(' ')],['The field text',o.x]].filter(function(s){return s[1];});
  src.forEach(function(s){var low=lc(s[1]);all.forEach(function(n){var t=tokens(n).filter(function(k){return mention(low,k);})[0];
    if(t)add(n,2,s[0]+(s[0]==='Tags'?' mention ':' mentions ')+'“'+t+'”');});});
  if(out.length)return out;
  all.forEach(function(n){add(n,1,o.k==='text'?'Description or tags mention food':o.k==='model'?'A vision model flagged feeding':'The '+(eat?'Eating':'Eaten by')+' field '+(o.x?'has text, no taxon':'is empty'));});
  return out;
}
// the model's P(feeding) for the observation scales the rank (0.5, the neutral, when it has no hint)
function score(e,id){var h=H&&H.obs[id];return Math.max(E.p(e.pred,e.prey),0.1)*e.tier*(h?Math.max(h.p,0.1):0.5);}
function ok(e){return (!Q.x||E.hit(e.pred,Q.x))&&(!Q.y||E.hit(e.prey,Q.y))&&(!S.cls||E.inClass(e.pred,S.cls));}
// the records for the question not yet drawn or answered, best first, each with its best pair
function ranked(){
  var seen=new Set(deck.map(function(c){return c.r.o.id;}).concat(Object.keys(S.ann).map(Number))),out=[];
  ITEMS.forEach(function(it){
    if(seen.has(it.r.o.id))return;
    var b=null;it.es.forEach(function(e){if(ok(e)&&(!b||score(e,it.r.o.id)>score(b,it.r.o.id)))b=e;});
    if(b)out.push({r:it.r,e:b,s:score(b,it.r.o.id)});});
  var one=new Set();  // an observation with both fields is two records: its best one only
  // model-only cards (3,000+) rank after every observer-reported card, so the field's records are not buried
  return out.sort(function(a,b){return (a.r.o.k==='model')-(b.r.o.k==='model')||b.s-a.s||(a.r.o.on===b.r.o.on?a.r.o.id-b.r.o.id:b.r.o.on>a.r.o.on?1:-1);}).filter(function(c){return !one.has(c.r.o.id)&&one.add(c.r.o.id);});
}
function state(pred,prey){
  if(E.seen(pred,prey))return 'before';
  return Object.keys(S.ann).some(function(i){var a=S.ann[i];return a&&a.v==='yes'&&a.pred&&a.prey&&E.hit(a.pred,pred)&&E.hit(a.prey,prey);})?'new':'';
}
// the pairs the reader confirmed in this browser
function pairs(){var m=new Map();Object.keys(S.ann).forEach(function(i){var a=S.ann[i];if(a&&a.v==='yes'&&a.pred&&a.prey)m.set(a.pred+'|'+a.prey,[a.pred,a.prey]);});return Array.from(m.values());}
function photo(o,a){
  var img=E.el('img');img.src=o.ph;img.alt='Photo of '+E.label(o.t[0]);img.loading='lazy';
  img.onerror=function(){a.replaceChildren(E.el('span','nophoto','Photo not shown here'));};
  return img;
}
// the vision-model hint of an observation (foodweb-vlm.json, absent is fine): the card's first line with a P(feeding) bar, and the prey box over the photo (0-1000 coords)
function hint(o,a,d){
  var h=H&&H.obs[o.id];if(!h)return;
  var g=h.name||(h.prey[0]&&h.prey[0][0]),b=h.box;
  var l=E.el('p','evl vlm',(h.p>=0.9?'Very likely':h.p>=0.5?'Likely':'Unlikely')+' feeding'+(g?' · prey guess: '+E.label(g):'')),m=E.el('span','vbar'),f=E.el('i');
  l.title='Model P(feeding) '+h.p.toFixed(2);f.style.width=Math.round(h.p*100)+'%';m.append(f);l.prepend(m);d.append(l);
  if(b){var x=E.el('span','pbox');x.style.cssText='left:'+b[0]/10+'%;top:'+b[1]/10+'%;width:'+(b[2]-b[0])/10+'%;height:'+(b[3]-b[1])/10+'%';a.append(x);}
}
function pairText(e){return E.label(e.pred)+(e.tier===4?' eats ':' may be eating ')+E.label(e.prey);}
function meter(){
  var n=ranked().length;
  $('draw').textContent=deck.length?'More photos':'Show photos';$('draw').disabled=!n||!ready;
  $('cand').textContent=!ready?E.pl(n,'candidate observation')+' so far. Searching descriptions and tags.':n?E.pl(n,'candidate observation')+(deck.length||Q.x||Q.y?' for this question.':' across the whole web. Pick a species in the question to draw its photos, or show photos from all of them.'):'No more observations for this question.';
}
// the three answers of a mark: a saved single mark (yes, no, unsure) is the same answer to all three
function steps(a){var t=a&&a.st;return Array.isArray(t)&&t.length===3&&t.every(function(x){return ANS.indexOf(x)>=0;})?t:a&&ANS.indexOf(a.v)>=0?[a.v,a.v,a.v]:[];}
// Shows it only when the animals are eating and neither photo-check said no; else Not visible if any said no, else Can't tell
function verdict(t){return t[2]==='yes'&&t[0]!=='no'&&t[1]!=='no'?'yes':t.indexOf('no')>=0?'no':'unsure';}
var STEPS=['Predator','Prey','Eating'],SAY={yes:'yes',no:'no',unsure:'can’t tell'};
function question(c){return 'Is '+E.label(c.e.pred)+' eating '+E.label(c.e.prey)+'?';}
function status(c){
  var a=S.ann[c.r.o.id],li=c.li,s=li.querySelector('.res'),busy=!li.querySelector('.which').hidden,got=busy?c.ans:steps(a);
  li.querySelector('.ask').textContent=a&&!busy?'':question(c);
  li.querySelector('.sum').textContent=got.map(function(x,i){return STEPS[i]+': '+SAY[x];}).join(' · ');
  s.textContent=!a||busy?'':a.v==='yes'?'Shows it'+(a.pred&&a.prey?': '+pairText({pred:a.pred,prey:a.prey,tier:4}).replace(' eats ',' eating '):''):a.v==='no'?'Not visible':'Can’t tell';
  li.classList.toggle('done',!!a);
  var h=li.querySelector('.hand'),y=!!a&&!busy&&a.v==='yes'&&!!a.pred&&!!a.prey;h.hidden=!y;li.querySelector('a.open').hidden=y;  // one link to the observation: the hand-off, else the plain one
  if(y){var by=c.r.o.k==='by',n=E.label(by?a.pred:a.prey),f=by?'Eaten by':'Eating';h.dataset.name=n;
    h.querySelector('a').textContent='Add '+f+' = '+n+' on iNaturalist';h.querySelector('.hint').textContent='On the observation, open Observation fields, pick '+f+', enter '+(by?'the predator':'the prey')+'.';h.querySelector('.cp').textContent='Copy';}
}
function next(){for(var k=1;k<=deck.length;k++){var i=(cur+k)%deck.length;if(!S.ann[deck[i].r.o.id]){focus(i);return;}}draw();}
function focus(i,quiet){
  cur=i;deck.forEach(function(c,j){c.li.classList.toggle('cur',j===i);});
  if(deck[i]&&!quiet)deck[i].li.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});
}
function put(c,t,pred,prey){
  var a={v:verdict(t),st:t.slice(),on:new Date().toISOString().slice(0,10),ask:[c.e.pred,c.e.prey]};if(pred){a.pred=pred;a.prey=prey;}
  S.ann[c.r.o.id]=a;save();status(c);change();next();
}
function copy(t,cs){(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){cs.textContent='Copied';},function(){cs.textContent='Copy failed';});}
// the model's best prey guess for an observation among the names, or a species within the card's prey (its Latin name, "Latin (common)" read as Latin)
function guess(c,names){
  var h=H&&H.obs[c.r.o.id],l=h?[h.name].concat((h.prey||[]).map(function(q){return q[0];})):[];
  return l.map(function(n){return String(n||'').replace(/ \(.*$/,'');}).filter(function(n){return E.all().has(n)&&(names.indexOf(n)>=0||E.hit(n,c.e.prey));})[0]||null;
}
// Shows it on a card whose field does not name the pair: which animal, from the candidates (or any in the metaweb)
function which(c){
  var li=c.li,o=c.r.o,eat=o.k!=='by',known=eat?c.e.pred:c.e.prey,M=E.M(),box=li.querySelector('.which'),pick=null;
  if(!box.hidden)return;
  box.hidden=false;
  function fill(names){
    var g=eat?guess(c,names):null,v=g||(eat?c.e.prey:c.e.pred),h=box.querySelector('.pk');if(g&&names.indexOf(g)<0)names=names.concat(g);
    h.replaceChildren(EatingPicker.create({id:'w'+o.id,ph:'Which '+(eat?'prey':'predator')+'?',value:v,names:names,obs:[],parent:M.parent,rank:M.rank,groups:M.groups,label:E.label,
      onPick:function(n){pick=n;value(n);}}));
    h.querySelector('input').setAttribute('aria-label','Which '+(eat?'prey':'predator')+' does the photo show?');pick=v;value(v);
  }
  // the iNaturalist field value for the animal picked, to copy before Confirm
  function value(n){box.querySelector('.ev').textContent=(eat?'Eating':'Eaten by')+' = '+E.label(n);box.querySelector('.cs').textContent='';}
  box.querySelector('.cp').onclick=function(){copy(E.label(pick),box.querySelector('.cs'));};
  function uniq(l){return Array.from(new Set(l));}
  fill(uniq((eat?E.preys(known):E.preds(known)).map(function(q){return q[eat?1:0];})));
  box.querySelector('.all').onclick=function(){fill(uniq(M.pairs.map(function(q){return q[eat?1:0];})));};
  box.querySelector('.ok').onclick=function(){if(pick){box.hidden=true;put(c,c.ans,eat?known:pick,eat?pick:known);}};
  box.querySelector('.ok').focus();
}
// option i (0-3) of the card's question finishes the mark; Eating on a card whose field does not name the pair asks which animal
function answer(c,i){
  var t=OPTS[i][1],y=verdict(t)==='yes';c.ans=t;c.li.querySelector('.which').hidden=true;
  if(y&&c.e.tier!==4)return which(c),status(c);
  put(c,t,y?c.e.pred:undefined,c.e.prey);
}
function card(c){
  var o=c.r.o,li=E.el('li'),a=E.el('a'),d=E.el('div'),b=E.el('p','mk');c.li=li;
  a.href=OBS+o.id;a.target='_blank';a.rel='noopener';a.append(photo(o,a));
  hint(o,a,d);
  d.append(E.el('p','pair',pairText(c.e)),E.el('p','evl','Why: '+c.e.why+'.'),
    E.el('p','evl',E.pl(o.np||1,'photo')+(o.c?' · '+E.pl(o.c,'comment'):'')+' · '+(o.on||'Date unknown')+' · '+(o.at||'Place unknown')));
  OPTS.forEach(function(x,i){
    var k=E.el('button',null,x[0]+' ');k.type='button';k.append(E.el('kbd',null,i+1));k.onclick=function(){focus(deck.indexOf(c));answer(c,i);};b.append(k);});
  var w=E.el('div','which'),pk=E.el('div','pk'),all=E.el('button','lnk all','Not in this list'),ok=E.el('button','ok','Confirm');
  w.hidden=true;all.type=ok.type='button';
  w.append(E.el('span','lab','Which '+(o.k==='by'?'predator':'prey')+'?'),pk,E.el('span','ev'),E.el('button','cp','Copy'),E.el('span','cs'),ok,all);
  w.querySelector('.cp').type='button';w.querySelector('.cs').setAttribute('aria-live','polite');
  // the hand-off: the page never writes to iNaturalist, so a confirmed mark sends the reader to add the field there
  var hd=E.el('div','hand'),ha=E.el('a'),cp=E.el('button','cp','Copy'),cs=E.el('span','cs');
  hd.hidden=true;ha.href=OBS+o.id;ha.target='_blank';ha.rel='noopener';cp.type='button';cs.setAttribute('aria-live','polite');
  cp.onclick=function(){copy(hd.dataset.name,cs);};
  hd.append(ha,cp,cs,E.el('p','hint evl'));
  var go=E.el('a','open','Open on iNaturalist');go.href=OBS+o.id;go.target='_blank';go.rel='noopener';
  var sh=E.el('button');WtidCarry.share(sh,function(){return ['record='+o.id];});
  d.append(E.el('p','ask'),b,w,E.el('p','res'),E.el('p','sum evl'),hd,go,sh);li.append(a,d);
  li.onclick=function(){if(cur!==deck.indexOf(c))focus(deck.indexOf(c));};
  status(c);return li;
}
function draw(auto){
  var r=ranked(),w=WANT?r.findIndex(function(c){return c.r.o.id===WANT;}):-1;if(w>0)r.unshift(r.splice(w,1)[0]);if(w>=0)WANT=0;
  var got=r.slice(0,TEN),ul=$('cards'),first=deck.length;
  got.forEach(function(c){deck.push(c);ul.append(card(c));});
  save();meter();if(got.length)focus(first,auto===true);
}
// asking starts over. The first ten are drawn when the question has a species (or on the first load, so the
// survey is not empty), once the food-word file has settled. Switching to the survey draws nothing: pick a species or press Show photos.
function ask(q){Q=q;deck=[];cur=-1;$('cards').replaceChildren();meter();if(!ready)return;var a=!!(q.x||q.y)||!booted;booted=true;if(a)draw(true);}
// what the network export needs: every mark (yes carries its pair, any mark the pair its card asked about), the pairs drawn, the photos shown
function marks(){return Object.keys(S.ann).filter(function(i){return S.ann[i];}).map(function(i){var a=S.ann[i];return {id:i,v:a.v,pred:a.pred,prey:a.prey,ask:a.ask};});}
function searched(pred,prey){
  var m=function(p){return p&&p[0]===pred&&p[1]===prey;};
  return deck.some(function(c){return c.e.pred===pred&&c.e.prey===prey;})||marks().some(function(a){return m(a.ask);});
}
function setClass(c){if(CLASSES.some(function(k){return k[0]===c;})){S.cls=c;save();ask(Q);}}
function shown(){return deck.length;}
function csv(){
  var q=function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';};
  return ['observation_id,url,predator,prey,answer,date,is_predator,is_prey,is_eating'].concat(Object.keys(S.ann).map(function(i){var a=S.ann[i]||{};
    return [i,OBS+i,a.pred,a.prey,a.v,a.on].concat(steps(a).length?steps(a):['','','']).map(q).join(',');})).join('\n')+'\n';
}
function exportCsv(){
  var u=URL.createObjectURL(new Blob([csv()],{type:'text/csv'})),a=E.el('a');a.href=u;a.download='food-web-annotations.csv';document.body.append(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},1000);
}
function reload(){
  var ids=new Set(E.R.all.map(function(r){return r.o.id;}));
  // a field record also found by the text search is one card
  ITEMS=E.R.all.concat(E.R.text.filter(function(r){return !ids.has(r.o.id);})).map(function(r){return {r:r,es:entries(r)};}).filter(function(it){return it.es.length;});
}
function init(core,onChange){
  E=core;change=onChange;load();
  reload();
  $('draw').onclick=function(){draw();};$('export').onclick=exportCsv;
  document.addEventListener('keydown',function(e){
    var t=e.target;if(e.ctrlKey||e.metaKey||e.altKey||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)||!deck.length)return;
    if(e.key==='j'||e.key==='k'){e.preventDefault();focus(Math.max(0,Math.min(deck.length-1,(cur<0?0:cur)+(e.key==='j'?1:-1))));return;}
    var v=['1','2','3','4'].indexOf(e.key);if(v>=0&&cur>=0){e.preventDefault();answer(deck[cur],v);}
  });
}
function go(){ready=true;}
function hints(v){H=v&&v.obs?v:null;}
return {hints:hints,init:init,reload:reload,go:go,ask:ask,state:state,pairs:pairs,marks:marks,searched:searched,shown:shown,csv:csv,CLASSES:CLASSES,cls:function(){return S.cls;},setClass:setClass,steps:steps,verdict:verdict,entries:entries,S:S};
})();
