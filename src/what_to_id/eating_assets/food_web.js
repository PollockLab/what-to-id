// The Food web page, four stages in one hash (q=eats&x=, q=eaten&y=, q=does&x=&y=, none for the survey): the question as a sentence, the
// predicted web as a matrix of the metaweb's p, the evidence search (food_loop.js) and the confirmed network. In the network green is a
// first photograph (confirmed in this browser, never named by a field), grey is photographed before (a field names the pair to species),
// no line is nothing found. Link out only; annotations stay in localStorage.
(function(){
'use strict';
var E=EatingCore,L=FoodLoop,C=EATING_CONFIG,W=Object.assign({eat:'eat',eats:'eats',ing:'eating',pred:'Predator',preds:'predators',prey:'Prey',web:'the food web',kin:'animal',
  drop:'a plant, a fungus or not known to be an animal',none:'No pair has a photograph yet. Mark what you see in the cards and it appears here.'},C.words),$=function(id){return document.getElementById(id);},el=E.el,label=E.label,M=null,ALL=null,NS='http://www.w3.org/2000/svg';
// the verb control: a short label, and the question it asks in full
var MODES=[['','Survey','What evidence is there for '+W.web+'?'],['eats','X '+(W.lab||W.eats),'What does X '+W.eat+'?'],['eaten',(W.lab||W.eats)+' Y','What '+W.eats+' Y?'],['does','X '+(W.lab||W.eats)+' Y','Does X '+W.eat+' Y?']];
var TRY=W.tries||[['Barred Owl','expanding west',{q:'eats',x:'Barred Owl'}],['Northern Leopard Frog','at risk',{q:'eaten',y:'Northern Leopard Frog'}],
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
  hd.append(el('td','corner',null));hd.firstChild.append(el('span',null,'rows '+W.eat+' columns'));
  a.cols.forEach(function(c){var th=el('th','v'),b=el('button',null,label(c));b.type='button';b.title='What '+W.eats+' '+label(c)+'?';b.onclick=function(){go({q:'eaten',y:c});};th.append(b);hd.append(th);});
  t.append(hd);
  a.rows.forEach(function(r){
    var tr=el('tr'),th=el('th'),b=el('button',null,label(r));b.type='button';b.title='What does '+label(r)+' '+W.eat+'?';b.onclick=function(){go({q:'eats',x:r});};th.append(b);tr.append(th);
    a.cols.forEach(function(c){
      var td=el('td'),v=E.p(r,c),st=L.state(r,c),b=el('button'),tip=label(r)+' and '+label(c)+': '+(v?E.words(v)+' in the metaweb':'not in the metaweb')+
        (st==='before'?', photographed before':st==='new'?', first photograph confirmed here':', nothing found yet');
      b.type='button';b.title=tip;b.setAttribute('aria-label',tip+'. Does '+label(r)+' '+W.eat+' '+label(c)+'?');
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
function tip(a,b,st){return label(a)+' '+W.eats+' '+label(b)+': '+(st==='new'?'first photograph (confirmed here)':'photographed before');}
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
  var n=parts.length,box=$('net'),svg=s('svg',{viewBox:'0 0 380 '+(n<5?300:370),role:'img','aria-label':desc}),cx=190,cy=n<5?150:185,rx=95,ry=n<5?85:132,at=[];box.replaceChildren();
  parts.forEach(function(nm,i){var a=-Math.PI/2+i*2*Math.PI/n;at.push([cx+rx*Math.cos(a),cy+ry*Math.sin(a),Math.cos(a),Math.sin(a)]);});
  edges.forEach(function(e){var q=at[e[0]],g=s('line',{x1:cx,y1:cy,x2:q[0],y2:q[1],class:'e '+e[1]});g.append(s('title',null,eats?tip(hub,parts[e[0]],e[1]):tip(parts[e[0]],hub,e[1])));svg.append(g);});
  parts.forEach(function(nm,i){
    var q=at[i],on=edges.some(function(e){return e[0]===i;}),ls=wrap(label(nm),12),side=Math.abs(q[2])<0.35,anchor=side?'middle':q[2]>0?'start':'end',
      t=s('text',{x:q[0]+(side?0:q[2]>0?10:-10),y:side?q[1]+(q[3]<0?-10-(ls.length-1)*13:19):q[1]+4-(ls.length-1)*6.5,'text-anchor':anchor,class:on?'on':''});
    ls.forEach(function(l,j){t.append(s('tspan',{x:t.getAttribute('x'),dy:j?13:0},l));});t.append(s('title',null,label(nm)));
    svg.append(s('circle',{cx:q[0],cy:q[1],r:5,class:on?'on':''}),t);});
  svg.append(s('circle',{cx:cx,cy:cy,r:9,class:'hub'}));words2(svg,label(hub),cx,cy+26,'middle',18,'hubt');box.append(svg);
}
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
// the pairs with a photograph: the field names them to species, or the reader confirmed them here
function pairsOf(){var m=new Map();E.R.all.forEach(function(r){if(r.pred&&r.prey&&r.pred.indexOf(' ')>0&&r.prey.indexOf(' ')>0)m.set(r.pred+'|'+r.prey,[r.pred,r.prey]);});
  L.pairs().forEach(function(q){m.set(q[0]+'|'+q[1],q);});return Array.from(m.values());}
function network(h){
  var note=$('netnote'),hid=0,tail='',desc;
  function link(ls,rs){var out=[];ls.forEach(function(a,i){rs.forEach(function(b,j){var st=L.state(a,b);if(st)out.push([i,j,st]);});});return out;}
  function count(es){var b=es.filter(function(e){return e[e.length-1]==='before';}).length;return E.pl(b,'pair')+' photographed before'+(W.cards===false?'.':', '+(es.length-b)+' confirmed here.');}
  if(h.q==='eats'||h.q==='eaten'){
    var eats=h.q==='eats',hub=eats?h.x:h.y,k=eats?1:0,st=function(n){return eats?L.state(hub,n):L.state(n,hub);},
      seen=pairsOf().filter(function(q){return E.hit(q[1-k],hub);}).map(function(q){return q[k];}),
      parts=seen.concat(uniq(eats?E.preys(hub):E.preds(hub),k,30)).filter(function(n,i,a){return a.map(label).indexOf(label(n))===i;});
    parts=parts.filter(function(n){return st(n);}).concat(parts.filter(function(n){return !st(n);}));
    parts=parts.slice(0,Math.max(8,parts.filter(st).length));
    var es=[];parts.forEach(function(n,i){var v=st(n);if(v)es.push([i,v]);});
    note.textContent=count(es);
    if(!parts.length){$('net').replaceChildren(el('p','muted','The metaweb names no '+(eats?W.prey:W.pred).toLowerCase()+' for '+label(hub)+'.'));return;}
    drawStar(hub,parts,es,note.textContent,eats);return;
  }
  var L0,R0,E0,nm=label;
  if(h.q==='does'){L0=[h.x];R0=[h.y];E0=link(L0,R0);}
  else{
    var ps=pairsOf(),keep=ps.filter(function(q){return E.p(q[0],q[1])>0||kingdom(q[0])==='animal'&&kingdom(q[1])===W.kin;}),deg=new Map(),rd=new Map(),top=[];hid=ps.length-keep.length;
    // the ten predators with most pairs and those pairs' prey: a region's whole web is a matrix, not a drawing
    keep.forEach(function(q){deg.set(q[0],(deg.get(q[0])||0)+1);});
    top=Array.from(deg.keys()).sort(function(a,b){return deg.get(b)-deg.get(a)||(label(a)<label(b)?-1:1);}).slice(0,10);
    keep=keep.filter(function(q){return top.indexOf(q[0])>=0;});
    if(W.cap){var pd=new Map();keep.forEach(function(q){pd.set(q[1],(pd.get(q[1])||0)+1);});
      var tp=Array.from(pd.keys()).sort(function(a,b){return pd.get(b)-pd.get(a)||(label(a)<label(b)?-1:1);}).slice(0,W.cap);keep=keep.filter(function(q){return tp.indexOf(q[1])>=0;});}
    function names(i){return Array.from(new Set(keep.map(function(q){return q[i];}))).sort(function(a,b){return label(a)<label(b)?-1:1;});}
    L0=names(0);R0=names(1);E0=link(L0,R0);
    nm=function(n){var g=kingdom(n);return label(n)+((g==='plant'||g==='fungus')&&g!==W.kin?' ('+g+')':'');};
    var o=bary(L0,R0,E0);L0=o.L;R0=o.R;E0=o.E;
    if(deg.size>top.length)tail=' The '+top.length+' of '+deg.size+' '+W.preds+' with most pairs.';
    if(hid)tail+=' '+E.pl(hid,'pair')+' hidden, the partner is '+W.drop+'.';
  }
  note.textContent=h.q==='does'?(E0.length?label(h.x)+' '+W.ing+' '+label(h.y)+': '+(E0[0][2]==='new'?'first photograph, confirmed here.':'photographed before.'):'Nothing found yet for '+label(h.x)+' '+W.ing+' '+label(h.y)+'.')
    :count(E0)+tail;
  if(!L0.length||!R0.length){$('net').replaceChildren(el('p','muted',W.none));return;}
  drawNet(L0,R0,E0,note.textContent,nm);
}
// the network as a tidy CSV: `# key: value` header lines (pandas comment='#'), then one row per pair of the question, the metaweb's
// and the photographed ones. Status: confirmed_here, photographed_before, nothing_found (searched, no yes) or not_searched.
var STATUS={new:'confirmed_here',before:'photographed_before'};
function netCsv(h){
  var q=function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';},m=new Map(),mk=L.marks(),
    ask=h.q==='eats'?'What does '+label(h.x)+' '+W.eat+'?':h.q==='eaten'?'What '+W.eats+' '+label(h.y)+'?':h.q==='does'?'Does '+label(h.x)+' '+W.eat+' '+label(h.y)+'?':'What evidence is there for '+W.web+'?';
  function add(a,c){m.set(a+'|'+c,[a,c]);}
  if(h.q==='does')add(h.x,h.y);
  else{M.pairs.filter(function(r){return h.q==='eats'?E.cov(h.x,r[0]):h.q==='eaten'?E.cov(h.y,r[1]):true;}).forEach(function(r){add(r[0],r[1]);});
    pairsOf().filter(function(r){return h.q==='eats'?E.hit(r[0],h.x):h.q==='eaten'?E.hit(r[1],h.y):true;}).forEach(function(r){add(r[0],r[1]);});}
  var rows=Array.from(m.values()).sort(function(a,c){return a[0]<c[0]?-1:a[0]>c[0]?1:a[1]<c[1]?-1:a[1]>c[1]?1:0;}).map(function(r){
    var yes=mk.filter(function(a){return a.v==='yes'&&E.hit(a.pred,r[0])&&E.hit(a.prey,r[1]);}),ex=function(v){return mk.filter(function(a){return a.v===v&&a.ask&&a.ask[0]===r[0]&&a.ask[1]===r[1];}).length;},
      before=E.R.all.filter(function(x){return x.pred&&x.prey&&E.hit(x.pred,r[0])&&E.hit(x.prey,r[1]);}).length;
    return [q(r[0]),E.taxonId(r[0]),q(r[1]),E.taxonId(r[1]),STATUS[L.state(r[0],r[1])]||(L.searched(r[0],r[1])?'nothing_found':'not_searched'),yes.length,ex('no'),ex('unsure'),
      q(yes.map(function(a){return a.id;}).join(';')),before,E.p(r[0],r[1])].join(',');});
  return ['# question: '+ask,'# metaweb: '+M.source+'; '+M.rule,'# date: '+new Date().toISOString().slice(0,10),'# shown: '+L.shown(),
    'predator,predator_taxon_id,prey,prey_taxon_id,status,shows_it,not_visible,cant_tell,shows_it_observation_ids,prior_records,metaweb_p'].concat(rows).join('\n')+'\n';
}
function exportNet(){
  var u=URL.createObjectURL(new Blob([netCsv(resolve(hash()))],{type:'text/csv'})),a=el('a');a.href=u;a.download=C.csv||'food-web-network.csv';document.body.append(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},1000);
}
function sentence(h){
  var b=$('sent'),pn=Array.from(new Set(M.pairs.map(function(x){return x[0];}))).sort(),yn=Array.from(new Set(M.pairs.map(function(x){return x[1];}))).sort();
  b.replaceChildren();
  function pk(id,ph,val,all,side,name){var d=EatingPicker.create({id:id,ph:ph,value:val,names:all,obs:E.R.all.map(function(r){return r[side];}).filter(Boolean),parent:M.parent,rank:M.rank,groups:M.groups,label:label,
    onPick:function(n){var g=resolve(hash());g[id]=n;go(g);}});var i=d.querySelector('input');i.setAttribute('aria-label',name);i.title=val?label(val):name;return d;}
  if(!h.q)b.append('What evidence is there for '+W.web+'?');
  if(h.q==='eats')b.append('What does ',pk('x',W.pred,h.x,pn,'pred',W.pred),' '+W.eat+'?');
  if(h.q==='eaten')b.append('What '+W.eats+' ',pk('y',W.prey,h.y,yn,'prey',W.prey),'?');
  if(h.q==='does')b.append('Does ',pk('x',W.pred,h.x,pn,'pred',W.pred),' '+W.eat+' ',pk('y',W.prey,h.y,yn,'prey',W.prey),'?');
}
// a radiogroup of buttons [value, text, full question] in the box: arrows move and pick, one tab stop, ticked() marks the current value
function seg(box,items,pick){
  items.forEach(function(x,i){var b=el('button',null,x[1]);b.type='button';b.setAttribute('role','radio');b.dataset.q=x[0];b.setAttribute('aria-label',x[2]);b.title=x[2];
    b.onclick=function(){pick(x[0]);};b.onkeydown=function(e){var j=e.key==='ArrowRight'||e.key==='ArrowDown'?1:e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:0;
      if(j){e.preventDefault();var n=box.children[(i+j+items.length)%items.length];n.focus();n.click();}};box.append(b);});
}
function ticked(box,v){[].forEach.call(box.children,function(b){b.setAttribute('aria-checked',String(b.dataset.q===v));b.tabIndex=b.dataset.q===v?0:-1;});}
function paint(){
  var h=resolve(hash()),now=Object.keys(h).filter(function(k){return h[k];}).map(function(k){return k+'='+encodeURIComponent(h[k]);}).join('&');
  if(now!==location.hash.slice(1)&&(h.q||location.hash.length>1))history.replaceState(null,'','#'+now);  // a blank or unknown taxon shows as the default
  ticked($('modes'),h.q);ticked($('classes'),L.cls());ticked($('sources'),L.src());
  sentence(h);matrix(h);network(h);fold();L.ask({x:h.q==='eats'||h.q==='does'?h.x:null,y:h.q==='eaten'||h.q==='does'?h.y:null});
  if(window.FoodSearch)FoodSearch.ask(h);
}
// the one line a collapsed section shows on a phone
function fold(){var c=$('mx').querySelectorAll('td button').length,e=$('mx').querySelectorAll('td.ev').length;
  $('s2sum').textContent=c?E.pl(c,'cell')+', '+e+' photographed.':'No pair for this question.';$('s4sum').textContent=$('netnote').textContent;}
function again(){var h=resolve(hash());matrix(h);network(h);fold();}
window.addEventListener('hashchange',paint);
function get(u,soft){if(!u)return Promise.resolve(null);return fetch(u).then(function(r){if(!r.ok)throw new Error(u+' '+r.status);return r.json();}).catch(function(e){if(soft)return null;throw e;});}
// the 1.4 MB food-word file loads after the first paint; the evidence stage fills in when it lands
Promise.all([get(C.metaweb),get(C.obs),get(C.vlm,true)]).then(function(d){
  E.init(d[0],d[1],null);M=E.M();ALL=E.all();L.hints(d[2]);L.init(E,again);$('exportnet').onclick=exportNet;$('src').textContent=E.how(d[1],null);
  if(C.page){$('kind').hidden=false;seg($('kind'),[['food-web.html','Predation','Predation: who eats whom'],['pollination.html','Pollination','Pollination: who visits flowers of what']],function(u){location.href=u;});ticked($('kind'),C.page);}
  seg($('modes'),MODES,function(q){go(q?{q:q}:{});});
  // the predator's class limits the cards; ticked() on the click too, as the hash does not change
  seg($('classes'),L.CLASSES.map(function(c){return [c[0],c[1],c[0]?c[1]+' ('+c[0]+')':'Predators of any class'];}),function(c){L.setClass(c);ticked($('classes'),c);});
  // the source filter only means something with the model study's file
  if(d[2]){$('sources').hidden=false;seg($('sources'),L.SOURCES,function(c){L.setSource(c);ticked($('sources'),c);study();});}
  var tr=$('try');TRY.forEach(function(x){var h={};Object.keys(x[2]).forEach(function(k){h[k]=k==='q'?x[2][k]:E.find(x[2][k],ALL);});
    if(Object.keys(h).some(function(k){return !h[k];}))return;
    var b=el('button','chip');b.type='button';b.onclick=function(){go(h);};b.append(el('span',null,x[0]),el('em',null,x[1]));tr.append(b);$('tryw').hidden=false;});
  // sections 2 and 4 start collapsed under 700px and cannot be closed above it
  var wide=matchMedia('(min-width:700px)');
  [].forEach.call(document.querySelectorAll('.fold'),function(f){f.open=wide.matches;f.addEventListener('toggle',function(){if(wide.matches&&!f.open&&!document.body.classList.contains('study'))f.open=true;});});
  // the model study is a focused labeling tool: the question and sections 2 and 4 are tucked into closed folds, the source row and the annotations export stay in view
  function study(){var on=!!d[2]&&L.src()==='study';if(on===document.body.classList.contains('study'))return;
    document.body.classList.toggle('study',on);$('qf').open=!on;
    if(on){$('qf').before($('sources'));$('draw').parentNode.append($('export'));}else{$('classes').after($('sources'));$('exportnet').before($('export'));}
    [].forEach.call(document.querySelectorAll('.fold'),function(f){f.open=!on&&wide.matches;});}
  study();
  paint();window.__food=true;
  get(C.text,true).then(function(t){L.go();if(t){E.init(d[0],d[1],t);M=E.M();ALL=E.all();L.reload();$('src').textContent=E.how(d[1],t);}
    paint();window.__text=true;});
},function(e){$('src').textContent='Could not load the data ('+e.message+').';$('cand').textContent='The page needs its data and could not load it. Reload to try again.';$('cand').classList.add('err');
  $('mx').replaceChildren(el('p','muted','No data.'));$('net').replaceChildren(el('p','muted','No data.'));});
})();
