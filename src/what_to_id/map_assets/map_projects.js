// Projects. pool-projects.bin (see map_projects.py) lists the records in each project of
// META.projects.list; each record gets a bitmask, bit k set when it is in project k. Each project is
// a chip with the one click rule of map_chips.js: pick (in), leave out (not in), clear. Picked
// projects combine with OR and left-out ones subtract. The viewer can also paste any other
// iNaturalist project, by number or URL: an "Identify only" chip that goes into the Identify link
// but not the map filter, as the page has no list of its records. Without the file the box stays
// hidden and nothing is filtered. The mask is one byte, so at most 8 map projects.
function projDecode(buf,list){
  var u=new Uint8Array(buf),hn=new DataView(buf).getUint32(0,true),o=4+hn,
    head=JSON.parse(new TextDecoder().decode(u.subarray(4,o))).projects,out=list.map(function(){return null;});
  head.forEach(function(p){
    var n=p.n,k=list.map(function(x){return x.id;}).indexOf(p.id);
    if(o+4*n>u.length)throw new Error('project file is cut short');
    if(k>=0){var a=new Uint32Array(n),s=0;
      for(var i=0;i<n;i++){s=(s+(u[o+i]|u[o+n+i]<<8|u[o+2*n+i]<<16|u[o+3*n+i]<<24))>>>0;a[i]=s;}out[k]=a;}
    o+=4*n;});
  if(o!==u.length)throw new Error('project file size does not match its header');
  return out;
}
// Sets bit k of mask[i] for records a..b-1 in lists[k]. Records arrive in shards, each sorted by id,
// so the range is walked run by run against each sorted list.
function projMask(id,lists,mask,a,b){
  for(var r=a;r<b;){var e=r+1;while(e<b&&id[e]>id[e-1])e++;
    for(var k=0;k<lists.length;k++){var L=lists[k];if(!L)continue;
      var lo=0,hi=L.length;while(lo<hi){var m=(lo+hi)>>1;if(L[m]<id[r])lo=m+1;else hi=m;}
      for(var i=r,j=lo;i<e&&j<L.length;i++){while(j<L.length&&L[j]<id[i])j++;if(L[j]===id[i])mask[i]|=1<<k;}}
    r=e;}
}
function projKeep(m,inc,exc){return !(m&exc)&&(!inc||(m&inc)!==0);}
// A pasted project: its number, or the number or slug in an iNaturalist project URL, as a string;
// null for anything else. iNaturalist takes a slug wherever it takes a project number
// (project_id=bc-rarities and project_id=90486 match the same records), so slugs pass as they are.
var PROJ_SLUG=/^[a-z0-9][a-z0-9_-]{0,99}$/;
function projId(t){t=String(t||'').toLowerCase();
  return /^\d+$/.test(t)?(+t>0&&+t<=4294967295?String(+t):null):PROJ_SLUG.test(t)&&t!=='new'?t:null;}
function projParse(s){s=String(s||'').trim();if(/^\d+$/.test(s))return projId(s);
  var m=/^(?:https?:\/\/)?(?:[a-z]+\.)?inaturalist\.[a-z]{2,3}(?:\.[a-z]{2})?\/projects\/([^\/?#\s]+)\/?(?:[\/?#]\S*)?$/i.exec(s);
  return m?projId(m[1]):null;}
// The selection is a list of {id, k, st}: id a string, k the project's index in list (-1 for a
// pasted one), st 'inc' or 'not'. In the hash each is its id, a minus for 'not' and a p before a
// pasted one: projects=86886,p90486,-pbc-rarities. A plain number not in list, as old links carry
// for projects the map has since dropped, reads as pasted. match=all, from when picked projects
// could be required together, is ignored.
function projRead(s,list){var ids=list.map(function(p){return String(p.id);}),out=[];
  String(s||'').split(',').forEach(function(t){t=t.trim();var not=t.charAt(0)==='-';if(not)t=t.slice(1);
    var paste=t.charAt(0)==='p',id=projId(paste?t.slice(1):t);if(!id||!paste&&!/^\d+$/.test(id))return;
    var k=ids.indexOf(id);
    if(!out.some(function(s){return s.id===id;}))out.push({id:id,k:k,st:not?'not':'inc'});});
  return out;}
function projWrite(sel){return sel.map(function(s){return (s.st==='not'?'-':'')+(s.k<0?'p':'')+s.id;}).join(',');}
// The Identify parameters: iNaturalist ORs the ids in project_id and leaves out those in
// not_in_project, map projects first. Exact when no pasted project is in.
function projParams(sel){
  var o=sel.filter(function(s){return s.k>=0;}).concat(sel.filter(function(s){return s.k<0;})),q={},
    ids=function(st){return o.filter(function(s){return s.st===st;}).map(function(s){return s.id;});};
  if(ids('not').length)q.not_in_project=ids('not').join(',');
  if(ids('inc').length)q.project_id=ids('inc').join(',');
  return {q:q,exact:!sel.some(function(s){return s.k<0;})};
}
function projLabel(s,list){return s.k>=0?list[s.k].title:'project '+s.id;}
// What the note under Identify says about pasted projects, as {more, fewer}. With a map project and
// a pasted one in, Identify opens records in either, so more than the map shows: more gives the map
// count (shown) and the most Identify can open (alt, the records that match every other filter).
// Otherwise any pasted project narrows what Identify opens, which the map count leaves out: fewer.
// shown is null while the records load.
function projNote(sel,list,shown,alt){var nf=new Intl.NumberFormat('en-CA'),
    p=sel.filter(function(s){return s.k<0;}),pin=p.filter(function(s){return s.st==='inc';});
  if(!p.length)return {more:'',fewer:''};
  var names=function(a){return a.map(function(s){return (s.st==='not'?'not in ':'in ')+projLabel(s,list);}).join(', ');};
  if(pin.length&&sel.some(function(s){return s.k>=0&&s.st==='inc';}))
    return {fewer:'',more:'it also opens records '+names(pin)+' (Identify only), which the map cannot count'+
      (shown!=null?', so up to '+nf.format(alt)+' rather than the '+nf.format(shown)+' on the map':'')};
  return {more:'',fewer:'The map count does not include the Identify only project filter ('+names(p)+
    '), so Identify opens '+(shown!=null?'at most the '+nf.format(shown)+' records shown':'fewer records than the map shows')+'.'};
}
function projectFilter(o){
  var meta=o.meta,list=(meta.projects&&meta.projects.list)||[],box=document.getElementById('projbox'),
    sel=projRead(o.hash.get('projects'),list),lists=null,mask=new Uint8Array(0),key=0,inc=0,exc=0,shown=null,alt=0;
  function bits(){inc=exc=0;if(!lists)return;
    sel.forEach(function(s){if(s.k>=0){if(s.st==='not')exc|=1<<s.k;else inc|=1<<s.k;}});}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;
    if(text!=null)e.textContent=text;return e;}
  function find(id){for(var j=0;j<sel.length;j++)if(sel[j].id===id)return sel[j];return null;}
  // a click steps the chip's state; cleared, it leaves the selection
  function step(id,k){var s=find(id),v=CH.next(s&&s.st,true);
    if(!v)sel.splice(sel.indexOf(s),1);else if(s)s.st=v;else sel.push({id:id,k:k,st:v});change();}
  var chips,input,msg;
  function chip(id,k,label){var b=chips.appendChild(el('button')),s=find(id),tag=k<0?' (Identify only)':'';
    b.type='button';b.title=label+tag+'. Click to pick, again to leave out, again to clear.';
    CH.show(b,label,s?s.st:'');b.setAttribute('aria-label',b.getAttribute('aria-label')+tag);
    if(k<0)b.appendChild(el('span','tag','Identify only'));b.onclick=function(){step(id,k);};}
  function draw(){chips.textContent='';
    list.forEach(function(p,k){chip(String(p.id),k,p.title);});
    sel.forEach(function(s){if(s.k<0)chip(s.id,-1,projLabel(s,list));});}
  function change(){bits();key++;if(chips)draw();o.changed();}
  function paste(){if(!input.value.trim())return;var id=projParse(input.value),k=list.map(function(p){return String(p.id);}).indexOf(id);
    if(!id){msg.textContent='Paste a project number, like 90486, or its iNaturalist URL.';return;}
    input.value='';if(find(id)){msg.textContent='That project is already picked.';return;}
    msg.textContent=k>=0?list[k].title+' is on the map, so it filters the map too.':
      'Added for Identify only; it does not change the map.';
    sel.push({id:id,k:k,st:'inc'});change();}
  function build(){
    box.appendChild(el('summary',null,'Projects ')).appendChild(el('span','n')).id='nproj';
    chips=box.appendChild(el('div','chips'));chips.setAttribute('role','group');chips.setAttribute('aria-label','Projects');
    var f=box.appendChild(el('form','prow')),lab=f.appendChild(el('label','muted','Add another project for Identify only'));
    input=f.appendChild(el('input','padd'));input.id=lab.htmlFor='projpaste';input.type='text';
    input.placeholder='Project number or URL';input.autocomplete='off';input.spellcheck=false;
    f.appendChild(el('button','padd','Add')).type='submit';
    f.onsubmit=function(e){e.preventDefault();paste();};
    input.addEventListener('paste',function(){setTimeout(paste,0);});
    msg=box.appendChild(el('p','muted'));msg.setAttribute('aria-live','polite');
    draw();box.hidden=false;
  }
  return {
    load:function(get){if(!list.length||!box)return;
      get(meta.projects.file).then(function(buf){
        lists=projDecode(buf,list).map(function(L){return L||new Uint32Array(0);});
        mask=new Uint8Array(0);build();bits();key++;o.changed();})
      .catch(function(e){if(window.console)console.warn('Project filters are off: '+e.message);});},
    sync:function(P){if(!lists||mask.length===P.n)return;var m=new Uint8Array(P.n),a=Math.min(mask.length,P.n);
      m.set(mask.subarray(0,a));projMask(P.id,lists,m,a,P.n);mask=m;},
    drop:function(i){return (inc|exc)!==0&&!projKeep(mask[i],inc,exc);},
    key:function(){return key;},
    // the records Identify can open with a pasted project in beside a map one: all but the left out
    wide:function(){return lists&&projNote(sel,list,null,0).more?function(i){return !(mask[i]&exc);}:null;},
    note:function(n,a){shown=n;alt=a;},
    inexact:function(){return lists?projNote(sel,list,shown,alt).more:'';},
    uncounted:function(){return lists?projNote(sel,list,shown,alt).fewer:'';},
    active:function(){return (inc|exc)!==0;},
    params:function(){return lists?projParams(sel).q:{};},
    // the chips for the selection bar (map_chips.js), once the file has loaded
    items:function(){return lists?sel.map(function(s){return {label:'in '+projLabel(s,list),not:s.st==='not',
      tag:s.k<0?'Identify only':'',remove:function(){sel.splice(sel.indexOf(s),1);change();},
      flip:function(){s.st=s.st==='not'?'inc':'not';change();}};}):[];},
    hash:function(){return sel.length?'projects='+projWrite(sel):'';},
    reset:function(){if(!sel.length)return;sel=[];bits();key++;if(chips)draw();}
  };
}
