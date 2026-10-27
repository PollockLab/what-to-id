// The drill-down under the group chips. A group opens to the ranks below it, as far as the data goes;
// each node shows how many observations lie at or below it and takes the chips' clicks (pick, leave
// out, clear) through o.cycle. Opening or closing a node changes no filter. The tree is the taxa that
// hold observations; a taxon with one child and no observations of its own is skipped, since picking
// it or its child keeps the same observations. Taxa files built without the tree have no parent
// column, so make() then returns null. o: T (taxa rows), tax, grp, n (the points), ranks, nf,
// state(id) for '', 'inc' or 'not', inside(row) for a row under an included pick, cycle(id), box,
// pass() for the points that count (a Uint8Array, or null for all), and onOpen after a change.
// slot(g), when given, is where group g's ranks go, in place of a section per group in box.
var TT=(function(){
'use strict';
var CAP=200;
function make(o){
  var T=o.T,R=T.length,par=new Int32Array(R),own=null,cnt=null,tot=null,gopen={},nopen={},syncs={},i;
  if(!R||T[0].length<5)return null;
  for(i=0;i<R;i++)par[i]=T[i][4];
  var ch=T.map(function(){return [];});
  for(i=0;i<R;i++)if(par[i]>=0)ch[par[i]].push(i);
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  // Observations at or below each row, per group, from the points that pass.
  function build(){
    if(own)return;
    var G=o.groups,ok=o.pass&&o.pass(),tax=o.tax,grp=o.grp,n=o.n,t,g,j;
    own=[];cnt=[];tot=new Float64Array(G);for(g=0;g<G;g++){own.push(new Float64Array(R));cnt.push(new Float64Array(R));}
    for(i=0;i<n;i++){t=tax[i];if(t<R&&(!ok||ok[i]))own[grp[i]][t]++;}
    for(g=0;g<G;g++)for(i=0;i<R;i++)if(own[g][i]){tot[g]+=own[g][i];for(j=i;j>=0;j=par[j])cnt[g][j]+=own[g][i];}
  }
  function kids(g,x){return ch[x].filter(function(k){return cnt[g][k]>0;});}
  // x, or the lowest row under it that is reached through single children without observations.
  function lead(g,x){
    for(;;){var ks=kids(g,x);if(ks.length!==1||own[g][x])return x;x=ks[0];}
  }
  function shown(g,x){
    var ks=kids(g,x).map(function(k){return lead(g,k);});
    return ks.sort(function(a,b){return cnt[g][b]-cnt[g][a]||a-b;});
  }
  function tops(g){
    var r=[];for(i=0;i<R;i++)if(par[i]<0&&cnt[g][i]>0)r.push(lead(g,i));
    return r.length===1?shown(g,r[0]):r;
  }
  function row(g,x,ul){
    var t=T[x],st=o.state(t[2]),ks=shown(g,x),isOpen=!!nopen[x]&&ks.length>0,
      li=el('li','tn'+(st==='not'?' not':'')+(!st&&o.inside(x)?' in':'')),
      lab=el('button','tl'),name=t[1]||t[0];
    li.setAttribute('role','treeitem');li.setAttribute('data-r',x);
    if(ks.length){var w=el('button','tw',isOpen?'▾':'▸');w.type='button';
      w.setAttribute('aria-label',(isOpen?'Close ':'Open ')+name);w.setAttribute('data-k','w'+x);
      w.onclick=function(){nopen[x]=!nopen[x];o.onOpen();};li.appendChild(w);
      li.setAttribute('aria-expanded',String(isOpen));}
    else li.appendChild(el('span','tw'));
    lab.type='button';lab.setAttribute('data-k','l'+x);lab.setAttribute('aria-pressed',String(!!st));
    lab.textContent=(st==='not'?'not ':'')+name;
    lab.title=[t[1],t[0],t[3]!==255?o.ranks[t[3]]:''].filter(Boolean).join(' · ')+
      '. Click to pick, again to leave out, again to clear.';
    lab.onclick=function(){o.cycle(t[2]);};li.appendChild(lab);
    // --s, the share of the group, for a page that draws it as a bar
    var c=el('span','tc',o.nf.format(cnt[g][x]));c.style.setProperty('--s',(tot[g]?cnt[g][x]/tot[g]*100:0)+'%');li.appendChild(c);
    ul.appendChild(li);
    if(isOpen){var sub=el('ul');sub.setAttribute('role','group');
      ks.slice(0,CAP).forEach(function(k){row(g,k,sub);});
      if(ks.length>CAP)sub.appendChild(el('li','muted','and '+o.nf.format(ks.length-CAP)+' more, find them by name'));
      ul.appendChild(sub);}
  }
  function render(){
    var open=Object.keys(gopen).filter(function(g){return gopen[g];});
    if(open.length)build();Object.keys(syncs).forEach(function(g){syncs[g]();});
    var a=document.activeElement,key=a&&o.box.contains(a)?a.getAttribute('data-k'):null;
    if(o.slot)for(i=0;i<o.groups;i++)o.slot(i).textContent='';else o.box.textContent='';
    open.forEach(function(g){
      var s=el('section'),ul=el('ul');if(!o.slot)s.appendChild(el('h3',null,o.label(+g)));ul.setAttribute('role','tree');
      ul.setAttribute('aria-label','Ranks under '+o.label(+g));
      tops(+g).slice(0,CAP).forEach(function(x){row(+g,x,ul);});s.appendChild(ul);(o.slot?o.slot(+g):o.box).appendChild(s);});
    if(key){var f=o.box.querySelector('[data-k="'+key+'"]');if(f)f.focus();}
  }
  return {render:render,
    // a toggle beside the group chip b, kept on its line: opens or closes that group's ranks
    attach:function(b,g){var w=el('button','tw gt','▸');w.type='button';
      function set(){var on=!!gopen[g];w.textContent=on?'▾':'▸';w.setAttribute('aria-expanded',String(on));
        w.setAttribute('aria-label',(on?'Close':'Open')+' the ranks under '+o.label(g));}
      w.onclick=function(){gopen[g]=!gopen[g];o.onOpen();};syncs[g]=set;set();
      var wrap=el('span','gw');b.replaceWith(wrap);wrap.append(b,w);},
    // after the points that count change
    refresh:function(){own=null;},
    // opens the way to taxa row x, in the group that holds most of it
    reveal:function(x){
      build();var best=0,g;
      for(g=1;g<o.groups;g++)if(cnt[g][x]>cnt[best][x])best=g;
      gopen[best]=true;for(var j=par[x];j>=0;j=par[j])nopen[j]=true;
      o.onOpen();
      var e=o.box.querySelector('[data-r="'+x+'"]');
      while(!e&&x>=0){x=par[x];e=o.box.querySelector('[data-r="'+x+'"]');}
      if(e)e.scrollIntoView({block:'nearest'});}};
}
return {make:make};
})();
