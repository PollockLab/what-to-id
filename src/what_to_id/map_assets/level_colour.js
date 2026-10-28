// The dot colours: each record's group, or, while Explore shows Identify beside the map, its Identify
// level. split.html says which ({type:'wtid-colour',by:'level'|'group',names:[[level,name],...]}); the
// levels (pool-levels.bin, the low nibble per record, format in pool_levels.py) load on the first ask.
// Records without a level stay as faint grey dots. The level colours are Okabe and Ito's, told apart
// with colour-blind sight too.
// o: META, get(url) (the map's fetch), url (the levels file), box (holds the legend), changed() after a switch.
var LevelColour=(function(){
'use strict';
var NONE=[150,150,150,60],C=[NONE,[0,158,115,170],[230,159,0,170],[0,114,178,170],[204,121,167,170],[213,94,0,170]];
function LevelColour(o){
var G=o.META.groups,gc=G.map(function(g,j){return MapFilter.color(g,j).concat(110);}),lv=null,ask=null,want=false,on=false,
  leg=document.createElement('div');
leg.className='lvleg';leg.hidden=true;leg.setAttribute('role','img');o.box.appendChild(leg);
function rgb(c){return 'rgb('+c.slice(0,3).join(',')+')';}
function legend(names){
  var rows=names.concat([[0,'No level']]);leg.textContent='';
  rows.forEach(function(r){var s=document.createElement('span'),i=document.createElement('i');
    i.style.background=rgb(C[r[0]]||NONE);if(!r[0])i.style.opacity=.5;s.append(i,r[1]);leg.appendChild(s);});
  leg.setAttribute('aria-label','Dot colours: '+rows.map(function(r){return r[1];}).join(', '));}
// The colours of records 0..n-1, as deck.gl reads them: 4 bytes a record.
function fill(grp,n){
  var col=new Uint8Array(4*n),i,c;
  for(i=0;i<n;i++){c=on?C[lv[i]&15]||NONE:gc[grp[i]];
    col[4*i]=c[0];col[4*i+1]=c[1];col[4*i+2]=c[2];col[4*i+3]=c[3];}
  return col;}
addEventListener('message',function(e){
  var d=e.data;
  if(e.origin!==location.origin||e.source!==parent||!d||d.type!=='wtid-colour')return;
  want=d.by==='level';
  if(want){legend(Array.isArray(d.names)?d.names:[]);
    ask=ask||o.get(o.url).then(function(b){var u=new Uint8Array(b);if(u.length===o.META.n)lv=u;})
      .catch(function(){});}  // without the file the groups keep their colours
  (want?ask:Promise.resolve()).then(function(){var w=want&&!!lv;if(w===on)return;on=w;leg.hidden=!on;o.changed();});
});
return {fill:fill};
}
return LevelColour;
})();
