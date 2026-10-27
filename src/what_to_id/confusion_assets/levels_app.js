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

// Range maps: BC grid cells, label-only / look-alike-only / both, and the record's point.
var KX=Math.cos(54*Math.PI/180),BOX=null,bitsMemo={},maps=[],seen=null;
function bits(t){
  if(bitsMemo[t])return bitsMemo[t];
  var b=atob(D.rng[t]),a=new Uint8Array(b.length);
  for(var k=0;k<b.length;k++)a[k]=b.charCodeAt(k);
  return(bitsMemo[t]=a);
}
function has(a,c){return(a[c>>3]>>(c&7))&1;}
function box(){
  if(BOX)return BOX;
  var x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
  D.grid.forEach(function(g){for(var k=0;k<g.length;k+=2){x0=Math.min(x0,g[k]);x1=Math.max(x1,g[k]);
    y0=Math.min(y0,g[k+1]);y1=Math.max(y1,g[k+1]);}});
  return(BOX={x0:x0,y0:y0,w:(x1-x0)*KX,h:y1-y0});
}
function inside(g,x,y){
  for(var k=0,n=g.length,r=false,j=n-2;k<n;j=k,k+=2)
    if((g[k+1]>y)!==(g[j+1]>y)&&x<(g[j]-g[k])*(y-g[k+1])/(g[j+1]-g[k+1])+g[k])r=!r;
  return r;
}
function cellAt(i){
  if(D.plon[i]==null||D.plat[i]==null)return null;
  var x=D.plon[i]*10,y=D.plat[i]*10;
  for(var c=0;c<D.grid.length;c++)if(inside(D.grid[c],x,y))return c;
  return-1;
}
function hasMap(i){return D.rng&&D.levels[S.l][0]==='taxonomist'&&D.rng[D.taxon[i]]&&D.rng[D.looks[i]];}
var NEITHER='Outside both ranges: maybe neither.';
function neither(i){var c=cellAt(i);return c!=null&&!(c>=0&&(has(bits(D.taxon[i]),c)||has(bits(D.looks[i]),c)));}
function mapText(i){
  var a=D.taxa[D.taxon[i]],b=D.taxa[D.looks[i]],c=cellAt(i);
  if(c==null)return'Range map of '+a+' and '+b+' in British Columbia';
  function w(t){return c>=0&&has(bits(t),c)?'inside':'outside';}
  return'Range map: this record is '+w(D.taxon[i])+' the range of '+a+', '+w(D.looks[i])+
    ' the range of '+b+(neither(i)?'. '+NEITHER:'');
}
function drawMap(m){
  var cv=m.cv,r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1,B=box();
  if(!r.width)return;
  cv.width=Math.round(r.width*dpr);cv.height=Math.round(r.height*dpr);
  var g=cv.getContext('2d'),st=getComputedStyle(cv),pad=2*dpr,k=(cv.width-2*pad)/B.w;
  function X(v){return pad+(v-B.x0)*KX*k;}
  function Y(v){return cv.height-pad-(v-B.y0)*k;}
  var A=bits(D.taxon[m.i]),L=bits(D.looks[m.i]);
  g.lineWidth=dpr*.6;g.lineJoin='round';g.strokeStyle=st.getPropertyValue('--panel');
  D.grid.forEach(function(p,c){
    var a=has(A,c),l=has(L,c);
    g.fillStyle=st.getPropertyValue(a?(l?'--rboth':'--rlab'):l?'--rlook':'--line');
    g.beginPath();
    for(var q=0;q<p.length;q+=2)g[q?'lineTo':'moveTo'](X(p[q]),Y(p[q+1]));
    g.closePath();g.fill();g.stroke();});
  if(D.plon&&D.plon[m.i]!=null&&D.plat[m.i]!=null){
    var x=X(D.plon[m.i]*10),y=Y(D.plat[m.i]*10);
    g.beginPath();g.arc(x,y,5*dpr,0,7);g.fillStyle='#fff';g.fill();
    g.beginPath();g.arc(x,y,3.2*dpr,0,7);g.fillStyle='#111';g.fill();}
}
function swatch(cls){return el('span','sw '+cls);}
function mapBox(i){
  var w=el('div','rmap'),b=el('button','rbtn'),cv=el('canvas'),B=box(),lg=el('ul','rleg'),
    a=D.taxa[D.taxon[i]],l=D.taxa[D.looks[i]];
  b.type='button';b.setAttribute('aria-expanded','false');b.title='Click to enlarge';
  cv.style.aspectRatio=B.w+'/'+B.h;cv.setAttribute('role','img');
  cv.setAttribute('aria-label',mapText(i));
  b.appendChild(cv);
  [['lab',a,1],['look',l,1],['both','both'],[null,'this record']].forEach(function(x){
    var li=el('li');li.appendChild(x[0]?swatch(x[0]):el('span','sw dot'));
    li.appendChild(x[2]?el('i',null,x[1]):document.createTextNode(x[1]));lg.appendChild(li);});
  if(neither(i))lg.appendChild(el('li','none',NEITHER));
  b.onclick=function(){var on=w.classList.toggle('big');b.setAttribute('aria-expanded',String(on));
    b.title=on?'Click to shrink':'Click to enlarge';
    w.closest('.card').classList.toggle('wide',on);};
  w.append(b,lg);
  var m={cv:cv,i:i};maps.push(m);
  seen=seen||new IntersectionObserver(function(es){es.forEach(function(e){
    if(!e.isIntersecting)return;seen.unobserve(e.target);
    new ResizeObserver(function(){drawMap(e.target.m);}).observe(e.target);});});
  cv.m=m;seen.observe(cv);
  return w;
}
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(){
  maps.forEach(function(m){if(m.cv.isConnected)drawMap(m);});});

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
  var nm=el('div');
  if(D.levels[S.l][0]==='taxonomist'){nm.textContent='Labelled ';nm.append(el('i',null,D.taxa[D.taxon[i]]),
    '. Often confused with ',el('i',null,D.taxa[D.looks[i]]),'.');}
  else nm.appendChild(el('i',null,D.taxa[D.taxon[i]]));
  li.appendChild(nm);
  if(D.note&&D.note[i]>=0)li.appendChild(el('div','range',D.notes[D.note[i]]));
  if(hasMap(i))li.appendChild(mapBox(i));
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
  drawLevels();drawTabs();$('cards').textContent='';maps=[];drawCards();drawAct();
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
