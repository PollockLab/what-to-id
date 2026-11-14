// The page's chrome around the modules' own controls: the mode control, the inline range, Research Grade and
// confidence filters and the At risk and Invasive chips sit on the bar row (the search bar, identify_bar.js, holds What,
// When and Where); the You button opens the User box (map_user.js) in a popover, with a loading line until its data is in.
// The result line counts the cards from the batch caption (which becomes its title).
// A help sheet holds the page notes, totals, progress, the level description and the keys.
// The modules keep writing their own controls and hash keys; this only moves and names them.
(function(){
'use strict';
function $(id){return document.getElementById(id);}
function has(k){return new RegExp('(^|&)'+k+'=').test(location.hash.slice(1));}
function labels(){
  var g=has('run')&&!$('sortb').hidden;$('sortb').firstChild.textContent=($('sortb').dataset.name||'Prioritize')+(g?' · grouped':'')+(has('out')?' · range':'')+' ';
  $('uload').hidden=!$('usrbox').hidden;
}
function count(){
  var cap=$('cap').textContent,m=/^[\d,.\s ]+/.exec(cap),n=$('none').hidden?(m?m[0].trim():''):'0';
  var st=$('status').textContent;  // loading and load errors stay in sight while the totals sit in the help sheet
  // the heading relates its cards to the tab's records: "22,902 cards · 3 per species of 324,594 records"
  var tb=document.querySelector('[role=tab][aria-selected=true] b'),pr=/up to (\d+) per/.exec(cap),rel=tb&&tb.textContent?(pr?' · '+pr[1]+' per species':'')+' of '+tb.textContent+' records':'';
  $('count').textContent=n?n+' cards':/^(Loading|Could not)/.test(st)?st:'';$('count').title=cap;
  if(n&&rel){var r=document.createElement('span');r.className='rel';r.textContent=rel;$('count').appendChild(r);}  // a phone keeps the short heading
  $('pshow').textContent=n?'Show '+n+' cards':'Close';
  [].forEach.call(document.querySelectorAll('.sdone .n'),function(s){s.textContent=n||'0';});
}
function sheets(){
  [].forEach.call(document.querySelectorAll('dialog.sheet'),function(d){
    [].forEach.call(d.querySelectorAll('.shx,.sdone'),function(b){b.onclick=function(){d.close();};});
    d.addEventListener('click',function(e){if(e.target===d)d.close();});  // a click on the backdrop
    d.addEventListener('keydown',function(e){  // Tab wraps inside, where a modal alone would let it out to the browser
      if(e.key!=='Tab')return;
      var f=[].filter.call(d.querySelectorAll('button,select,input,a[href],summary,[tabindex="0"]'),function(x){return x.offsetParent&&!x.disabled;});
      var a=f[0],z=f[f.length-1];
      if(e.shiftKey?document.activeElement===a:document.activeElement===z){e.preventDefault();(e.shiftKey?z:a).focus();}});
    [].forEach.call(document.querySelectorAll('[aria-controls="'+d.id+'"]'),function(b){
      b.onclick=function(){d.showModal();};});
  });
}
// the Sort and You popovers open under their buttons, the You one right-aligned; on a phone the CSS makes them bottom sheets
function popovers(){
  $('pshow').onclick=function(){$('sortpop').hidePopover();};
  [['sortpop','sortb',420]].forEach(function(x){
    var p=$(x[0]),b=$(x[1]);
    p.addEventListener('beforetoggle',function(e){
      if(e.newState!=='open')return;
      [].forEach.call(p.querySelectorAll('details details'),function(d){d.open=true;});  // the genera threshold shows at once
      var r=b.getBoundingClientRect();
      p.style.setProperty('--pt',r.bottom+6+'px');p.style.setProperty('--pl',Math.max(8,Math.min(r.right-x[2],innerWidth-x[2]-8))+'px');});
  });
}
function start(){
  popovers();
  sheets();labels();count();
  var mo=new MutationObserver(function(){labels();count();});
  ['cap','status'].forEach(function(id){mo.observe($(id),{childList:true,characterData:true,subtree:true});});
  ['none','batch'].forEach(function(id){mo.observe($(id),{attributes:true,subtree:true,attributeFilter:['hidden']});});
  mo.observe($('usrbox'),{attributes:true,attributeFilter:['hidden'],childList:true,subtree:true});
  document.addEventListener('change',labels);
  addEventListener('hashchange',labels);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
