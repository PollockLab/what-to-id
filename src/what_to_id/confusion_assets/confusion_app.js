// The confused-pairs page. Reads confusion-data.bin (format in page_confusion.py), lists the pairs
// for the chosen group or search, and shows one pair's or one species' records worst first.
(function(){
'use strict';
var LIMIT=200,SEEN_KEY='what-to-id.confusion.seen',SEEN_MAX=5000,KEEP=50;
var IDENTIFY='https://www.inaturalist.org/observations/identify?taxon_id=',
  IDENTIFY_TAIL='&place_id=7085&quality_grade=needs_id',
  OBS='https://www.inaturalist.org/observations/';
var D=null,S={g:-1,q:'',t:-1,l:-1},pairShown=LIMIT,cardShown=LIMIT,view=[],skip=new Set(),
  focus=-1,seen=new Set();
try{seen=new Set(JSON.parse(localStorage.getItem(SEEN_KEY)||'[]'));}catch(e){}

function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
  if(text!=null)e.textContent=text;return e;}
function name(k){return el('i',null,D.taxa[k][1]);}
function link(href,text,cls){var a=el('a',cls,text);a.href=href;a.target='_blank';
  a.rel='noopener';return a;}
function key(x){return x[0]!=null?String(x[0]):x[1];}

function decode(buf){
  var h=new DataView(buf).getUint32(0,true),head=JSON.parse(new TextDecoder().decode(
    new Uint8Array(buf,4,h))),n=head.n,o=(4+h+3)&~3;
  // typed views read the platform byte order; every browser that runs this is little endian
  function col(T){var a=new T(buf,o,n);o+=n*T.BYTES_PER_ELEMENT;return a;}
  var d={head:head,taxa:head.taxa,pairs:head.pairs,n:n,id:col(Uint32Array),
    photo:col(Uint32Array),tax:col(Uint16Array),looks:col(Uint16Array),score:col(Uint8Array),
    meta:col(Uint8Array),byKey:new Map(),byName:new Map()};
  if(o!==buf.byteLength)throw new Error('confusion-data.bin has an unexpected size');
  d.start=new Int32Array(d.taxa.length).fill(-1);d.end=new Int32Array(d.taxa.length);
  for(var i=0;i<n;i++){var t=d.tax[i];if(d.start[t]<0)d.start[t]=i;d.end[t]=i+1;}
  d.lower=d.taxa.map(function(x,k){var s=x[1].toLowerCase();d.byKey.set(key(x),k);
    if(!d.byName.has(s))d.byName.set(s,k);return s;});
  return d;
}
function photoUrl(i){
  var m=D.meta[i],E=D.head.exts.length;
  return m===255?'':D.head.hosts[Math.floor(m/E)]+D.photo[i]+'/medium.'+D.head.exts[m%E];
}
function margin(i){var r=D.head.score;return r[0]+D.score[i]/255*(r[1]-r[0]);}
function pairOf(t,l){for(var k=0;k<D.pairs.length;k++)
  if(D.pairs[k][0]===t&&D.pairs[k][1]===l)return D.pairs[k];return null;}
function groupName(g){return g!=null&&g>=0?D.head.groups[g][0]:'';}

function readHash(){
  var s=decodeURIComponent(location.hash.slice(1)),m=/^t(\d+)$/.exec(s),p;
  S={g:-1,q:'',t:-1,l:-1};
  if(m){var t=D.byKey.get(m[1]);if(t==null)return;S.t=t;
    p=D.pairs.find(function(x){return x[0]===t;});S.l=p?p[1]:-1;return;}
  var h=new URLSearchParams(location.hash.slice(1)),g=h.get('g');
  if(g)S.g=D.head.groups.findIndex(function(x){return x[0]===g;});
  S.q=h.get('q')||'';
  var tk=D.byKey.get(h.get('t')||''),lk=D.byKey.get(h.get('l')||'');
  if(tk!=null){S.t=tk;if(lk!=null)S.l=lk;}
}
function writeHash(){
  var h=[],e=encodeURIComponent;
  if(S.g>=0)h.push('g='+e(groupName(S.g)));
  if(S.q)h.push('q='+e(S.q));
  if(S.t>=0)h.push('t='+e(key(D.taxa[S.t])));
  if(S.l>=0)h.push('l='+e(key(D.taxa[S.l])));
  history.replaceState(null,'',h.length?'#'+h.join('&'):location.pathname+location.search);
}

function drawTabs(){
  var box=$('tabs');box.textContent='';
  [[-1,'All',D.n]].concat(D.head.groups.map(function(x,k){return [k,x[0],x[1]];}))
    .forEach(function(a){
      var b=el('button',null,a[1]+(a[2]?' '+a[2].toLocaleString():''));b.type='button';
      b.setAttribute('aria-pressed',String(S.g===a[0]));
      if(a[2])b.setAttribute('aria-label',a[1]+', '+a[2].toLocaleString()+' records');
      b.onclick=function(){S.g=a[0];pairShown=LIMIT;update();};box.appendChild(b);});
  var fungi=groupName(S.g)==='Fungi'||(S.t>=0&&groupName(D.taxa[S.t][2])==='Fungi');
  $('caveat').hidden=!fungi;
}
function pairsNow(){
  var q=S.q.toLowerCase(),out=[];
  D.pairs.forEach(function(p,k){
    if(S.g>=0&&D.taxa[p[0]][2]!==S.g)return;
    if(q&&D.lower[p[0]].indexOf(q)<0&&D.lower[p[1]].indexOf(q)<0)return;out.push(k);});
  return out;
}
function drawPairs(scroll){
  var list=pairsNow(),ul=$('pairs'),sel=-1,frag=document.createDocumentFragment(),j;
  for(j=0;j<list.length&&sel<0;j++){var p=D.pairs[list[j]];if(p[0]===S.t&&p[1]===S.l)sel=j;}
  var upto=Math.min(list.length,Math.max(pairShown,sel+1)),selBtn=null;
  for(j=0;j<upto;j++){
    var k=list[j],x=D.pairs[k],li=el('li'),b=el('button','pair');b.type='button';b.dataset.k=k;
    b.setAttribute('aria-pressed',String(j===sel));
    b.append('Labelled ',name(x[0]),' → looks like ',name(x[1]));
    b.appendChild(el('span','sub',x[2].toLocaleString()+' photos, '+
      Math.round(100*x[2]/x[3])+'% of its photos'));
    if(j===sel)selBtn=b;li.appendChild(b);frag.appendChild(li);}
  ul.textContent='';ul.appendChild(frag);
  if(list.length>upto){var m=el('button','more','Show more pairs ('+
    (list.length-upto).toLocaleString()+' left)');m.type='button';m.id='morepairs';
    m.onclick=function(){pairShown=upto+LIMIT;drawPairs();};var li2=el('li');li2.appendChild(m);
    ul.appendChild(li2);}
  $('status').textContent=list.length.toLocaleString()+(list.length===1?' pair':' pairs')+
    (S.g>=0?' in '+groupName(S.g):'')+(S.q?' matching “'+S.q+'”':'');
  if(scroll&&selBtn)selBtn.scrollIntoView({block:'nearest'});
}

function recordsNow(){
  var out=[],i;
  if(S.t<0)return out;
  var a=D.start[S.t],b=D.end[S.t];
  if(a>=0){for(i=a;i<b;i++)if(S.l<0||D.looks[i]===S.l)out.push(i);return out;}
  if(S.l>=0)return out;
  // a look-alike with no records of its own: the records that look like it, worst first
  for(i=0;i<D.n;i++)if(D.looks[i]===S.t)out.push(i);
  return out.sort(function(x,y){return D.score[x]-D.score[y]||D.id[x]-D.id[y];});
}
function drawAct(){
  var act=$('act');act.textContent='';
  if(S.t<0)return;
  var ids=[];view.forEach(function(i){if(!skip.has(D.id[i]))ids.push(D.id[i]);});
  if(ids.length){var b=IdentifyLinks.prepare(ids).batches;b.forEach(function(x,k){
    act.appendChild(link(x.url,'Identify these '+x.n+(b.length>1?' (batch '+(k+1)+' of '+
      b.length+')':''),'identify'));});}
  else if(view.length)act.appendChild(el('span','muted','None selected'));
  var tid=D.taxa[S.t][0];
  if(tid!=null)act.appendChild(link(IDENTIFY+tid+IDENTIFY_TAIL,
    'Identify all of '+D.taxa[S.t][1],'all'));
}
function card(i,j){
  var id=D.id[i],url=OBS+id,li=el('li','card'+(seen.has(id)?' seen':'')),src=photoUrl(i);
  li.tabIndex=-1;li.dataset.j=j;li.dataset.id=id;
  var pick=el('label','pick'),box=el('input');box.type='checkbox';box.checked=!skip.has(id);
  box.dataset.id=id;box.setAttribute('aria-label','Include observation '+id+' in Identify');
  pick.appendChild(box);li.appendChild(pick);
  var ph=link(url,null,'ph');ph.dataset.obs=id;
  if(src){var img=el('img');img.loading='lazy';img.width=400;img.height=300;
    img.alt='labelled '+D.taxa[D.tax[i]][1];img.src=src;ph.appendChild(img);}
  else ph.textContent='No photo';
  li.appendChild(ph);
  var nm=el('div');nm.append(name(D.tax[i]),' looks like ',name(D.looks[i]));li.appendChild(nm);
  var mg=margin(i),lo=D.head.score[0],bar=el('div','bar'),fill=el('span');
  bar.setAttribute('role','img');bar.setAttribute('aria-label','margin '+mg.toFixed(3));
  fill.style.width=(lo<0?Math.min(100,100*mg/lo):0).toFixed(1)+'%';
  bar.appendChild(fill);li.appendChild(bar);
  var ob=link(url,'Observation '+id,'obs');ob.dataset.obs=id;li.appendChild(ob);
  return li;
}
function drawCards(){
  var ol=$('cards'),frag=document.createDocumentFragment(),n=Math.min(view.length,cardShown);
  for(var j=ol.children.length;j<n;j++)frag.appendChild(card(view[j],j));
  ol.appendChild(frag);
  var more=$('morecards');
  if(view.length>n){if(!more){more=el('button','more');more.type='button';more.id='morecards';
    more.onclick=function(){cardShown+=LIMIT;drawCards();};ol.after(more);}
    more.textContent='Show more ('+(view.length-n)+' left)';}
  else if(more)more.remove();
}
function drawRecords(){
  view=recordsNow();focus=-1;$('cards').textContent='';
  var title=$('rec-title'),sub=$('rec-sub');title.textContent='';
  if(S.t<0){title.textContent='Choose a pair';drawAct();drawCards();return;}
  var p=S.l>=0?pairOf(S.t,S.l):null;
  if(S.l>=0)title.append('Labelled ',name(S.t),' → looks like ',name(S.l));
  else if(D.start[S.t]>=0)title.append('All records of ',name(S.t));
  else title.append('Records that look like ',name(S.t));
  sub.textContent=!D.n?'Per-record rows arrive with the next build.':
    view.length.toLocaleString()+(view.length===1?' record':' records')+
    (p?' of its '+p[2].toLocaleString()+' photos':'')+', worst first'+
    (S.l>=0||D.start[S.t]>=0?' (the page keeps the '+KEEP+' worst per species)':'')+'.';
  drawAct();drawCards();
}
function update(scroll){drawTabs();drawPairs(scroll);drawRecords();writeHash();}

function markSeen(id){
  seen.delete(id);seen.add(id);
  var c=$('cards').querySelector('.card[data-id="'+id+'"]');if(c)c.classList.add('seen');
  try{localStorage.setItem(SEEN_KEY,JSON.stringify(Array.from(seen).slice(-SEEN_MAX)));}
  catch(e){}
}
function suggest(q){
  var dl=$('names'),hits=[],pre=[];dl.textContent='';
  if(q.length<2)return;
  q=q.toLowerCase();
  for(var k=0;k<D.lower.length&&pre.length<20;k++){var at=D.lower[k].indexOf(q);
    if(at===0)pre.push(k);else if(at>0&&hits.length<20)hits.push(k);}
  pre.concat(hits).slice(0,20).forEach(function(k){var o=el('option');o.value=D.taxa[k][1];
    dl.appendChild(o);});
}

$('pairs').addEventListener('click',function(e){
  var b=e.target.closest('button.pair');if(!b)return;
  var p=D.pairs[+b.dataset.k];S.t=p[0];S.l=p[1];cardShown=LIMIT;skip.clear();update();
  if(matchMedia('(max-width:760px)').matches)$('records').scrollIntoView({block:'start'});
});
$('cards').addEventListener('change',function(e){
  var id=+e.target.dataset.id;if(!id)return;
  if(e.target.checked)skip.delete(id);else skip.add(id);drawAct();
});
['click','auxclick'].forEach(function(t){$('cards').addEventListener(t,function(e){
  var a=e.target.closest('a[data-obs]');if(a)markSeen(+a.dataset.obs);});});
$('cards').addEventListener('focusin',function(e){
  var c=e.target.closest('.card');if(c)focus=+c.dataset.j;});
$('q').addEventListener('input',function(e){
  S.q=e.target.value.trim();pairShown=LIMIT;suggest(S.q);drawPairs();writeHash();});
$('q').addEventListener('change',function(e){
  var k=D.byName.get(e.target.value.trim().toLowerCase());
  if(k==null)return;S.t=k;S.l=-1;S.g=-1;cardShown=LIMIT;skip.clear();update();
});
document.addEventListener('keydown',function(e){
  if(e.altKey||e.ctrlKey||e.metaKey||/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))return;
  var cards=$('cards').children;if(!cards.length)return;
  if(e.key==='j'||e.key==='k'){
    focus=Math.max(0,Math.min(cards.length-1,focus+(e.key==='j'?1:-1)));
    cards[focus].focus();cards[focus].scrollIntoView({block:'nearest'});e.preventDefault();}
  else if(e.key==='Enter'&&e.target.classList.contains('card')){
    var a=e.target.querySelector('a.obs');markSeen(+a.dataset.obs);
    window.open(a.href,'_blank','noopener');e.preventDefault();}
});
addEventListener('hashchange',function(){readHash();$('q').value=S.q;update(true);});

fetch(CONFIG.data).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);
  return r.arrayBuffer();}).then(EmbeddingsLayout.gunzip).then(function(buf){
  D=decode(buf);readHash();$('q').value=S.q;update(true);
}).catch(function(e){$('status').textContent='Could not load the pairs: '+e.message;});
})();
