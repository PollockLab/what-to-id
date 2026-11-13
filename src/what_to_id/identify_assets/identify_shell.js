// The page's chrome around the modules' own controls: the Filters button opens the Range, Confidence, Sort, Research Grade,
// By species and User controls in a sheet (the search bar, identify_bar.js, holds What, When and Where). Each filter away from its
// default (its hash key present) shows as a chip with a remove button, and the Filters button counts them. The result
// line counts the cards from the batch caption (which becomes its title) and holds the batch links in a popover.
// A help sheet holds the page notes, totals, progress, the level description and the keys.
// The modules keep writing their own controls and hash keys; this only moves and names them.
(function(){
'use strict';
function $(id){return document.getElementById(id);}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function has(k){return new RegExp('(^|&)'+k+'=').test(location.hash.slice(1));}
var NS='http://www.w3.org/2000/svg';
function cross(){var s=document.createElementNS(NS,'svg'),p=document.createElementNS(NS,'path');s.setAttribute('viewBox','0 0 24 24');
  s.setAttribute('aria-hidden','true');p.setAttribute('d','M6 6l12 12M18 6L6 18');s.appendChild(p);return s;}
// a filter: its hash key, and where its control is (a segmented row, or the By species box)
var F=[['out','#rout .seg'],['conf','#sort .seg[aria-label=Confidence]'],['sort','#sort .seg[aria-label=Sort]'],['rg','#rg .seg'],['run','#frun input']];
function label(f){
  var c=document.querySelector(f[1]);if(!c)return null;
  if(c.tagName==='INPUT')return c.parentNode.textContent.trim();
  return c.getAttribute('aria-label')+': '+[].filter.call(c.children,function(b){return b.getAttribute('aria-checked')==='true';})
    .map(function(b){return b.textContent;}).join(' + ');
}
// back to the default: the box unticked, a radio row's options tried in order until the key leaves the hash, a checkbox row all on
function clear(f){
  var c=document.querySelector(f[1]);if(!c)return;
  if(c.tagName==='INPUT'){c.click();return;}
  [].some.call(c.children,function(b){
    if(c.getAttribute('role')==='group'?b.getAttribute('aria-checked')==='false':true)b.click();return !has(f[0]);});
}
function on(){return F.filter(function(f){return has(f[0])&&document.querySelector(f[1]);});}
function chips(){
  var a=on(),box=$('chips'),n=$('fcount');
  box.replaceChildren.apply(box,a.map(function(f){
    var t=label(f),c=el('span','chip',t+' '),x=el('button','chipx');x.type='button';x.setAttribute('aria-label','Remove '+t);
    x.appendChild(cross());x.onclick=function(){clear(f);chips();$('fbtn').focus();};c.appendChild(x);return c;}));
  n.hidden=!a.length;n.textContent=a.length;$('fbtn').setAttribute('aria-label','Filters'+(a.length?', '+a.length+' on':''));
}
function count(){
  var cap=$('cap').textContent,m=/^[\d,.\s ]+/.exec(cap),n=$('none').hidden?(m?m[0].trim():''):'0';
  var st=$('status').textContent;  // loading and load errors stay in sight while the totals sit in the help sheet
  $('count').textContent=n?n+' cards to ID':/^(Loading|Could not)/.test(st)?st:'';$('count').title=cap;$('inatb').title=cap;
  [].forEach.call(document.querySelectorAll('.sdone .n'),function(s){s.textContent=n||'0';});
  $('inatb').hidden=$('batch').hidden;
}
function sheets(){
  [].forEach.call(document.querySelectorAll('dialog.sheet'),function(d){
    [].forEach.call(d.querySelectorAll('.shx,.sdone'),function(b){b.onclick=function(){d.close();};});
    d.addEventListener('click',function(e){if(e.target===d)d.close();});  // a click on the backdrop
    d.addEventListener('close',chips);
    d.addEventListener('keydown',function(e){  // Tab wraps inside, where a modal alone would let it out to the browser
      if(e.key!=='Tab')return;
      var f=[].filter.call(d.querySelectorAll('button,select,input,a[href],summary,[tabindex="0"]'),function(x){return x.offsetParent&&!x.disabled;});
      var a=f[0],z=f[f.length-1];
      if(e.shiftKey?document.activeElement===a:document.activeElement===z){e.preventDefault();(e.shiftKey?z:a).focus();}});
    [].forEach.call(document.querySelectorAll('[aria-controls="'+d.id+'"]'),function(b){
      b.onclick=function(){d.showModal();var s=b.id==='sortb'&&$('sort');if(s&&!s.hidden)s.scrollIntoView({block:'nearest'});};});
  });
  $('fclear').onclick=function(){on().forEach(clear);chips();};
}
function start(){
  sheets();chips();count();
  var mo=new MutationObserver(function(){chips();count();});
  ['cap','status'].forEach(function(id){mo.observe($(id),{childList:true,characterData:true,subtree:true});});
  ['none','batch','fsheet'].forEach(function(id){mo.observe($(id),{attributes:true,subtree:true,attributeFilter:['hidden','aria-checked']});});
  document.addEventListener('change',chips);
  addEventListener('hashchange',chips);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
