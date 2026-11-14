// The Identify search bar: What, When, Where and Who, each opening its own panel under its segment. The panels are the map's
// controls, shared: the taxon picker and groups list (What), the dates, months and histograms (When) and the area
// live map and its area tools (Where). A change writes S and calls changed(), so the cards follow at once. A phone (760px
// and under) opens one full-screen sheet with the three panels as accordion sections, one open at a time.
// Keys: Left and Right move between the segments, an open panel follows the focus, Tab walks from a segment into its
// panel, Esc closes it and returns to the segment, a click outside closes it.
// IdentifyBar(o), o {S, META, mf (MapFilter(META)), nf, taxa(), P(), tf() (the taxon filter), mask(st) (1 per record
// st keeps at the chosen level), all(st) (the same at every level), tab() ({name, has(i)}: the chosen
// level), changed() (S changed), where(rings, hash) (the area changed), get(url), map (the map
// page's address), key() (the selection as text), embedded}.
// Returns update(), called after every selection and level change. Needs map_taxa.js, map_chips.js, map_area.js,
// group_list.js, map_hist.js, map_time.js, map_only.js and identify_where.js.
var IdentifyBar=(function(){
'use strict';
var NAMES=['What','When','Where','Who'];
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
return function(o){
var S=o.S,META=o.META,MF=o.mf,G=META.groups,LAST=MF.LAST,iso=MF.iso,bar=$('bar'),SH=$('bsheet'),phone=matchMedia('(max-width:760px)'),
  SEG=NAMES.map(function(n){var b=$('b'+n.toLowerCase());return {b:b,p:$('p'+n.toLowerCase()),l:b.querySelector('b')};}),
  cur=-1,CUM=null,SUB=null,TC,TOT=null,GM=null,A=null,ACC=[];
SEG[2].b.hidden=o.embedded;  // the split view's map beside it holds the area

// What: the taxon picker and its shortcuts, then the groups list with the groups filter left out of its counts, then the Show only
// chips and the location accuracy (the projects box is the app's, identify_only.js)
var PK=TX.picker({input:$('q'),list:$('sugg'),msg:$('qn'),get picks(){return S.picks;},ranks:META.ranks,nf:o.nf,taxa:o.taxa,
  counts:function(){var p=o.P();return TX.counts(o.taxa(),p.tax,p.n);},onChange:o.changed});
var GL=GroupList({box:$('groups'),bar:$('gbar'),keep:$('gkeep'),mine:$('mine'),S:S,META:META,nf:o.nf,changed:o.changed,taxa:o.taxa,P:o.P,
  pass:function(){return GM;},inside:function(r){var f=o.tf();return !!f.inc&&f.inc[r]===1;},pk:function(){return PK;},quiet:true});
var CL=MapOnly.clades({S:S,box:$('clades'),wrap:$('cladebox'),pk:PK,presets:META.presets||[],refilter:o.changed}),
  OL=MapOnly({S:S,META:META,mf:MF,box:$('flagbox'),flags:$('flags'),acclbl:$('acclbl'),acc:$('acc'),accr:$('accr'),refilter:o.changed});
$('gall').onclick=function(){S.groups={};GL.show();o.changed();};
function counts(){
  var P=o.P(),c=new Uint32Array(G.length),i;
  GM=o.mask(Object.assign({},S,{groups:{}}));
  for(i=0;i<P.n;i++)if(GM[i])c[P.grp[i]]++;
  GL.set(c);
}

// When: the presets, dates and months, and the histograms of the records per day, the dates left out of the selection
// One pass counts every record that still needs an ID (as the map does) and, in sub, those in the chosen tab
function cum(){
  if(CUM)return CUM;
  var P=o.P(),m=o.all(Object.assign({},S,{lo:0,hi:LAST})),day=S.up?P.up:P.obs,c=new Float64Array(META.days+1),
    t=new Float64Array(META.days+1),has=o.tab().has,i;
  for(i=0;i<P.n;i++)if(m[i]&&day[i]!==MF.NO){c[day[i]+1]++;if(has(i))t[day[i]+1]++;}
  for(i=0;i<META.days;i++){c[i+1]+=c[i];t[i+1]+=t[i];}
  SUB=t;return (CUM=c);
}
// The all-record counts (the map's totals file) load beside the records; the light bars wait for them
function tc(){
  if(TC===undefined)TC=MapHist.tc(TOT,S,MF,CH.groupPass(S.groups,G,false),o.blocked());
  return TC;
}
if(META.files.totals)o.get(META.files.totals).then(function(b){TOT=JSON.parse(new TextDecoder().decode(b));update();}).catch(function(){});
var TM=MapTime({S:S,mf:MF,render:o.changed,refilter:o.changed,byObs:$('byObs'),byUp:$('byUp'),presets:$('presets'),from:$('from'),to:$('to'),
  months:$('months'),mclear:$('mclear')});
var MH=MapHist({S:S,META:META,mf:MF,nf:o.nf,over:$('over'),hist:$('hist'),htip:$('htip'),unit:$('unit'),cum:cum,sub:{cum:function(){cum();return SUB;},name:function(){return o.tab().name;}},tc:tc,render:o.changed});

// Where: the live map (identify_where.js), loaded when the panel first opens. Until then, and for a shared link's area, a
// stand-in for the map (no controls of its own) restores the address's area; the map takes over once it is live.
var W=null,LBL=null;
if(!o.embedded){
  W=IdentifyWhere({box:$('wbox'),url:o.map,key:o.key,done:function(){if(SH.open)SH.close();else close(false);},leave:function(){if(!SH.open)close(true);},set:function(a,h,l){LBL=l;o.where(a,h);}});
  var h=new URLSearchParams(location.hash.slice(1)),world={getEast:function(){return 180;},getWest:function(){return -180;},
    getNorth:function(){return 90;},getSouth:function(){return -90;}};
  A=MapArea({map:{addControl:function(){},on:function(){},getBounds:function(){return world;}},S:S,LAST:LAST,
    hash:h.get('area')||'',park:h.get('park')||'',bcpark:h.get('bcpark')||'',fit:false,place:META.place_id,parks:META.parks,get:o.get,P:o.P,
    keep:function(){return null;},change:function(){if(!W.live())o.where(A.area(),A.hash());},sel:function(){return '';},step:null});
}

// The segments' words
function short(g){return (META.names[g]||g).replace(/ \([^)]*\)$/,'');}
function many(a,n){return a.length===1?short(a[0]):a.length+' '+n;}
function taxon(p){var r=o.taxa().filter(function(t){return t[2]===p.id;})[0];return (p.not?'not ':'')+(r?r[1]||r[0]:'1 taxon');}
function what(){
  var inc=CH.picked(S.groups,G,'inc'),not=CH.picked(S.groups,G,'not'),t=[];
  if(inc.length)t.push(many(inc,'groups'));
  if(not.length)t.push('not '+many(not,'groups'));
  if(S.picks.length)t.push(S.picks.length===1?taxon(S.picks[0]):S.picks.length+' taxa');
  MF.ONLYDEF.forEach(function(d){if(S.only[d[0]])t.push((S.only[d[0]]==='not'?'not ':'')+d[1]);});
  if(S.acc)t.push(OL.label().toLowerCase()||S.acc);
  return t.join(', ')||'All groups';
}
function when(){
  var p=TM.presets.filter(function(x){var r=x.range();return r[0]===S.lo&&r[1]===S.hi;})[0],m=0,i;
  for(i=0;i<12;i++)m+=S.months>>i&1;
  return [S.up?'Uploaded':'',p&&S.lo===0?'Any time':p?p.el.textContent:iso(S.lo)+' to '+iso(S.hi),m?m+' months':''].filter(Boolean).join(' · ');
}
// the identifier the cards fit: Anyone, or @login and what is ticked
var TICKS={taxa:'my genera',unid:'not by me',observer:'my observations',first:'my genera first'};
function who(){
  if(!S.user)return 'Anyone';
  var t=(S.umode||'').split(',').filter(function(k){return TICKS[k];}).map(function(k){return TICKS[k];});
  return '@'+S.user+(t.length?' \u00b7 '+t.join(', '):'');
}
function where(){var t=A&&A.term();return LBL!==null?LBL||'Anywhere':t?t.label:'Anywhere';}

// The panels: the open one is raised under its segment, the rest of the bar greyed
function visible(k){return SEG[k].p.offsetParent!==null;}
// What's links to the full-screen photo space and taxonomy (explore.html), with the selection in the address
var XL=$('xlinks');
function xl(){['xspace','xtree'].forEach(function(id){var a=$(id);a.href=a.getAttribute('href').split('#')[0]+location.hash;});}
if(XL&&!o.embedded)fetch('explore.html',{method:'HEAD'}).then(function(r){XL.hidden=!r.ok;}).catch(function(){});
if(XL)XL.addEventListener('click',xl,true);
function fill(k){
  if(!visible(k))return;
  if(k===0){counts();if(XL)xl();}
  else if(k===1)MH.draw();
  else if(k===2){if(W)W.show();}
  else [].forEach.call(SEG[3].p.querySelectorAll('details details'),function(d){d.open=true;});  // Who: the threshold sits in a closed Adjust
}
function place(k){
  var r=SEG[k].b.getBoundingClientRect(),b=bar.getBoundingClientRect(),p=SEG[k].p;
  p.style.left=Math.max(0,Math.min(r.left-b.left,b.width-p.offsetWidth))+'px';
}
function open(k){
  if(cur===k)return;
  close(false);cur=k;
  SEG[k].p.hidden=false;SEG[k].b.setAttribute('aria-expanded','true');SEG[k].b.classList.add('on');bar.classList.add('open');
  place(k);fill(k);
}
function close(back){
  if(cur<0)return;
  var s=SEG[cur];cur=-1;
  s.p.hidden=true;s.b.setAttribute('aria-expanded','false');s.b.classList.remove('on');bar.classList.remove('open');
  if(back)s.b.focus();
}
function shown(){return SEG.map(function(s,k){return k;}).filter(function(k){return !SEG[k].b.hidden;});}
var press=false;  // a press focuses the segment before its click: the click alone opens or closes
SEG.forEach(function(s,k){
  s.b.onclick=function(){press=false;if(phone.matches)sheet(k);else if(cur===k)close(false);else open(k);};
  s.b.addEventListener('pointerdown',function(){press=true;});
  s.b.addEventListener('focus',function(){if(cur>=0&&!press&&!phone.matches)open(k);});  // an open panel follows the focus
  s.b.addEventListener('keydown',function(e){
    var d={ArrowLeft:-1,ArrowRight:1}[e.key],v=shown(),to=d&&v[v.indexOf(k)+d];
    if(!d)return;e.preventDefault();if(to!=null)SEG[to].b.focus();});
});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&cur>=0&&!SH.open)close(true);});
document.addEventListener('pointerdown',function(e){if(cur>=0&&!e.target.closest('#bar'))close(false);});
addEventListener('resize',function(){if(cur>=0){place(cur);fill(cur);}});

// A phone: the panels move into the sheet's accordion sections and back
function openAcc(k){
  var was=ACC[k].h.getAttribute('aria-expanded')==='true';
  ACC.forEach(function(a){a.h.setAttribute('aria-expanded','false');a.b.hidden=true;});
  if(was)return;
  ACC[k].h.setAttribute('aria-expanded','true');ACC[k].b.hidden=false;fill(k);
}
function sheet(k){
  close(false);
  ACC.forEach(function(a,j){a.b.appendChild(SEG[j].p);SEG[j].p.hidden=false;});
  SH.showModal();openAcc(k);
}
SEG.forEach(function(s,k){
  var sec=el('section','acc'),h=el('button','ahead'),b=el('div','abody');
  h.type='button';h.id='ah'+k;h.setAttribute('aria-expanded','false');h.setAttribute('aria-controls','ab'+k);
  h.append(el('span',null,NAMES[k]),el('b'));
  b.id='ab'+k;b.hidden=true;b.setAttribute('role','region');b.setAttribute('aria-labelledby',h.id);
  h.onclick=function(){openAcc(k);};
  sec.hidden=s.b.hidden;sec.append(el('h3',null),b);sec.firstChild.appendChild(h);
  SH.querySelector('.sbody').appendChild(sec);ACC[k]={h:h,b:b};
});
SH.addEventListener('close',function(){SEG.forEach(function(s){s.b.after(s.p);s.p.hidden=true;});});
phone.addEventListener('change',function(){if(SH.open)SH.close();close(false);});

SEG.forEach(function(s){s.b.disabled=false;});
// After every selection or level change: the words, the controls, and the open panel's numbers
function update(){
  CUM=null;TC=undefined;if(W)W.sync();
  var w=[what(),when(),where(),who()];
  SEG.forEach(function(s,k){s.l.textContent=w[k];ACC[k].h.lastChild.textContent=w[k];});
  GL.show();TM.update();OL.show();CL.show();
  SEG.forEach(function(s,k){if(!s.b.hidden)fill(k);});
}
return {update:update};
};
})();
