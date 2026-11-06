// The user filter. The User box takes an iNaturalist login or user number (hash: user=, and umode=
// first, taxa or unid; none is Observer, or My taxa without an observer file, so old links keep their meaning; a typed
// login starts on My taxa first; umin= is the genus threshold of My taxa and My taxa first,
// 5, 20 or 100, none is 50). Observer opens
// Identify on the user's records (user_id); the others add without_ident_user_id, which would hide nearly all of an observer's own records. The
// select applies one of four rules: My taxa first hides nothing but ranks the records inside a genus where
// the user has at least umin current identifications in BC (mine(i): first on Identify, the rest dimmed on the map),
// My taxa keeps only those, Observer keeps the dots the user observed
// (pool-observer.bin, one uint32 per record in shard order), Not yet identified by me hides the dots the user identified in the view.
// Everything but the observer file comes from api.inaturalist.org in the browser, one request at a
// time and at least a second apart, and is kept for the session. Without a user nothing is filtered.
var USR_CAP={taxa:5,unid:25},USR_PER={taxa:500,unid:200},USR_MINS=[5,20,50,100],USR_MIN=50;
// {id} for a user number, {login} for a login, null for anything else.
function usrParse(s){s=String(s||'').trim();
  return /^\d+$/.test(s)?(+s>0&&+s<=4294967295?{id:+s}:null):/^[A-Za-z0-9_-]{1,40}$/.test(s)?{login:s}:null;}
// The genera the My taxa mode keeps, as [iNaturalist id, count] pairs: each species_counts count is added to
// the pool genus row among the taxon and its ancestors (ancestor_ids), and a genus stays at min or more.
// Records identified above genus rank belong to no genus. T is the pool taxa, ranks META.ranks.
function usrGenera(T,ranks,results,min){
  var row=new Map(),sum=new Map();T.forEach(function(t){row.set(t[2],t);});
  results.forEach(function(r){var x=r.taxon||{},g=(x.ancestor_ids||[]).concat(x.id).filter(function(id){
    var t=row.get(id);return t&&t[3]!==255&&ranks[t[3]]==='genus';})[0];
    if(g)sum.set(g,(sum.get(g)||0)+(r.count||0));});
  return Array.from(sum).filter(function(e){return e[1]>=min;});}
// usrGenera at min, or when that keeps none at the highest lower threshold of USR_MINS that keeps one:
// {genera, used}, used 0 when even the lowest keeps none.
function usrKeep(T,ranks,results,min){
  var ts=USR_MINS.filter(function(t){return t<=min;}).reverse(),g=[];
  for(var i=0;i<ts.length;i++){g=usrGenera(T,ranks,results,ts[i]);if(g.length)return {genera:g,used:ts[i]};}
  return {genera:[],used:0};}
// Which of the genera (ids) fit one Identify link, as {ids, cut}: all of them while their ids stay within
// budget characters, else the ones with the most pool records (tax: each record's taxa row) that do, and
// cut is how many were left out.
function usrFit(T,ranks,ids,tax,budget){
  var len=ids.reduce(function(n,id){return n+String(id).length+1;},0);
  if(len-1<=budget)return {ids:ids,cut:0};
  var want=new Set(ids),need=new Map(),memo=new Map();
  function up(r){var g=memo.get(r);if(g!==undefined)return g;
    g=want.has(T[r][2])&&ranks[T[r][3]]==='genus'?T[r][2]:T[r][4]>=0?up(T[r][4]):0;memo.set(r,g);return g;}
  for(var i=0;i<tax.length;i++)if(tax[i]<T.length){var g=up(tax[i]);if(g)need.set(g,(need.get(g)||0)+1);}
  var top=ids.slice().sort(function(a,b){return (need.get(b)||0)-(need.get(a)||0);}),out=[],n=-1;
  for(var k=0;k<top.length&&n+String(top[k]).length+1<=budget;k++){out.push(top[k]);n+=String(top[k]).length+1;}
  return {ids:out,cut:ids.length-out.length};}
// 1 per pool taxa row at or below one of ids (TX.filter's inside test); no ids keeps nothing.
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
    api=inatGate({gap:o.gap,fetch:o.fetch,say:function(t){say(t);}}),cur='',run=0,id=0,mask=null,ob=null,hide=null,capped=false,key=0,Pn=null,gen=[],used=0,fit=null,input,mode,minsel,msg,again;
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  function em(){return S.umode||(META.observer?'observer':'taxa');}
  function min(){return S.umin||USR_MIN;}
  // the genera kept and how many go to Identify: ids that fit the URL beside the rest of the link
  function kept(){var n=Pn?Pn.n:0;
    if(!fit||fit.n!==n)fit=Object.assign({n:n},usrFit(o.taxa(),META.ranks,gen.map(function(e){return e[0];}),
      Pn?Pn.tax:[],META.max_url-1500));return fit;}
  function head(){return gen.length?'Genera where '+S.user+' has at least '+used+' IDs in BC ('+nf.format(gen.length)+
    (gen.length===1?' genus':' genera')+')'+(used<min()?'; none reach '+min()+' yet.':'.'):
    S.user+' has fewer than '+USR_MINS[0]+' IDs in any BC genus yet. Try Observer or Not yet identified by me.';}
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
      var k=usrKeep(o.taxa(),META.ranks,r.items,min());gen=k.genera;used=k.used;fit=null;
      mask=usrMask(o.taxa(),gen.map(function(e){return e[0];}));});}
  // Starts what S.user and S.umode ask for once, whenever the records are drawn again.
  function start(){
    var u=S.user,m=em(),g=m==='taxa'||m==='first',p=usrParse(u),k=u?u+'|'+m+(g?'|'+min():''):'';
    if(k===cur||(p&&g&&!o.taxa()))return;  // the genus modes wait for the taxa table; the next refilter retries
    var tag=++run;cur=k;id=0;mask=ob=hide=null;gen=[];used=0;fit=null;capped=false;key++;
    if(!u){say('');return;}
    if(!p){say('Enter an iNaturalist login or user number.');return;}
    say('Looking up '+u+'…');
    var live=function(v){if(run!==tag)throw 0;return v;};
    (p.id?Promise.resolve(p.id):api('users/autocomplete?q='+encodeURIComponent(p.login)).then(function(j){
      var r=(j.results||[]).filter(function(x){return String(x.login).toLowerCase()===p.login.toLowerCase();})[0];
      if(!r)throw new Error('No iNaturalist user "'+p.login+'"');return r.id;})).then(live)
    .then(function(v){id=v;key++;o.changed();say('Loading '+u+'…');return load(m,p);}).then(live)
    .then(function(){say(m==='observer'?'Showing records observed by '+u+'.':m==='unid'?'Hiding records '+u+' identified.':
        head());key++;o.changed();})
    .catch(function(e){if(e===0)return;mask=ob=hide=null;key++;
      say(e instanceof TypeError?'Could not reach iNaturalist.':e.message);o.changed();});}
  function tag(){mode.dataset.explain={first:'my-taxa-first',observer:'observer-filter',taxa:'my-taxa',unid:'not-identified-by-me'}[mode.value];}
  function apply(){tag();S.user=input.value.trim().slice(0,100);S.umode=mode.value===(META.observer?'observer':'taxa')?'':mode.value;o.changed();}
  if(box){
    box.appendChild(el('summary',null,'User'));
    var f=box.appendChild(el('form','prow')),lab=f.appendChild(el('label','muted','iNaturalist login or user number'));
    input=f.appendChild(el('input','padd'));input.id=lab.htmlFor='usrname';input.type='text';
    input.placeholder='Login or number';input.autocomplete='off';input.spellcheck=false;
    mode=f.appendChild(el('select'));mode.setAttribute('aria-label','What to do with the user');
    [['first','My taxa first'],['taxa','My taxa'],['unid','Not yet identified by me'],['observer','Observer']].forEach(function(m){
      var op=mode.appendChild(el('option',null,m[1]));op.value=m[0];
      if(m[0]==='observer'&&!META.observer)op.disabled=true;});
    mode.value='first';  // until a user is set, what a typed login starts on
    minsel=f.appendChild(el('select'));minsel.setAttribute('aria-label','Fewest IDs in a genus');
    USR_MINS.forEach(function(v){var op=minsel.appendChild(el('option',null,v+'+ IDs'));op.value=v;});
    again=f.appendChild(el('button','padd','Reload for this view'));again.type='button';again.hidden=true;
    again.onclick=function(){cur='';o.changed();};
    f.onsubmit=function(e){e.preventDefault();apply();};input.onchange=apply;mode.onchange=apply;minsel.onchange=function(){S.umin=+minsel.value===USR_MIN?0:+minsel.value;o.changed();};
    msg=box.appendChild(el('p','muted'));msg.setAttribute('aria-live','polite');box.hidden=false;
  }
  return {
    // brings the box in line with S and starts any load it needs; P is the records so far
    sync:function(P){Pn=P;if(input){if(document.activeElement!==input)input.value=S.user;
      if(S.user)mode.value=em();tag();minsel.value=used||min();minsel.hidden=mode.value!=='taxa'&&mode.value!=='first';again.hidden=em()!=='unid'||!S.user;}start();},
    drop:function(i){if(!id||em()==='first')return false;
      if(mask){var t=Pn.tax[i];return !(t<mask.length&&mask[t]===1);}
      if(ob)return i<ob.length&&ob[i]!==id;
      return hide?hide.has(Pn.id[i]):false;},
    key:function(){return key;},
    mode:em,
    // true while some records are left out; My taxa first leaves none out, it ranks them (ranked, mine)
    active:function(){return !!(mask&&em()!=='first'||ob||hide);},
    ranked:function(){return !!mask&&em()==='first';},
    mine:function(i){var t=Pn.tax[i];return t<mask.length&&mask[t]===1;},
    // noTaxa leaves taxon_id out, for links that list the records by id
    params:function(noTaxa){if(!id)return {};if(em()==='observer')return {user_id:String(id)};
      var p={without_ident_user_id:String(id)},k=mask&&!noTaxa&&em()==='taxa'?kept().ids:[];if(k.length)p.taxon_id=k.join(',');return p;},
    tip:function(){return id&&em()!=='observer'?' Records the user identified are left out; ones you skipped are hidden by iNaturalist when you are signed in.':'';},
    // the map counts are approximate under My taxa and Not yet identified, as Identify cannot say them
    note:function(){return mask?head()+(capped?' Only the first '+nf.format(USR_CAP.taxa*USR_PER.taxa)+' taxa were read.':'')+
      (em()==='first'?' Dots outside them are dimmed.':kept().cut?' Identify gets only the top '+(kept().ids.length===1?'genus':nf.format(kept().ids.length)+' genera')+
        ' by records to identify.':''):
      hide?'The map hides records '+S.user+' identified'+(capped?' (first '+nf.format(USR_CAP.unid*USR_PER.unid)+' only)':'')+
        ', so its count is approximate.':'';}
  };
}
