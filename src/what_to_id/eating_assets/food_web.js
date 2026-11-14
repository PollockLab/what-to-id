// The Food web page, four stages in one hash (q=eats&x=, q=eaten&y=, q=does&x=&y=, none for the survey): the question as a sentence, the
// predicted web as a matrix of the metaweb's p, the evidence search (food_loop.js) and the confirmed network. In the network green is a
// first photograph (confirmed in this browser, never named by a field), grey is photographed before (a field names the pair to species),
// no line is nothing found. Link out only; annotations stay in localStorage.
(function(){
'use strict';
var E=EatingCore,L=FoodLoop,C=EATING_CONFIG,$=function(id){return document.getElementById(id);},el=E.el,label=E.label,M=null,ALL=null,NS='http://www.w3.org/2000/svg';
// the verb control: a short label, and the question it asks in full
var MODES=[['','Survey','What evidence is there for the BC food web?'],['eats','X eats','What does X eat?'],['eaten','eats Y','What eats Y?'],['does','X eats Y','Does X eat Y?']];
var TRY=[['Barred Owl','expanding west',{q:'eats',x:'Barred Owl'}],['Northern Leopard Frog','at risk',{q:'eaten',y:'Northern Leopard Frog'}],
  ['Northwestern Crow on American Red Squirrel','unconfirmed',{q:'does',x:'Northwestern Crow',y:'American Red Squirrel'}]];
function hash(){var h={};location.hash.slice(1).split('&').forEach(function(kv){var i=kv.indexOf('=');if(i>0)h[kv.slice(0,i)]=decodeURIComponent(kv.slice(i+1));});return h;}
function go(h){location.hash=Object.keys(h).filter(function(k){return h[k];}).map(function(k){return k+'='+encodeURIComponent(h[k]);}).join('&');}
function inMeta(n,side){return M.pairs.some(function(q){return E.cov(n,q[side==='pred'?0:1]);});}
// the species most often photographed on that side with a metaweb pair, else the one in most pairs: a default for a blank slot
function top(side){
  var c=new Map();E.R.all.forEach(function(r){var n=r[side];if(n&&n.indexOf(' ')>0&&inMeta(n,side))c.set(n,(c.get(n)||0)+1);});
  if(!c.size)M.pairs.forEach(function(q){var n=q[side==='pred'?0:1];c.set(n,(c.get(n)||0)+1);});
  return Array.from(c.keys()).sort(function(a,b){return c.get(b)-c.get(a)||(a<b?-1:1);})[0]||null;
}
// the question the hash asks with every blank or unknown taxon replaced: q, x, y as Latin names
function resolve(h){
  var q=['eats','eaten','does'].indexOf(h.q)>=0?h.q:'',r={q:q};
  if(q==='eats'||q==='does')r.x=E.find(h.x,ALL)||top('pred');
  if(q==='eaten'||q==='does')r.y=E.find(h.y,ALL)||(q==='does'&&r.x&&(E.preys(r.x).filter(function(x){return !E.seen(r.x,x[1]);})[0]||E.preys(r.x)[0]||[])[1])||top('prey');
  return r;
}
// one rank per axis: species with a common name when there are enough, else species, else whatever the metaweb holds
function sp(n){return n.indexOf(' ')>0;}
function lvl(l,k){var a=l.filter(function(q){return sp(q[k])&&label(q[k])!==q[k];});if(a.length>=3)return a;a=l.filter(function(q){return sp(q[k]);});return a.length>=3?a:l;}
function uniq(list,k,n){var s=new Set(),out=[];list=lvl(list,k);list.forEach(function(q){var l=label(q[k]);if(!s.has(l)&&out.length<n){s.add(l);out.push(q[k]);}});return out;}
function sum(list,k){var m=new Map();list.forEach(function(q){m.set(q[k],(m.get(q[k])||0)+q[2]);});return Array.from(m.keys()).sort(function(a,b){return m.get(b)-m.get(a)||(a<b?-1:1);});}
// stage 2: the rows and columns of the matrix for the question
function axes(h){
  if(h.q==='eats'||h.q==='does'){var c=uniq(E.preys(h.x),1,13);if(h.q==='does'&&c.indexOf(h.y)<0)c.unshift(h.y);return {rows:[h.x],cols:c};}
  if(h.q==='eaten')return {rows:uniq(E.preds(h.y),0,14),cols:[h.y]};
  var rows=sum(lvl(M.pairs,0),0).slice(0,8),sub=M.pairs.filter(function(q){return rows.indexOf(q[0])>=0;});
  return {rows:rows,cols:sum(lvl(sub,1),1).slice(0,10)};
}
function matrix(h){
  var a=axes(h),box=$('mx'),t=el('table'),hd=el('tr');box.replaceChildren();
  if(!a.rows.length||!a.cols.length){box.append(el('p','muted','The metaweb has no pair for this question.'));return;}
  hd.append(el('td','corner',null));hd.firstChild.append(el('span',null,'rows eat columns'));
  a.cols.forEach(function(c){var th=el('th','v'),b=el('button',null,label(c));b.type='button';b.title='What eats '+label(c)+'?';b.onclick=function(){go({q:'eaten',y:c});};th.append(b);hd.append(th);});
  t.append(hd);
  a.rows.forEach(function(r){
    var tr=el('tr'),th=el('th'),b=el('button',null,label(r));b.type='button';b.title='What does '+label(r)+' eat?';b.onclick=function(){go({q:'eats',x:r});};th.append(b);tr.append(th);
    a.cols.forEach(function(c){
      var td=el('td'),v=E.p(r,c),st=L.state(r,c),b=el('button'),tip=label(r)+' and '+label(c)+': '+(v?E.words(v)+' in the metaweb':'not in the metaweb')+
        (st==='before'?', photographed before':st==='new'?', first photograph confirmed here':', nothing found yet');
      b.type='button';b.title=tip;b.setAttribute('aria-label',tip+'. Does '+label(r)+' eat '+label(c)+'?');
      if(v)b.style.background='rgba(32,109,203,'+(0.14+0.55*v)+')';
      if(st)td.className='ev';if(h.q==='does'&&c===h.y)td.className+=' sel';
      b.onclick=function(){go({q:'does',x:r,y:c});};td.append(b);tr.append(td);});
    t.append(tr);});
  box.append(t);
}
// a label in lines of at most n characters, broken at spaces, never cut
function wrap(t,n){var out=[],cur='';t.split(' ').forEach(function(w){if(cur&&(cur+' '+w).length>n){out.push(cur);cur=w;}else cur=cur?cur+' '+w:w;});out.push(cur);return out;}
function s(tag,at,text){var e=document.createElementNS(NS,tag);Object.keys(at||{}).forEach(function(k){e.setAttribute(k,at[k]);});if(text!=null)e.textContent=text;return e;}
// stage 4: a line for each pair with evidence. A question about one animal is a star (it in the middle, its partners around it, a hollow
// node and no line for nothing found); the survey and Does X eat Y? are two columns, ordered so the lines cross as little as they can.
function tip(a,b,st){return label(a)+' eats '+label(b)+': '+(st==='new'?'first photograph (confirmed here)':'photographed before');}
function words2(g,t,x,y,anchor,n,k){var tx=s('text',{x:x,y:y,'text-anchor':anchor,class:k||''});wrap(t,n).forEach(function(l,j){tx.append(s('tspan',{x:x,dy:j?13:0},l));});g.append(tx);return tx;}
function drawNet(Ls,Rs,edges,desc,nm){
  var box=$('net'),n=Math.max(Ls.length,Rs.length),RH=36,H=n*RH+8,svg=s('svg',{viewBox:'0 0 380 '+H,role:'img','aria-label':desc});box.replaceChildren();nm=nm||label;
  function ys(l,i){return 4+(n-l.length)*RH/2+RH/2+i*RH;}
  // the shorter column sits level with the middle of its lines, spread so no two labels touch
  var yl=Ls.map(function(_,i){return ys(Ls,i);});
  if(Ls.length>1&&Ls.length<Rs.length){
    yl=Ls.map(function(_,i){var nb=edges.filter(function(e){return e[0]===i;});return nb.length?nb.reduce(function(a,e){return a+ys(Rs,e[1]);},0)/nb.length:ys(Ls,i);});
    for(var i=1;i<yl.length;i++)yl[i]=Math.max(yl[i],yl[i-1]+RH);
    for(i=yl.length-1;i>=0;i--)yl[i]=Math.min(yl[i],i===yl.length-1?ys(Rs,Rs.length-1):yl[i+1]-RH);
    yl=yl.map(function(y){return Math.max(y,ys(Rs,0));});
  }
  edges.forEach(function(e){var g=s('line',{x1:152,x2:228,y1:yl[e[0]],y2:ys(Rs,e[1]),class:'e '+e[2]});g.append(s('title',null,tip(Ls[e[0]],Rs[e[1]],e[2])));svg.append(g);});
  function side(list,x,anchor,k){list.forEach(function(nm0,i){
    var on=edges.some(function(e){return e[k]===i;}),y=k?ys(list,i):yl[i],ls=wrap(nm(nm0),22),t=s('text',{x:anchor==='end'?140:240,y:y+4-(ls.length-1)*6.5,'text-anchor':anchor,class:on?'on':''});
    ls.forEach(function(l,j){t.append(s('tspan',{x:anchor==='end'?140:240,dy:j?13:0},l));});
    t.append(s('title',null,nm(nm0)));svg.append(s('circle',{cx:x,cy:y,r:5,class:on?'on':''}),t);});}
  side(Ls,152,'end',0);side(Rs,228,'start',1);box.append(svg);
}
function drawStar(hub,parts,edges,desc,eats){
  var box=$('net'),svg=s('svg',{viewBox:'0 0 380 '+(n<5?300:370),role:'img','aria-label':desc}),cx=190,cy=n<5?150:185,n=parts.length,rx=95,ry=n<5?85:132,at=[];box.replaceChildren();
  parts.forEach(function(nm,i){var a=-Math.PI/2+i*2*Math.PI/n;at.push([cx+rx*Math.cos(a),cy+ry*Math.sin(a),Math.cos(a),Math.sin(a)]);});
  edges.forEach(function(e){var q=at[e[0]],g=s('line',{x1:cx,y1:cy,x2:q[0],y2:q[1],class:'e '+e[1]});g.append(s('title',null,eats?tip(hub,parts[e[0]],e[1]):tip(parts[e[0]],hub,e[1])));svg.append(g);});
  parts.forEach(function(nm,i){
    var q=at[i],on=edges.some(function(e){return e[0]===i;}),ls=wrap(label(nm),12),side=Math.abs(q[2])<0.35,anchor=side?'middle':q[2]>0?'start':'end',
      t=s('text',{x:q[0]+(side?0:q[2]>0?10:-10),y:side?q[1]+(q[3]<0?-10-(ls.length-1)*13:19):q[1]+4-(ls.length-1)*6.5,'text-anchor':anchor,class:on?'on':''});
    ls.forEach(function(l,j){t.append(s('tspan',{x:t.getAttribute('x'),dy:j?13:0},l));});t.append(s('title',null,label(nm)));
    svg.append(s('circle',{cx:q[0],cy:q[1],r:5,class:on?'on':''}),t);});
  svg.append(s('circle',{cx:cx,cy:cy,r:9,class:'hub'}));words2(svg,label(hub),cx,cy+26,'middle',18,'hubt');box.append(svg);
}
var DROP='a plant, a fungus or not known to be an animal';
// the kingdom of a name by the metaweb's parent table (a species it lacks by its genus): plant, fungus, animal or ''
function kingdom(n){
  var P=M.parent||{};if(!(n in P)&&sp(n))n=n.split(' ')[0];
  for(var k=0;n&&k<40;k++,n=P[n]){if(n==='Plantae')return 'plant';if(n==='Fungi')return 'fungus';if(n==='Animalia')return 'animal';}
  return '';
}
function bary(Ls,Rs,E0){
  var lo=Ls.map(function(_,i){return i;}),ro=Rs.map(function(_,i){return i;});
  function sweep(o,oth,k){
    var pos=[];oth.forEach(function(v,i){pos[v]=i;});
    var m=o.map(function(v){var nb=E0.filter(function(e){return e[k]===v;});return nb.length?nb.reduce(function(a,e){return a+pos[e[1-k]];},0)/nb.length:1e9;});
    return o.map(function(_,i){return i;}).sort(function(a,b){return m[a]-m[b]||a-b;}).map(function(i){return o[i];});
  }
  for(var t=0;t<8;t++){ro=sweep(ro,lo,1);lo=sweep(lo,ro,0);}
  var nl=[],nr=[];lo.forEach(function(v,i){nl[v]=i;});ro.forEach(function(v,i){nr[v]=i;});
  return {L:lo.map(function(i){return Ls[i];}),R:ro.map(function(i){return Rs[i];}),E:E0.map(function(e){return [nl[e[0]],nr[e[1]],e[2]];})};
}
function network(h){
  var note=$('netnote'),hid=0,tail='',desc;
  function pairsOf(){var m=new Map();E.R.all.forEach(function(r){if(r.pred&&r.prey&&r.pred.indexOf(' ')>0&&r.prey.indexOf(' ')>0)m.set(r.pred+'|'+r.prey,[r.pred,r.prey]);});
    L.pairs().forEach(function(q){m.set(q[0]+'|'+q[1],q);});return Array.from(m.values());}
  function link(ls,rs){var out=[];ls.forEach(function(a,i){rs.forEach(function(b,j){var st=L.state(a,b);if(st)out.push([i,j,st]);});});return out;}
  function count(es){var b=es.filter(function(e){return e[e.length-1]==='before';}).length;return E.pl(b,'pair')+' photographed before, '+(es.length-b)+' confirmed here.';}
  if(h.q==='eats'||h.q==='eaten'){
    var eats=h.q==='eats',hub=eats?h.x:h.y,k=eats?1:0,st=function(n){return eats?L.state(hub,n):L.state(n,hub);},
      seen=pairsOf().filter(function(q){return E.hit(q[1-k],hub);}).map(function(q){return q[k];}),
      parts=seen.concat(uniq(eats?E.preys(hub):E.preds(hub),k,30)).filter(function(n,i,a){return a.map(label).indexOf(label(n))===i;});
    parts=parts.filter(function(n){return st(n);}).concat(parts.filter(function(n){return !st(n);}));
    parts=parts.slice(0,Math.max(8,parts.filter(st).length));
    var es=[];parts.forEach(function(n,i){var v=st(n);if(v)es.push([i,v]);});
    note.textContent=count(es);
    if(!parts.length){$('net').replaceChildren(el('p','muted','The metaweb names no '+(eats?'prey':'predator')+' for '+label(hub)+'.'));return;}
    drawStar(hub,parts,es,note.textContent,eats);return;
  }
  var L0,R0,E0,nm=label;
  if(h.q==='does'){L0=[h.x];R0=[h.y];E0=link(L0,R0);}
  else{
    var ps=pairsOf(),keep=ps.filter(function(q){return E.p(q[0],q[1])>0||kingdom(q[0])==='animal'&&kingdom(q[1])==='animal';}),deg=new Map(),rd=new Map(),top=[];hid=ps.length-keep.length;
    // the ten predators with most pairs and those pairs' prey: a region's whole web is a matrix, not a drawing
    keep.forEach(function(q){deg.set(q[0],(deg.get(q[0])||0)+1);});
    top=Array.from(deg.keys()).sort(function(a,b){return deg.get(b)-deg.get(a)||(label(a)<label(b)?-1:1);}).slice(0,10);
    keep=keep.filter(function(q){return top.indexOf(q[0])>=0;});
    function names(i){return Array.from(new Set(keep.map(function(q){return q[i];}))).sort(function(a,b){return label(a)<label(b)?-1:1;});}
    L0=names(0);R0=names(1);E0=link(L0,R0);
    nm=function(n){var g=kingdom(n);return label(n)+(g==='plant'||g==='fungus'?' ('+g+')':'');};
    var o=bary(L0,R0,E0);L0=o.L;R0=o.R;E0=o.E;
    if(deg.size>top.length)tail=' The '+top.length+' of '+deg.size+' predators with most pairs.';
    if(hid)tail+=' '+E.pl(hid,'pair')+' hidden, the partner is '+DROP+'.';
  }
  note.textContent=h.q==='does'?(E0.length?label(h.x)+' eating '+label(h.y)+': '+(E0[0][2]==='new'?'first photograph, confirmed here.':'photographed before.'):'Nothing found yet for '+label(h.x)+' eating '+label(h.y)+'.')
    :count(E0)+tail;
  if(!L0.length||!R0.length){$('net').replaceChildren(el('p','muted','No pair has a photograph yet. Mark what you see in the cards and it appears here.'));return;}
  drawNet(L0,R0,E0,note.textContent,nm);
}
function sentence(h){
  var b=$('sent'),pn=Array.from(new Set(M.pairs.map(function(x){return x[0];}))).sort(),yn=Array.from(new Set(M.pairs.map(function(x){return x[1];}))).sort();
  b.replaceChildren();
  function pk(id,ph,val,all,side,name){var d=EatingPicker.create({id:id,ph:ph,value:val,names:all,obs:E.R.all.map(function(r){return r[side];}).filter(Boolean),parent:M.parent,rank:M.rank,groups:M.groups,label:label,
    onPick:function(n){var g=resolve(hash());g[id]=n;go(g);}});var i=d.querySelector('input');i.setAttribute('aria-label',name);i.title=val?label(val):name;return d;}
  if(!h.q)b.append('What evidence is there for the BC food web?');
  if(h.q==='eats')b.append('What does ',pk('x','Predator',h.x,pn,'pred','Predator'),' eat?');
  if(h.q==='eaten')b.append('What eats ',pk('y','Prey',h.y,yn,'prey','Prey'),'?');
  if(h.q==='does')b.append('Does ',pk('x','Predator',h.x,pn,'pred','Predator'),' eat ',pk('y','Prey',h.y,yn,'prey','Prey'),'?');
}
function paint(){
  var h=resolve(hash()),now=Object.keys(h).filter(function(k){return h[k];}).map(function(k){return k+'='+encodeURIComponent(h[k]);}).join('&');
  if(now!==location.hash.slice(1)&&(h.q||location.hash.length>1))history.replaceState(null,'','#'+now);  // a blank or unknown taxon shows as the default
  [].forEach.call($('modes').children,function(b){b.setAttribute('aria-checked',String(b.dataset.q===h.q));b.tabIndex=b.dataset.q===h.q?0:-1;});
  sentence(h);matrix(h);network(h);L.ask({x:h.q==='eats'||h.q==='does'?h.x:null,y:h.q==='eaten'||h.q==='does'?h.y:null});
}
function again(){var h=resolve(hash());matrix(h);network(h);}
window.addEventListener('hashchange',paint);
function get(u,soft){return fetch(u).then(function(r){if(!r.ok)throw new Error(u+' '+r.status);return r.json();}).catch(function(e){if(soft)return null;throw e;});}
// the 1.4 MB food-word file loads after the first paint; the evidence stage fills in when it lands
Promise.all([get(C.metaweb),get(C.obs)]).then(function(d){
  E.init(d[0],d[1],null);M=E.M();ALL=E.all();L.init(E,again);$('src').textContent=E.how(d[1],d[2]);
  var ms=$('modes');MODES.forEach(function(x,i){var b=el('button',null,x[1]);b.type='button';b.setAttribute('role','radio');b.dataset.q=x[0];b.setAttribute('aria-label',x[2]);b.title=x[2];
    b.onclick=function(){go(x[0]?{q:x[0]}:{});};b.onkeydown=function(e){var j=e.key==='ArrowRight'||e.key==='ArrowDown'?1:e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:0;
      if(j){e.preventDefault();var n=ms.children[(i+j+MODES.length)%MODES.length];n.focus();n.click();}};ms.append(b);});
  var tr=$('try');TRY.forEach(function(x){var h={};Object.keys(x[2]).forEach(function(k){h[k]=k==='q'?x[2][k]:E.find(x[2][k],ALL);});
    if(Object.keys(h).some(function(k){return !h[k];}))return;
    var b=el('button','chip');b.type='button';b.onclick=function(){go(h);};b.append(el('span',null,x[0]),el('em',null,x[1]));tr.append(b);$('tryw').hidden=false;});
  paint();window.__food=true;
  get(C.text,true).then(function(t){L.go();if(t){E.init(d[0],d[1],t);M=E.M();ALL=E.all();L.reload();$('src').textContent=E.how(d[1],t);}
    paint();window.__text=true;});
},function(e){$('src').textContent='Could not load the data ('+e.message+').';$('cand').textContent='The page needs its data and could not load it. Reload to try again.';$('cand').classList.add('err');
  $('mx').replaceChildren(el('p','muted','No data.'));$('net').replaceChildren(el('p','muted','No data.'));});
})();
