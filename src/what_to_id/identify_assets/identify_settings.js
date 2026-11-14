// The Settings popover (#setpop, native radios): the page language and how species names show (identify_i18n.js keeps both).
// A change saves and reloads; the Popover API closes it on Escape and returns focus to the gear, which after a reload takes it back.
(function(){
'use strict';
function start(){
  var pop=document.getElementById('setpop'),b=document.getElementById('setb');
  [].forEach.call(pop.querySelectorAll('input'),function(i){
    i.checked=i.value===I18N[i.name];
    i.addEventListener('change',function(){I18N.set(i.name,i.value);});
  });
  try{if(sessionStorage.getItem('wtid-set')){sessionStorage.removeItem('wtid-set');b.focus();}}catch(e){}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
