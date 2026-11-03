// Toggletips: any element with data-explain="<key>" explains itself from #explain-data (glossary.py) in one shared
// popover. Hover opens it after 300 ms where there is a mouse, a click, tap, Enter or Space pins it, Esc or a click
// outside closes it; on a touch phone it is a bottom sheet. Listeners sit on document, so rows drawn later work too.
// Rule for controls: a link, button, field, label or summary never becomes a trigger and keeps its own click; tag the
// text beside or above it instead.
(function(){
var D=document.getElementById('explain-data'),G=D?JSON.parse(D.textContent):{},
  CTRL='a,button,input,select,textarea,label,summary',pop,cur=null,pin=false,t=0,q=0;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e;}
function hover(){return matchMedia('(hover:hover)').matches;}
function free(x){return !x.closest(CTRL)&&!x.querySelector(CTRL);}
function trig(e){
  var x=e.target&&e.target.closest&&e.target.closest('[data-explain]');
  return x&&G[x.dataset.explain]&&free(x)?x:null;
}
// role, tab stop and state for the triggers on the page; rows drawn later get them on the next frame
function prep(){
  [].forEach.call(document.querySelectorAll('[data-explain]:not([aria-controls])'),function(x){
    if(!G[x.dataset.explain]||!free(x))return;
    x.setAttribute('role','button');if(!x.hasAttribute('tabindex'))x.tabIndex=0;
    x.setAttribute('aria-expanded','false');x.setAttribute('aria-controls','explain-pop');});
}
pop=el('div','xpop');pop.id='explain-pop';pop.setAttribute('role','dialog');pop.hidden=true;pop.tabIndex=-1;
var X=el('button','xx','×');X.type='button';X.setAttribute('aria-label','Close');
X.onclick=function(){close(true);};
var more=el('a','xmore','More →');
pop.append(X,el('p','xdef'),el('p','xuse'),more);
(document.body||document.documentElement).appendChild(pop);
function open(x,p,kb){
  clearTimeout(t);
  if(cur&&cur!==x)cur.setAttribute('aria-expanded','false');
  var g=G[x.dataset.explain];cur=x;pin=p;
  pop.setAttribute('aria-label',x.textContent.trim()||x.dataset.explain);
  pop.children[1].textContent=g[0];
  pop.children[2].textContent=g[1]||'';pop.children[2].hidden=!g[1];
  if(g[2])more.href=g[2];else more.removeAttribute('href');more.hidden=!g[2];
  x.setAttribute('aria-expanded','true');pop.hidden=false;
  if(innerWidth>=600||hover()){var r=x.getBoundingClientRect(),w=pop.offsetWidth,h=pop.offsetHeight;
    pop.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';
    pop.style.top=Math.max(8,Math.min(r.bottom+h+12>innerHeight&&r.top>h+12?r.top-h-6:r.bottom+6,innerHeight-h-8))+'px';}
  else{pop.style.left=pop.style.top='';}
  if(kb)pop.focus();
}
function close(refocus){
  clearTimeout(t);
  if(pop.hidden)return;
  pop.hidden=true;cur.setAttribute('aria-expanded','false');
  if(refocus)cur.focus();
  cur=null;
}
document.addEventListener('mouseover',function(e){
  if(!hover())return;
  var x=trig(e);
  if(pop.contains(e.target)||x&&x===cur){clearTimeout(t);return;}
  if(x){clearTimeout(t);t=setTimeout(function(){open(x,false,false);},300);}
});
document.addEventListener('mouseout',function(e){
  var x=trig(e),r=e.relatedTarget,o=x||cur;
  if(!x&&!pop.contains(e.target))return;
  if(r&&(pop.contains(r)||o&&o.contains(r)))return;
  clearTimeout(t);
  if(cur&&!pin)t=setTimeout(function(){close(false);},200);
});
document.addEventListener('click',function(e){
  var x=trig(e);if(!x)return;
  if(x===cur&&!pop.hidden&&(pin||e.detail===0)){close(e.detail===0);return;}
  open(x,true,e.detail===0);
});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'&&!pop.hidden){var a=document.activeElement;close(a===cur||pop.contains(a));return;}
  var x=(e.key==='Enter'||e.key===' ')&&trig(e);if(!x)return;
  e.preventDefault();
  if(x===cur&&!pop.hidden)close(true);else open(x,true,true);
});
document.addEventListener('pointerdown',function(e){
  if(!pop.hidden&&!pop.contains(e.target)&&!(cur&&cur.contains(e.target)))close(false);
});
new MutationObserver(function(){if(!q)q=requestAnimationFrame(function(){q=0;prep();});})
  .observe(document.documentElement,{childList:true,subtree:true});
prep();
})();
