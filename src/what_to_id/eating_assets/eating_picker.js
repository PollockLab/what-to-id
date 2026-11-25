// The taxon picker of the Eating page: a combobox over the metaweb's taxa. Empty, it opens a tree of the iconic groups (the map's
// Groups tree: indented rows, disclosure triangles, right-aligned counts) that expands in place to the next rank that branches;
// typed, it lists ranked matches on common and Latin name, each with its lineage. Counts are the metaweb taxa under a row and the
// BC feeding observations naming one. Rows with no observation are muted, never hidden.
var EatingPicker=(function(){
'use strict';
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
// the model: o = {parent, rank, groups (group taxon: label), names (the taxa to pick from), obs (observed names), label}
function model(o){
  var P=o.parent||{},G=o.groups||{},R=o.rank||{},S=new Set(o.names),N=new Set(),cnt={},obs={},ch={},gr={},K=[],kc={};
  function up(n){var s=n,out=[];for(var k=0;k<40&&P[n]!==undefined&&out.indexOf(P[n])<0;k++){n=P[n];out.push(n);}return out.filter(function(x){return x!==s;});}
  function grp(n){if(gr[n]===undefined)gr[n]=[n].concat(up(n)).filter(function(a){return G[a];})[0]||'';return gr[n];}
  function lab(n){return n===''?'Other':G[n]||o.label(n);}
  S.forEach(function(s){[s].concat(up(s)).forEach(function(a){N.add(a);cnt[a]=(cnt[a]||0)+1;});});
  N.forEach(function(n){var p=P[n];if(p&&N.has(p)&&p!==n)(ch[p]=ch[p]||[]).push(n);});
  o.obs.forEach(function(n){  // a name the table lacks counts toward its genus
    var c=n in P||n.indexOf(' ')<0?[n].concat(up(n)):[n,n.split(' ')[0]].concat(up(n.split(' ')[0]));
    c.forEach(function(a){if(N.has(a))obs[a]=(obs[a]||0)+1;});});
  var roots=Object.keys(G).filter(function(g){return cnt[g];}),spine=new Set();
  roots.forEach(function(g){up(g).forEach(function(a){spine.add(a);});});
  N.forEach(function(u){if(!grp(u)&&!spine.has(u)&&(!P[u]||spine.has(P[u])))K.push(u);});  // what no iconic group holds
  if(K.length){K.forEach(function(k){cnt['']=(cnt['']||0)+cnt[k];obs['']=(obs['']||0)+(obs[k]||0);});}
  function alpha(a,b){return lab(a)<lab(b)?-1:1;}
  function by(a,b){return (obs[b]||0)-(obs[a]||0)||cnt[b]-cnt[a];}
  roots.sort(function(a,b){return by(a,b)||alpha(a,b);});if(K.length)roots.push('');
  function skip(c){for(var k=0;k<40&&!S.has(c)&&ch[c]&&ch[c].length===1;k++)c=ch[c][0];return c;}  // single-child ranks do not show
  function kids(n){if(!kc[n])kc[n]=(n===''?K:ch[n]||[]).map(skip).sort(function(a,b){return by(a,b)||alpha(a,b);});return kc[n];}
  function flat(open){var out=[];(function walk(l,d){l.forEach(function(n){var k=kids(n);out.push({n:n,d:d,k:k.length>0});if(k.length&&open.has(n)&&d<30)walk(k,d+1);});})(roots,0);return out;}
  function score(q,t){  // exact, whole word, prefix, word prefix, anywhere
    var l=t.toLowerCase(),i=l.indexOf(q),w=i>=0&&(i===0||/[ -]/.test(l[i-1]));
    return i<0?9:l===q?0:w&&!/[a-z]/.test(l[i+q.length]||' ')?1:i===0?2:w?3:4;}
  function search(q){
    var hit=[];N.forEach(function(n){var s=Math.min(score(q,o.label(n)),score(q,n));if(s<9)hit.push([s,n]);});
    return hit.sort(function(a,b){return a[0]-b[0]||by(a[1],b[1])||o.label(a[1]).length-o.label(b[1]).length||alpha(a[1],b[1]);}).slice(0,40).map(function(h){return h[1];});
  }
  // "Birds › Accipitridae": the group, then the nearest family (else order, else parent)
  function crumb(n){
    var g=grp(n),u=up(n),p=['family','order'].reduce(function(r,k){return r||u.filter(function(a){return R[a]===k;})[0];},null)||u[0],out=[];
    if(g!==n)out.push(g?G[g]:'Other');
    if(p&&p!==g&&p!=='Life')out.push(lab(p));
    return out.join(' › ');
  }
  return {roots:roots,kids:kids,flat:flat,search:search,crumb:crumb,lab:lab,up:up,
    cnt:function(n){return cnt[n]||0;},obs:function(n){return obs[n]||0;},leaf:function(n){return !kids(n).length;}};
}
function mark(text,q){
  var f=document.createDocumentFragment(),i=q?text.toLowerCase().indexOf(q):-1;
  if(i<0){f.append(text);return f;}
  f.append(text.slice(0,i),el('mark',null,text.slice(i,i+q.length)),text.slice(i+q.length));return f;
}
// o = model input plus {id, ph, value (a name or null), onPick(name)}, and optionally more(q): a promise of Latin names from outside
// the model (iNaturalist), listed after the model's matches; returns the element
function create(o){
  var m=model(o),host=el('div','cb'),inp=el('input'),pop=el('div','cbp'),hd=el('div','cbh'),ul=el('ul'),live=el('span','sr'),uid='cb-'+o.id;
  var open=new Set(),isOpen=false,typed=false,rows=[],act=-1,q='',X={q:'',l:[]},T=0;
  inp.setAttribute('role','combobox');inp.setAttribute('aria-controls',uid);inp.setAttribute('aria-expanded','false');inp.setAttribute('aria-autocomplete','list');
  inp.setAttribute('aria-label',o.ph);inp.placeholder=o.ph;inp.autocomplete='off';inp.spellcheck=false;
  ul.id=uid;ul.setAttribute('aria-label',o.ph+' suggestions');pop.hidden=true;live.setAttribute('aria-live','polite');
  hd.setAttribute('aria-hidden','true');hd.append(el('span',null,'Group, family or species'),el('span','n','taxa'),el('span','n','obs'));
  pop.append(hd,ul);host.append(inp,pop,live);
  function reset(){inp.value=o.value?m.lab(o.value):'';}
  function setAct(i){
    act=i;inp.removeAttribute('aria-activedescendant');
    [].forEach.call(ul.children,function(li,j){li.classList.toggle('on',j===i);});
    if(i>=0&&ul.children[i]){inp.setAttribute('aria-activedescendant',ul.children[i].id);ul.children[i].scrollIntoView({block:'nearest'});}
  }
  function render(keep){
    q=typed?inp.value.trim().toLowerCase():'';
    rows=q?m.search(q).map(function(n){return {n:n,d:0,k:false};}):m.flat(open);
    if(o.more&&q.length>=3){if(X.q===q)X.l.forEach(function(n){if(!rows.some(function(r){return r.n===n;}))rows.push({n:n,d:0,k:false,x:true});});else fetchMore(q);}
    ul.setAttribute('role',q?'listbox':'tree');inp.setAttribute('aria-haspopup',q?'listbox':'tree');ul.replaceChildren();
    rows.forEach(function(r,i){
      var n=r.n,label=m.lab(n),li=el('li',m.obs(n)||r.x?'':'z'),t=el('span','t'),c=m.cnt(n);
      li.id=uid+'-'+i;li.setAttribute('role',q?'option':'treeitem');
      if(!q){li.setAttribute('aria-level',r.d+1);li.style.paddingLeft=(6+r.d*16)+'px';if(r.k)li.setAttribute('aria-expanded',String(open.has(n)));}
      li.setAttribute('aria-selected',String(n===o.value));li.title=n||'Other';
      li.append(el('i','tri'+(q?' no':r.k?open.has(n)?' o':'':' leaf')));
      var latin=n!==label&&n.toLowerCase().indexOf(q)>=0&&label.toLowerCase().indexOf(q)<0;
      t.append(mark(label,q));
      if(q){var sub=el('small');if(latin||r.x&&n!==label)sub.append(mark(n,q),' · ');sub.append(r.x?'iNaturalist':m.crumb(n));t.append(sub);}
      li.append(t,el('span','n',c>1?String(c):''),el('span','n',r.x?'':String(m.obs(n))));
      li.onmousedown=function(e){e.preventDefault();};
      li.onclick=function(e){if(r.k&&e.target.classList.contains('tri'))toggle(n);else pick(n);};
      ul.append(li);});
    hd.hidden=!rows.length;live.textContent=q?rows.length+' match'+(rows.length===1?'':'es'):'';
    if(!rows.length&&q)ul.append(el('li','none',o.more&&q.length>=3&&X.q!==q?'Searching iNaturalist...':'No taxon matches "'+inp.value.trim()+'".'));
    setAct(keep!==undefined?keep:q&&rows.length?0:-1);
  }
  function fetchMore(s){
    clearTimeout(T);T=setTimeout(function(){
      o.more(s).catch(function(){return [];}).then(function(l){X={q:s,l:l};if(isOpen&&q===s)render(act<0?undefined:act);});},250);
  }
  function toggle(n,on){if(on===undefined?open.has(n):!on)open.delete(n);else open.add(n);render(rows.findIndex(function(r){return r.n===n;}));}
  function show(){
    if(isOpen)return;isOpen=true;typed=false;pop.hidden=false;inp.setAttribute('aria-expanded','true');
    if(o.value)m.up(o.value).forEach(function(a){open.add(a);});  // open on the current pick
    render();setAct(rows.findIndex(function(r){return r.n===o.value;}));
  }
  function hide(){isOpen=false;typed=false;pop.hidden=true;inp.setAttribute('aria-expanded','false');inp.removeAttribute('aria-activedescendant');reset();}
  function pick(n){if(n==='')return toggle(n);hide();inp.blur();o.onPick(n);}
  inp.onfocus=function(){inp.select();show();};
  inp.onclick=show;
  inp.onblur=hide;
  inp.oninput=function(){isOpen=true;pop.hidden=false;typed=true;inp.setAttribute('aria-expanded','true');render();};
  inp.onkeydown=function(e){
    var k=e.key,r=rows[act],go=function(i){e.preventDefault();show();setAct(Math.max(0,Math.min(rows.length-1,i)));};
    if(k==='ArrowDown')go(act+1);
    else if(k==='ArrowUp')go(act<0?rows.length-1:act-1);
    else if(k==='Enter'&&isOpen&&r){e.preventDefault();pick(r.n);}
    else if(k==='Escape'&&isOpen){e.preventDefault();hide();}
    else if(k==='ArrowRight'&&isOpen&&!typed&&r&&r.k){e.preventDefault();if(open.has(r.n))setAct(act+1);else toggle(r.n,true);}
    else if(k==='ArrowLeft'&&isOpen&&!typed&&r){
      e.preventDefault();
      if(r.k&&open.has(r.n))toggle(r.n,false);
      else for(var i=act-1;i>=0;i--)if(rows[i].d<r.d){setAct(i);break;}}
  };
  reset();return host;
}
return {create:create};
})();
