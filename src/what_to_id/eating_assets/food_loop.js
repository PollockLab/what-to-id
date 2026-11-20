// The evidence search of the Food web page: "Draw ten" pulls the ten most promising BC observations for the question, each with the
// pair it may show and why it was drawn, and the reader marks it Shows it (and which animal), Not visible or Can't tell. Annotations,
// the budget and the annotations live in localStorage only (one key, read defensively); nothing goes to iNaturalist.
// Rank = the pair's p in the metaweb x the evidence: 4 the field names the pair, 3 it names a coarse ancestor of one animal, 2 the
// description, tags or field text mention a candidate (common or Latin name), 1 they only talk about food or the field is empty.
// FoodLoop.init(E, onChange); FoodLoop.ask({x, y}) when the question changes; FoodLoop.state(pred, prey) is 'before', 'new' or ''.
var FoodLoop=(function(){
'use strict';
var KEY='wtid-loop',OBS='https://www.inaturalist.org/observations/',TEN=10,$=function(id){return document.getElementById(id);};
var S={budget:30,ann:{}},E=null,Q={x:null,y:null},ITEMS=[],deck=[],cur=-1,change=function(){},TOK=new Map(),ready=false,booted=false;
function load(){
  try{var v=JSON.parse(localStorage.getItem(KEY)),b=Number(v&&v.budget);
    if(v&&typeof v==='object'){S.budget=isFinite(b)&&b>=0?Math.floor(b):30;S.ann=v.ann&&typeof v.ann==='object'&&!Array.isArray(v.ann)?v.ann:{};}}catch(e){}
}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S));}catch(e){}}
function lc(s){return String(s||'').toLowerCase();}
// the words that name a prey in a text: its Latin and common name, and the common name's last word ("vole")
function tokens(n){
  if(!TOK.has(n)){var t=[lc(n)],c=lc(E.label(n));if(c!==t[0]){t.push(c);var w=c.split(/[ -]/).pop();if(w.length>=4&&t.indexOf(w)<0)t.push(w);}TOK.set(n,t);}
  return TOK.get(n);
}
function mention(text,tok){for(var i=text.indexOf(tok);i>=0;i=text.indexOf(tok,i+1))if(i===0||!/[a-z]/.test(text[i-1]))return true;return false;}
// the pairs one record may show, each with its evidence tier and the reason, as [{pred, prey, tier, why}]
function entries(r){
  var o=r.o,eat=o.k!=='by',known=eat?r.pred:r.prey,named=eat?r.prey:r.pred,out=[];
  if(!known||known.indexOf(' ')<0)return out;
  var all=(eat?E.preys(known):E.preds(known)).map(function(q){return q[eat?1:0];});
  function add(n,tier,why){out.push(eat?{pred:known,prey:n,tier:tier,why:why}:{pred:n,prey:known,tier:tier,why:why});}
  if(named&&!E.open(r,eat?'prey':'pred')){add(named,4,'The field names the pair');return out;}
  if(named){all.filter(function(n){return E.within(n,named);}).forEach(function(n){add(n,3,'The field names '+E.label(named)+', not a species');});return out;}
  var src=[['Description',o.d],['Tags',(o.g||[]).join(' ')],['The field text',o.x]].filter(function(s){return s[1];});
  src.forEach(function(s){var low=lc(s[1]);all.forEach(function(n){var t=tokens(n).filter(function(k){return mention(low,k);})[0];
    if(t)add(n,2,s[0]+(s[0]==='Tags'?' mention ':' mentions ')+'“'+t+'”');});});
  if(out.length)return out;
  all.forEach(function(n){add(n,1,o.k==='text'?'Description or tags mention food':'The '+(eat?'Eating':'Eaten by')+' field '+(o.x?'has text, no taxon':'is empty'));});
  return out;
}
function score(e){return Math.max(E.p(e.pred,e.prey),0.1)*e.tier;}
function ok(e){return (!Q.x||E.hit(e.pred,Q.x))&&(!Q.y||E.hit(e.prey,Q.y));}
// the records for the question not yet drawn or answered, best first, each with its best pair
function ranked(){
  var seen=new Set(deck.map(function(c){return c.r.o.id;}).concat(Object.keys(S.ann).map(Number))),out=[];
  ITEMS.forEach(function(it){
    if(seen.has(it.r.o.id))return;
    var b=null;it.es.forEach(function(e){if(ok(e)&&(!b||score(e)>score(b)))b=e;});
    if(b)out.push({r:it.r,e:b,s:score(b)});});
  return out.sort(function(a,b){return b.s-a.s||(b.r.o.on>a.r.o.on?1:-1);});
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
function pairText(e){return E.label(e.pred)+(e.tier===4?' eats ':' may be eating ')+E.label(e.prey);}
function meter(){
  var used=deck.length,left=S.budget-used,n=ranked().length,bar=$('mbar');
  $('budget').value=S.budget;$('used').textContent=used+' used';
  $('mfill').style.width=(S.budget?Math.min(100,used/S.budget*100):100)+'%';bar.setAttribute('aria-valuenow',used);bar.setAttribute('aria-valuemax',S.budget);
  bar.setAttribute('aria-valuetext',used+' of '+S.budget+' photos');bar.classList.toggle('full',left<=0);
  $('draw').textContent=deck.length?'Draw ten more':'Draw ten';$('draw').disabled=left<=0||!n||!ready;
  $('cand').textContent=!ready?E.pl(n,'candidate observation')+' so far. Searching descriptions and tags.':left<=0?'Budget spent. Raise it to draw more.':n?E.pl(n,'candidate observation')+(deck.length||Q.x||Q.y?' for this question.':' across the whole web. Pick a species in the question to draw its photos, or draw ten from all of them.'):'No more observations for this question.';
}
function status(c){
  var a=S.ann[c.r.o.id],li=c.li,s=li.querySelector('.res');
  [].forEach.call(li.querySelectorAll('.mk button'),function(b){b.setAttribute('aria-pressed',String(!!a&&b.dataset.v===a.v));});
  s.textContent=!a?'':a.v==='yes'?'Shows it'+(a.pred&&a.prey?': '+pairText({pred:a.pred,prey:a.prey,tier:4}).replace(' eats ',' eating '):''):a.v==='no'?'Not visible':'Can’t tell';
  li.classList.toggle('done',!!a);
  var h=li.querySelector('.hand'),y=!!a&&a.v==='yes'&&!!a.pred&&!!a.prey;h.hidden=!y;li.querySelector('a.open').hidden=y;  // one link to the observation: the hand-off, else the plain one
  if(y){var by=c.r.o.k==='by',n=E.label(by?a.pred:a.prey),f=by?'Eaten by':'Eating';h.dataset.name=n;
    h.querySelector('a').textContent='Add '+f+' = '+n+' on iNaturalist';h.querySelector('.hint').textContent='On the observation, open Observation fields, pick '+f+', enter '+(by?'the predator':'the prey')+'.';h.querySelector('.cp').textContent='Copy';}
}
function next(){for(var k=1;k<=deck.length;k++){var i=(cur+k)%deck.length;if(!S.ann[deck[i].r.o.id]){focus(i);return;}}}
function focus(i,quiet){
  cur=i;deck.forEach(function(c,j){c.li.classList.toggle('cur',j===i);});
  if(deck[i]&&!quiet)deck[i].li.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});
}
function put(c,v,pred,prey){
  var a={v:v,on:new Date().toISOString().slice(0,10),ask:[c.e.pred,c.e.prey]};if(pred){a.pred=pred;a.prey=prey;}
  S.ann[c.r.o.id]=a;save();status(c);change();next();
}
// Shows it on a card whose field does not name the pair: which animal, from the candidates (or any in the metaweb)
function which(c){
  var li=c.li,o=c.r.o,eat=o.k!=='by',known=eat?c.e.pred:c.e.prey,M=E.M(),box=li.querySelector('.which'),pick=null;
  if(!box.hidden)return;
  box.hidden=false;
  function fill(names){
    var h=box.querySelector('.pk');h.replaceChildren(EatingPicker.create({id:'w'+o.id,ph:'Which '+(eat?'prey':'predator')+'?',value:eat?c.e.prey:c.e.pred,names:names,obs:[],parent:M.parent,rank:M.rank,groups:M.groups,label:E.label,
      onPick:function(n){pick=n;}}));
    h.querySelector('input').setAttribute('aria-label','Which '+(eat?'prey':'predator')+' does the photo show?');pick=eat?c.e.prey:c.e.pred;
  }
  function uniq(l){return Array.from(new Set(l));}
  fill(uniq((eat?E.preys(known):E.preds(known)).map(function(q){return q[eat?1:0];})));
  box.querySelector('.all').onclick=function(){fill(uniq(M.pairs.map(function(q){return q[eat?1:0];})));};
  box.querySelector('.ok').onclick=function(){if(pick){box.hidden=true;put(c,'yes',eat?known:pick,eat?pick:known);}};
  box.querySelector('.ok').focus();
}
function mark(c,v){
  if(v!=='yes'){c.li.querySelector('.which').hidden=true;return put(c,v);}
  if(c.e.tier===4)return put(c,'yes',c.e.pred,c.e.prey);
  which(c);
}
function card(c){
  var o=c.r.o,li=E.el('li'),a=E.el('a'),d=E.el('div'),b=E.el('p','mk');c.li=li;
  a.href=OBS+o.id;a.target='_blank';a.rel='noopener';a.append(photo(o,a));
  d.append(E.el('p','pair',pairText(c.e)),E.el('p','evl','Why: '+c.e.why+'.'),
    E.el('p','evl',E.pl(o.np||1,'photo')+(o.c?' · '+E.pl(o.c,'comment'):'')+' · '+(o.on||'Date unknown')+' · '+(o.at||'Place unknown')));
  [['yes','Shows it','1'],['no','Not visible','2'],['unsure','Can’t tell','3']].forEach(function(x){
    var k=E.el('button',null,x[1]+' ');k.type='button';k.dataset.v=x[0];k.setAttribute('aria-pressed','false');k.append(E.el('kbd',null,x[2]));k.onclick=function(){focus(deck.indexOf(c));mark(c,x[0]);};b.append(k);});
  var w=E.el('div','which'),pk=E.el('div','pk'),all=E.el('button','lnk all','Not in this list'),ok=E.el('button','ok','Confirm');
  w.hidden=true;all.type=ok.type='button';
  w.append(E.el('span','lab','Which '+(o.k==='by'?'predator':'prey')+'?'),pk,ok,all);
  // the hand-off: the page never writes to iNaturalist, so a confirmed mark sends the reader to add the field there
  var hd=E.el('div','hand'),ha=E.el('a'),cp=E.el('button','cp','Copy'),cs=E.el('span','cs');
  hd.hidden=true;ha.href=OBS+o.id;ha.target='_blank';ha.rel='noopener';cp.type='button';cs.setAttribute('aria-live','polite');
  cp.onclick=function(){var t=hd.dataset.name;
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){cs.textContent='Copied';},function(){cs.textContent='Copy failed';});};
  hd.append(ha,cp,cs,E.el('p','hint evl'));
  var go=E.el('a','open','Open on iNaturalist');go.href=OBS+o.id;go.target='_blank';go.rel='noopener';
  d.append(b,w,E.el('p','res'),hd,go);li.append(a,d);
  li.onclick=function(){if(cur!==deck.indexOf(c))focus(deck.indexOf(c));};
  status(c);return li;
}
function draw(auto){
  var n=Math.min(TEN,S.budget-deck.length);if(n<=0)return;
  var got=ranked().slice(0,n),ul=$('cards'),first=deck.length;
  got.forEach(function(c){deck.push(c);ul.append(card(c));});
  save();meter();if(got.length)focus(first,auto===true);
}
// the budget is per question: asking resets it. The first ten are drawn when the question has a species (or on the first load, so the
// survey is not empty), once the food-word file has settled. Switching to the survey draws nothing: pick a species or press Draw ten.
function ask(q){Q=q;deck=[];cur=-1;$('cards').replaceChildren();meter();if(!ready)return;var a=!!(q.x||q.y)||!booted;booted=true;if(a)draw(true);}
// what the network export needs: every mark (yes carries its pair, any mark the pair its card asked about), the pairs drawn, the budget
function marks(){return Object.keys(S.ann).filter(function(i){return S.ann[i];}).map(function(i){var a=S.ann[i];return {id:i,v:a.v,pred:a.pred,prey:a.prey,ask:a.ask};});}
function searched(pred,prey){
  var m=function(p){return p&&p[0]===pred&&p[1]===prey;};
  return deck.some(function(c){return c.e.pred===pred&&c.e.prey===prey;})||marks().some(function(a){return m(a.ask);});
}
function budget(){return {used:deck.length,total:S.budget};}
function csv(){
  var q=function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';};
  return ['observation_id,url,predator,prey,answer,date'].concat(Object.keys(S.ann).map(function(i){var a=S.ann[i]||{};
    return [i,OBS+i,a.pred,a.prey,a.v,a.on].map(q).join(',');})).join('\n')+'\n';
}
function exportCsv(){
  var u=URL.createObjectURL(new Blob([csv()],{type:'text/csv'})),a=E.el('a');a.href=u;a.download='food-web-annotations.csv';document.body.append(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},1000);
}
function reload(){
  ITEMS=E.R.all.concat(E.R.text).map(function(r){return {r:r,es:entries(r)};}).filter(function(it){return it.es.length;});
}
function init(core,onChange){
  E=core;change=onChange;load();
  reload();
  $('draw').onclick=function(){draw();};$('export').onclick=exportCsv;
  $('budget').onchange=function(){var b=Math.floor(Number(this.value));S.budget=isFinite(b)&&b>=0?b:S.budget;save();meter();};
  document.addEventListener('keydown',function(e){
    var t=e.target;if(e.ctrlKey||e.metaKey||e.altKey||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)||!deck.length)return;
    if(e.key==='j'||e.key==='k'){e.preventDefault();focus(Math.max(0,Math.min(deck.length-1,(cur<0?0:cur)+(e.key==='j'?1:-1))));return;}
    var v={1:'yes',2:'no',3:'unsure'}[e.key];if(v&&cur>=0){e.preventDefault();mark(deck[cur],v);}
  });
}
function go(){ready=true;}
return {init:init,reload:reload,go:go,ask:ask,state:state,pairs:pairs,marks:marks,searched:searched,budget:budget,csv:csv,entries:entries,S:S};
})();
