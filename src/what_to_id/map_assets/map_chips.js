// One click rule for the short-list filters (groups, show only, months) and the "your selection"
// bar. A chip's state is '' (off), 'inc' (picked) or 'not' (left out). A click steps it '' -> 'inc'
// -> 'not' -> '', as the taxon shortcuts do; a two-state chip skips 'not'. Within a filter the picked
// chips combine with OR and the left-out ones subtract; filters combine with AND. In the hash a
// filter is a list of keys, a minus marking a left-out one: groups=Insecta,-Aves.
var CH=(function(){
'use strict';
var NEXT={'':'inc',inc:'not',not:''};
function next(st,three){var n=NEXT[st||'']||'';return n==='not'&&!three?'':n;}
// The hash value back to states over the known keys. Old links listed picked keys only, which read
// as picked; a minus on a key in two (the two-state keys) is dropped.
function read(s,keys,two){var out={};
  String(s||'').split(',').forEach(function(t){t=t.trim();var not=t.charAt(0)==='-',k=not?t.slice(1):t;
    if(keys.indexOf(k)>=0&&!(k in out)&&!(not&&two&&two.indexOf(k)>=0))out[k]=not?'not':'inc';});
  return out;}
function write(st,keys){return keys.filter(function(k){return st[k];}).map(function(k){
  return (st[k]==='not'?'-':'')+encodeURIComponent(k);}).join(',');}
function picked(st,keys,v){return keys.filter(function(k){return st[k]===v;});}
function any(st){for(var k in st)if(st[k])return true;return false;}
// Which groups pass, one per key. With none picked every group passes, else the picked ones, less
// those left out. With taxa included the picked groups join the taxa as one set (see pointData in
// map.js), so here every group passes but the left-out ones.
function groupPass(st,keys,taxa){var some=picked(st,keys,'inc').length>0;
  return keys.map(function(k){return st[k]!=='not'&&(taxa||!some||st[k]==='inc');});}
// The groups in the Identify link. Without included taxa the picked groups go in as iconic_taxa,
// which already leaves the others out. With included taxa they go in as their taxa beside them
// (taxa). Left-out groups go in without_taxon_id (not). A group with no taxon id cannot: without
// taxa, iconic_taxa then names every group but the left-out ones, which is exact; with taxa,
// inc and not name the groups the link cannot add or leave out.
function groupLink(st,keys,gid,taxa){
  var pi=picked(st,keys,'inc'),pn=picked(st,keys,'not'),out={groups:[],taxa:[],not:[],inc:[],out:[]};
  if(!taxa){if(pi.length){out.groups=pi;return out;}
    if(pn.some(function(g){return !gid[g];})){out.groups=keys.filter(function(k){return st[k]!=='not';});
      return out;}}
  pi.forEach(function(g){if(gid[g])out.taxa.push(gid[g]);else out.inc.push(g);});
  pn.forEach(function(g){if(gid[g])out.not.push(gid[g]);else out.out.push(g);});
  return out;}
// Shows a chip button's state. Picked and left out are both pressed; a left-out chip reads
// "not <label>", in text and accessible name, in the not style the taxon and project chips share.
function show(b,label,st){b.setAttribute('aria-pressed',String(!!st));b.classList.toggle('not',st==='not');
  b.textContent=(st==='not'?'not ':'')+label;b.setAttribute('aria-label',(st==='not'?'Not ':'')+label);}
// A chip in box for key k of the states object get() returns; a click steps it and calls changed.
function chip(box,k,label,get,three,title,changed){var b=document.createElement('button');
  b.type='button';if(title)b.title=title+'. Click to pick'+(three?', again to leave out, again to clear.':
    ', again to clear.');
  b.onclick=function(){var st=get(),v=next(st[k],three);if(v)st[k]=v;else delete st[k];
    show(b,label,v);changed();};
  show(b,label,get()[k]||'');box.appendChild(b);return b;}
// The selection bar's chips, in the order of the filters, each with what removes it and, when its
// filter can leave things out, what flips it between picked and left out. o: S, meta, terms (the
// taxon terms, see TX.terms), picker (the taxon picker), pj (the project filter), months (month
// names), only ([key, label] per status chip), two (the status keys that cannot be left out), area,
// and redraw() after a group, month or status chip changes.
function items(o){var out=[],S=o.S,m=o.meta,two=o.two||[];
  function add(label,not,remove,flip){out.push({label:label,not:not,remove:remove,flip:flip});}
  function drop(st,k){return function(){delete st[k];o.redraw();};}
  function turn(st,k){return function(){st[k]=st[k]==='not'?'inc':'not';o.redraw();};}
  o.terms.forEach(function(t){var ids=[].concat(t.id);add(t.label,t.exclude,function(){
    for(var k=S.picks.length-1;k>=0;k--)if(ids.indexOf(S.picks[k].id)>=0)S.picks.splice(k,1);
    o.picker.changed();},function(){S.picks.forEach(function(p){if(ids.indexOf(p.id)>=0)p.not=!t.exclude;});
    o.picker.changed();});});
  out=out.concat(o.pj.items());
  m.groups.forEach(function(g){if(S.groups[g])add(m.names[g]||g,S.groups[g]==='not',drop(S.groups,g),
    turn(S.groups,g));});
  o.months.forEach(function(n,i){if(S.months>>i&1)add(n,false,function(){S.months&=~(1<<i);o.redraw();});});
  o.only.forEach(function(d){if(S.only[d[0]])add(d[1],S.only[d[0]]==='not',drop(S.only,d[0]),
    two.indexOf(d[0])<0?turn(S.only,d[0]):null);});
  var a=o.area.term();if(a)add(a.label,false,function(){o.area.clear();});
  return out;}
// The selection bar, the one list of what is picked: one chip per active pick, items [{label, not,
// tag, remove, flip}], each with × to remove it, and Clear all; a tag (as "Identify only") shows
// after the label. A chip with flip is a button that flips it between picked and left out. set()
// redraws only when the items change, and keeps focus in the bar: on the flipped chip, after a
// removal on the next × (else Clear all), or, once the bar is empty, on fallback.
function bar(o){
  var box=o.box,list=box.querySelector('ul'),clear=box.querySelector('button'),sig=null,want=null;
  clear.onclick=function(){want={clear:true};o.clear();};
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  return {set:function(items){
    var s=items.map(function(t){return (t.not?'-':'+')+t.label+'|'+(t.tag||'');}).join('\n');
    if(s===sig)return;sig=s;list.textContent='';
    var xs=[],fs=[];
    items.forEach(function(t,j){var text=(t.not?'not ':'')+t.label,li=el('li','schip'+(t.not?' not':'')),
        x=el('button','x','×'),sp=li.appendChild(el(t.flip?'button':'span',t.flip?'sl':null,text));
      if(t.tag)sp.appendChild(el('span','tag',t.tag));
      if(t.flip){sp.type='button';sp.setAttribute('aria-pressed',String(!!t.not));
        sp.title='Click to '+(t.not?'pick':'leave out')+' instead';
        sp.onclick=function(){want={flip:j};t.flip();};}
      x.type='button';x.setAttribute('aria-label','Remove '+text+(t.tag?' ('+t.tag+')':''));
      x.onclick=function(){want={x:j};t.remove();};li.appendChild(x);list.appendChild(li);
      xs.push(x);fs.push(t.flip?sp:x);});
    box.hidden=!items.length;
    if(want&&want.flip!=null&&fs[want.flip])fs[want.flip].focus();
    else if(want&&want.x!=null)(xs.length?xs[Math.min(want.x,xs.length-1)]:o.fallback).focus();
    else if(want&&want.clear&&!items.length)o.fallback.focus();
    want=null;}};}
return {next:next,read:read,write:write,picked:picked,any:any,groupPass:groupPass,groupLink:groupLink,
  show:show,chip:chip,items:items,bar:bar};
})();
