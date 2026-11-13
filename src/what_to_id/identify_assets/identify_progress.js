// Progress: the cards opened today on this device, and for an iNaturalist login (hash me=, else the one typed, kept in
// localStorage) the improving IDs it made for others in the last 30 days, toward the 10 an OAuth app needs. Counts
// come from /v1/identifications total_results, kept for 10 minutes. No sign in.
var IdentifyProgress=(function(){
'use strict';
var OPENED='wtid-opened',LOGIN='wtid-login',CACHE='wtid-improving',GOAL=10,TTL=6e5;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function get(k){try{return JSON.parse(localStorage.getItem(k));}catch(e){return null;}}
function put(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
function day(){return new Date().toLocaleDateString('en-CA');}
return function(box){
  var o=get(OPENED),ids=new Set(o&&o.d===day()?o.ids:[]),n=el('span'),me=el('input','padd'),bar=el('progress'),t=el('span','muted');
  var h=/(?:^|&)me=([\w-]{1,40})(?:&|$)/.exec(location.hash.slice(1));
  me.placeholder='iNat login';me.size=10;me.setAttribute('aria-label','Your iNaturalist login');me.value=h?h[1]:get(LOGIN)||'';
  bar.max=GOAL;bar.hidden=true;
  function count(){n.textContent=ids.size+' opened today';}
  function improving(){
    var u=me.value.trim();bar.hidden=true;t.textContent='';
    if(!/^[\w-]{1,40}$/.test(u))return;
    put(LOGIN,u);
    var c=get(CACHE),show=function(v){bar.hidden=false;bar.value=Math.min(v,GOAL);t.textContent=v+'/'+GOAL+' IDs, 30 days';t.title='Improving IDs for others in the last 30 days; 10 open iNaturalist OAuth';};
    if(c&&c.u===u&&Date.now()-c.at<TTL)return show(c.n);
    var q=new URLSearchParams({user_id:u,own_observation:'false',current:'true',category:'improving',
      d1:new Date(Date.now()-30*864e5).toISOString().slice(0,10),per_page:'1'});
    fetch('https://api.inaturalist.org/v1/identifications?'+q).then(function(r){if(!r.ok)throw 0;return r.json();})
      .then(function(j){if(me.value.trim()!==u)return;put(CACHE,{u:u,at:Date.now(),n:j.total_results});show(j.total_results);})
      .catch(function(){if(me.value.trim()===u)t.textContent='Login not found';});
  }
  document.addEventListener('wtid-opened',function(e){
    if(ids.has(e.detail))return;ids.add(e.detail);put(OPENED,{d:day(),ids:[...ids]});count();});
  me.onchange=improving;
  box.append(n,' · ',me,' ',bar,' ',t);count();improving();
};
})();
