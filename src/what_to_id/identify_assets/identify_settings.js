// The language links in the header (the current one is plain text) and the Settings popover (#setpop, native radios): how species names show.
// A change saves and reloads; the Popover API closes it on Escape and returns focus to the gear, which after a reload takes it back (a language change leaves focus on the other language link).
(function(){
'use strict';
function start(){
  var pop=document.getElementById('setpop'),b=document.getElementById('setb');
  [].forEach.call(document.querySelectorAll('.lng a'),function(a){
    if(a.lang===I18N.lang){a.removeAttribute('href');a.setAttribute('aria-current','true');}
    else a.addEventListener('click',function(e){e.preventDefault();I18N.set('lang',a.lang);});
  });
  [].forEach.call(pop.querySelectorAll('input'),function(i){
    i.checked=i.value===I18N[i.name];
    i.addEventListener('change',function(){I18N.set(i.name,i.value);});
  });
  try{var w=sessionStorage.getItem('wtid-set');if(w){sessionStorage.removeItem('wtid-set');(w==='lang'?document.querySelector('.lng a[href]'):b).focus();}}catch(e){}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
