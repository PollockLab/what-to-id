// "My taxa first" in #me: with an iNaturalist login, the records whose label or look-alike sits in a genus where the user has
// made at least USR_MIN identifications in the map's place (fewer when none reach it, usrKeep) come first in every level.
// The genera come from identifications/species_counts, as the map's My taxa. The login is kept in the hash (me=) and
// localStorage, and goes only to iNaturalist.
// IdentifyMine(ctx), ctx {taxa (the TAXA table), ranks, place, tax (each record's taxa row), look(i) the look-alike or null,
// redraw(), track(name)}. Needs map_user.js (usrParse, inatGate, usrPages, usrKeep, usrMask).
var IdentifyMine=(function(){
'use strict';
var LS='wtid-identify-me';
function $(id){return document.getElementById(id);}
function hashGet(){var m=/(?:^|&)me=([^&]*)/.exec(location.hash.slice(1));return m?decodeURIComponent(m[1]):null;}
function hashSet(v){
  var t=location.hash.slice(1).split('&').filter(function(x){return x&&x.indexOf('me=')!==0;});
  if(v)t.push('me='+encodeURIComponent(v));
  history.replaceState(null,'','#'+t.join('&'));
}
return function(ctx){
  var T=ctx.taxa,row=new Map(),mask=null,run=0,input,note,
    api=inatGate({say:function(t){if(note)note.textContent=t;}});
  T.forEach(function(t,r){row.set(t[0],r);});
  // 1 when record i's label or look-alike is in one of the user's genera
  function has(i){
    if(!mask)return false;
    var t=ctx.tax[i];if(t<mask.length&&mask[t])return true;
    var l=ctx.look(i),r=l==null?undefined:row.get(l);return r!==undefined&&!!mask[r];
  }
  function load(u){
    var me=++run,p=usrParse(u),live=function(v){if(me!==run)throw 0;return v;};
    mask=null;
    if(!u){note.textContent='';ctx.redraw();return;}
    if(!p){note.textContent='Enter an iNaturalist login or user number.';ctx.redraw();return;}
    note.textContent='Reading '+u+"'s identifications…";
    (p.id?Promise.resolve(p.id):api('users/autocomplete?q='+encodeURIComponent(p.login)).then(function(j){
      var r=(j.results||[]).filter(function(x){return String(x.login).toLowerCase()===p.login.toLowerCase();})[0];
      if(!r)throw new Error('No iNaturalist user "'+p.login+'"');return r.id;})).then(live)
    .then(function(id){return usrPages(function(n){
      return api('identifications/species_counts?user_id='+id+'&place_id='+ctx.place+'&per_page=500&page='+n);},USR_CAP.taxa,USR_PER.taxa);})
    .then(live).then(function(r){
      var k=usrKeep(T,ctx.ranks,r.items,USR_MIN);
      mask=k.genera.length?usrMask(T,k.genera.map(function(e){return e[0];})):null;
      note.textContent=mask?'Records in your '+k.genera.length+(k.genera.length===1?' genus':' genera')+' (at least '+k.used+
        ' of your IDs each) come first.':u+' has fewer than '+USR_MINS[0]+' IDs in any genus here yet, so the order is unchanged.';
      ctx.track('mine-'+(mask?'on':'none'));ctx.redraw();})
    .catch(function(e){if(e===0)return;note.textContent=e instanceof TypeError?'Could not reach iNaturalist.':e.message;ctx.redraw();});
  }
  function apply(){
    var v=input.value.trim().slice(0,100);
    try{if(v)localStorage.setItem(LS,v);else localStorage.removeItem(LS);}catch(e){}
    hashSet(v);load(v);
  }
  var box=$('me');  // the form is in the page, so it does not shift the cards when the records land
  if(box){
    input=$('melogin');note=box.querySelector('.segnote');
    box.querySelector('form').onsubmit=function(e){e.preventDefault();apply();};
    var v=hashGet();
    if(v===null)try{v=localStorage.getItem(LS);}catch(e){}
    if(v){input.value=v;load(v);}
  }
  return {has:has,active:function(){return !!mask;}};
};
})();
