// The dot colours: each record's group, or, while Explore shows Identify beside the map, its Identify
// level. split.html says which ({type:'wtid-colour',by:'level'|'group',names:[[level,name],...]}); the
// levels (pool-levels.bin, the low nibble per record, format in pool_levels.py) load on the first ask.
// The legend toggles Levels or Groups (kept in localStorage). Level rows pick as the filter chips do: none picked
// shows every level, a click picks a level so only the picked ones show, a second click unpicks it.
// Records without a level stay as faint grey dots. The level colours are Okabe and Ito's, told apart
// with colour-blind sight too.
// In group colours a selection of one group or one taxon breaks its dots down by its children (clade_colour.js,
// the tree's colours): the TOP children with the most records, the rest as one muted Other. With two or more
// groups picked the legend lists them. A click on a group (or on a clade with clades below it) picks it in
// place of the selection's picked groups and taxa, as the rail's pick would, so the data narrows a level; the
// trail above (All groups / Plants / Tracheophyta) and Esc in the legend step the pick back up.
// o: META, get(url) (the map's fetch), url (the levels file), box (holds the legend), changed() after a switch,
// taxa() the taxa table, P() the records, st() the map's selection, shown() the records the filters show as
// {k: a key that changes with them, f(i)}, or null before they are counted (then every record counts),
// picked() after the legend changed the selection's groups or picks.
var LevelColour=(function(){
'use strict';
var NONE=[150,150,150,60],C=[NONE,[0,158,115,170],[230,159,0,170],[0,114,178,170],[204,121,167,170],[213,94,0,170]],
  TOP=8,OUT=-1,OTHER=TOP;
function LevelColour(o){
var G=o.META.groups,gc=G.map(function(g,j){return MapFilter.color(g,j).concat(110);}),lv=null,ask=null,want=false,on=false,
  mode='levels',names=[],sel={},KEY='wtid-colour-by',HID=[0,0,0,0],  // sel: the levels the viewer picked
  leg=document.createElement('div'),seg=document.createElement('div'),rows=document.createElement('div'),bs,
  T=null,CC=null,row=null,cnt=null,cn=-1,inc=[],top=-1,show=[],sc=[],slot=null,key='';
leg.className='lvleg';leg.hidden=true;leg.setAttribute('role','group');leg.setAttribute('aria-label','Dot colours');
seg.className='seg';seg.setAttribute('role','group');seg.setAttribute('aria-label','Colour dots by');rows.className='lrows';
try{if(localStorage.getItem(KEY)==='groups')mode='groups';}catch(e){}  // the choice is kept per browser
function rgb(c){return 'rgb('+c.slice(0,3).join(',')+')';}
function dot(c,faint){var i=document.createElement('i');i.style.background=rgb(c);if(faint)i.style.opacity=.5;return i;}
function gname(g){return (o.META.names&&o.META.names[g]||g).replace(/ \([^)]*\)$/,'');}
// The group whose taxon row r is, else undefined.
function gof(r){for(var g in CC.gr)if(CC.gr[g]===r)return g;}
// A clade's name: its group's for a group taxon, else its common name, else its latin one.
function cname(r){var g=gof(r);return g?gname(g):T[r][1]||T[r][0];}
// The palette and the shown records at or below each row (group taxa cut loose, as the tree has them), kept until
// the taxa or the shown records change. The counts pick the legend's clades; the colours stay the palette's.
function prep(){var t=o.taxa(),P=o.P(),v=o.shown&&o.shown(),k=v?v.k:P.n;if(!t)return false;
  if(t!==T){T=t;CC=CladeColour.build(T,o.META);row=new Map();T.forEach(function(x,i){row.set(x[2],i);});cn=-1;}
  if(cn!==k){cn=k;var own=new Float64Array(T.length),i,j;cnt=new Float64Array(T.length);
    for(i=0;i<P.n;i++)if(P.tax[i]<T.length&&(!v||v.f(i)))own[P.tax[i]]++;
    for(i=0;i<T.length;i++)if(own[i])for(j=i;j>=0;j=CC.par[j])cnt[j]+=own[i];}
  return true;}
// The children of r that hold records, most first.
function held(r){return CC.kids[r].filter(function(k){return cnt[k]>0;}).sort(function(a,b){return cnt[b]-cnt[a]||a-b;});}
function deep(r){return r>=0&&held(r).length>=2;}
// The row the selection narrows to: its one included group's taxon with no taxon picked, or its one included taxon
// with no group picked; else -1.
function focus(S){var t=S.picks.filter(function(p){return !p.not;});inc=CH.picked(S.groups,G,'inc');
  if(inc.length===1&&!t.length)return CC.gr[inc[0]]!=null?CC.gr[inc[0]]:-1;
  var r=t.length===1&&!inc.length?row.get(t[0].id):null;return r==null?-1:r;}
// Which of show (or OTHER below top, OUT elsewhere) each taxa row falls under: a walk up stops at the first row
// already known, then marks the rows it passed, so each row is settled once.
function slots(){var n=T.length,s=new Int8Array(n).fill(-2),path=[],i,j,v;s[top]=OTHER;
  show.forEach(function(c,k){s[c]=k;});
  for(i=0;i<n;i++){for(j=i,path.length=0;j>=0&&s[j]===-2;j=CC.par[j])path.push(j);
    v=j<0?OUT:s[j];path.forEach(function(p){s[p]=v;});}
  return s;}
// Works out the breakdown; a change of it recolours the dots.
function sync(){
  if(!prep())return;
  var t=focus(o.st());t=deep(t)?t:-1;
  if(t!==top||t>=0&&held(t).slice(0,TOP).join()!==show.join()){top=t;
    // below a group (a picked sub-clade) the palette focuses on the breakdown, as the tree's focus does
    show=t<0?[]:held(t).slice(0,TOP);var F=CC.at(t);sc=show.map(function(c){return F[c].concat(110);});
    if(t>=0){var c=F[t];sc[OTHER]=c.map(function(v){return Math.round(v*0.4+150*0.6);}).concat(110);slot=slots();}}
  apply();}
function picked(){for(var k in sel)return true;return false;}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// A legend row: swatch and name, cut to one line with the full name in its title; go() makes it a button.
function line(c,text,go){var s=el('span');s.title=text;s.append(dot(c),el('em',null,text));
  if(go){s.setAttribute('role','button');s.tabIndex=0;s.setAttribute('aria-pressed','false');s.onclick=go;
    s.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();go();}};}
  return s;}
// Picks row r (-1: no group or taxon) in place of the picked groups and taxa; the left-out ones stay.
function pick(r){var S=o.st(),g=r>=0?gof(r):null,id=r>=0&&!g?T[r][2]:null,k=S.picks.filter(function(p){return p.not&&p.id!==id;});
  G.forEach(function(x){if(S.groups[x]==='inc')delete S.groups[x];});if(g)S.groups[g]='inc';
  S.picks.length=0;k.forEach(function(p){S.picks.push(p);});if(id!=null)S.picks.push({id:id,not:false});
  o.picked();var f=rows.querySelector('[role=button],button');if(f)f.focus();}
// The breakdown's row and those above it to its group's, top first.
function path(){for(var p=[],r=top;r>=0;r=CC.par[r])p.unshift(r);return p;}
// Levels mode: a button a level (click picks or unpicks it); Groups mode: the group swatches, as the rail has
// them, or the breakdown with its trail.
function draw(){
  rows.textContent='';
  rows.classList.toggle('pick',on&&picked());
  if(on)return names.concat([[0,'No level']]).forEach(function(r){var b=document.createElement('button');
    b.type='button';b.className='lr';b.title='Show only '+r[1]+'; click again to show all';
    b.setAttribute('aria-pressed',String(!!sel[r[0]]));b.append(dot(C[r[0]]||NONE,!r[0]),r[1]);
    b.onclick=function(){if(sel[r[0]])delete sel[r[0]];else sel[r[0]]=1;draw();o.changed();};
    rows.appendChild(b);});
  if(top<0)return (inc.length?inc:G).forEach(function(g){var j=G.indexOf(g),r=CC?CC.gr[g]:null;
    rows.appendChild(line(gc[j],gname(g),r!=null&&deep(r)?function(){pick(r);}:null));});
  var tr=el('span','lt'),ps=[-1].concat(path());
  ps.forEach(function(r,k){var n=r<0?'All groups':cname(r);if(k)tr.append(' / ');
    if(k===ps.length-1){var e=el('b',null,n);e.title=n;return tr.append(e);}
    var b=el('button','lb',n);b.type='button';b.onclick=function(){pick(r);};tr.append(b);});
  tr.setAttribute('role','navigation');tr.setAttribute('aria-label','Legend trail');
  rows.appendChild(tr);
  show.forEach(function(c,k){rows.appendChild(line(sc[k],cname(c),deep(c)?function(){pick(c);}:null));});
  if(cnt[top]>show.reduce(function(s,c){return s+cnt[c];},0)){var n=cname(top);
    rows.appendChild(line(sc[OTHER],/^other /i.test(n)?n:'Other '+(T[top][1]?n.toLowerCase():n)));}}
bs=[['levels','Levels'],['groups','Groups']].map(function(m){var b=document.createElement('button');
  b.type='button';b.textContent=m[1];b.onclick=function(){if(mode===m[0])return;mode=m[0];
    try{localStorage.setItem(KEY,mode);}catch(e){}
    apply();};seg.appendChild(b);return [m[0],b];});
function apply(){var lvl=want&&!!lv,a=lvl||top>=0||inc.length>=2,k;on=lvl&&mode==='levels';
  leg.hidden=!a;seg.hidden=!lvl;leg.firstChild.hidden=!lvl;
  bs.forEach(function(m){m[1].setAttribute('aria-pressed',String(m[0]===mode));});
  // a redraw keeps the focus on the control of the same name, so a recount does not drop it
  var f=rows.contains(document.activeElement)&&document.activeElement.textContent;
  if(a)draw();if(f)[].some.call(rows.querySelectorAll('button,[role=button]'),function(e){if(e.textContent===f){e.focus();return true;}});
  k=on?'L':top+':'+show.join();if(k!==key){key=k;o.changed();}}
leg.append(el('span','lt','Colour by'),seg,rows);o.box.appendChild(leg);
addEventListener('keydown',function(e){if(e.key!=='Escape'||on||top<0||leg.hidden||!leg.contains(document.activeElement))return;
  var p=path();pick(p.length>1?p[p.length-2]:-1);});  // Esc in the legend steps the pick up a level
// The colours of records 0..n-1, as deck.gl reads them: 4 bytes a record.
function fill(grp,n){
  var col=new Uint8Array(4*n),tax=o.P().tax,cut=top>=0&&!on,any=picked(),i,c,s;
  for(i=0;i<n;i++){if(on)c=any&&!sel[lv[i]&15]?HID:C[lv[i]&15]||NONE;
    else if(cut&&(s=tax[i]<slot.length?slot[tax[i]]:OUT)!==OUT)c=sc[s];
    else c=gc[grp[i]];
    col[4*i]=c[0];col[4*i+1]=c[1];col[4*i+2]=c[2];col[4*i+3]=c[3];}
  return col;}
addEventListener('message',function(e){
  var d=e.data;
  if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-colour')return;
  want=d.by==='level';
  if(want){names=Array.isArray(d.names)?d.names:[];
    ask=ask||o.get(o.url).then(function(b){var u=new Uint8Array(b);if(u.length===o.META.n)lv=u;})
      .catch(function(){});}  // without the file the groups keep their colours
  (want?ask:Promise.resolve()).then(apply);
});
return {fill:fill,sync:sync};
}
return LevelColour;
})();
