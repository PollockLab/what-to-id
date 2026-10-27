// The Groups section: one row per group with its count of the records in view and its share of
// them, largest first, and a stacked bar of the shares in the section's summary. The shares leave
// the group filter out, so picking a group highlights its row and the others keep their numbers.
// A row's click picks the group or clears it, its Leave out button leaves it out or clears it; the
// states are the chips' (see map_chips.js), so the hash stays groups=Insecta,-Aves. A caret opens
// the ranks below a group (taxon_tree.js) once the taxa carry the tree.
// o: box (the list), bar (the summary bar), S, META, nf, changed() after a click, taxa() (the taxa
// rows or null), P() (the records), pass() (the records in view, a Uint8Array), inside(row), pk()
// (the taxon picker).
var GroupList=(function(){
'use strict';
function pct(v,t){var f=t?v/t*100:0;
  return !f?'0%':f<.1?'<0.1%':f<.95?f.toFixed(1)+'%':Math.round(f)+'%';}
function GroupList(o){
var S=o.S,META=o.META,G=META.groups,nf=o.nf,cnt=null,tot=0,TR=null;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
  if(text!=null)e.textContent=text;return e;}
function gname(g){return META.names[g]||g;}
// a row shows the plain name, "Fish" for "Fish (Actinopterygii)"; its title has both
function gshort(g){return gname(g).replace(/ \([^)]*\)$/,'');}
function color(j){return 'rgb('+MapFilter.color(G[j],j).join(',')+')';}
function flip(g,v){if(S.groups[g]===v)delete S.groups[g];else S.groups[g]=v;show();o.changed();}
var R=G.map(function(g,j){
  var li=el('li','gr'),b=el('button','gb'),x=el('button','gx','Leave out'),dot=el('i');
  b.type=x.type='button';dot.style.background=color(j);
  b.append(dot,el('span','nm'),el('span','gc'),el('span','gp'));
  b.title=gname(g)+'. Click to pick, again to clear.';x.title='Leave out '+gname(g)+', again to clear.';
  b.onclick=function(){flip(g,'inc');};x.onclick=function(){flip(g,'not');};
  li.append(b,x,el('div','gs'));o.box.appendChild(li);
  return {li:li,b:b,x:x};});
// Brings the rows up to date with S.groups.
function show(){R.forEach(function(r,j){var st=S.groups[G[j]]||'',nm=r.b.querySelector('.nm');
  r.b.setAttribute('aria-pressed',String(st==='inc'));r.x.setAttribute('aria-pressed',String(st==='not'));
  r.li.classList.toggle('not',st==='not');r.li.classList.toggle('on',st==='inc');
  nm.textContent=(st==='not'?'not ':'')+gshort(G[j]);
  r.x.setAttribute('aria-label',(st==='not'?'Keep ':'Leave out ')+gshort(G[j]));});}
// The ranks under each group, once the taxa are in; the records arrive in shards, so the tree
// reads them through getters.
function tree(){
  var T=o.taxa();if(TR||!T)return;
  TR=TT.make({T:T,get tax(){return o.P().tax;},get grp(){return o.P().grp;},get n(){return o.P().n;},
    groups:G.length,ranks:META.ranks,nf:nf,box:o.box,label:function(j){return gshort(G[j]);},
    slot:function(j){return R[j].li.lastChild;},pass:o.pass,inside:o.inside,
    onOpen:function(){TR.render();},state:function(id){return o.pk().state([id]);},
    cycle:function(id){o.pk().cycle([id]);}});
  if(TR)R.forEach(function(r,j){TR.attach(r.b,j);});
}
// c: the records in view per group, the group filter left out. Called after every count.
function set(c){
  tree();if(!c||c===cnt)return;cnt=c;tot=0;var j,top=[],a=document.activeElement;
  for(j=0;j<G.length;j++)tot+=c[j];
  var ord=G.map(function(g,k){return k;}).sort(function(a,b){return c[b]-c[a]||a-b;});
  ord.forEach(function(j,k){var r=R[j],p=pct(c[j],tot),q=r.b.querySelector('.gc');
    q.textContent=nf.format(c[j]);r.b.querySelector('.gp').textContent=p;
    r.b.style.setProperty('--s',(tot?c[j]/tot*100:0)+'%');r.li.classList.toggle('z',!c[j]);
    if(o.box.children[k]!==r.li)o.box.insertBefore(r.li,o.box.children[k]);});
  if(a&&o.box.contains(a)&&document.activeElement!==a)a.focus();
  o.bar.textContent='';
  ord.forEach(function(j){if(!c[j])return;var s=el('i');s.style.background=color(j);
    s.style.width=c[j]/tot*100+'%';o.bar.appendChild(s);
    if(top.length<3)top.push(gshort(G[j])+' '+pct(c[j],tot));});
  o.bar.setAttribute('aria-label',top.length?'Largest groups in view: '+top.join(', '):'No records in view');
  if(TR){TR.refresh();TR.render();}
}
show();
return {show:show,set:set};
}
GroupList.pct=pct;
return GroupList;
})();
