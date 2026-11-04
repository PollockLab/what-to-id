// The split view's search box asks this frame what its text could pick (wtid-suggest, answered with
// rows {group,key,label,sub,count,exact}) and applies a row (wtid-apply {group,key}) as the map's own
// control would: a taxon as a #q pick, a park as ticking it in the park picker, a user as the User box,
// a project as a pasted one. Users and projects are offered only for text that names one outright.
// o: taxa(), counts(), S, ranks, area, pj, pick(id) and user(login).
var MapSuggest=(function(){
var USER=/^(?:@|(?:https?:\/\/)?(?:[a-z]+\.)?inaturalist\.[a-z]{2,3}(?:\.[a-z]{2})?\/people\/)([A-Za-z0-9_-]{1,40})\/?$/i,
  PROJ=/^(?:https?:\/\/)?(?:[a-z]+\.)?inaturalist\.[a-z]{2,3}(?:\.[a-z]{2})?\/projects\//i;
function norm(s){return String(s||'').trim().toLowerCase().replace(/s$/,'');}  // a plural names what its singular does
function shown(id){var e=document.getElementById(id);return !!e&&!e.hidden;}
return function(o){
  function rows(q){var out=[],T=o.taxa(),c=T&&o.counts();
    if(T)TX.suggest(T,q,c,o.S.picks).forEach(function(r){var t=T[r];
      out.push({group:'Taxon',key:String(t[2]),label:t[0],count:c[r]||0,
        sub:[t[1],t[3]!==255?o.ranks[t[3]]:''].filter(Boolean).join(' · '),exact:norm(q)===norm(t[0])||norm(q)===norm(t[1])});});
    return out;}
  function names(q){var out=[],u=USER.exec(q),p=PROJ.test(q)&&projParse(q);
    if(u&&usrParse(u[1])&&shown('usrbox'))out.push({group:'User',key:u[1],label:'@'+u[1],sub:'iNaturalist user',exact:true});
    if(p&&shown('projbox'))out.push({group:'Project',key:p,label:'Project '+p,sub:'iNaturalist project',exact:true});
    return out;}
  addEventListener('message',function(e){
    var d=e.data;
    if(e.origin!==location.origin||parent===window||e.source!==parent||!d)return;
    if(d.type==='wtid-suggest'&&typeof d.q==='string'){var q=d.q.trim().slice(0,200);
      o.area.suggest(q).then(function(ps){
        parent.postMessage({type:'wtid-suggest',seq:d.seq,rows:rows(q).concat(ps.map(function(r){
          return Object.assign({group:'Place'},r);}),names(q))},location.origin);});}
    else if(d.type==='wtid-apply'&&typeof d.key==='string'){var T=o.taxa(),id=+d.key;
      if(d.group==='Taxon'&&T&&T.some(function(t){return t[2]===id;}))o.pick(id);
      else if(d.group==='Place')o.area.pick(d.key);
      else if(d.group==='User'&&usrParse(d.key)&&shown('usrbox'))o.user(d.key);
      else if(d.group==='Project'&&projId(d.key)&&shown('projbox'))o.pj.add(projId(d.key));}
  });
};
})();
