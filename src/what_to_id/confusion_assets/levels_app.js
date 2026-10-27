// The levels page. Reads levels-data.bin (format in page_levels.py) and shows one level's records
// for the chosen group as cards, in the order the build wrote them.
(function(){
'use strict';
// OUT_KM: a res-4 cell is ~22 km across, so under 50 km is cell-edge noise, not a range outlier.
var LIMIT=60,OUT_KM=50,OBS='https://www.inaturalist.org/observations/';
var D=null,S={l:0,g:-1,o:0},shown=LIMIT,view=[];

function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
  if(text!=null)e.textContent=text;return e;}
function link(href,text,cls){var a=el('a',cls,text);a.href=href;a.target='_blank';
  a.rel='noopener';return a;}
function photoUrl(i){
  var m=D.meta[i],E=D.exts.length;
  return m===255?'':D.hosts[Math.floor(m/E)]+D.photo[i]+'/medium.'+D.exts[m%E];
}

// Range maps, in one shared popover: BC grid cells, label-only / look-alike-only / both, the record.
var KX=Math.cos(54*Math.PI/180),BOX=null,OUTL=null,bitsMemo={},
  REFS=[['Vancouver',-123120,49280],['Prince George',-122750,53920]];
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
// The BC outline: grid edges no other cell shares (vertices are rounded, so shared ones match).
function outline(){
  if(OUTL)return OUTL;
  var n={},e=[];
  D.grid.forEach(function(g){for(var k=0,m=g.length;k<m;k+=2){var j=(k+2)%m,
    a=g[k]+','+g[k+1],b=g[j]+','+g[j+1],key=a<b?a+'|'+b:b+'|'+a;
    n[key]=n[key]?n[key]+1:1;if(n[key]===1)e.push([key,g[k],g[k+1],g[j],g[j+1]]);}});
  return(OUTL=e.filter(function(x){return n[x[0]]===1;}));
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
function tax(){return D.levels[S.l][0]==='taxonomist';}
function hasMap(i){return D.rng&&D.rng[D.taxon[i]]&&(!tax()||D.rng[D.looks[i]]);}
function okm(i){return D.okm?D.okm[i]:-1;}
// a coarser step farther out, so a distance never reads more precise than the range data
function kmText(i){var k=okm(i),s=k>=1000?100:k>=500?50:10;return(Math.round(k/s)*s).toLocaleString('en');}
function inR(t,c){return c>=0&&has(bits(t),c);}
var NEITHER='Outside both ranges: maybe neither.';
// What the map says about the record's point, as words (caption and aria-label).
function mapText(i){
  var a=D.taxa[D.taxon[i]],b=D.taxa[D.looks[i]],c=cellAt(i),far=okm(i)>=OUT_KM,t=tax();
  if(c==null)return{aria:'Range map of '+a+(t?' and '+b:'')+' in British Columbia',cap:''};
  var la=inR(D.taxon[i],c),lb=t&&inR(D.looks[i],c),cap=[];
  if(far)cap.push('About '+kmText(i)+" km outside the label's usual range.");
  else if(t&&!la&&!lb)cap.push(NEITHER);
  else if(!la)cap.push("Outside the label's usual range.");
  if(far&&t&&lb)cap.push("Inside the look-alike's.");
  if(far&&t&&!lb)cap.push(NEITHER);
  return{aria:'Range map: this record is '+(la?'inside':'outside')+' the range of '+a+
    (t?', '+(lb?'inside':'outside')+' the range of '+b:'')+(cap.length?'. '+cap.join(' '):''),
    cap:cap.join(' ')};
}
function drawMap(cv,i){
  var r=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1,B=box(),two=tax();
  if(!r.width)return;
  cv.width=Math.round(r.width*dpr);cv.height=Math.round(r.height*dpr);
  var g=cv.getContext('2d'),st=getComputedStyle(cv),pad=2*dpr,k=(cv.width-2*pad)/B.w;
  function X(v){return pad+(v-B.x0)*KX*k;}
  function Y(v){return cv.height-pad-(v-B.y0)*k;}
  function col(n){return st.getPropertyValue(n);}
  var A=bits(D.taxon[i]),L=two?bits(D.looks[i]):A;
  g.lineWidth=dpr*.5;g.lineJoin='round';
  D.grid.forEach(function(p,c){
    var a=has(A,c),l=has(L,c);
    g.fillStyle=g.strokeStyle=col(a?(two&&l?'--rboth':'--rlab'):l?'--rlook':'--line');
    g.beginPath();
    for(var q=0;q<p.length;q+=2)g[q?'lineTo':'moveTo'](X(p[q]),Y(p[q+1]));
    g.closePath();g.fill();g.stroke();});
  g.strokeStyle=col('--muted');g.lineWidth=dpr;g.beginPath();
  outline().forEach(function(e){g.moveTo(X(e[1]),Y(e[2]));g.lineTo(X(e[3]),Y(e[4]));});g.stroke();
  var pt=D.plon&&D.plon[i]!=null&&D.plat[i]!=null,
    px=pt?X(D.plon[i]*10):-1e4,py=pt?Y(D.plat[i]*10):-1e4;
  g.font=10*dpr+'px system-ui,sans-serif';g.textBaseline='middle';g.fillStyle=col('--muted');
  REFS.forEach(function(r){
    var x=X(r[1]),y=Y(r[2]);
    g.beginPath();g.arc(x,y,2*dpr,0,7);g.fill();
    if(Math.hypot(x-px,y-py)>15*dpr)g.fillText(r[0],x+4*dpr,y);});
  if(pt){
    g.beginPath();g.arc(px,py,5*dpr,0,7);g.fillStyle='#fff';g.fill();
    g.beginPath();g.arc(px,py,3.2*dpr,0,7);g.fillStyle='#111';g.fill();}
}
// The chip on a card: the verdict in a few words, opening the one shared popover with the map.
function verdict(i){
  var far=okm(i)>=OUT_KM,c=cellAt(i);
  if(tax()&&D.note&&D.note[i]>=0){var n=D.notes[D.note[i]].replace('Range: ','');
    return n.charAt(0).toUpperCase()+n.slice(1).replace('both ranges','both ranges: maybe neither');}
  if(far)return'About '+kmText(i)+' km outside';
  return c==null?'Range map':inR(D.taxon[i],c)?'In range':'Just outside range';
}
function svg(tag,attrs){var e=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(var k in attrs)e.setAttribute(k,attrs[k]);return e;}
function pin(){
  var s=svg('svg',{viewBox:'0 0 16 16',width:12,height:12,'aria-hidden':'true'});
  s.appendChild(svg('path',{d:'M8 15s5-4.5 5-8.2A5 5 0 0 0 3 6.8C3 10.5 8 15 8 15z',fill:'none',
    stroke:'currentColor','stroke-width':1.6,'stroke-linejoin':'round'}));
  s.appendChild(svg('circle',{cx:8,cy:6.8,r:1.8,fill:'currentColor'}));return s;
}
var P={i:-1,chip:null,pin:false,kb:false,t:0},pop=null;
function popEl(){
  if(pop)return pop;
  pop=el('div','rpop');pop.id='rpop';pop.setAttribute('role','dialog');pop.hidden=true;
  pop.setAttribute('aria-label','Range map');pop.tabIndex=-1;
  var x=el('button','rx','×');x.type='button';x.setAttribute('aria-label','Close range map');
  x.onclick=function(){closePop(true);};
  pop.append(x,el('canvas'),el('ul','rleg'),el('p','rcap'));
  pop.onmouseenter=function(){clearTimeout(P.t);};
  pop.onmouseleave=leave;
  document.body.appendChild(pop);return pop;
}
function openPop(chip,i,pinned,kb){
  clearTimeout(P.t);
  if(P.chip&&P.chip!==chip)P.chip.setAttribute('aria-expanded','false');
  var p=popEl(),cv=p.children[1],lg=p.children[2],t=mapText(i),two=tax();
  P={i:i,chip:chip,pin:pinned,kb:kb,t:0};
  chip.setAttribute('aria-expanded','true');
  cv.setAttribute('role','img');cv.setAttribute('aria-label',t.aria);
  cv.style.aspectRatio=box().w+'/'+box().h;
  lg.textContent='';
  (two?[['lab',D.taxa[D.taxon[i]],1],['look',D.taxa[D.looks[i]],1],['both','both']]:
    [['lab',D.taxa[D.taxon[i]],1]]).concat([[null,'this record']]).forEach(function(x){
    var li=el('li');li.appendChild(x[0]?el('span','sw '+x[0]):el('span','sw dot'));
    li.appendChild(x[2]?el('i',null,x[1]):document.createTextNode(x[1]));lg.appendChild(li);});
  p.children[3].textContent=t.cap;p.children[3].hidden=!t.cap;
  p.hidden=false;
  if(innerWidth>=600){var r=chip.getBoundingClientRect(),w=p.offsetWidth,h=p.offsetHeight;
    p.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';
    p.style.top=(r.bottom+h+12>innerHeight&&r.top>h+12?r.top-h-6:r.bottom+6)+'px';}
  else{p.style.left=p.style.top='';}
  drawMap(cv,i);
  if(kb)p.focus();
}
function closePop(refocus){
  if(!pop||pop.hidden)return;
  clearTimeout(P.t);pop.hidden=true;P.chip.setAttribute('aria-expanded','false');
  if(refocus)P.chip.focus();
  P.chip=null;
}
function leave(){
  clearTimeout(P.t);
  if(P.chip&&!P.pin)P.t=setTimeout(function(){closePop(false);},200);
}
function chip(i){
  var b=el('button','rchip'),v=verdict(i);
  b.type='button';b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-expanded','false');
  b.setAttribute('aria-controls','rpop');b.append(pin(),el('span',null,v));
  if(v!=='In range'&&v!=='Range map')b.classList.add('bad');
  b.onclick=function(e){
    if(P.chip===b&&!pop.hidden&&(P.pin||e.detail===0)){closePop(e.detail===0);return;}
    openPop(b,i,true,e.detail===0);};
  b.onmouseenter=function(){
    if(!matchMedia('(hover:hover)').matches||innerWidth<600)return;
    clearTimeout(P.t);if(P.chip===b)return;
    P.t=setTimeout(function(){openPop(b,i,false,false);},300);};
  b.onmouseleave=leave;
  return b;
}
addEventListener('keydown',function(e){if(e.key==='Escape')closePop(true);});
addEventListener('pointerdown',function(e){
  if(pop&&!pop.hidden&&!pop.contains(e.target)&&!(P.chip&&P.chip.contains(e.target)))closePop(false);});
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',function(){
  if(pop&&!pop.hidden)drawMap(pop.children[1],P.i);});

function readHash(){
  var h=new URLSearchParams(location.hash.slice(1)),l=h.get('level'),g=h.get('g');S.o=h.get('out')==='1'?1:0;
  S.l=Math.max(0,D.levels.findIndex(function(x){return x[0]===l;}));
  S.g=g?D.groups.indexOf(g):-1;
}
function writeHash(){
  var h='level='+D.levels[S.l][0]+(S.g>=0?'&g='+encodeURIComponent(D.groups[S.g]):'')+(S.o?'&out=1':'');
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
  var n=D.groups.map(function(){return 0;}),all=0,out=0,box=$('tabs');
  for(var i=0;i<D.id.length;i++)if(D.level[i]===S.l&&(!S.o||okm(i)>=OUT_KM)){
    all++;if(D.group[i]>=0)n[D.group[i]]++;}
  for(i=0;i<D.id.length;i++)if(D.level[i]===S.l&&(S.g<0||D.group[i]===S.g)&&okm(i)>=OUT_KM)out++;
  box.textContent='';
  [[-1,'All',all]].concat(D.groups.map(function(g,k){return [k,g,n[k]];})).forEach(function(a){
    if(!a[2]&&a[0]>=0)return;
    var b=el('button',null,a[1]+' '+a[2].toLocaleString());b.type='button';
    b.setAttribute('aria-pressed',String(S.g===a[0]));
    b.setAttribute('aria-label',a[1]+', '+a[2].toLocaleString()+(a[2]===1?' record':' records'));
    b.onclick=function(){S.g=a[0];update();};box.appendChild(b);});
  if(!D.okm)return;
  var o=el('button','out',"Outside its range "+out.toLocaleString());o.type='button';
  o.setAttribute('aria-pressed',String(!!S.o));o.disabled=!out&&!S.o;
  o.onclick=function(){S.o=S.o?0:1;update();};box.appendChild(o);
}
function card(i){
  var id=D.id[i],li=el('li','card'),src=photoUrl(i),ph=link(OBS+id,null,'ph');
  if(src){var img=el('img');img.loading='lazy';img.width=400;img.height=300;
    img.alt='labelled '+D.taxa[D.taxon[i]];img.src=src;ph.appendChild(img);}
  else ph.textContent='No photo';
  li.appendChild(ph);
  var nm=el('div'),m=hasMap(i),lab=el('i',m?'nl':null,D.taxa[D.taxon[i]]);
  if(tax()){nm.textContent='Labelled ';
    nm.append(lab,'. Often confused with ',el('i',m?'nk':null,D.taxa[D.looks[i]]),'.');}
  else nm.appendChild(lab);
  li.appendChild(nm);
  // the photo links to the observation; beside Identify, the range chip, or why there is none
  var links=el('div','links');
  links.appendChild(link(IdentifyLinks.batches([id])[0].url,'Identify','identify btn'));
  if(m)links.appendChild(chip(i));
  else if(D.note&&D.note[i]>=0)links.appendChild(el('span','range',D.notes[D.note[i]]));
  else if(D.rng)links.appendChild(el('span','range','No range map: range unknown'));
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
    (b.length>1?' (batch '+(k+1)+' of '+b.length+')':''),'all btn'));});
}
function update(){
  view=[];shown=LIMIT;
  for(var i=0;i<D.id.length;i++)if(D.level[i]===S.l&&(S.g<0||D.group[i]===S.g)&&(!S.o||okm(i)>=OUT_KM))view.push(i);
  if(S.o)view.sort(function(a,b){return okm(b)-okm(a)||a-b;});
  drawLevels();drawTabs();closePop(false);$('cards').textContent='';drawCards();drawAct();
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
