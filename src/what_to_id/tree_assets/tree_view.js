// The tree of life page: the radial tree of record counts (tree_model.js), the outline that mirrors it for the
// keyboard and for phones, the card of the selected taxon and the photos iNaturalist has for each tip. Inside
// the split view (?embed=1) "Show on map" sends the taxon as the shared selection, as the photo space does.
(function(){
'use strict';
var CT=new Set(),M=TreeModel,L=EmbeddingsLayout,META=CFG.meta,nf=new Intl.NumberFormat('en'),
  nc=new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}),EMBED=/[?&]embed=1/.test(location.search),
  BUDGET=400,BAR=26,TH=24,MINF=9,MINR=420,reduce=matchMedia('(prefers-reduced-motion: reduce)'),
  D=null,S=null,V=null,G={},GS=[],COL=new Map(),prev=null,anim=0,SEL='',SY=null,PS=-1,PH={},Q=[],qt=0,qlast=0,lt=0,split=false,OL=null;
function $(i){return document.getElementById(i);}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function status(t){$('status').textContent=t||'';}
function col(r){
  if(COL.has(r))return COL.get(r);
  var g=D.grp[r],c=g?'rgb('+M.shade(MapFilter.color(g,META.groups.indexOf(g)),M.tone(D,r)).join(',')+')':'var(--muted)';
  COL.set(r,c);return c;}
function rowOf(n){return n.row<0?n.parent.row:n.row;}
function cmn(r){var c=M.common(D,r);return c.toLowerCase()===M.name(D,r).toLowerCase()?'':c;}
function label(r){var c=M.chain(D,r).map(function(x){return M.name(D,x);});
  return c.length>3?c[0]+' › … › '+c[c.length-1]:c.join(' › ');}
function cut(s,n){return s.length>n?s.slice(0,Math.max(1,n-1))+'…':s;}
var CX=document.createElement('canvas').getContext('2d');
// s cut to w pixels in the tree's 11px type (bold for the inner labels); '' when not even 3 letters fit.
function fit(s,w,b){CX.font=(b?'600 ':'')+'11px '+getComputedStyle(document.body).fontFamily;
  if(CX.measureText(s).width<=w)return s;
  while(s.length>3&&CX.measureText(s+'…').width>w)s=s.slice(0,-1);return CX.measureText(s+'…').width>w?'':s+'…';}
// n as a share of d (by default all records needing an ID); a share above nil never reads 0%.
function pct(n,d){var p=100*n/(d||D.tot[D.root]);return p>=10?Math.round(p)+'%':p>=0.1?p.toFixed(1)+'%':p>0?'<0.1%':'0%';}
function rk(r){return r===M.lead(D,D.root)?'':M.rank(D,r);}
// The circle's text s for shown row r; the Unknown group's row is iNaturalist's Life, so it takes the group's map name.
function cname(r,s){return r===D.nr&&r!==D.root&&cmn(r)||s;}
// The life group (a map chip) that shown node r stands for, or ''.
function grpOf(r){return M.chain(D,r).map(function(x){return G[M.id(D,x)];}).filter(Boolean).pop()||'';}
function recs(n){return nf.format(n)+(n===1?' record':' records');}
function tip(n){
  if(n.row<0)return '+'+nf.format(n.more)+' more taxa ('+recs(n.tot)+')';
  var r=n.row,un=r===D.nr&&r!==D.root,cm=un?'':cmn(r),k=un?'':rk(r);
  return (un?cmn(r):label(r))+(cm?' ('+cm+')':'')+(k?', '+k:'')+': '+recs(n.tot)+' need ID'+(n.own?', '+nf.format(n.own)+' only to here':'');}
// ---- the radial tree
// A view of a few leaves fans out over span (centred on the right, where labels read level) and the circle
// grows and shifts so the fan's bounding box fills the canvas, left of the card where it floats over the plot.
// The label ring takes at most cap; rl, for a full circle, sets the ring where the tip labels start.
function geo(span,cap,rl){var b=$('radial'),r=b.getBoundingClientRect(),c=$('card').getBoundingClientRect(),
  W=b.clientWidth-(c.width&&c.left<r.right&&c.right>r.left&&c.top<r.bottom&&c.bottom>r.top?r.right-c.left+18:12),H=b.clientHeight-12,h=span/2,x0=Math.min(0,Math.cos(h)),
  R=Math.max(60,Math.min(W/(1-x0),H/2/(h>=Math.PI/2?1:Math.max(0.3,Math.sin(h))))),
  lab=rl?170:Math.max(46,Math.min(170,R*0.3,cap==null?170:cap)),R1=Math.max(24,rl?rl-BAR-8:R-BAR-10-lab);
  return {span:span,W:W+12,H:H+12,x1:6+W,y1:6+H,cx:6+(W-(1-x0)*R)/2-x0*R,cy:6+H/2,R1:R1,RL:R1+BAR+8,lab:lab,a0:span<2*Math.PI?Math.PI/2-h:0};}
// A guide ring (the tag's start) as a full circle, or for a fan only the arc over the fan.
function ring(g,r){return g.span<2*Math.PI?'path d="M'+P(g,g.a0,r)+arc(g,r,g.a0,g.a0+g.span,1)+'"':
  'circle cx="'+g.cx+'" cy="'+g.cy+'" r="'+r.toFixed(1)+'"';}
// pixels from the centre to the canvas edge (left of the card) at angle a
function edge(g,a){var s=Math.sin(a),c=-Math.cos(a);
  return Math.min(s>1e-6?(g.x1-g.cx)/s:s<-1e-6?(g.cx-6)/-s:1e9,c>1e-6?(g.y1-g.cy)/c:c<-1e-6?(g.cy-6)/-c:1e9);}
function P(g,a,r){return (g.cx+r*Math.sin(a)).toFixed(1)+','+(g.cy-r*Math.cos(a)).toFixed(1);}
function arc(g,r,a0,a1,sweep){return r<0.5||a0===a1?'':'A'+r.toFixed(1)+','+r.toFixed(1)+' 0 '+(Math.abs(a1-a0)>Math.PI?1:0)+','+
  sweep+' '+P(g,a1,r);}
function sector(g,a0,a1,r0,r1){return 'M'+P(g,a0,r1)+arc(g,r1,a0,a1,1)+'L'+P(g,a1,r0)+arc(g,r0,a1,a0,0)+'Z';}
function draw(animate){
  if(!D)return;
  // the card floats beside the circle, or stacks above it where that would leave the circle under MINR px
  var c=$('card'),bd=document.body;c.hidden=S.sel<0;bd.classList.remove('stack');
  bd.classList.toggle('stack',!c.hidden&&$('radial').clientWidth-c.offsetWidth-24<MINR);
  var v=M.view(D,S),span=Math.min(2*Math.PI,Math.max(Math.PI/6,v.root.leaves*Math.PI/12)),g=geo(span);
  // each leaf at least half an even share (5 to 16px), so a small view labels every tip; a fan of a few
  // tips shares out evenly, as one big tip would crowd the rest (the outline has the counts)
  var lay=function(){V=M.layout(v,g.a0,g.a0+span,v.root.leaves<24?Infinity:Math.max(5,Math.min(16,span*g.RL/v.root.leaves/2))/g.RL);};
  lay();
  // the label ring shrinks to the longest tip label that fits, so a dense view gives the tree the room
  var need=0;V.all.forEach(function(n){var t=rim(n,g);if(t)need=Math.max(need,t.w+4);});
  if(need<g.lab-4){g=geo(span,need);lay();}
  // a tip label shows whole in MINF px type or not at all (its name is on hover), as in iTOL and Nextstrain, so on a full
  // circle the label ring goes where the most labels show whole, the widest such ring, never below
  // the default one. The tips are laid out once at the widest ring, so a narrower one only shortens the slots, a label
  // showing from l[0] up, and lengthens the room, its name fitting up to l[1].
  if(span===2*Math.PI){var lo=g.RL,top=Math.min(g.x1-g.cx,g.y1-g.cy)-6,L=[],best=-1,rl=lo;g=geo(span,170,top);lay();
    V.all.forEach(function(n){var t=rim(n,g);if(t&&t.nw)L.push([(MINF+3)/(n.a1-n.a0),edge(g,n.a)-t.nw-7]);});
    [lo,top].concat([].concat.apply([],L.map(function(l){return [l[0],l[0]-0.5,l[1]];}))).forEach(function(c){
      var k=c<lo||c>top?-1:L.filter(function(l){return c>=l[0]&&c<=l[1];}).length;if(k>best||k===best&&c>rl){best=k;rl=c;}});
    g=geo(span,170,rl);}
  var t0=V.root.t,tm=Math.max.apply(null,V.all.map(function(n){return n.lo;})),k=tm>t0?g.R1/(tm-t0):0;
  V.all.forEach(function(n){n.r=(n.t-t0)*k;n.rl=(n.lo-t0)*k;});
  V.g=g;V.t0=t0;V.k=k;V.tm=tm;
  cancelAnimationFrame(anim);anim=0;
  if(animate&&prev&&!reduce.matches&&g.W&&V.all.some(function(n){var p=prev[n.key];return !p||p.a!==n.a||p.r!==n.r;})){var from=prev,t1=performance.now();
    anim=requestAnimationFrame(function frame(now){var f=Math.min(1,(now-t1)/450),e=f<0.5?2*f*f:1-Math.pow(2-2*f,2)/2;
      if(f<1){render(V,tween(from,e));anim=requestAnimationFrame(frame);}else{anim=0;render(V,null);}});}
  else render(V,null);
  prev={};V.all.forEach(function(n){prev[n.key]={a:n.a,r:n.r};});
  outline();card();crumbs();
}
// Each node moves from where it (or the nearest shown ancestor) was to where it goes.
function tween(from,e){return function(n){var s=null;for(var x=n;x&&!s;x=x.parent)s=from[x.key];s=s||{a:n.a,r:0};
  return {a:s.a+(n.a-s.a)*e,r:s.r+(n.r-s.r)*e};};}
function render(V,pos){
  var g=V.g;if(!g.W)return;
  var h=[],full=!pos,at=pos||function(n){return n;},on=S.sel>=0?String(M.lead(D,S.sel)):'',max=Math.log(V.root.tot+1)||1;
  if(full){var last=0;V.rk=[];M.RINGS.forEach(function(x,i){if(x[1]<=V.t0||x[1]>V.tm+1e-9)return;var r=(x[1]-V.t0)*V.k;
    if(i%2)h.push('<'+ring(g,(r+last)/2)+' class="band" stroke-width="'+(r-last).toFixed(1)+'"/>');
    var t=P(g,g.a0,r+3).split(',');h.push('<'+ring(g,r)+' class="ring"/>');V.rk.push([+t[0]+3,+t[1],x[0]]);last=r;});
    V.all.forEach(function(n){if(n.kids.length)return;var w=n.a1-n.a0,pad=Math.min(0.15*w,0.004),c=col(rowOf(n));
      if(n.row<0||D.kids[n.row].length)h.push('<path class="wd'+(n.row<0?' more':'')+'" data-k="'+n.key+'" fill="'+c+'" stroke="'+c+
        '" d="'+sector(g,n.a0+pad,n.a1-pad,n.r,Math.max(n.rl,n.r+4))+'"/>');
      var len=BAR*Math.log(n.tot+1)/max,bw=Math.max(1,Math.min(8,w*g.R1*0.6));
      h.push('<path class="br" data-k="'+n.key+'" stroke="'+c+'" stroke-width="'+bw.toFixed(1)+'" d="M'+P(g,n.a,g.R1+4)+'L'+
        P(g,n.a,g.R1+4+Math.max(1,len))+'"/>');});}
  V.all.forEach(function(n){if(!n.parent)return;var p=at(n.parent),c=at(n);
    h.push('<path class="lk" data-k="'+n.key+'" stroke="'+col(rowOf(n))+'" d="M'+P(g,p.a,p.r)+arc(g,p.r,p.a,c.a,c.a>p.a?1:0)+'L'+P(g,c.a,c.r)+'"/>');});
  V.all.forEach(function(n){if(n.row<0)return;var c=at(n),xy=P(g,c.a,c.r).split(','),x=+xy[0],y=+xy[1],
    rr=n.key===on?6:n.parent?3.5:5,f=n.tot?n.own/n.tot:0,cl=col(n.row);
    h.push('<g class="nd'+(n.key===on?' on':'')+'" data-k="'+n.key+'"><title>'+esc(tip(n))+'</title><circle cx="'+x+'" cy="'+y+
      '" r="'+rr+'" stroke="'+cl+'"/>'+(f>=1?'<circle cx="'+x+'" cy="'+y+'" r="'+(rr-1)+'" fill="'+cl+'"/>':f>0.02?'<path fill="'+cl+
      '" d="M'+x+','+y+'L'+x+','+(y-rr+1)+'A'+(rr-1)+','+(rr-1)+' 0 '+(f>0.5?1:0)+',1 '+(x+(rr-1)*Math.sin(2*Math.PI*f)).toFixed(2)+
      ','+(y-(rr-1)*Math.cos(2*Math.PI*f)).toFixed(2)+'Z"/>':'')+(n.key===on?'<circle class="halo" cx="'+x+'" cy="'+y+'" r="'+(rr+4)+
      '"/>':'')+'</g>');});
  if(full)labels(V,h,on);
  var s=$('svg'),pk=null,hp={};
  s.innerHTML='<defs><clipPath id="cc" clipPathUnits="objectBoundingBox"><circle cx=".5" cy=".5" r=".5"/></clipPath></defs>'+h.join('');
  // a selection below the root keeps its path from the root and its own clade in colour and dims the rest
  V.all.forEach(function(n){if(n.key===on)pk=n;});
  s.classList.toggle('picked',!!(pk&&pk.parent));if(!pk||!pk.parent)return;
  V.all.forEach(function(n){for(var x=n;x;x=x.parent)if(x===pk)return hp[n.key]=1;});
  for(var x=pk;x;x=x.parent)hp[x.key]=1;
  [].forEach.call(s.querySelectorAll('[data-k]'),function(e){if(hp[e.getAttribute('data-k')])e.classList.add('hp');});
}
// Tip labels (the latin name) run outward only where a tip's slot is a full line high, so none overlap; the
// outline and the hover name the rest.
// A tip's rim label keeps its full name as iTOL and OneZoom do: the type shrinks from 11px to MINF px to fit the slot and
// the room to the label ring and canvas edge. th when the photo fits beside the name at MINF px, fs the type size, w the
// pixels photo and text take, nw the full name's width at MINF px; null when the slot is less than a MINF px line high;
// no text when the name does not fit whole even at MINF px.
function rim(n,g){var room=(n.a1-n.a0)*g.RL,b=Math.min(g.lab,edge(g,n.a)-g.RL-6);if(n.kids.length||room<MINF+3)return null;
  var nm=n.row>=0&&grpOf(n.row)?'':n.row<0?'+'+nf.format(n.more)+' more':cname(n.row,M.name(D,n.row)),
    nw=nm?CX.measureText(fit(nm,Infinity)).width*MINF/11:0;if(nw>b-1)return {txt:'',w:0,nw:nw};
  var th=room>=TH+2&&n.row>=0&&b>=TH+4+nw,o=th?TH+4:0,
    fs=Math.max(MINF,Math.min(11,room-3,nw?MINF*(b-o-1)/nw:11)),txt=nm&&fit(nm,(b-o)*11/fs);
  return {th:th,txt:txt,fs:fs,nw:nw,w:o+(txt?CX.measureText(txt).width*fs/11:0)};}
function labels(V,h,on){
  var g=V.g,box=[];
  V.all.forEach(function(n){var t=rim(n,g);if(!t)return;
    var id=n.row<0?0:M.id(D,n.row),ph=id&&PH[id],th=t.th,txt=t.txt,deg=n.a*180/Math.PI-90,left=Math.sin(n.a)<0,x0=g.RL+(th?TH+4:0);
    if(th)want(id);
    if(th&&ph&&ph.ok){var c=P(g,n.a,g.RL+TH/2).split(',');h.push('<image data-k="'+n.key+'" href="'+esc(ph.sq)+'" x="'+(c[0]-TH/2)+'" y="'+
      (c[1]-TH/2)+'" width="'+TH+'" height="'+TH+'" clip-path="url(#cc)" preserveAspectRatio="xMidYMid slice"/>');}
    if(txt)h.push('<text class="lb'+(n.key===on?' on':'')+'" data-k="'+n.key+'"'+(t.fs<11?' font-size="'+t.fs.toFixed(1)+'"':'')+' dy=".32em" transform="translate('+g.cx+','+g.cy+') rotate('+
      (left?deg+180:deg).toFixed(2)+')" x="'+(left?-x0:x0)+'"'+(left?' text-anchor="end"':'')+'><title>'+esc(tip(n))+'</title>'+
      esc(txt)+'</text>');});
  // the inner labels show whole or not at all, by their screen boxes (a line of 11px type is 14px high): the selection and
  // its ancestors first, always, then the life groups, then the biggest clades; a hidden one keeps its name on hover. The
  // ring names (species, genus, ...) give way to them. 3px more width keeps a gap and fits the bolder selected label.
  var hit=function(b){return box.some(function(o){return b[0]<o[2]&&o[0]<b[2]&&b[1]<o[3]&&o[1]<b[3];});},
    out=function(b){return [0,2].some(function(i){return [1,3].some(function(j){return Math.hypot(b[i]-g.cx,b[j]-g.cy)>g.RL-2;});});},
    up={};V.all.forEach(function(n){if(n.key===on)for(var x=n;x;x=x.parent)up[x.key]=1;});
  V.all.filter(function(n){return n.row>=0&&(n.kids.length||grpOf(n.row));}).map(function(n){return [n,n.parent?grpOf(n.row):'',up[n.key]||0];})
    .sort(function(a,b){return b[2]-a[2]||!a[1]-!b[1]||b[0].tot-a[0].tot;}).slice(0,60).forEach(function(q){
    var n=q[0],xy=P(g,n.a,n.r).split(','),x=+xy[0],y=+xy[1],
      txt=fit(q[1]||(n.parent?cname(n.row,label(n.row)):M.name(D,n.row)+' · '+recs(n.tot)),Infinity,1),
      w=CX.measureText(txt).width+3,right=Math.sin(n.a)>=-0.01,
      at=function(r,d){return n.parent?[r?x+7:x-7-w,y-16+d,r?x+7+w:x-7,y-2+d]:[x-w/2,y+8+d,x+w/2,y+22+d];},
      // the groups move up or down a line or two, the selection's line also to the node's other side
      cs=[0,14,-14,28,-28].slice(0,q[1]||q[2]?5:1).reduce(function(a,d){return a.concat([at(right,d)],q[2]?[at(!right,d)]:[]);},[]),
      b=cs.filter(function(c){return !hit(c)&&(!n.parent||!out(c));})[0]||q[2]&&(cs.filter(function(c){return !hit(c);})[0]||cs[0]);
    if(!txt||!b)return;
    box.push(b);
    h.push('<text class="lb in'+(n.key===on?' on':'')+'" data-k="'+n.key+'" x="'+b[0].toFixed(1)+'" y="'+(b[3]-3).toFixed(1)+'"><title>'+
      esc(tip(n))+'</title>'+esc(txt)+'</text>');});
  CX.font='10px '+getComputedStyle(document.body).fontFamily;
  V.rk.forEach(function(r){var b=[r[0],r[1]-10,r[0]+CX.measureText(r[2]).width,r[1]+3];
    if(!hit(b)&&box.push(b))h.push('<text class="rk" x="'+r[0]+'" y="'+r[1]+'">'+r[2]+'</text>');});
}
// ---- photos: iNaturalist's default photo per taxon, at most 30 taxa a request and a request a second; an
// image shows only once it has loaded, and a taxon that failed is not asked again.
function want(id){if(id&&!(id in PH)&&Q.indexOf(id)<0)Q.push(id);
  if(Q.length&&!qt)qt=setTimeout(flush,Math.max(0,qlast+1000-Date.now()));}
function flush(){
  qt=0;qlast=Date.now();var ids=Q.splice(0,30);ids.forEach(function(i){PH[i]=null;});
  fetch('https://api.inaturalist.org/v1/taxa/'+ids.join(',')).then(function(r){if(!r.ok)throw new Error(r.status);return r.json();})
    .then(function(j){(j.results||[]).forEach(function(t){var p=t.default_photo;if(!p||!p.square_url)return;
      var o=PH[t.id]={sq:p.square_url,md:p.medium_url||p.square_url,by:p.attribution||'',ok:false},im=new Image();
      im.onload=function(){o.ok=true;later();};im.src=o.sq;});})
    .catch(function(){}).then(function(){want(0);});}
function later(){if(!lt)lt=setTimeout(function(){lt=0;if(V&&!anim)render(V,null);photos();},200);}
function photos(){[].forEach.call(document.querySelectorAll('[data-ph]'),function(el){var p=PH[el.dataset.ph];
  if(!p||!p.ok||el.dataset.done)return;el.dataset.done=1;var im=new Image();im.alt='';
  im.src=el.classList.contains('big')?p.md:p.sq;el.textContent='';el.appendChild(im);
  if(el.classList.contains('big')){if(p.by){var c=document.createElement('small');c.textContent=p.by;el.appendChild(c);}im.onload=seen;}});}
// ---- the card of the selected taxon
function el(tag,attrs,kids){var e=document.createElement(tag);for(var k in attrs||{})e.setAttribute(k,attrs[k]);
  (kids||[]).forEach(function(c){if(c!=null)e.appendChild(typeof c==='string'?document.createTextNode(c):c);});return e;}
function card(){
  var c=$('card');c.textContent='';if(S.sel<0){c.hidden=true;return;}c.hidden=false;
  var e=M.lead(D,S.sel),id=M.id(D,e),tot=D.tot[e],own=D.own[e],k=rk(e),cm=cmn(e),ks=D.kids[e],f=M.lead(D,S.focus),
    pk=M.pick(D,e),gp=/^groups=/.test(pk)?pk.slice(7):'',
    hd=cm||M.name(D,e),sub=gp===M.REST?'Records not identified past Life, or with no taxon.':label(e)+(k?' · '+k:'');
  if(id)want(id);
  var link=function(href,text,cls){return el('a',{'class':'btn '+(cls||''),href:href,target:EMBED?'_blank':'_self',rel:'noopener'},[text]);};
  var btn=function(text,fn){var b=el('button',{type:'button','class':'btn'},[text]);b.addEventListener('click',fn);return b;};
  var acts=el('div',{'class':'actions'});
  // a group's node opens its iconic taxon, as its chip on the map does (Other animals and Unknown are not one
  // taxon), any other node its taxon less the groups taken out from under it, as M.pick
  if(id){acts.appendChild(link(TX.identifyUrl({groups:gp?[gp]:[],all:META.groups.length,months:[],only:{},acc:'',taxa:gp?[]:[id],not:gp?[]:D.ex[e]||[]},null,META).url,
    'Help identify on iNaturalist','primary'));acts.lastChild.target='_blank';
    if(!(EMBED&&SY)){acts.appendChild(link(CFG.mapUrl+'#'+pk,'Show on map'));
      if(split)acts.appendChild(link('split.html?view=space#'+pk,'Show in photo space'));}}
  if(id&&!EMBED&&CT.has(id))acts.appendChild(link('confusion.html#t'+id,'Often confused with \u2026'));
  if(e!==f&&ks.length)acts.append(btn('Focus here',function(){focusOn(e);}),
    btn(S.open.has(e)?'Close':'Open',function(){act(String(e),'toggle',true);}));
  if(ks.length)acts.appendChild(btn('Open more below',function(){act(String(e),'expand');}));
  // a taxon above or below selects in place, like a click on the circle
  var pick=function(x){S.sel=x;M.reveal(D,S,x);go(true,true);},row=function(x,cn){var i=M.id(D,x),b=el('button',{type:'button'},[
    el('span',{'class':'th','data-ph':i}),el('span',{'class':'nm'},[e===D.root&&M.common(D,x)||label(x),cn&&cmn(x)?el('span',{'class':'cm'},[' '+cmn(x)]):null]),el('span',{'class':'tc'},[nf.format(D.tot[x])])]);want(i);
    b.addEventListener('click',function(){pick(x);});return el('li',{},[b]);};
  var kids=el('ul',{'class':'kids','aria-label':'Biggest taxa below'});
  ks.slice(0,e===D.root?ks.length:6).forEach(function(k){kids.appendChild(row(M.lead(D,k)));});
  // the path up to the grandparent (Part of names the parent), its middle folded into a … that unfolds
  var up=M.crumbs(D,e).map(function(p){return M.lead(D,p);}),pp=up.slice(0,-1),path=el('nav',{'class':'path','aria-label':'Taxa above'});
  (function fill(all){path.textContent='';(all||pp.length<5?pp:[pp[0],-1].concat(pp.slice(-2))).forEach(function(x,i){
    var b=el('button',{type:'button','class':'link'},[x<0?'…':cut(M.name(D,x),24)]);if(i)path.appendChild(document.createTextNode(' › '));
    if(x<0){b.title=pp.slice(1,-2).map(function(y){return M.name(D,y);}).join(' › ');b.setAttribute('aria-label','Show all taxa above');}
    b.addEventListener('click',function(){if(x<0)fill(true);else pick(x);});path.appendChild(b);});})();
  var x=el('button',{type:'button','class':'x','aria-label':'Close'},['×']);x.addEventListener('click',function(){S.sel=-1;go(false,true);});
  [x,id?el('div',{'class':'ph big','data-ph':id},['']):null,el('div',{'class':'body'},[
    pp.length?path:null,el('h2',{},[hd]),sub===hd?null:el('p',{'class':'muted'},[sub]),
    el('dl',{},[el('dt',{},['Need an ID']),el('dd',{},[nf.format(tot)]),
      el('dt',{},['Share of all needing ID']),el('dd',{},[pct(tot)]),
      el('dt',{},['Identified only to this rank']),el('dd',{},[nf.format(own)+(tot?' ('+pct(own,tot)+')':'')]),
      e===D.nr&&D.none?el('dt',{},['No taxon']):null,e===D.nr&&D.none?el('dd',{},[nf.format(D.none)]):null,
      el('dt',{},['Species below']),el('dd',{},[nf.format(D.sp[e])])]),
    acts,up.length?el('p',{'class':'muted'},['Part of']):null,up.length?el('ul',{'class':'kids up','aria-label':'Part of'},[row(up[up.length-1],1)]):null,
    ks.length?el('p',{'class':'muted'},[shown(e)]):null,ks.length?el('p',{'class':'muted'},[e===D.root?'Groups, as on the map':'Biggest below']):null,ks.length?kids:null])].forEach(function(n){if(n)c.appendChild(n);});
  photos();
}
// How much below e the circle shows. Open more below stops at family (order for insects) and at BUDGET tips.
function shown(e){var all=0,on=0,nd=null;V.all.forEach(function(n){if(n.key===String(e))nd=n;});
  (function cnt(r){D.kids[r].forEach(function(c){if(D.tot[c]){all++;cnt(M.lead(D,c));}});})(e);
  (function cnt(n){n.kids.forEach(function(c){if(c.row>=0){on++;cnt(c);}});})(nd||{kids:[]});
  var tx=nf.format(all)+(all===1?' taxon':' taxa');
  return on>=all?'The circle shows all '+tx+' below.':!on?'Its '+tx+' below are not on the circle yet: Open shows the next rank, Open more below as many as fit.':'The circle shows '+nf.format(on)+' of the '+tx+' below. Open more below goes down to family (order for insects) as far as fits; open or focus a taxon to go deeper.';}
// ---- the outline: the same shown tree as an ARIA tree, with a roving tab stop
function outline(){
  var o=$('outline'),had=o.contains(document.activeElement)?document.activeElement.dataset.k:null,
    on=S.sel>=0?String(M.lead(D,S.sel)):V.root.key,h=[];
  (function li(n,lv){var ex=n.row>=0&&D.kids[n.row].length?' aria-expanded="'+n.open+'"':'';
    h.push('<li role="treeitem" aria-level="'+lv+'"'+ex+' aria-selected="'+(n.key===on)+'" tabindex="'+(n.key===on?0:-1)+
      '" data-k="'+n.key+'" style="--lv:'+lv+'"><span class="row" title="'+esc(tip(n))+'"><span class="tw" aria-hidden="true">'+(ex?n.open?'▾':'▸':'')+'</span><i style="background:'+
      col(rowOf(n))+'"></i><span class="nm">'+esc(n.row<0?'+'+nf.format(n.more)+' more taxa':label(n.row))+
      (n.row>=0&&cmn(n.row)?' <span class="cm">'+esc(cmn(n.row))+'</span>':'')+'</span><span class="tc" style="--s:'+(100*n.tot/D.tot[D.root]).toFixed(2)+'%;--c:'+col(rowOf(n))+'" title="'+
      recs(n.tot)+', '+pct(n.tot)+' of all needing ID">'+nc.format(n.tot)+'<span class="p"> · '+pct(n.tot)+'</span></span></span>');
    if(n.kids.length){h.push('<ul role="group">');n.kids.forEach(function(k){li(k,lv+1);});h.push('</ul>');}
    h.push('</li>');})(V.root,1);
  o.innerHTML=h.join('');
  if(had){var f=o.querySelector('[data-k="'+had+'"]')||o.querySelector('[tabindex="0"]');if(f)f.focus();}
  if(on!==OL){OL=on;seen();}
}
// A new selection, from the card, the circle or the map, brings its row into view below the pinned rows; again once the
// card's photo has pushed the outline down on a phone.
function seen(){var r=$('outline').querySelector('[aria-selected="true"]>.row');if(!r)return;
  var sd=$('side').getBoundingClientRect(),b=r.getBoundingClientRect(),pin=Math.min(4,r.parentNode.getAttribute('aria-level')-1)*28;
  if(b.top<sd.top+pin||b.bottom>sd.bottom)r.scrollIntoView({block:'center'});}
function items(){return [].slice.call($('outline').querySelectorAll('[role=treeitem]'));}
function move(to){if(!to)return;items().forEach(function(i){i.tabIndex=-1;});to.tabIndex=0;to.focus();}
$('outline').addEventListener('click',function(e){var t=e.target.closest('[data-k]');if(!t)return;
  act(t.dataset.k,e.target.closest('.tw')||t.dataset.k[0]==='+'?'toggle':'select');});
$('outline').addEventListener('keydown',function(e){
  var t=e.target.closest('[role=treeitem]');if(!t)return;var all=items(),i=all.indexOf(t),k=t.dataset.k,ex=t.getAttribute('aria-expanded');
  if(e.key==='ArrowDown')move(all[i+1]);else if(e.key==='ArrowUp')move(all[i-1]);
  else if(e.key==='Home')move(all[0]);else if(e.key==='End')move(all[all.length-1]);
  else if(e.key==='ArrowRight'){if(ex==='false')act(k,'toggle',true);else if(ex==='true')move(all[i+1]);}
  else if(e.key==='ArrowLeft'){if(ex==='true')act(k,'toggle',true);else move(t.parentNode.closest('[role=treeitem]'));}
  else if(e.key==='Enter'||e.key===' ')act(k,k[0]==='+'?'toggle':'select');
  else return;
  e.preventDefault();});
// ---- actions and the address
function act(key,how,keep){
  status('');
  if(key[0]==='+'){M.more(S,+key.slice(1));return go(true,false);}
  var r=+key;if(!keep)S.sel=r;
  if(how==='expand'){if(M.expandBelow(D,S,r,BUDGET))status('Opened as much as fits. Focus on a smaller taxon to open more.');}
  else if(how==='toggle')M.toggle(D,S,r);
  go(true,how!=='toggle');
}
function focusOn(r){S.focus=r;if(!S.open.has(r))M.toggle(D,S,r);go(true,true);}
// A focus with nothing below moves up to its parent and selects itself; a closed focus opens.
function settle(){var f=M.lead(D,S.focus),c=M.crumbs(D,f);
  if(!D.kids[f].length&&c.length){if(S.sel<0)S.sel=f;S.focus=f=c[c.length-1];M.reveal(D,S,S.sel);}
  if(!S.open.has(f))M.toggle(D,S,f);}
// With no address the page opens on the root selected, so the card names the biggest taxa below.
function readHash(){S=M.read(D,location.hash,GS);if(!location.hash.slice(1))S.sel=M.lead(D,D.root);settle();}
function reread(){readHash();share();draw(true);}
function go(animate,push){
  settle();var base=location.pathname+location.search,h=M.write(D,S),u=base+(h?'#'+h:'');
  if(u!==base+location.hash)history[push?'pushState':'replaceState'](null,'',u);
  share();draw(animate);
}
// in the split view a new selection is the map's and the photo space's too
function share(){
  if(SY&&S.sel!==PS){PS=S.sel;SEL=SEL.split('&').filter(function(t){return !/^(taxa|groups)=/.test(t);})
    .concat(M.pick(D,S.sel)).filter(Boolean).join('&');SY.send();}}
function crumbs(){
  var c=$('crumbs'),f=M.lead(D,S.focus),path=M.crumbs(D,f).concat(f);c.textContent='';
  path.forEach(function(r,i){var b=el('button',{type:'button','class':'link'},[cut(M.name(D,M.chain(D,r).pop()),24)]);
    if(r===f)b.setAttribute('aria-current','true');else b.addEventListener('click',function(){focusOn(r);});
    if(i)c.appendChild(document.createTextNode(' › '));c.appendChild(b);});
  $('up').disabled=path.length<2;
}
var svg=$('svg');
// A click selects and leaves the layout as it is (a more node pages on), shift+click opens below and a
// double-click opens or closes; a click on the background or Esc clears the selection.
function clear(){if(S&&S.sel>=0){S.sel=-1;go(false,true);}}
svg.addEventListener('click',function(e){var t=e.target.closest('[data-k]');if(!t)return clear();
  act(t.dataset.k,t.dataset.k[0]==='+'?'toggle':e.shiftKey?'expand':'select');});
svg.addEventListener('dblclick',function(e){var t=e.target.closest('[data-k]');if(t&&t.dataset.k[0]!=='+')act(t.dataset.k,'toggle',true);});
addEventListener('keydown',function(e){if(e.key==='Escape'&&!(e.target.closest&&e.target.closest('input')))clear();});
$('up').addEventListener('click',function(){var c=M.crumbs(D,M.lead(D,S.focus));if(c.length)focusOn(c[c.length-1]);});
$('collapse').addEventListener('click',function(){S.open=new Map([[M.lead(D,S.focus),1]]);go(true,false);});
$('reset').addEventListener('click',function(){S=M.home(D,GS);S.sel=M.lead(D,D.root);go(true,true);});
$('mode').addEventListener('click',function(){var r=document.body.classList.toggle('radial');
  this.setAttribute('aria-pressed',String(r));draw(false);});
$('info').addEventListener('click',function(){var a=$('about');a.hidden=!a.hidden;this.setAttribute('aria-expanded',String(!a.hidden));});
function back(){if(D)reread();}
addEventListener('popstate',back);addEventListener('hashchange',back);
var rz=0;new ResizeObserver(function(){if(!rz)rz=requestAnimationFrame(function(){rz=0;if(V)draw(false);});}).observe($('radial'));
var picks=[];
TX.picker({input:$('q'),list:$('sugg'),msg:$('qn'),picks:picks,ranks:META.ranks,nf:nf,
  taxa:function(){return D&&D.T;},counts:function(){return D.tot;},onChange:function(){picks.length=0;},
  onPick:function(r){if(!D.tot[r])return status('No record of this taxon needs an ID.');S.sel=r;M.reveal(D,S,r);go(true,true);}});
// The map's selection selects its taxon or group here; one this side already shows is left as it is.
// The groups the map leaves out leave the tree too; a focus or selection inside one goes back to the root.
var D0=null,EX='';
// taxa with a row on confusion.html; absent on a site built without it
fetch('confusion-taxa.json').then(function(r){return r.ok?r.json():[];}).then(function(a){CT=new Set(a);}).catch(function(){});
function groupsOut(){return SEL.split('&').filter(function(t){return /^groups=/.test(t);}).map(function(t){return t.slice(7);}).join(',')
  .split(',').filter(function(x){return x[0]==='-';}).map(function(x){return decodeURIComponent(x.slice(1));}).sort().join(',');}
function take(){var ex=groupsOut();
  if(ex!==EX){EX=ex;D=M.without(D0,ex?ex.split(','):[]);groupRows();if(!D.tot[S.focus])S.focus=D.root;if(S.sel>=0&&!D.tot[S.sel])S.sel=-1;}
  var r=M.find(D,SEL);if(r!==S.sel){S.sel=r;if(r>=0)M.reveal(D,S,r);}PS=S.sel;}
function groupRows(){GS=Object.keys(G).map(function(i){return D.row.get(+i);}).filter(function(x){return x!=null&&D.tot[x];});}
if(EMBED&&parent!==window)SY=MapFilter.sync({hash:false,key:function(){return SEL;},apply:function(s){SEL=s;if(D){take();draw(true);}}});
async function load(){
  status('Loading the taxa…');
  var has=fetch('split.html',{method:'HEAD'}).then(function(r){return r.ok;},function(){return false;});
  var r=await fetch(new URL(META.taxa,location.href));if(!r.ok)throw new Error('the taxa file answered '+r.status);
  var T=JSON.parse(new TextDecoder().decode(await L.gunzip(await r.arrayBuffer())));
  if(!T.length||T[0].length<6)throw new Error('this site was built without the taxon tree');
  Object.keys(META.group_ids||{}).forEach(function(g){G[META.group_ids[g]]=g;});
  if(META.groups.indexOf('Animalia')>=0)G[1]=G[1]||'Animalia';  // iNaturalist's iconic Animalia: kingdom 1, less the other groups
  D=D0=M.build(T,META.ranks,G,{order:META.groups,names:META.names,total:META.n});groupRows();
  readHash();if(SY){SEL=SEL||MapFilter.tokens(location.hash);take();if(S.sel<0)S.sel=PS=M.lead(D,D.root);}split=await has;status('');draw(false);
}
load().catch(function(e){status('The tree could not load: '+e.message);});
})();
