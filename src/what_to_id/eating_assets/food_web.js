// The Food web page, four stages in one hash (q=eats&x=, q=eaten&y=, q=does&x=&y=, none for the survey): the question as a sentence, the
// predicted web as a matrix of the metaweb's p, the evidence search (food_loop.js) and the confirmed network. In the network green is a
// first photograph (confirmed in this browser, never named by a field), grey is photographed before (a field names the pair to species),
// no line is nothing found. Link out only; annotations stay in localStorage.
(function(){
'use strict';
var E=EatingCore,L=FoodLoop,C=EATING_CONFIG,$=function(id){return document.getElementById(id);},el=E.el,label=E.label,M=null,ALL=null,NS='http://www.w3.org/2000/svg';
var MODES=[['','Survey'],['eats','What does X eat?'],['eaten','What eats Y?'],['does','Does X eat Y?']];
var TRY=[['Barred Owl','expanding west',{q:'eats',x:'Barred Owl'}],['Northern Leopard Frog','at risk',{q:'eaten',y:'Northern Leopard Frog'}],
  ['Northwestern Crow on American Red Squirrel','',{q:'does',x:'Northwestern Crow',y:'American Red Squirrel'}]];
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
function uniq(list,k,n){var s=new Set(),out=[];list.forEach(function(q){var l=label(q[k]);if(!s.has(l)&&out.length<n){s.add(l);out.push(q[k]);}});return out;}
function sum(list,k){var m=new Map();list.forEach(function(q){m.set(q[k],(m.get(q[k])||0)+q[2]);});return Array.from(m.keys()).sort(function(a,b){return m.get(b)-m.get(a)||(a<b?-1:1);});}
// stage 2: the rows and columns of the matrix for the question
function axes(h){
  if(h.q==='eats'||h.q==='does'){var c=uniq(E.preys(h.x),1,13);if(h.q==='does'&&c.indexOf(h.y)<0)c.unshift(h.y);return {rows:[h.x],cols:c};}
  if(h.q==='eaten')return {rows:uniq(E.preds(h.y),0,14),cols:[h.y]};
  var rows=sum(M.pairs,0).slice(0,8),sub=M.pairs.filter(function(q){return rows.indexOf(q[0])>=0;});
  return {rows:rows,cols:sum(sub,1).slice(0,10)};
}
function matrix(h){
  var a=axes(h),box=$('mx'),t=el('table'),hd=el('tr');box.replaceChildren();
  if(!a.rows.length||!a.cols.length){box.append(el('p','muted','The metaweb has no pair for this question.'));return;}
  hd.append(el('td'));
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
// stage 4: predators left, prey right, a line for each pair that has evidence
function drawNet(Ls,Rs,edges,desc){
  var box=$('net'),n=Math.max(Ls.length,Rs.length),RH=44,H=n*RH+8,svg=s('svg',{viewBox:'0 0 420 '+H,role:'img','aria-label':desc});box.replaceChildren();
  function ys(l,i){return 4+(n-l.length)*RH/2+RH/2+i*RH;}
  edges.forEach(function(e){var g=s('line',{x1:182,x2:238,y1:ys(Ls,e[0]),y2:ys(Rs,e[1]),class:'e '+e[2]});
    g.append(s('title',null,label(Ls[e[0]])+' eats '+label(Rs[e[1]])+': '+(e[2]==='new'?'first photograph (confirmed here)':'photographed before')));svg.append(g);});
  function side(list,x,anchor,k){list.forEach(function(nm,i){
    var on=edges.some(function(e){return e[k]===i;}),y=ys(list,i),ls=wrap(label(nm),24),t=s('text',{x:anchor==='end'?170:250,y:y+4-(ls.length-1)*6.5,'text-anchor':anchor,class:on?'on':''});
    ls.forEach(function(l,j){t.append(s('tspan',{x:anchor==='end'?170:250,dy:j?13:0},l));});
    svg.append(s('circle',{cx:x,cy:y,r:4,class:on?'on':''}),t);});}
  side(Ls,182,'end',0);side(Rs,238,'start',1);box.append(svg);
}
function network(h){
  var note=$('netnote'),L0=[],R0=[],E0=[];
  function pairsOf(){var m=new Map();E.R.all.forEach(function(r){if(r.pred&&r.prey&&r.pred.indexOf(' ')>0&&r.prey.indexOf(' ')>0)m.set(r.pred+'|'+r.prey,[r.pred,r.prey]);});
    L.pairs().forEach(function(q){m.set(q[0]+'|'+q[1],q);});return Array.from(m.values());}
  function link(ls,rs){var out=[];ls.forEach(function(a,i){rs.forEach(function(b,j){var st=L.state(a,b);if(st)out.push([i,j,st]);});});return out;}
  if(h.q==='does'){L0=[h.x];R0=[h.y];E0=link(L0,R0);}
  else if(h.q==='eats'){L0=[h.x];var seenP=pairsOf().filter(function(q){return E.hit(q[0],h.x);}).map(function(q){return q[1];});
    R0=uniq(E.preys(h.x),1,10).concat(seenP).filter(function(n,i,a){return a.map(label).indexOf(label(n))===i;}).slice(0,14);E0=link(L0,R0);}
  else if(h.q==='eaten'){R0=[h.y];var seenQ=pairsOf().filter(function(q){return E.hit(q[1],h.y);}).map(function(q){return q[0];});
    L0=uniq(E.preds(h.y),0,10).concat(seenQ).filter(function(n,i,a){return a.map(label).indexOf(label(n))===i;}).slice(0,14);E0=link(L0,R0);}
  else{var ps=pairsOf(),deg=new Map();ps.forEach(function(q){deg.set(q[0],(deg.get(q[0])||0)+1);});
    L0=Array.from(deg.keys()).sort(function(a,b){return deg.get(b)-deg.get(a)||(a<b?-1:1);}).slice(0,8);
    var rd=new Map();ps.forEach(function(q){if(L0.indexOf(q[0])>=0)rd.set(q[1],(rd.get(q[1])||0)+1);});
    R0=Array.from(rd.keys()).sort(function(a,b){return rd.get(b)-rd.get(a)||(a<b?-1:1);}).slice(0,14);E0=link(L0,R0);}
  var before=E0.filter(function(e){return e[2]==='before';}).length,nw=E0.length-before;
  note.textContent=h.q==='does'?(E0.length?label(h.x)+' eating '+label(h.y)+': '+(E0[0][2]==='new'?'first photograph, confirmed here.':'photographed before.'):'Nothing found yet for '+label(h.x)+' eating '+label(h.y)+'.')
    :E.pl(before,'pair')+' photographed before, '+nw+' confirmed here.';
  if(!L0.length||!R0.length){$('net').replaceChildren(el('p','muted','No pair is named yet.'));return;}
  drawNet(L0,R0,E0,note.textContent);
}
function sentence(h){
  var b=$('sent'),pn=Array.from(new Set(M.pairs.map(function(x){return x[0];}))).sort(),yn=Array.from(new Set(M.pairs.map(function(x){return x[1];}))).sort();
  b.replaceChildren();
  function pk(id,ph,val,all,side,name){var d=EatingPicker.create({id:id,ph:ph,value:val,names:all,obs:E.R.all.map(function(r){return r[side];}).filter(Boolean),parent:M.parent,rank:M.rank,groups:M.groups,label:label,
    onPick:function(n){var g=resolve(hash());g[id]=n;go(g);}});d.querySelector('input').setAttribute('aria-label',name);return d;}
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
  var ms=$('modes');MODES.forEach(function(x,i){var b=el('button',null,x[1]);b.type='button';b.setAttribute('role','radio');b.dataset.q=x[0];
    b.onclick=function(){go(x[0]?{q:x[0]}:{});};b.onkeydown=function(e){var j=e.key==='ArrowRight'||e.key==='ArrowDown'?1:e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:0;
      if(j){e.preventDefault();var n=ms.children[(i+j+MODES.length)%MODES.length];n.focus();n.click();}};ms.append(b);});
  var tr=$('try');TRY.forEach(function(x){var h={};Object.keys(x[2]).forEach(function(k){h[k]=k==='q'?x[2][k]:E.find(x[2][k],ALL);});
    if(Object.keys(h).some(function(k){return !h[k];}))return;
    var b=el('button','chip',x[0]);b.type='button';b.onclick=function(){go(h);};tr.append(b,el('span','muted',x[1]?' '+x[1]+' ':' '));});
  paint();window.__food=true;
  get(C.text,true).then(function(t){if(!t)return;E.init(d[0],d[1],t);M=E.M();ALL=E.all();L.reload();$('src').textContent=E.how(d[1],t);
    if($('cards').children.length)again();else paint();window.__text=true;});
},function(e){$('src').textContent='Could not load the data ('+e.message+').';$('cand').textContent='';});
})();
