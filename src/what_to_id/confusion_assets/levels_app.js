// The levels page. Reads levels-data.bin (format in page_levels.py) and shows one level's records
// for the chosen group as cards, in the order the build wrote them.
(function(){
'use strict';
var LIMIT=60,OBS='https://www.inaturalist.org/observations/';
var D=null,S={l:0,g:-1},shown=LIMIT,view=[];

function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
  if(text!=null)e.textContent=text;return e;}
function link(href,text,cls){var a=el('a',cls,text);a.href=href;a.target='_blank';
  a.rel='noopener';return a;}
function photoUrl(i){
  var m=D.meta[i],E=D.exts.length;
  return m===255?'':D.hosts[Math.floor(m/E)]+D.photo[i]+'/medium.'+D.exts[m%E];
}

function readHash(){
  var h=new URLSearchParams(location.hash.slice(1)),l=h.get('level'),g=h.get('g');
  S.l=Math.max(0,D.levels.findIndex(function(x){return x[0]===l;}));
  S.g=g?D.groups.indexOf(g):-1;
}
function writeHash(){
  var h='level='+D.levels[S.l][0]+(S.g>=0?'&g='+encodeURIComponent(D.groups[S.g]):'');
  history.replaceState(null,'','#'+h);
}
function drawLevels(){
  var box=$('levels');box.textContent='';
  D.levels.forEach(function(x,k){
    var b=el('button');b.type='button';b.dataset.level=x[0];
    b.setAttribute('aria-pressed',String(S.l===k));
    b.append(el('b',null,x[1]),el('span',null,x[2]));
    b.onclick=function(){S.l=k;update();};box.appendChild(b);});
}
function drawTabs(){
  var n=D.groups.map(function(){return 0;}),all=0,box=$('tabs');
  for(var i=0;i<D.id.length;i++)if(D.level[i]===S.l){all++;if(D.group[i]>=0)n[D.group[i]]++;}
  box.textContent='';
  [[-1,'All',all]].concat(D.groups.map(function(g,k){return [k,g,n[k]];})).forEach(function(a){
    if(!a[2]&&a[0]>=0)return;
    var b=el('button',null,a[1]+' '+a[2].toLocaleString());b.type='button';
    b.setAttribute('aria-pressed',String(S.g===a[0]));
    b.setAttribute('aria-label',a[1]+', '+a[2].toLocaleString()+(a[2]===1?' record':' records'));
    b.onclick=function(){S.g=a[0];update();};box.appendChild(b);});
}
function card(i){
  var id=D.id[i],li=el('li','card'),src=photoUrl(i),ph=link(OBS+id,null,'ph');
  if(src){var img=el('img');img.loading='lazy';img.width=400;img.height=300;
    img.alt='labelled '+D.taxa[D.taxon[i]];img.src=src;ph.appendChild(img);}
  else ph.textContent='No photo';
  li.appendChild(ph);
  var nm=el('div');nm.appendChild(el('i',null,D.taxa[D.taxon[i]]));
  if(D.levels[S.l][0]==='taxonomist')nm.append(' or ',el('i',null,D.taxa[D.looks[i]]),'?');
  li.appendChild(nm);
  if(D.note&&D.note[i]>=0)li.appendChild(el('div','range',D.notes[D.note[i]]));
  var links=el('div','links');
  links.append(link(OBS+id,'Observation '+id,'obs'),
    link(IdentifyLinks.batches([id])[0].url,'Identify','identify'));
  li.appendChild(links);
  return li;
}
function drawCards(){
  var ol=$('cards'),frag=document.createDocumentFragment(),n=Math.min(view.length,shown);
  for(var j=ol.children.length;j<n;j++)frag.appendChild(card(view[j]));
  ol.appendChild(frag);
  var more=$('more');
  if(view.length>n){if(!more){more=el('button','more');more.type='button';more.id='more';
    more.onclick=function(){shown+=LIMIT;drawCards();drawAct();};ol.after(more);}
    more.textContent='Show more ('+(view.length-n).toLocaleString()+' left)';}
  else if(more)more.remove();
}
function drawAct(){
  var act=$('act'),ids=view.slice(0,shown).map(function(i){return D.id[i];});act.textContent='';
  if(!ids.length)return;
  var b=IdentifyLinks.prepare(ids).batches;
  b.forEach(function(x,k){act.appendChild(link(x.url,'Identify these '+x.n+
    (b.length>1?' (batch '+(k+1)+' of '+b.length+')':''),'all'));});
}
function update(){
  view=[];shown=LIMIT;
  for(var i=0;i<D.id.length;i++)if(D.level[i]===S.l&&(S.g<0||D.group[i]===S.g))view.push(i);
  drawLevels();drawTabs();$('cards').textContent='';drawCards();drawAct();
  $('status').textContent=view.length.toLocaleString()+(view.length===1?' record':' records')+
    (S.g>=0?' in '+D.groups[S.g]:'')+'.';
  writeHash();
}

addEventListener('hashchange',function(){readHash();update();});
fetch(CONFIG.data).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);
  return r.arrayBuffer();}).then(EmbeddingsLayout.gunzip).then(function(buf){
  D=JSON.parse(new TextDecoder().decode(buf));readHash();update();
}).catch(function(e){$('status').textContent='Could not load the records: '+e.message;});
})();
