// The dot colours: each record's group, or, while Explore shows Identify beside the map, its Identify
// level. split.html says which ({type:'wtid-colour',by:'level'|'group',names:[[level,name],...]}); the
// levels (pool-levels.bin, the low nibble per record, format in pool_levels.py) load on the first ask.
// The legend toggles Levels or Groups (kept in localStorage) and each level row hides its dots.
// Records without a level stay as faint grey dots. The level colours are Okabe and Ito's, told apart
// with colour-blind sight too.
// o: META, get(url) (the map's fetch), url (the levels file), box (holds the legend), changed() after a switch.
var LevelColour=(function(){
'use strict';
var NONE=[150,150,150,60],C=[NONE,[0,158,115,170],[230,159,0,170],[0,114,178,170],[204,121,167,170],[213,94,0,170]];
function LevelColour(o){
var G=o.META.groups,gc=G.map(function(g,j){return MapFilter.color(g,j).concat(110);}),lv=null,ask=null,want=false,on=false,
  mode='levels',names=[],off={},KEY='wtid-colour-by',HID=[0,0,0,0],  // off: the levels the viewer switched off
  leg=document.createElement('div'),seg=document.createElement('div'),rows=document.createElement('div'),bs;
try{if(localStorage.getItem(KEY)==='groups')mode='groups';}catch(e){}  // the choice is kept per browser
leg.className='lvleg';leg.hidden=true;leg.setAttribute('role','group');leg.setAttribute('aria-label','Dot colours');
seg.className='seg';seg.setAttribute('role','group');seg.setAttribute('aria-label','Colour dots by');rows.className='lrows';
function rgb(c){return 'rgb('+c.slice(0,3).join(',')+')';}
function dot(c,faint){var i=document.createElement('i');i.style.background=rgb(c);if(faint)i.style.opacity=.5;return i;}
// Levels mode: a button a level (click hides or shows its dots); Groups mode: the group swatches, as the rail has them.
function draw(){
  rows.textContent='';
  if(mode==='groups')G.forEach(function(g,j){var s=document.createElement('span');s.append(dot(gc[j]),(o.META.names&&o.META.names[g]||g).replace(/ \([^)]*\)$/,''));rows.appendChild(s);});
  else names.concat([[0,'No level']]).forEach(function(r){var b=document.createElement('button');
    b.type='button';b.className='lr';b.title='Show or hide: '+r[1];b.setAttribute('aria-pressed',String(!off[r[0]]));
    b.append(dot(C[r[0]]||NONE,!r[0]),r[1]);
    b.onclick=function(){off[r[0]]=!off[r[0]];b.setAttribute('aria-pressed',String(!off[r[0]]));o.changed();};
    rows.appendChild(b);});}
bs=[['levels','Levels'],['groups','Groups']].map(function(m){var b=document.createElement('button');
  b.type='button';b.textContent=m[1];b.onclick=function(){if(mode===m[0])return;mode=m[0];
    try{localStorage.setItem(KEY,mode);}catch(e){}
    apply();};seg.appendChild(b);return [m[0],b];});
function apply(){var a=want&&!!lv,w=a&&mode==='levels';
  leg.hidden=!a;bs.forEach(function(m){m[1].setAttribute('aria-pressed',String(m[0]===mode));});
  if(a)draw();if(w!==on){on=w;o.changed();}}
leg.append(Object.assign(document.createElement('span'),{className:'lt',textContent:'Colour by'}),seg,rows);o.box.appendChild(leg);
// The colours of records 0..n-1, as deck.gl reads them: 4 bytes a record.
function fill(grp,n){
  var col=new Uint8Array(4*n),i,c;
  for(i=0;i<n;i++){c=on?off[lv[i]&15]?HID:C[lv[i]&15]||NONE:gc[grp[i]];
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
return {fill:fill};
}
return LevelColour;
})();
