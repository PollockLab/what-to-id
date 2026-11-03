// The user filter. The User box takes an iNaturalist login or user number (hash: user=, and umode=
// taxa or unid; none is Observer, or My taxa on a map without an observer file). Observer opens
// Identify on the user's records (user_id); the others add without_ident_user_id, which would hide nearly all of an observer's own records. The
// select narrows the map by one of three rules: Observer (the default) keeps the dots the user observed
// (pool-observer.bin, one uint32 per record in shard order), My taxa the dots inside a genus or family
// the user has identified in BC, Not yet identified by me hides the dots the user identified in the view.
// Everything but the observer file comes from api.inaturalist.org in the browser, one request at a
// time and at least a second apart, and is kept for the session. Without a user nothing is filtered.
var USR_CAP={taxa:5,unid:25},USR_PER={taxa:500,unid:200};
// {id} for a user number, {login} for a login, null for anything else.
function usrParse(s){s=String(s||'').trim();
  return /^\d+$/.test(s)?(+s>0&&+s<=4294967295?{id:+s}:null):/^[A-Za-z0-9_-]{1,40}$/.test(s)?{login:s}:null;}
// The taxa the My taxa mode keeps, as iNaturalist ids: each species_counts taxon and those of its
// ancestors (ancestor_ids) the pool has as a genus or family row. T is the pool taxa, ranks META.ranks.
function usrRanked(T,ranks,results){
  var row=new Map(),out=[],seen={};T.forEach(function(t){row.set(t[2],t);});
  results.forEach(function(r){var x=r.taxon||{};
    (x.ancestor_ids||[]).concat(x.id).forEach(function(id){var t=row.get(id),k=t&&t[3]!==255?ranks[t[3]]:'';
      if(id&&!seen[id]&&(id===x.id||k==='genus'||k==='family')){seen[id]=1;out.push(id);}});});
  return out;}
// 1 per pool taxa row at or below one of ids (TX.filter's inside test, so a family-level record counts
// when its family is in); no ids keeps nothing.
function usrMask(T,ids){return ids.length?TX.filter(T,ids.map(function(id){return {id:id,not:false};})).inc:
  new Uint8Array(T.length);}
// Pages 1..cap of a listing one after the other; get(page) gives {results, total_results}. capped is
// true when the listing goes on past the last page read.
function usrPages(get,cap,per){var out=[];
  function next(p){return get(p).then(function(j){var r=j.results||[];out=out.concat(r);
    if(r.length<per||(j.total_results&&out.length>=j.total_results))return {items:out,capped:false};
    return p>=cap?{items:out,capped:true}:next(p+1);});}
  return next(1);}
// api.inaturalist.org/v1 from the browser (the map's user filter, the tree's identifier counts): one request at a time,
// the next no sooner than gap ms after the last began, each answer (and each request in flight) kept for the session. A throttled reply (429 comes
// without CORS headers, so it reads as a TypeError) or a 5xx is tried again after 5 and 15 gaps, saying so through
// say; live() false on a queued request drops it unsent. api(path[, live]) gives the parsed JSON.
function inatGate(o){var cache={},q=Promise.resolve(),last=0,gap=o.gap==null?1000:o.gap,fetcher=o.fetch||function(u){return fetch(u);};
  return function(path,live){var url='https://api.inaturalist.org/v1/'+path;if(cache[url])return cache[url];
    function wait(ms){return new Promise(function(r){setTimeout(r,Math.max(0,ms));});}
    function go(n){return wait(last+gap-Date.now()).then(function(){last=Date.now();return fetcher(url);})
      .then(function(r){if(r.status===429||r.status>=500)throw new TypeError('busy');if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
      .catch(function(e){if(!(e instanceof TypeError)||n>=2)throw e;if(o.say)o.say('iNaturalist is busy, trying again…');
        return wait([5,15][n]*gap).then(function(){return go(n+1);});});}
    var p=cache[url]=q.then(function(){if(live&&!live())throw 0;return go(0);});  // kept while in flight, so a repeat asks nothing
    q=p.catch(function(){delete cache[url];});return p;};}
function userFilter(o){
  var S=o.S,META=o.meta,nf=new Intl.NumberFormat('en-CA'),box=document.getElementById('usrbox'),
    api=inatGate({gap:o.gap,fetch:o.fetch,say:function(t){say(t);}}),cur='',run=0,id=0,mask=null,ob=null,hide=null,capped=false,key=0,Pn=null,input,mode,msg,again;
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  function em(){return S.umode||(META.observer?'observer':'taxa');}
  function say(t){if(msg)msg.textContent=t;}
  function load(m,p){
    var place='&place_id='+META.place_id;
    if(m==='observer'){if(!META.observer)throw new Error('This map has no observer file');
      return o.get(META.observer).then(function(buf){if(buf.byteLength!==4*META.n)throw new Error('observer file does not match the map');
        ob=new Uint32Array(buf);});}
    if(m==='unid'){var b=o.bounds(),view='&swlat='+b.s.toFixed(4)+'&swlng='+b.w.toFixed(4)+'&nelat='+b.n.toFixed(4)+'&nelng='+b.e.toFixed(4);
      return usrPages(function(n){return api('observations?ident_user_id='+id+place+'&quality_grade=needs_id&per_page=200&only_id=true'+view+'&page='+n);},
        USR_CAP.unid,USR_PER.unid).then(function(r){hide=new Set(r.items.map(function(x){return x.id;}));capped=r.capped;});}
    return usrPages(function(n){return api('identifications/species_counts?user_id='+id+place+'&per_page=500&page='+n);},
      USR_CAP.taxa,USR_PER.taxa).then(function(r){capped=r.capped;
      mask=usrMask(o.taxa(),usrRanked(o.taxa(),META.ranks,r.items));});}
  // Starts what S.user and S.umode ask for once, whenever the records are drawn again.
  function start(){
    var u=S.user,m=em(),p=usrParse(u),k=u?u+'|'+m:'';
    if(k===cur||(p&&m==='taxa'&&!o.taxa()))return;  // My taxa waits for the taxa table; the next refilter retries
    var tag=++run;cur=k;id=0;mask=ob=hide=null;capped=false;key++;
    if(!u){say('');return;}
    if(!p){say('Enter an iNaturalist login or user number.');return;}
    say('Looking up '+u+'…');
    var live=function(v){if(run!==tag)throw 0;return v;};
    (p.id?Promise.resolve(p.id):api('users/autocomplete?q='+encodeURIComponent(p.login)).then(function(j){
      var r=(j.results||[]).filter(function(x){return String(x.login).toLowerCase()===p.login.toLowerCase();})[0];
      if(!r)throw new Error('No iNaturalist user "'+p.login+'"');return r.id;})).then(live)
    .then(function(v){id=v;key++;o.changed();say('Loading '+u+'…');return load(m,p);}).then(live)
    .then(function(){say(m==='observer'?'Showing records observed by '+u+'.':m==='unid'?'Hiding records '+u+' identified.':
        'Showing taxa '+u+' has identified.');key++;o.changed();})
    .catch(function(e){if(e===0)return;mask=ob=hide=null;key++;
      say(e instanceof TypeError?'Could not reach iNaturalist.':e.message);o.changed();});}
  function apply(){S.user=input.value.trim().slice(0,100);S.umode=mode.value===(META.observer?'observer':'taxa')?'':mode.value;o.changed();}
  if(box){
    box.appendChild(el('summary',null,'User'));
    var f=box.appendChild(el('form','prow')),lab=f.appendChild(el('label','muted','iNaturalist login or user number'));
    input=f.appendChild(el('input','padd'));input.id=lab.htmlFor='usrname';input.type='text';
    input.placeholder='Login or number';input.autocomplete='off';input.spellcheck=false;
    mode=f.appendChild(el('select'));mode.setAttribute('aria-label','What to do with the user');
    [['observer','Observer'],['taxa','My taxa'],['unid','Not yet identified by me']].forEach(function(m){
      var op=mode.appendChild(el('option',null,m[1]));op.value=m[0];
      if(m[0]==='observer'&&!META.observer)op.disabled=true;});
    again=f.appendChild(el('button','padd','Reload for this view'));again.type='button';again.hidden=true;
    again.onclick=function(){cur='';o.changed();};
    f.onsubmit=function(e){e.preventDefault();apply();};input.onchange=apply;mode.onchange=apply;
    msg=box.appendChild(el('p','muted'));msg.setAttribute('aria-live','polite');box.hidden=false;
  }
  return {
    // brings the box in line with S and starts any load it needs; P is the records so far
    sync:function(P){Pn=P;if(input){if(document.activeElement!==input)input.value=S.user;
      mode.value=em();again.hidden=em()!=='unid'||!S.user;}start();},
    drop:function(i){if(!id)return false;
      if(mask){var t=Pn.tax[i];return !(t<mask.length&&mask[t]===1);}
      if(ob)return i<ob.length&&ob[i]!==id;
      return hide?hide.has(Pn.id[i]):false;},
    key:function(){return key;},
    active:function(){return !!(mask||ob||hide);},
    params:function(){return !id?{}:em()==='observer'?{user_id:String(id)}:{without_ident_user_id:String(id)};},
    tip:function(){return id&&em()!=='observer'?' Records the user identified are left out; ones you skipped are hidden by iNaturalist when you are signed in.':'';},
    // the map counts are approximate under My taxa and Not yet identified, as Identify cannot say them
    note:function(){return mask?'The map keeps only the genera and families '+S.user+' has identified'+(capped?' (first '+
      nf.format(USR_CAP.taxa*USR_PER.taxa)+' taxa only)':'')+', which Identify cannot filter, so its count differs.':
      hide?'The map hides records '+S.user+' identified'+(capped?' (first '+nf.format(USR_CAP.unid*USR_PER.unid)+' only)':'')+
        ', so its count is approximate.':'';}
  };
}
