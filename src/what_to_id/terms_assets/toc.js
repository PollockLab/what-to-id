(function(){
var toc=document.getElementById('toc'),links=[].slice.call(toc.querySelectorAll('a'));
var wide=matchMedia('(min-width:1100px)');
function fit(){toc.open=wide.matches;}
fit();wide.addEventListener('change',fit);
var by={};links.forEach(function(a){by[a.getAttribute('href').slice(1)]=a;});
var heads=[].slice.call(document.querySelectorAll('main :is(h2,h3)')).filter(function(h){return by[h.id];});
function mark(id){links.forEach(function(a){
  if(a===by[id])a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}
links.forEach(function(a){a.addEventListener('click',function(){mark(a.getAttribute('href').slice(1));
  if(!wide.matches)toc.open=false;});});
if('IntersectionObserver' in window){
  var inside={};  // the first callback reports every heading, so only a heading seen inside counts as left
  var io=new IntersectionObserver(function(es){es.forEach(function(e){
    var i=heads.indexOf(e.target);
    if(e.isIntersecting){inside[e.target.id]=1;mark(e.target.id);}
    else if(inside[e.target.id]){delete inside[e.target.id];if(e.boundingClientRect.top>0&&i>0)mark(heads[i-1].id);}});
  },{rootMargin:'0px 0px -75% 0px'});
  heads.forEach(function(h){io.observe(h);});
}
var box=document.getElementById('find'),q=document.getElementById('find-q'),n=document.getElementById('find-n');
var dts=[].slice.call(document.querySelectorAll('#glossary-list dt'));
box.hidden=false;
q.addEventListener('input',function(){
  var v=q.value.trim().toLowerCase(),shown=0;
  dts.forEach(function(dt){var dd=dt.nextElementSibling,
    ok=!v||(dt.textContent+' '+dd.textContent).toLowerCase().indexOf(v)>=0;
    dt.hidden=dd.hidden=!ok;if(ok)shown++;});
  [].forEach.call(document.querySelectorAll('#glossary-list dl'),function(dl){
    var h=dl.previousElementSibling;dl.hidden=h.hidden=!dl.querySelector('dt:not([hidden])');});
  n.textContent=v?shown+' of '+dts.length+' terms':'';
});
})();
