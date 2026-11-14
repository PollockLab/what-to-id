// The user filter. The User box takes an iNaturalist login or user number (hash: user=). A login always ranks
// the records inside the user's genera first (mine(i): first on Identify, the rest dimmed on the map): by default the
// genera holding about 80% of the user's current identifications in any BC pool genus, or with umin= (5, 20, 50
// or 100) the genera with at least that many. Three ticks leave records out and add up (umode=, see MF.read): Only my
// genera (taxa), Hide records I identified (unid: the dots the user identified in the view) and Only records I
// observed (observer: pool-observer.bin, one uint32 per record in shard order). Observed opens Identify on the
// user's records (user_id); otherwise the link adds without_ident_user_id, which would hide nearly all of an
// observer's own records, so Hide and Observed exclude each other. A typed login ticks only Hide, and only if it was
// last left ticked; the login is kept a day (localStorage) for the next page opened without one.
// Everything but the observer file comes from api.inaturalist.org in the browser, one request at a
// time and at least a second apart, and is kept for the session. Without a user nothing is filtered.
var USR_CAP={taxa:5,unid:25},USR_PER={taxa:500,unid:200},USR_MINS=[5,20,50,100],USR_AUTO=0.8,USR_DAY=864e5,
  USR_LOGIN='wtid.user',USR_HIDE='wtid.uhide',USR_FLAGS=[['taxa',function(u){return 'Only '+u+"'s genera";},'my-taxa'],
    ['unid',function(u){return 'Hide records '+u+' identified';},'not-identified-by-me'],
    ['observer',function(u){return 'Only records '+u+' observed';},'observer-filter']];
function usrWho(S){return S.user?'@'+S.user:'the user';}  // the tick labels name the entered user
// {id} for a user number, {login} for a login, null for anything else.
// A profile link (any iNaturalist network host) or a leading @ is taken for the login or number it holds.
function usrParse(s){s=String(s||'').trim();
  var u=/^(?:https?:\/\/)?(?:[\w-]+\.)*inaturalist\.[a-z]{2,3}\/people\/([^\/?#]+)/i.exec(s);if(u)s=u[1];
  s=s.replace(/^@/,'');
  return /^\d+$/.test(s)?(+s>0&&+s<=4294967295?{id:+s}:null):/^[A-Za-z0-9_-]{1,40}$/.test(s)?{login:s}:null;}
// The genera a fixed threshold keeps, as [iNaturalist id, count] pairs: each species_counts count is added to
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
// The genera the automatic threshold keeps, most IDs first, until they hold USR_AUTO of the user's IDs in any pool
// genus, none under USR_MINS[0]: {genera, total (IDs in any pool genus), n (IDs in the kept)}.
function usrTop(T,ranks,results){
  var all=usrGenera(T,ranks,results,0).sort(function(a,b){return b[1]-a[1];}),total=0,n=0,g=[];
  all.forEach(function(e){total+=e[1];});
  for(var i=0;i<all.length&&n<USR_AUTO*total&&all[i][1]>=USR_MINS[0];i++){g.push(all[i]);n+=all[i][1];}
  return {genera:g,total:total,n:n};}
// localStorage, which may be missing or refuse: the value of k, or with v set it (null removes it)
function usrStore(k,v){try{if(v===undefined)return localStorage.getItem(k);if(v===null)localStorage.removeItem(k);
  else localStorage.setItem(k,v);}catch(e){}return null;}
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
    api=inatGate({gap:o.gap,fetch:o.fetch,say:function(t){say(t);}}),cur='',bad=0,run=0,id=0,mask=null,ob=null,hide=null,capT=false,capU=false,key=0,Pn=null,
    gen=[],used=0,top=null,fit=null,restored=0,cb={},input,minsel,adj,msg,again,out,sum,note;
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  // with no umode an old link's single mode: Observed, or Only my genera without an observer file
  function em(){return S.umode||(META.observer?'observer':'taxa');}
  function has(f){return em().split(',').indexOf(f)>=0;}
  // S.umode for the ticked flags, in USR_FLAGS order (MF.read's)
  function pick(f){var s=f.join(',')||'first';return s===(META.observer?'observer':'taxa')?'':s;}
  function min(){return S.umin||0;}
  function ranked(){return !!mask&&gen.length>0&&!has('taxa');}
  // the genera kept and how many go to Identify: ids that fit the URL beside the rest of the link
  function kept(){var n=Pn?Pn.n:0;
    if(!fit||fit.n!==n)fit=Object.assign({n:n},usrFit(o.taxa(),META.ranks,gen.map(function(e){return e[0];}),
      Pn?Pn.tax:[],META.max_url-1500));return fit;}
  function head(){var n=gen.length;
    return !n?S.user+' has fewer than '+USR_MINS[0]+' IDs in any BC genus yet. Try '+(META.observer?USR_FLAGS[2][1](usrWho(S))+' or ':'')+USR_FLAGS[1][1](usrWho(S))+'.':
      top?'Your top '+(n===1?'genus':nf.format(n)+' genera')+', '+Math.round(100*top.n/top.total)+'% of your '+nf.format(top.total)+' IDs in BC.':
      'Genera where '+S.user+' has at least '+used+' IDs in BC ('+nf.format(n)+(n===1?' genus':' genera')+')'+(used<min()?'; none reach '+min()+' yet.':'.');}
  function dim(){return ranked()?' Other records are listed last on Identify and dimmed on the map.':'';}
  function say(t){if(msg)msg.textContent=t;}
  // the user's genera always, then the observer file and the ids identified in the view when ticked
  function load(live){
    var place='&place_id='+META.place_id;
    return usrPages(function(n){return api('identifications/species_counts?user_id='+id+place+'&per_page=500&page='+n);},
      USR_CAP.taxa,USR_PER.taxa).then(function(r){capT=r.capped;
      var T=o.taxa(),k=min()?usrKeep(T,META.ranks,r.items,min()):usrTop(T,META.ranks,r.items);
      gen=k.genera;used=k.used||0;top=min()?null:k;fit=null;mask=usrMask(T,gen.map(function(e){return e[0];}));}).then(live)
    .then(function(){if(!has('observer'))return;if(!META.observer)throw new Error('This map has no observer file');
      return o.get(META.observer).then(function(buf){if(buf.byteLength!==4*META.n)throw new Error('observer file does not match the map');
        ob=new Uint32Array(buf);});}).then(live)
    .then(function(){if(!has('unid'))return;
      var b=o.bounds(),view='&swlat='+b.s.toFixed(4)+'&swlng='+b.w.toFixed(4)+'&nelat='+b.n.toFixed(4)+'&nelng='+b.e.toFixed(4);
      return usrPages(function(n){return api('observations?ident_user_id='+id+place+'&quality_grade=needs_id&per_page=200&only_id=true'+view+'&page='+n);},
        USR_CAP.unid,USR_PER.unid).then(function(r){hide=new Set(r.items.map(function(x){return x.id;}));capU=r.capped;});});}
  // Starts what S.user, S.umode and S.umin ask for once, whenever the records are drawn again.
  function start(){
    var u=S.user,p=usrParse(u),k=u?u+'|'+em()+'|'+min():'';
    if(k===cur||(p&&!o.taxa()))return;  // the genera wait for the taxa table; the next refilter retries
    bad=0;var tag=++run;cur=k;id=0;mask=ob=hide=top=null;gen=[];used=0;fit=null;capT=capU=false;key++;
    if(!u){say('');return;}
    if(!p){say('Enter an iNaturalist login or user number.');return;}
    say('Looking up '+u+'…');
    var live=function(v){if(run!==tag)throw 0;return v;};
    (p.id?Promise.resolve(p.id):api('users/autocomplete?q='+encodeURIComponent(p.login)).then(function(j){
      var r=(j.results||[]).filter(function(x){return String(x.login).toLowerCase()===p.login.toLowerCase();})[0];
      if(!r)throw new Error('No iNaturalist user "'+p.login+'"');return r.id;})).then(live)
    .then(function(v){id=v;key++;o.changed();say('Loading '+u+'…');return load(live);}).then(live)
    .then(function(){say([head()+dim(),ob?'Showing records observed by '+u+'.':'',hide?'Hiding records '+u+' identified.':''].filter(Boolean).join(' '));
      key++;o.changed();})
    .catch(function(e){if(e===0)return;bad=1;mask=ob=hide=null;key++;
      say(e instanceof TypeError?'Could not reach iNaturalist.':e.message);o.changed();});}
  // Hide and Observed together would leave almost nothing, as an observer's own ID counts as an identification
  function excl(){var why="Off while the other is ticked: a user's own records carry their own ID.",no=!S.user,hint='Enter a user name first';
    cb.taxa.disabled=no;cb.taxa.title=no?hint:'';
    cb.observer.disabled=no||!META.observer||cb.unid.checked;cb.unid.disabled=no||cb.observer.checked;
    cb.observer.title=no?hint:!META.observer?'This map has no observer file.':cb.unid.checked?why:'';cb.unid.title=no?hint:cb.observer.checked?why:'';
    if(note)note.hidden=!no;
    USR_FLAGS.forEach(function(m){cb[m[0]].parentNode.lastChild.textContent=' '+m[1](usrWho(S));});}
  // what a typed login starts on: nothing ticked but Hide, if it was last left ticked
  function defaults(){cb.taxa.checked=cb.observer.checked=false;cb.unid.checked=usrStore(USR_HIDE)==='1';excl();}
  // an unparseable entry is not written to the hash; a failed lookup is tried again on the next apply
  function apply(){var v=input.value.trim().slice(0,100),p=v&&usrParse(v);
    if(v&&!p){say('Enter an iNaturalist login or user number.');return;}
    if(bad){cur='';bad=0;}
    var was=S.user;S.user=p?String(p.id||p.login):'';input.value=S.user;  // ticks made before a login stay
    if(S.user)usrStore(USR_LOGIN,JSON.stringify({user:S.user,t:Date.now()}));else if(was){usrStore(USR_LOGIN,null);defaults();}
    S.umode=pick(USR_FLAGS.map(function(m){return m[0];}).filter(function(f){return cb[f].checked;}));o.changed();}
  if(box){
    sum=box.appendChild(el('summary',null,'User'));sum.dataset.explain='my-taxa-first';
    var f=box.appendChild(el('form','prow')),lab=f.appendChild(el('label','muted','iNaturalist login or user number'));
    input=f.appendChild(el('input','padd'));input.id=lab.htmlFor='usrname';input.type='text';
    input.placeholder='Login or number';input.autocomplete='off';input.spellcheck=false;
    USR_FLAGS.forEach(function(m){var l=f.appendChild(el('label')),c=l.appendChild(el('input'));
      c.type='checkbox';c.id='usr'+m[0];c.dataset.explain=m[2];l.append(' '+m[1](usrWho(S)));cb[m[0]]=c;
      c.onchange=function(){if(m[0]==='unid')usrStore(USR_HIDE,c.checked?'1':'0');excl();apply();};});
    note=f.appendChild(el('span','muted','Enter a user name first'));note.id='usrhint';
    defaults();
    adj=f.appendChild(el('details'));adj.appendChild(el('summary',null,'Adjust'));
    minsel=adj.appendChild(el('select'));minsel.setAttribute('aria-label','Fewest IDs in a genus');
    [[0,'Automatic ('+100*USR_AUTO+'% of their IDs)']].concat(USR_MINS.map(function(v){return [v,v+'+ of their IDs per genus'];})).forEach(function(v){
      var op=minsel.appendChild(el('option',null,v[1]));op.value=v[0];});
    again=f.appendChild(el('button','padd','Reload for this view'));again.type='button';again.hidden=true;
    again.onclick=function(){cur='';o.changed();};
    out=f.appendChild(el('button','padd','Sign out'));out.type='button';out.hidden=true;
    out.onclick=function(){input.value='';S.umin=0;apply();};
    f.onsubmit=function(e){e.preventDefault();apply();};input.onchange=apply;minsel.onchange=function(){S.umin=+minsel.value;o.changed();};
    msg=box.appendChild(el('p','muted'));msg.setAttribute('aria-live','polite');box.hidden=false;
  }
  return {
    // brings the box in line with S and starts any load it needs; P is the records so far. The first call
    // brings back a login kept from the last day when the page opened without one.
    sync:function(P){Pn=P;
      if(!restored){restored=1;var r=null;try{r=JSON.parse(usrStore(USR_LOGIN));}catch(e){}
        if(!S.user&&r&&usrParse(r.user)&&Date.now()-r.t<USR_DAY){S.user=String(r.user);S.umode=pick(usrStore(USR_HIDE)==='1'?['unid']:[]);
          if(box)box.open=true;}}
      if(input){if(document.activeElement!==input)input.value=S.user;
        if(S.user)USR_FLAGS.forEach(function(m){cb[m[0]].checked=has(m[0]);});
        excl();
        minsel.value=min();adj.hidden=!S.user;again.hidden=!o.again||!has('unid')||!S.user;out.hidden=!S.user;
        sum.textContent=S.user?'User: '+S.user+' · '+(USR_FLAGS.filter(function(m){return has(m[0]);}).map(function(m){return m[1](usrWho(S));}).join(', ')||'Your genera first'):'User';}
      start();},
    drop:function(i){if(!id)return false;var t=Pn.tax[i];
      return !!(mask&&has('taxa')&&!(t<mask.length&&mask[t]===1)||ob&&i<ob.length&&ob[i]!==id||hide&&hide.has(Pn.id[i]));},
    key:function(){return key;},
    // the ticked flags as S.umode would write them, e.g. first or taxa,unid
    flags:em,
    // true while some records are left out; with no tick nothing is, the records are ranked (ranked, mine)
    active:function(){return !!(mask&&has('taxa')||ob||hide);},
    ranked:ranked,
    // the record tooltip's line while ranked
    where:function(i){return ranked()?'<br>'+(this.mine(i)?'In':'Outside')+' your genera':'';},
    // Identify's empty Observed view offers this: every record, the user's genera first
    first:function(){USR_FLAGS.forEach(function(m){cb[m[0]].checked=false;});excl();apply();},
    mine:function(i){var t=Pn.tax[i];return t<mask.length&&mask[t]===1;},
    // noTaxa leaves taxon_id out, for links that list the records by id
    params:function(noTaxa){if(!id)return {};var p=has('observer')?{user_id:String(id)}:{without_ident_user_id:String(id)},
      k=mask&&!noTaxa&&has('taxa')?kept().ids:[];if(k.length)p.taxon_id=k.join(',');return p;},
    tip:function(){return id&&!has('observer')?' Records the user identified are left out; ones you skipped are hidden by iNaturalist when you are signed in.':'';},
    // the map counts are approximate under Only my genera and Hide, as Identify cannot say them
    note:function(){return [mask?head()+(capT?' Only the first '+nf.format(USR_CAP.taxa*USR_PER.taxa)+' taxa were read.':'')+
      (ranked()?dim():has('taxa')&&kept().cut?' Identify gets only the top '+(kept().ids.length===1?'genus':nf.format(kept().ids.length)+' genera')+
        ' by records to identify.':''):'',
      hide?'The map hides records '+S.user+' identified'+(capU?' (first '+nf.format(USR_CAP.unid*USR_PER.unid)+' only)':'')+
        ', so its count is approximate.':''].filter(Boolean).join(' ');}
  };
}
