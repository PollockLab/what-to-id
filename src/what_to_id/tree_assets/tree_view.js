// The tree of life page: the radial tree of record counts (tree_model.js), the outline that mirrors it for the
// keyboard and for phones, the card of the selected taxon and the photos iNaturalist has for each tip. Inside
// the split view (?embed=1) "Show on map" sends the taxon as the shared selection, as the photo space does.
(function(){
'use strict';
var M=TreeModel,L=EmbeddingsLayout,META=CFG.meta,nf=new Intl.NumberFormat('en'),EMBED=/[?&]embed=1/.test(location.search),
  BUDGET=400,BAR=26,TH=24,reduce=matchMedia('(prefers-reduced-motion: reduce)'),
  D=null,S=null,V=null,G={},GS=[],COL=new Map(),prev=null,anim=0,SEL='',SY=null,PS=-1,PH={},Q=[],qt=0,qlast=0,lt=0,split=false;
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
function recs(n){return nf.format(n)+(n===1?' record':' records');}
function tip(n){
  if(n.row<0)return '+'+nf.format(n.more)+' more taxa ('+recs(n.tot)+')';
  var r=n.row,cm=cmn(r),rk=M.rank(D,r);
  return label(r)+(cm?' ('+cm+')':'')+(rk?', '+rk:'')+': '+recs(n.tot)+' need ID'+(n.own?', '+nf.format(n.own)+' only to here':'');}
// ---- the radial tree
function geo(){var b=$('radial'),W=b.clientWidth,H=b.clientHeight,R=Math.max(60,Math.min(W,H)/2-6),
  lab=Math.max(46,Math.min(120,R*0.26)),R1=Math.max(24,R-BAR-10-lab);
  return {W:W,H:H,cx:W/2,cy:H/2,R1:R1,RL:R1+BAR+8,lab:lab};}
function P(g,a,r){return (g.cx+r*Math.sin(a)).toFixed(1)+','+(g.cy-r*Math.cos(a)).toFixed(1);}
function arc(g,r,a0,a1,sweep){return r<0.5||a0===a1?'':'A'+r.toFixed(1)+','+r.toFixed(1)+' 0 '+(Math.abs(a1-a0)>Math.PI?1:0)+','+
  sweep+' '+P(g,a1,r);}
function sector(g,a0,a1,r0,r1){return 'M'+P(g,a0,r1)+arc(g,r1,a0,a1,1)+'L'+P(g,a1,r0)+arc(g,r0,a1,a0,0)+'Z';}
function draw(animate){
  if(!D)return;
  var g=geo();
  V=M.layout(M.view(D,S),0,2*Math.PI,13/g.RL);
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
  if(full){var last=0;M.RINGS.forEach(function(x,i){if(x[1]<=V.t0||x[1]>V.tm+1e-9)return;var r=(x[1]-V.t0)*V.k;
    if(i%2)h.push('<circle class="band" cx="'+g.cx+'" cy="'+g.cy+'" r="'+((r+last)/2).toFixed(1)+'" stroke-width="'+(r-last).toFixed(1)+'"/>');
    h.push('<circle class="ring" cx="'+g.cx+'" cy="'+g.cy+'" r="'+r.toFixed(1)+'"/><text class="rk" x="'+(g.cx+3)+'" y="'+
      (g.cy-r-3).toFixed(1)+'">'+x[0]+'</text>');last=r;});
    V.all.forEach(function(n){if(n.kids.length)return;var w=n.a1-n.a0,pad=Math.min(0.15*w,0.004),c=col(rowOf(n));
      if(n.row<0||D.kids[n.row].length)h.push('<path class="wd'+(n.row<0?' more':'')+'" data-k="'+n.key+'" fill="'+c+'" stroke="'+c+
        '" d="'+sector(g,n.a0+pad,n.a1-pad,n.r,Math.max(n.rl,n.r+4))+'"/>');
      var len=BAR*Math.log(n.tot+1)/max,bw=Math.max(1,Math.min(8,w*g.R1*0.6));
      h.push('<path class="br" data-k="'+n.key+'" stroke="'+c+'" stroke-width="'+bw.toFixed(1)+'" d="M'+P(g,n.a,g.R1+4)+'L'+
        P(g,n.a,g.R1+4+Math.max(1,len))+'"/>');});}
  V.all.forEach(function(n){if(!n.parent)return;var p=at(n.parent),c=at(n);
    h.push('<path class="lk" stroke="'+col(rowOf(n))+'" d="M'+P(g,p.a,p.r)+arc(g,p.r,p.a,c.a,c.a>p.a?1:0)+'L'+P(g,c.a,c.r)+'"/>');});
  V.all.forEach(function(n){if(n.row<0)return;var c=at(n),xy=P(g,c.a,c.r).split(','),x=+xy[0],y=+xy[1],
    rr=n.key===on?6:n.parent?3.5:5,f=n.tot?n.own/n.tot:0,cl=col(n.row);
    h.push('<g class="nd'+(n.key===on?' on':'')+'" data-k="'+n.key+'"><title>'+esc(tip(n))+'</title><circle cx="'+x+'" cy="'+y+
      '" r="'+rr+'" stroke="'+cl+'"/>'+(f>=1?'<circle cx="'+x+'" cy="'+y+'" r="'+(rr-1)+'" fill="'+cl+'"/>':f>0.02?'<path fill="'+cl+
      '" d="M'+x+','+y+'L'+x+','+(y-rr+1)+'A'+(rr-1)+','+(rr-1)+' 0 '+(f>0.5?1:0)+',1 '+(x+(rr-1)*Math.sin(2*Math.PI*f)).toFixed(2)+
      ','+(y-(rr-1)*Math.cos(2*Math.PI*f)).toFixed(2)+'Z"/>':'')+'</g>');});
  if(full)labels(V,h,on);
  $('svg').innerHTML='<defs><clipPath id="cc" clipPathUnits="objectBoundingBox"><circle cx=".5" cy=".5" r=".5"/></clipPath></defs>'+h.join('');
}
// Tip labels run outward where a tip has room for a line (and a photo where it has room for one); the inner
// labels go biggest first, each only where it overlaps none placed before it.
function labels(V,h,on){
  var g=V.g,box=[];
  V.all.forEach(function(n){if(n.kids.length)return;var room=(n.a1-n.a0)*g.RL;if(room<11)return;
    var id=n.row<0?0:M.id(D,n.row),ph=id&&PH[id],th=room>=TH+2&&n.row>=0,deg=n.a*180/Math.PI-90,left=n.a>Math.PI,
      x0=g.RL+(th?TH+4:0),txt=n.row<0?'+'+nf.format(n.more)+' more':label(n.row)+(cmn(n.row)?' ('+cmn(n.row)+')':'');
    if(th)want(id);
    if(ph&&ph.ok){var c=P(g,n.a,g.RL+TH/2).split(',');h.push('<image data-k="'+n.key+'" href="'+esc(ph.sq)+'" x="'+(c[0]-TH/2)+'" y="'+
      (c[1]-TH/2)+'" width="'+TH+'" height="'+TH+'" clip-path="url(#cc)" preserveAspectRatio="xMidYMid slice"/>');}
    h.push('<text class="lb'+(n.key===on?' on':'')+'" data-k="'+n.key+'" dy=".32em" transform="translate('+g.cx+','+g.cy+') rotate('+
      (left?deg+180:deg).toFixed(2)+')" x="'+(left?-x0:x0)+'"'+(left?' text-anchor="end"':'')+'><title>'+esc(tip(n))+'</title>'+
      esc(cut(txt,Math.floor((g.lab-(th?TH+4:0))/6.2)))+'</text>');});
  V.all.filter(function(n){return n.kids.length;}).sort(function(a,b){return b.tot-a.tot;}).slice(0,60).forEach(function(n){
    var xy=P(g,n.a,n.r).split(','),x=+xy[0],y=+xy[1],txt=cut(n.parent?label(n.row):M.name(D,n.row)+' · '+recs(n.tot),32),
      w=txt.length*6.2,right=Math.sin(n.a)>=-0.01,b=[right?x+7:x-7-w,y-15,right?x+7+w:x-7,y-3];
    if(!n.parent)b=[x-w/2,y+8,x+w/2,y+20];
    if(box.some(function(o){return b[0]<o[2]&&o[0]<b[2]&&b[1]<o[3]&&o[1]<b[3];}))return;box.push(b);
    h.push('<text class="lb in'+(n.key===on?' on':'')+'" data-k="'+n.key+'" x="'+b[0].toFixed(1)+'" y="'+(b[3]-2).toFixed(1)+'"><title>'+
      esc(tip(n))+'</title>'+esc(txt)+'</text>');});
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
  if(el.classList.contains('big')&&p.by){var c=document.createElement('small');c.textContent=p.by;el.appendChild(c);}});}
// ---- the card of the selected taxon
function el(tag,attrs,kids){var e=document.createElement(tag);for(var k in attrs||{})e.setAttribute(k,attrs[k]);
  (kids||[]).forEach(function(c){if(c!=null)e.appendChild(typeof c==='string'?document.createTextNode(c):c);});return e;}
function card(){
  var c=$('card');c.textContent='';if(S.sel<0){c.hidden=true;return;}c.hidden=false;
  var e=M.lead(D,S.sel),id=M.id(D,e),tot=D.tot[e],own=D.own[e],rk=M.rank(D,e),cm=cmn(e),ks=D.kids[e];
  if(id)want(id);
  var link=function(href,text,cls){return el('a',{'class':'btn '+(cls||''),href:href,target:EMBED?'_blank':'_self',rel:'noopener'},[text]);};
  var btn=function(text,fn){var b=el('button',{type:'button','class':'btn'},[text]);b.addEventListener('click',fn);return b;};
  var acts=el('div',{'class':'actions'});
  if(id){acts.appendChild(link(TX.identifyUrl({groups:[],all:0,months:[],only:{},acc:'',taxa:[id],not:[]},null,META).url,
    'Help identify on iNaturalist','primary'));acts.lastChild.target='_blank';
    if(!(EMBED&&SY)){acts.appendChild(link(CFG.mapUrl+'#taxa='+id,'Show on map'));
      if(split)acts.appendChild(link('split.html?view=space#taxa='+id,'Show in photo space'));}}
  if(e!==M.lead(D,S.focus))acts.appendChild(btn('Focus here',function(){focusOn(e);}));
  if(ks.length)acts.appendChild(btn('Expand all below',function(){act(String(e),'expand');}));
  var kids=el('ul',{'class':'kids','aria-label':'Biggest taxa below'});
  ks.slice(0,e===D.root?ks.length:6).forEach(function(k){var x=M.lead(D,k),i=M.id(D,x),b=el('button',{type:'button'},[el('span',{'class':'th','data-ph':i}),
    el('span',{'class':'nm'},[e===D.root&&M.common(D,x)||label(x)]),el('span',{'class':'tc'},[nf.format(D.tot[x])])]);want(i);
    b.addEventListener('click',function(){S.sel=x;M.reveal(D,S,x);go(true,true);});kids.appendChild(el('li',{},[b]));});
  var x=el('button',{type:'button','class':'x','aria-label':'Close'},['×']);x.addEventListener('click',function(){S.sel=-1;go(false,true);});
  [x,id?el('div',{'class':'ph big','data-ph':id},['']):null,el('div',{'class':'body'},[
    el('h2',{},[cm||M.name(D,e)]),el('p',{'class':'muted'},[label(e)+(rk?' · '+rk:'')]),
    el('dl',{},[el('dt',{},['Need an ID']),el('dd',{},[nf.format(tot)]),
      el('dt',{},['Identified only to this rank']),el('dd',{},[nf.format(own)+(tot?' ('+Math.round(100*own/tot)+'%)':'')]),
      el('dt',{},['Species below']),el('dd',{},[nf.format(D.sp[e])])]),
    acts,ks.length?el('p',{'class':'muted'},[e===D.root?'Groups, as on the map':'Biggest below']):null,ks.length?kids:null])].forEach(function(n){if(n)c.appendChild(n);});
  photos();
}
// ---- the outline: the same shown tree as an ARIA tree, with a roving tab stop
function outline(){
  var o=$('outline'),had=o.contains(document.activeElement)?document.activeElement.dataset.k:null,
    on=S.sel>=0?String(M.lead(D,S.sel)):V.root.key,h=[];
  (function li(n,lv){var ex=n.row>=0&&D.kids[n.row].length?' aria-expanded="'+n.open+'"':'';
    h.push('<li role="treeitem" aria-level="'+lv+'"'+ex+' aria-selected="'+(n.key===on)+'" tabindex="'+(n.key===on?0:-1)+
      '" data-k="'+n.key+'"><span class="row"><span class="tw" aria-hidden="true">'+(ex?n.open?'▾':'▸':'')+'</span><i style="background:'+
      col(rowOf(n))+'"></i><span class="nm">'+esc(n.row<0?'+'+nf.format(n.more)+' more taxa':label(n.row))+
      (n.row>=0&&cmn(n.row)?' <span class="cm">'+esc(cmn(n.row))+'</span>':'')+'</span><span class="tc">'+nf.format(n.tot)+
      '</span></span>');
    if(n.kids.length){h.push('<ul role="group">');n.kids.forEach(function(k){li(k,lv+1);});h.push('</ul>');}
    h.push('</li>');})(V.root,1);
  o.innerHTML=h.join('');
  if(had){var f=o.querySelector('[data-k="'+had+'"]')||o.querySelector('[tabindex="0"]');if(f)f.focus();}
}
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
function go(animate,push){
  var base=location.pathname+location.search,h=M.write(D,S),u=base+(h?'#'+h:'');
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
svg.addEventListener('click',function(e){var t=e.target.closest('[data-k]');if(t)act(t.dataset.k,e.shiftKey&&t.dataset.k[0]!=='+'?'expand':'toggle');});
svg.addEventListener('dblclick',function(e){var t=e.target.closest('[data-k]');if(t&&t.dataset.k[0]!=='+')focusOn(+t.dataset.k);});
$('up').addEventListener('click',function(){var c=M.crumbs(D,M.lead(D,S.focus));if(c.length)focusOn(c[c.length-1]);});
$('collapse').addEventListener('click',function(){S.open=new Map([[M.lead(D,S.focus),1]]);go(true,false);});
$('reset').addEventListener('click',function(){var s=S.sel;S=M.home(D,GS);S.sel=s;go(true,true);});
$('mode').addEventListener('click',function(){var r=document.body.classList.toggle('radial');
  this.setAttribute('aria-pressed',String(r));draw(false);});
$('info').addEventListener('click',function(){var a=$('about');a.hidden=!a.hidden;this.setAttribute('aria-expanded',String(!a.hidden));});
function back(){if(D){S=M.read(D,location.hash,GS);share();draw(true);}}
addEventListener('popstate',back);addEventListener('hashchange',back);
var rz=0;new ResizeObserver(function(){if(!rz)rz=requestAnimationFrame(function(){rz=0;if(V)draw(false);});}).observe($('radial'));
var picks=[];
TX.picker({input:$('q'),list:$('sugg'),msg:$('qn'),picks:picks,ranks:META.ranks,nf:nf,
  taxa:function(){return D&&D.T;},counts:function(){return D.tot;},onChange:function(){picks.length=0;},
  onPick:function(r){if(!D.tot[r])return status('No record of this taxon needs an ID.');S.sel=r;M.reveal(D,S,r);go(true,true);}});
// The map's selection selects its taxon or group here; one this side already shows is left as it is.
function take(){var r=M.find(D,SEL);if(r!==S.sel){S.sel=r;if(r>=0)M.reveal(D,S,r);}PS=S.sel;}
if(EMBED&&parent!==window)SY=MapFilter.sync({hash:false,key:function(){return SEL;},apply:function(s){SEL=s;if(D){take();draw(true);}}});
async function load(){
  status('Loading the taxa…');
  var has=fetch('split.html',{method:'HEAD'}).then(function(r){return r.ok;},function(){return false;});
  var r=await fetch(new URL(META.taxa,location.href));if(!r.ok)throw new Error('the taxa file answered '+r.status);
  var T=JSON.parse(new TextDecoder().decode(await L.gunzip(await r.arrayBuffer())));
  if(!T.length||T[0].length<6)throw new Error('this site was built without the taxon tree');
  Object.keys(META.group_ids||{}).forEach(function(g){G[META.group_ids[g]]=g;});
  if(META.groups.indexOf('Animalia')>=0)G[1]=G[1]||'Animalia';  // iNaturalist's iconic Animalia: kingdom 1, less the other groups
  D=M.build(T,META.ranks,G,{order:META.groups,names:META.names,total:META.n});
  GS=Object.keys(G).map(function(i){return D.row.get(+i);}).filter(function(x){return x!=null&&D.tot[x];});
  S=M.read(D,location.hash,GS);if(SY){SEL=SEL||MapFilter.tokens(location.hash);take();}split=await has;status('');draw(false);
}
load().catch(function(e){status('The tree could not load: '+e.message);});
})();
