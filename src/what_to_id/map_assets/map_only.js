// The Show only chips (introduced, threatened, one ID from Research Grade, outside usual range) with the location accuracy
// slider, and the taxa shortcuts. The filter bar draws them in the map and the Identify page in its What panel.
// MapOnly(o), o {S, META, mf (MapFilter(META)), box (the section, hidden when it holds nothing), flags, acclbl, acc, accr
// (the elements), refilter() (a filter changed)}. Returns {show() (the controls follow S), label() (the accuracy choice's
// words, '' for any)}. MapOnly.clades(o), o {S, box, wrap, pk (the taxon picker), presets (META.presets), refilter()},
// returns {show()}. Needs map_chips.js (CH).
var MapOnly=(function(){
'use strict';
function MapOnly(o){
var S=o.S,META=o.META,MF=o.mf,refilter=o.refilter,ONLYDEF=MF.ONLYDEF,
  ONLY=ONLYDEF.map(function(d){return CH.chip(o.flags,d[0],d[1],function(){return S.only;},true,d[3],refilter);}),
  ACCDEF=META.flags.indexOf('accuracy')<0?[]:MF.ACCDEF,STOPS=['','known','1000','100','10'],AR=o.accr,
  UB=ACCDEF.length?document.createElement('button'):null;
// The location accuracy is one choice of several: the known classes run from any to within 10 m, so one slider, and
// unknown, off that scale, is a toggle on its label line; a pool without accuracy has neither.
if(UB){UB.type='button';UB.className='link accu';UB.title=ACCDEF[0][2]+'. Click to pick.';o.acclbl.appendChild(UB);
  UB.onclick=function(){S.acc=S.acc==='unknown'?'':'unknown';show();refilter();};
  AR.oninput=function(){S.acc=STOPS[+AR.value];show();refilter();};}
function label(){var d=ACCDEF.filter(function(a){return a[0]===S.acc;})[0];return d?d[1]:'';}
function show(){ONLY.forEach(function(b,j){CH.show(b,ONLYDEF[j][1],S.only[ONLYDEF[j][0]]||'');});
  if(!UB)return;CH.show(UB,'Unknown only',S.acc==='unknown'?'inc':'');
  var k=STOPS.indexOf(S.acc);AR.value=Math.max(k,0);AR.setAttribute('aria-valuetext',label()||'Any accuracy');
  [].forEach.call(o.acc.querySelectorAll('.accticks span'),function(t,j){t.classList.toggle('on',j===k);});AR.title=k>0?ACCDEF[k][2]:'Any location accuracy';}
show();
if(!ONLY.length&&!UB)o.box.hidden=true;
if(!UB)o.acc.hidden=o.acclbl.hidden=true;
return {show:show,label:label};
}
// A shortcut picks, then leaves out, a set of taxa, and shows only once the taxa file carries the whole tree.
MapOnly.clades=function(o){
  var S=o.S,PK=o.pk,PRE=o.presets,CB=PRE.map(function(c){
    var b=document.createElement('button');b.type='button';b.textContent=c[0];if(c[2])b.title=c[2];b.setAttribute('aria-pressed','false');
    b.onclick=function(){S.split=(S.split||[]).filter(function(n){return n!==c[0];});PK.cycle(c[1]);
      b.setAttribute('aria-pressed',String(PK.state(c[1])!==''));o.refilter();};
    o.box.appendChild(b);return b;});
  o.wrap.hidden=!CB.length;
  function show(){CB.forEach(function(b,k){CH.show(b,PRE[k][0],PK.state(PRE[k][1]));});}
  show();
  return {show:show};
};
return MapOnly;
})();
