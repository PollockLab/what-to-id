// The taxon picker and the Identify link. Each taxa row is [latin, common, iNaturalist id, rank,
// parent row]; a record matches a taxon when the taxon is its own or any ancestor, so Bryophyta keeps
// every moss. Typing suggests taxa of any rank whose latin or common name holds the text, those with
// the most records below them first. Each pick is a chip: records under any included chip show, and
// records under an excluded chip leave. Taxa files built without the tree have no parent column, so a
// chip then matches only the taxon it names.
var TX=(function(){
'use strict';
var MAX_IDS=50,SUGGEST=8,memo=null,cmemo=null;
function index(T){
  if(memo&&memo.T===T)return memo;
  var n=T.length,par=new Int32Array(n),row=new Map();
  for(var i=0;i<n;i++){row.set(T[i][2],i);par[i]=T[i].length>4?T[i][4]:-1;}
  return memo={T:T,par:par,row:row};
}
// 1 for each row that is a hit or lies below one. Each row is settled once: a walk up stops at the
// first row already known, then marks the rows it passed.
function below(ix,hit){
  var n=hit.length,st=new Uint8Array(n),path=[],i,j,k,v;
  for(i=0;i<n;i++){
    for(j=i,path.length=0;j>=0&&!st[j]&&!hit[j];j=ix.par[j])path.push(j);
    v=j<0?2:hit[j]?1:st[j];if(j>=0)st[j]=v;
    for(k=0;k<path.length;k++)st[path[k]]=v;
  }
  for(i=0;i<n;i++)st[i]=st[i]===1?1:0;
  return st;
}
// Records at or below each row, from each record's row in tax (the first n records).
function counts(T,tax,n){
  if(cmemo&&cmemo.T===T&&cmemo.n===n)return cmemo.c;
  var ix=index(T),own=new Float64Array(T.length),c=new Float64Array(T.length),i,j;
  for(i=0;i<n;i++)if(tax[i]<T.length)own[tax[i]]++;
  for(i=0;i<T.length;i++)if(own[i])for(j=i;j>=0;j=ix.par[j])c[j]+=own[i];
  cmemo={T:T,n:n,c:c};return c;
}
function suggest(T,text,cnt,picks){
  var q=String(text||'').trim().toLowerCase(),out=[],had={};
  if(!T||q.length<2)return out;
  picks.forEach(function(p){had[p.id]=1;});
  for(var i=0;i<T.length;i++)if(!had[T[i][2]]&&(T[i][0].toLowerCase().indexOf(q)>=0||
    T[i][1].toLowerCase().indexOf(q)>=0))out.push(i);
  out.sort(function(a,b){return (cnt?cnt[b]-cnt[a]:0)||a-b;});
  return out.slice(0,SUGGEST);
}
// What the picks match: inc and exc, 1 per taxa row at or below an included or excluded pick (null
// for none, or before the taxa load); ids and not, the included and excluded iNaturalist taxa for
// Identify's taxon_id and without_taxon_id.
function filter(T,picks){
  var out={inc:null,exc:null,ids:[],not:[]};
  picks.forEach(function(p){(p.not?out.not:out.ids).push(p.id);});
  if(!T)return out;
  var ix=index(T);
  function hits(ids){var h=new Uint8Array(T.length);
    ids.forEach(function(id){var r=ix.row.get(id);if(r!=null)h[r]=1;});return below(ix,h);}
  if(out.ids.length)out.inc=hits(out.ids);
  if(out.not.length)out.exc=hits(out.not);
  return out;
}
// The picks as a hash value, "311249,-64615", and back.
function write(picks){return picks.map(function(p){return (p.not?'-':'')+p.id;}).join(',');}
function read(s){var out=[],seen={};String(s||'').split(',').forEach(function(t){
  var m=/^(-?)(\d+)$/.exec(t.trim());if(m&&!seen[m[2]]){seen[m[2]]=1;out.push({id:+m[2],not:!!m[1]});}});
  return out;}
// Picks for the old q hash value, "Carex, -Carex aquatilis": each name becomes the taxon of that
// latin or common name (any case), else its first suggestion, and a minus leaves it out.
function resolve(T,s,cnt){var out=[];
  String(s||'').split(',').forEach(function(t){t=t.trim();var not=t[0]==='-';if(not)t=t.slice(1).trim();
    var q=t.toLowerCase(),best=-1,bs=0;if(!T||!q)return;
    // a latin name beats a common one, then the taxon with more records
    for(var i=0;i<T.length;i++){var v=T[i][0].toLowerCase()===q?2:T[i][1].toLowerCase()===q?1:0;
      if(v&&(v>bs||v===bs&&cnt&&cnt[i]>cnt[best])){best=i;bs=v;}}
    if(best<0)best=suggest(T,q,cnt,out)[0];
    if(best!=null&&best>=0&&!out.some(function(p){return p.id===T[best][2];}))
      out.push({id:T[best][2],not:not});});
  return out;}
// The taxon selection as terms a shared selection module can take over: each group chip, shortcut
// and picked taxon is {dim:'taxon', kind:'group'|'preset'|'clade', id, label, exclude, mask(),
// inat()}, mask() 1 per record the term covers and inat() its Identify parameters. Includes combine
// with OR and excludes subtract. o: T, picks, groups (the chosen group names, [] for all), meta, and
// the records' tax, grp and n.
function terms(o){
  var out=[],m=o.meta,gid=m.group_ids||{},left=o.picks.slice(),ix=o.T&&index(o.T),
    tree=!!(o.T&&o.T.length&&o.T[0].length>4);
  function recs(ids){var f=filter(o.T,ids.map(function(id){return {id:id};})).inc,r=new Uint8Array(o.n);
    if(f)for(var i=0;i<o.n;i++)r[i]=o.tax[i]<f.length?f[o.tax[i]]:0;return r;}
  function name(id){var r=ix?ix.row.get(id):null;return r==null?'Taxon '+id:o.T[r][0];}
  o.groups.forEach(function(g){var k=m.groups.indexOf(g),id=gid[g]||null;
    out.push({dim:'taxon',kind:'group',id:id,label:m.names[g]||g,exclude:false,
      mask:function(){var r=new Uint8Array(o.n);for(var i=0;i<o.n;i++)r[i]=o.grp[i]===k?1:0;return r;},
      inat:function(){return {params:id?{taxon_id:String(id)}:{iconic_taxa:g},exact:true};}});});
  function term(kind,ids,label,not){var key=not?'without_taxon_id':'taxon_id',p={};p[key]=ids.join(',');
    out.push({dim:'taxon',kind:kind,id:kind==='preset'?ids.slice():ids[0],label:label,exclude:not,
      mask:function(){return recs(ids);},inat:function(){return {params:p,exact:tree};}});}
  (m.presets||[]).forEach(function(c){var hit=c[1].map(function(id){
    return left.filter(function(p){return p.id===id;})[0];});
    if(hit.every(Boolean)&&hit.every(function(p){return p.not===hit[0].not;})){
      left=left.filter(function(p){return hit.indexOf(p)<0;});term('preset',c[1],c[0],hit[0].not);}});
  left.forEach(function(p){term('clade',[p.id],name(p.id),p.not);});
  return out;}
// Whether taxon id lies at or below any of ids.
function within(T,id,ids){var ix=index(T),r=ix.row.get(id);
  for(;r!=null&&r>=0;r=ix.par[r])if(ids.indexOf(T[r][2])>=0)return true;return false;}
// The chips and suggestion list. o: input, box (chips), list (suggestions), msg (a note under the
// box), picks (kept in place), taxa() and counts() for the current table, ranks, nf, and onChange
// after every change.
function picker(o){
  var act=-1,rows=[];
  function name(id){var ix=o.taxa()&&index(o.taxa()),r=ix?ix.row.get(id):null;
    return r==null?{latin:'Taxon '+id,common:'',rank:''}:{latin:ix.T[r][0],common:ix.T[r][1],
      rank:ix.T[r][3]!==255?o.ranks[ix.T[r][3]]||'':''};}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  function chips(){o.box.textContent='';
    o.picks.forEach(function(p,k){var t=name(p.id),s=el('span','pick'+(p.not?' not':'')),
      b=el('button','pn',(p.not?'not ':'')+t.latin),x=el('button','px','×');
      b.type=x.type='button';b.setAttribute('aria-pressed',String(p.not));
      b.title=(t.common?t.common+', ':'')+(t.rank||'taxon')+'. Click to '+(p.not?'include':'exclude')+' it.';
      x.setAttribute('aria-label','Remove '+t.latin);
      b.onclick=function(){p.not=!p.not;changed();};
      x.onclick=function(){o.picks.splice(k,1);changed();o.input.focus();};
      s.appendChild(b);s.appendChild(x);o.box.appendChild(s);});
    o.box.hidden=!o.picks.length;}
  function changed(){chips();o.onChange();}
  function show(){
    var T=o.taxa();rows=suggest(T,o.input.value,T&&o.counts(),o.picks);act=rows.length?0:-1;
    o.list.textContent='';
    rows.forEach(function(r,k){var t=T[r],c=o.counts(),li=el('li');li.id='sg'+k;
      li.setAttribute('role','option');
      li.appendChild(el('b',null,t[0]));
      li.appendChild(el('span',null,[t[1],t[3]!==255?o.ranks[t[3]]:'',c[r]?o.nf.format(c[r])+
        (c[r]===1?' record':' records'):''].filter(Boolean).join(' · ')));
      li.onpointerdown=function(e){e.preventDefault();pick(k);};o.list.appendChild(li);});
    var q=o.input.value.trim();o.msg.textContent=q.length===1?'Type one more letter':
      q.length>1&&T&&!rows.length?'No taxon matches':'';
    var open=rows.length>0;o.list.hidden=!open;o.input.setAttribute('aria-expanded',String(open));
    mark();}
  function mark(){[].forEach.call(o.list.children,function(li,k){
    li.setAttribute('aria-selected',String(k===act));});
    if(act>=0)o.input.setAttribute('aria-activedescendant','sg'+act);
    else o.input.removeAttribute('aria-activedescendant');}
  function hide(){o.list.hidden=true;rows=[];act=-1;o.input.setAttribute('aria-expanded','false');mark();}
  function pick(k){var r=rows[k];if(r==null)return;o.picks.push({id:o.taxa()[r][2],not:false});
    o.input.value='';hide();changed();}
  o.input.addEventListener('input',show);
  o.input.addEventListener('focus',show);
  o.input.addEventListener('blur',hide);
  o.input.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(o.list.hidden)show();if(!rows.length)return;
      act=(act+(e.key==='ArrowDown'?1:rows.length-1))%rows.length;mark();e.preventDefault();}
    else if(e.key==='Enter'){if(act>=0){pick(act);e.preventDefault();}}
    else if(e.key==='Escape')hide();
    else if(e.key==='Backspace'&&!o.input.value&&o.picks.length){o.picks.pop();changed();}});
  chips();
  // A shortcut's state: 'inc' when all its taxa are picked, 'not' when all are left out, else ''.
  function state(ids){var st=null;ids.forEach(function(id){var p=o.picks.filter(function(q){
    return q.id===id;})[0],v=p?(p.not?'not':'inc'):'';st=st===null||st===v?v:'';});return st||'';}
  return {refresh:chips,changed:changed,state:state,
    // a click on a shortcut picks its taxa, the next leaves them out, the third removes them
    cycle:function(ids){var next={'':'inc',inc:'not',not:''}[state(ids)];
      for(var k=o.picks.length-1;k>=0;k--)if(ids.indexOf(o.picks[k].id)>=0)o.picks.splice(k,1);
      if(next)ids.forEach(function(id){o.picks.push({id:id,not:next==='not'});});changed();return next;}};
}
// The Identify link: the same records on iNaturalist, as far as its filters can say it. iNaturalist
// counts a taxon's descendants under taxon_id and without_taxon_id, as the map does. lost names what
// the link had to leave out for MAX_IDS or the URL length: 'taxa' (it then opens every taxon) and
// 'not' (it then keeps the excluded taxa).
function identifyUrl(st,b,meta){
  var q=new URLSearchParams({quality_grade:'needs_id',place_id:meta.place_id}),r=function(v,m){
    return Math.max(-m,Math.min(m,v)).toFixed(4);},lost=[];
  q.set('swlat',r(b.s,90));q.set('swlng',r(b.w,180));q.set('nelat',r(b.n,90));q.set('nelng',r(b.e,180));
  var g=st.groups;
  if(g.length&&g.length<st.all&&g.indexOf('rest')<0)q.set('iconic_taxa',g.join(','));
  if(st.d1)q.set(st.up?'created_d1':'d1',st.d1);if(st.d2)q.set(st.up?'created_d2':'d2',st.d2);
  if(st.months.length)q.set('month',st.months.join(','));
  // iNaturalist has a search parameter for each status filter, so Identify opens the same records
  var o=st.only||{};if(o.introduced)q.set('introduced','true');if(o.threatened)q.set('threatened','true');
  if(o.exact){q.set('obscuration','none');q.set('acc_below_or_unknown',meta.imprecise_m+1);}
  var base='https://www.inaturalist.org/observations/identify?',u=base+q;
  function add(key,ids,what){if(!ids||!ids.length)return;
    if(ids.length<=MAX_IDS){q.set(key,ids.join(','));if((base+q).length<meta.max_url){u=base+q;return;}
      q.delete(key);}
    lost.push(what);}
  add('taxon_id',st.taxa,'taxa');add('without_taxon_id',st.not,'not');
  return {url:u,lost:lost};
}
return {filter:filter,suggest:suggest,counts:counts,read:read,write:write,resolve:resolve,within:within,
  terms:terms,picker:picker,identifyUrl:identifyUrl};
})();
